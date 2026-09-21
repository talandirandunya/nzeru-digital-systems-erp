# VPS deployment (Docker Compose, behind aaPanel)

This VPS already runs other apps behind a panel (aaPanel/BT Panel) that owns ports
80/443 and manages domains + SSL itself — the same pattern the `le-poloo` app on
this box already uses (container listens on a loopback-only port, the panel
reverse-proxies the public domain to it). This stack follows that pattern:
`docker-compose.prod.yml` only runs `db` (Postgres) and `web` (this app); the panel
handles the public-facing side.

Files involved: `docker-compose.prod.yml`, `.env.production.example`,
`deploy/media/`. The app code and `Dockerfile` are unchanged.

## 1. Configure environment

```bash
cp .env.production.example .env
```

Fill in every value — at minimum: `SECRET_KEY`, `ALLOWED_HOSTS`,
`CSRF_TRUSTED_ORIGINS` (your real domain), `POSTGRES_PASSWORD` / `DATABASE_URL`
(keep them consistent), and `RESEND_API_KEY` for email.

If you don't have Cloudinary credentials, leave those three blank — uploaded
files persist in `./deploy/media` on the VPS instead, and the panel serves them
directly (step 3).

## 2. Check port 8010 is free, then start the stack

Other apps on this VPS already use 5051, 5101, 5433, 8072, 5769 — 8010 should be
clear, but confirm:

```bash
sudo ss -tulpn | grep 8010
```

If something's already there, change the `8010` in `docker-compose.prod.yml`'s
`web.ports` to a free port and use that port everywhere below instead.

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

`web` runs `migrate` automatically on start (see `Dockerfile`); static files were
already collected at image-build time and are served via whitenoise.

## 3. Point aaPanel at it

In aaPanel:

1. **Website → Add site** for your domain (or reuse an existing site entry if one
   was already created for this app).
2. Set it up as a **reverse proxy** to `http://127.0.0.1:8010` (whatever port you
   used in step 2).
3. **SSL** tab → issue a free Let's Encrypt certificate for the domain through
   aaPanel's own SSL manager (same as your other panel-managed sites) and force
   HTTPS.
4. Add a location block so uploaded media is served directly from disk instead of
   proxied through gunicorn — in the site's **Config file**, add this *above* the
   existing reverse-proxy `location /` block:

   ```nginx
   location /media/ {
       alias /path/to/this/repo/deploy/media/;
   }
   ```

   Replace `/path/to/this/repo` with the actual path on the VPS (e.g.
   `/www/wwwroot/erp` or wherever you cloned it).
5. Also add, near the top of the `server` block, to allow file uploads larger
   than aaPanel's 1M default:

   ```nginx
   client_max_body_size 25M;
   ```

## 4. Create an admin user

```bash
docker compose -f docker-compose.prod.yml exec web \
  python management_system/manage.py createsuperuser
```

## Redeploying after a code change

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

`db` data (named volume) and `./deploy/media` (bind mount) persist across
rebuilds.

## Notes

- Postgres is bound to `127.0.0.1:5433` only (see `docker-compose.prod.yml` for
  the SSH-tunnel command to reach it from your machine) — not exposed to the
  internet. `web` is `127.0.0.1:8010` only — same story; only the panel's own
  Nginx (80/443) is public.
- Back up the database: `docker compose -f docker-compose.prod.yml exec db pg_dump -U <POSTGRES_USER> <POSTGRES_DB> > backup.sql`
- Local development is unaffected — keep using `docker compose up` with the
  existing `docker-compose.yml`.
