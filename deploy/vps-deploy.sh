#!/usr/bin/env bash
#
# One-command VPS deploy for this Django stack behind aaPanel.
#
#   sudo ./deploy/vps-deploy.sh
#
# Safe to re-run. On the first run (before a TLS certificate exists) it writes an
# HTTP-only vhost so aaPanel's Let's Encrypt manager can validate; once the cert
# is in place, re-running writes the full HTTP+HTTPS vhost.
#
# Override any of these from the environment:
#   DOMAIN=erp.example.com APP_PORT=8011 ./deploy/vps-deploy.sh
#
# Flags: --no-pull  --no-build  --skip-nginx  --superuser
#
set -euo pipefail

# ------------------------------- configuration -------------------------------
DOMAIN="${DOMAIN:-zentral.mec-cmr.com}"
APP_DIR="${APP_DIR:-/www/wwwroot/$DOMAIN}"
APP_PORT="${APP_PORT:-8010}"
MAX_BODY="${MAX_BODY:-25M}"
COMPOSE_FILE="docker-compose.prod.yml"

NGINX_BIN="/www/server/nginx/sbin/nginx"     # aaPanel's nginx, NOT the apt one
VHOST_DIR="/www/server/panel/vhost/nginx"
CERT_DIR="/www/server/panel/vhost/cert/$DOMAIN"
LOG_DIR="/www/wwwlogs"

DO_PULL=1
DO_BUILD=1
DO_NGINX=1
DO_SUPERUSER=0
HAVE_CERT=0

while [ $# -gt 0 ]; do
  case "$1" in
    --no-pull)    DO_PULL=0 ;;
    --no-build)   DO_BUILD=0 ;;
    --skip-nginx) DO_NGINX=0 ;;
    --superuser)  DO_SUPERUSER=1 ;;
    -h|--help)    sed -n '2,15p' "$0" | sed 's/^#\{1,\} \{0,1\}//'; exit 0 ;;
    *)            echo "Unknown flag: $1" >&2; exit 2 ;;
  esac
  shift
done

# --------------------------------- plumbing ----------------------------------
step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m OK \033[0m %s\n' "$*"; }
warn() { printf '  \033[33m !! \033[0m %s\n' "$*"; }
die()  { printf '\n  \033[31m FAIL  %s\033[0m\n\n' "$*" >&2; exit 1; }

dc() { docker compose -f "$COMPOSE_FILE" "$@"; }

# --------------------------------- preflight ---------------------------------
step "Preflight"

[ "$(id -u)" = "0" ] || die "Run as root (nginx config and /www paths need it)."
command -v docker >/dev/null || die "docker not found. Install it, then re-run."
docker compose version >/dev/null 2>&1 \
  || die "'docker compose' v2 unavailable. Install docker-compose-plugin."
ok "docker $(docker --version | awk '{print $3}' | tr -d ,)"

[ -d "$APP_DIR" ] || die "APP_DIR does not exist: $APP_DIR"
cd "$APP_DIR"
[ -f "$COMPOSE_FILE" ] || die "$COMPOSE_FILE not found in $APP_DIR - is this the repo root?"
ok "project dir $APP_DIR"

[ -f .env ] || die ".env missing. Run: cp .env.production.example .env  and fill it in."
chmod 600 .env
ok ".env present (mode 600)"

if [ "$DO_NGINX" = "1" ]; then
  [ -x "$NGINX_BIN" ] || die "aaPanel nginx not at $NGINX_BIN. Re-run with --skip-nginx."
  [ -d "$VHOST_DIR" ] || die "aaPanel vhost dir not found: $VHOST_DIR"
  mkdir -p "$LOG_DIR"
  ok "aaPanel nginx present"
fi

# ----------------------------- .env sanity checks ----------------------------
step "Validating .env"

getenv() { sed -n "s/^$1=//p" .env | tail -1 | tr -d '\r'; }

SECRET_KEY_V="$(getenv SECRET_KEY)"
case "$SECRET_KEY_V" in
  ""|replace-with-*|django-insecure-*)
    die "SECRET_KEY is unset or still a placeholder in .env." ;;
esac
[ "${#SECRET_KEY_V}" -ge 40 ] || warn "SECRET_KEY is ${#SECRET_KEY_V} chars; 50+ recommended."
ok "SECRET_KEY set"

[ "$(getenv DEBUG)" = "False" ] || die "DEBUG must be False for a production deploy."
ok "DEBUG=False"

case ",$(getenv ALLOWED_HOSTS)," in
  *",$DOMAIN,"*) ok "ALLOWED_HOSTS contains $DOMAIN" ;;
  *) die "ALLOWED_HOSTS does not contain $DOMAIN - Django would return 400." ;;
esac

case "$(getenv CSRF_TRUSTED_ORIGINS)" in
  *"https://$DOMAIN"*) ok "CSRF_TRUSTED_ORIGINS contains https://$DOMAIN" ;;
  *) die "CSRF_TRUSTED_ORIGINS needs https://$DOMAIN (scheme included) or login fails." ;;
esac

# The bundled Postgres container speaks no TLS; ssl_require would refuse to connect.
if [ "$(getenv DB_SSL_REQUIRE)" != "False" ]; then
  if grep -q "^DB_SSL_REQUIRE=" .env; then
    sed -i 's/^DB_SSL_REQUIRE=.*/DB_SSL_REQUIRE=False/' .env
  else
    printf '\nDB_SSL_REQUIRE=False\n' >> .env
  fi
  warn "set DB_SSL_REQUIRE=False (the db container has no TLS certificate)"
else
  ok "DB_SSL_REQUIRE=False"
fi

# POSTGRES_PASSWORD and the password inside DATABASE_URL are two separate strings
# that must agree; disagreeing is a silent auth failure at container boot.
PG_PASS="$(getenv POSTGRES_PASSWORD)"
URL_PASS="$(getenv DATABASE_URL | sed -n 's|^postgres\(ql\)\{0,1\}://[^:]*:\([^@]*\)@.*|\2|p')"
[ -n "$PG_PASS" ] || die "POSTGRES_PASSWORD is empty in .env."
[ "$PG_PASS" = "$URL_PASS" ] \
  || die "POSTGRES_PASSWORD does not match the password inside DATABASE_URL."
case "$PG_PASS" in
  replace-with-*|zentral_dev_2026) warn "POSTGRES_PASSWORD looks like a default - rotate it." ;;
esac
ok "database credentials consistent"

if [ -z "$(getenv RESEND_API_KEY)" ] && [ -z "$(getenv EMAIL_HOST)" ]; then
  die "With DEBUG=False the app will not start without RESEND_API_KEY or EMAIL_HOST."
fi
ok "email backend configured"

# ------------------- settings.py: honour DB_SSL_REQUIRE ----------------------
SETTINGS="management_system/management_system/settings.py"
if grep -q "ssl_require=not DEBUG," "$SETTINGS" 2>/dev/null; then
  sed -i "s/ssl_require=not DEBUG,/ssl_require=env_bool('DB_SSL_REQUIRE', not DEBUG),/" "$SETTINGS"
  warn "patched $SETTINGS to honour DB_SSL_REQUIRE (commit this upstream)"
fi

# ----------------------------- port availability -----------------------------
step "Checking port $APP_PORT"
# Advisory only. 'docker compose up' reports "port is already allocated" with far
# better accuracy than we can here, so never abort the deploy on this check.
PORT_LINE="$(ss -tulpn 2>/dev/null | grep "127.0.0.1:$APP_PORT " || true)"
if [ -z "$PORT_LINE" ]; then
  ok "port $APP_PORT free"
elif [ -n "$(dc ps -q web 2>/dev/null)" ] || printf '%s' "$PORT_LINE" | grep -qi docker; then
  ok "port $APP_PORT held by docker (this stack)"
else
  warn "port $APP_PORT is in use and not obviously ours:"
  printf '        %s\n' "$PORT_LINE"
  warn "continuing - docker will fail clearly if the port is genuinely taken"
fi

grep -q "\"127.0.0.1:$APP_PORT:8000\"" "$COMPOSE_FILE" \
  || warn "$COMPOSE_FILE does not bind 127.0.0.1:$APP_PORT:8000 - check web.ports"

# ------------------------------- build & start -------------------------------
if [ "$DO_PULL" = "1" ] && [ -d .git ]; then
  step "Pulling latest code"
  git pull --ff-only || warn "git pull failed (local edits?) - using the working tree"
fi

step "Starting containers"
if [ "$DO_BUILD" = "1" ]; then
  dc up -d --build
else
  dc up -d
fi
dc ps

# ------------------------------- health check --------------------------------
step "Waiting for the app on 127.0.0.1:$APP_PORT"
HEALTHY=0
for _ in $(seq 1 60); do
  CODE="$(curl -s -o /dev/null -w '%{http_code}' -m 5 \
          -H "Host: $DOMAIN" "http://127.0.0.1:$APP_PORT/" 2>/dev/null || true)"
  case "$CODE" in
    200|301|302) ok "HTTP $CODE from gunicorn"; HEALTHY=1; break ;;
    400) die "HTTP 400 - $DOMAIN not in ALLOWED_HOSTS as the app sees it." ;;
    500|502) die "HTTP $CODE - app error. Run: docker compose -f $COMPOSE_FILE logs --tail=50 web" ;;
  esac
  sleep 2
done

if [ "$HEALTHY" != "1" ]; then
  echo
  dc logs --tail=40 web || true
  die "App never became reachable. The tail above should say why."
fi

# ----------------------------- media permissions -----------------------------
step "Media directory permissions"
mkdir -p "$APP_DIR/deploy/media"
chmod 755 /www /www/wwwroot "$APP_DIR" 2>/dev/null || true
chmod -R 755 "$APP_DIR/deploy"
ok "nginx can read $APP_DIR/deploy/media"

# -------------------------------- nginx vhost --------------------------------
if [ "$DO_NGINX" = "1" ]; then
  VHOST="$VHOST_DIR/$DOMAIN.conf"
  if [ -f "$CERT_DIR/fullchain.pem" ] && [ -f "$CERT_DIR/privkey.pem" ]; then
    HAVE_CERT=1
  fi

  [ -f "$VHOST" ] && cp "$VHOST" "$VHOST.bak.$(date +%Y%m%d-%H%M%S)"

  if [ "$HAVE_CERT" = "1" ]; then
    step "Writing nginx vhost (HTTP + HTTPS)"
  else
    step "Writing nginx vhost (HTTP only - no certificate yet)"
  fi

  {
    cat <<NGINX
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN;

    # From disk, so Let's Encrypt validation is never proxied or redirected.
    location ^~ /.well-known/acme-challenge/ {
        root $APP_DIR;
    }
NGINX

    if [ "$HAVE_CERT" = "1" ]; then
      cat <<NGINX

    location / {
        return 301 https://\$host\$request_uri;
    }

    access_log $LOG_DIR/$DOMAIN.log;
    error_log  $LOG_DIR/$DOMAIN.error.log;
}

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name $DOMAIN;

    ssl_certificate     $CERT_DIR/fullchain.pem;
    ssl_certificate_key $CERT_DIR/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    client_max_body_size $MAX_BODY;

    # Uploads come off disk; proxying them ties up a gunicorn worker per file.
    location /media/ {
        alias $APP_DIR/deploy/media/;
        access_log off;
        expires 30d;
    }

    location / {
        proxy_pass http://127.0.0.1:$APP_PORT;
        proxy_http_version 1.1;

        proxy_set_header Host              \$host;
        proxy_set_header X-Real-IP         \$remote_addr;
        proxy_set_header X-Forwarded-For   \$proxy_add_x_forwarded_for;
        # Required: settings.py trusts this header to know the request was HTTPS.
        # Without it, SECURE_SSL_REDIRECT causes an infinite redirect loop.
        proxy_set_header X-Forwarded-Proto \$scheme;

        proxy_redirect off;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }

    access_log $LOG_DIR/$DOMAIN.log;
    error_log  $LOG_DIR/$DOMAIN.error.log;
}
NGINX
    else
      cat <<NGINX

    client_max_body_size $MAX_BODY;

    location /media/ {
        alias $APP_DIR/deploy/media/;
        access_log off;
        expires 30d;
    }

    location / {
        proxy_pass http://127.0.0.1:$APP_PORT;
        proxy_http_version 1.1;

        proxy_set_header Host              \$host;
        proxy_set_header X-Real-IP         \$remote_addr;
        proxy_set_header X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;

        proxy_redirect off;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }

    access_log $LOG_DIR/$DOMAIN.log;
    error_log  $LOG_DIR/$DOMAIN.error.log;
}
NGINX
    fi
  } > "$VHOST"

  if ! "$NGINX_BIN" -t 2>/dev/null; then
    "$NGINX_BIN" -t || true
    LAST_BAK="$(ls -t "$VHOST".bak.* 2>/dev/null | head -1 || true)"
    if [ -n "$LAST_BAK" ]; then
      cp "$LAST_BAK" "$VHOST"
      warn "restored $LAST_BAK"
    fi
    die "nginx config test failed - nothing was reloaded."
  fi
  "$NGINX_BIN" -s reload
  ok "nginx reloaded"

  # Prove the ACME path reaches disk rather than the proxy.
  mkdir -p "$APP_DIR/.well-known/acme-challenge"
  echo ok > "$APP_DIR/.well-known/acme-challenge/.probe"
  if [ "$(curl -sS -m 10 "http://$DOMAIN/.well-known/acme-challenge/.probe" 2>/dev/null)" = "ok" ]; then
    ok "ACME challenge path reachable"
  else
    warn "ACME path unreachable - certificate issuance/renewal will fail"
  fi
  rm -f "$APP_DIR/.well-known/acme-challenge/.probe"
fi

# --------------------------------- superuser ---------------------------------
if [ "$DO_SUPERUSER" = "1" ]; then
  step "Creating a superuser"
  dc exec web python management_system/manage.py createsuperuser
fi

# ---------------------------------- summary ----------------------------------
step "Result"
if [ "$DO_NGINX" = "1" ] && [ "$HAVE_CERT" = "1" ]; then
  PUB="$(curl -s -o /dev/null -w '%{http_code}' -m 10 "https://$DOMAIN/" 2>/dev/null || echo '---')"
  case "$PUB" in
    200|302) ok "https://$DOMAIN/ -> HTTP $PUB - live" ;;
    301)     warn "https://$DOMAIN/ -> 301. If it loops, X-Forwarded-Proto is missing." ;;
    *)       warn "https://$DOMAIN/ -> $PUB. Check $LOG_DIR/$DOMAIN.error.log" ;;
  esac
else
  echo
  echo "  App is running, HTTP only. To finish:"
  echo "    1. Confirm DNS:  dig +short $DOMAIN"
  echo "    2. aaPanel -> Website -> $DOMAIN -> SSL -> Let's Encrypt -> Apply"
  echo "    3. Re-run this script; it adds the HTTPS block automatically."
fi
echo
echo "  Logs:    docker compose -f $COMPOSE_FILE logs -f web"
echo "  nginx:   tail -f $LOG_DIR/$DOMAIN.error.log"
echo "  Admin:   $0 --superuser"
echo
