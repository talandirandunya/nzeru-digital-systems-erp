# Clerk + Resend Integration Guide

## Overview

**Clerk** = Authentication & User Management (replaces your current `accounts` app logic)
**Resend** = Transactional Email (replaces Django's `send_mail()` for invitations, notifications)

---

## Part 1: Understanding the Tools

### Clerk
- **What it does**: Hosted authentication (sign up, sign in, SSO, MFA, user profiles)
- **Why use it**: Reduces code maintenance, handles security best practices, provides user dashboard
- **For your project**: Replace custom login/register with Clerk UI, store company metadata in Clerk organizations
- **Cost**: Free tier covers ~500 active users; then $0.02–$0.50 per monthly active user

### Resend
- **What it does**: Transactional email API (sends email via HTTP, not SMTP)
- **Why use it**: Reliable delivery, better deliverability than Django's SMTP, easy integrations
- **For your project**: Use for company invitations, leave approvals, password resets, notifications
- **Cost**: Free tier 100 emails/day; then $0.0005 per email (very cheap)

---

## Part 2: Architecture Decision

### Option A: Full Migration (Recommended for new projects)
- Replace Django auth with Clerk
- Store minimal user data in Django (sync from Clerk via webhooks)
- Use Resend for all transactional email
- Simplifies codebase, offloads security concerns

### Option B: Hybrid (Recommended for existing projects)
- Keep Django auth for now, use only Clerk for additional SSO layer (optional)
- Replace `send_mail()` with Resend immediately
- Gradual migration to full Clerk later
- Lower risk, incremental changes

**For your project**: I recommend **Option B** (Hybrid) since you have existing auth infrastructure. You can replace email first, then migrate auth later.

---

## Part 3: Setup Steps

### 3.1 Create Accounts

1. **Clerk** (https://clerk.com/sign-up)
   - Create project
   - Get `CLERK_FRONTEND_API_KEY` and `CLERK_API_KEY`
   - Create organization template for companies

2. **Resend** (https://resend.com/signup)
   - Create account
   - Verify sender domain (e.g., `noreply@yourdomain.com`)
   - Get `RESEND_API_KEY`

### 3.2 Install Python Packages

```bash
pip install clerk-sdk-python resend python-dotenv
pip freeze > requirements.txt
```

### 3.3 Environment Variables

Create `.env` file (or add to Render dashboard):

```env
# Clerk (optional for now, add later)
CLERK_FRONTEND_API_KEY=pk_test_xxxxx
CLERK_API_KEY=sk_test_xxxxx
CLERK_WEBHOOK_SECRET=whsec_xxxxx

# Resend
RESEND_API_KEY=re_xxxxx

# Django (existing)
SECRET_KEY=...
DEBUG=False
ALLOWED_HOSTS=yourdomain.com
DATABASE_URL=postgresql://...
```

---

## Part 4: Immediate Changes (Email Only - Option B)

### 4.1 Replace Django Email with Resend

Create `management_system/emails.py`:

```python
import resend
from django.conf import settings

resend.api_key = settings.RESEND_API_KEY

def send_invitation_email(recipient_email, company_name, accept_url, invited_by_name):
    """Send invitation via Resend instead of Django mail."""
    try:
        email = resend.Emails.send(
            {
                "from": "noreply@yourdomain.com",
                "to": recipient_email,
                "subject": f"You've been invited to join {company_name}",
                "html": f"""
                <h2>Welcome to {company_name}!</h2>
                <p>{invited_by_name} invited you to join {company_name} on Zentral.</p>
                <a href="{accept_url}" style="background: #16a34a; color: white; padding: 10px 20px; border-radius: 8px; text-decoration: none; display: inline-block;">
                    Accept Invitation
                </a>
                <p><small>This link expires in 7 days.</small></p>
                """,
            }
        )
        return True
    except Exception as e:
        print(f"Resend email error: {e}")
        return False

def send_password_reset_email(recipient_email, reset_url):
    """Send password reset via Resend."""
    try:
        resend.Emails.send(
            {
                "from": "noreply@yourdomain.com",
                "to": recipient_email,
                "subject": "Reset your Zentral password",
                "html": f"""
                <h2>Password Reset</h2>
                <p>Click below to reset your password:</p>
                <a href="{reset_url}" style="background: #16a34a; color: white; padding: 10px 20px; border-radius: 8px; text-decoration: none; display: inline-block;">
                    Reset Password
                </a>
                <p><small>This link expires in 1 hour.</small></p>
                """,
            }
        )
        return True
    except Exception as e:
        print(f"Resend email error: {e}")
        return False
```

### 4.2 Update `accounts/views.py`

Replace `send_mail()` calls:

```python
# OLD:
# send_mail(subject, body, None, [email], fail_silently=False)

# NEW:
from management_system.emails import send_invitation_email

# In invite_user view:
send_invitation_email(
    recipient_email=email,
    company_name=company.name,
    accept_url=accept_url,
    invited_by_name=request.user.first_name or request.user.email
)
```

### 4.3 Update `settings.py`

```python
import os
from dotenv import load_dotenv

load_dotenv()

# Resend
RESEND_API_KEY = os.getenv("RESEND_API_KEY")

# Remove Django email config (no longer needed for Resend)
# EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
# EMAIL_HOST = ...
```

### 4.4 Test Locally

```bash
python manage.py shell
from management_system.emails import send_invitation_email
send_invitation_email(
    "test@example.com",
    "TestCorp",
    "http://localhost:8000/invite/accept/123/",
    "Admin User"
)
```

---

## Part 5: Full Migration (Clerk Auth - Later)

### 5.1 Architecture Change

```
Before (Django Auth):
  User clicks "Register" → Django creates User & Company → Stores in DB

After (Clerk Auth):
  User clicks "Register" → Clerk UI handles signup → Webhook triggers → Django syncs metadata
```

### 5.2 Create Clerk Organization Template

1. Go to Clerk dashboard → Organizations
2. Create template: `company`
3. Add metadata fields:
   - `domain` (string)
   - `subscription_plan` (string)
   - `is_active` (boolean)

### 5.3 Webhook Handler

Create `management_system/webhooks.py`:

```python
import json
import hmac
import hashlib
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from accounts.models import Company, User
import os

CLERK_WEBHOOK_SECRET = os.getenv("CLERK_WEBHOOK_SECRET")

def verify_clerk_webhook(request):
    """Verify Clerk webhook signature."""
    signature = request.headers.get("svix-signature", "")
    timestamp = request.headers.get("svix-timestamp", "")
    msg_id = request.headers.get("svix-msg-id", "")
    
    msg = f"{msg_id}.{timestamp}.{request.body.decode()}"
    expected = hmac.new(
        CLERK_WEBHOOK_SECRET.encode(),
        msg.encode(),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(signature.split(",")[1], expected)

@csrf_exempt
@require_http_methods(["POST"])
def clerk_webhook(request):
    """Handle Clerk webhook events."""
    if not verify_clerk_webhook(request):
        return JsonResponse({"error": "Unauthorized"}, status=401)
    
    data = json.loads(request.body)
    event_type = data["type"]
    
    if event_type == "organization.created":
        org_data = data["data"]
        company, created = Company.objects.get_or_create(
            domain=org_data["slug"],
            defaults={
                "name": org_data["name"],
                "is_active": True,
            }
        )
    
    elif event_type == "user.created":
        user_data = data["data"]
        email = user_data["email_addresses"][0]["email_address"]
        User.objects.get_or_create(
            email=email,
            defaults={
                "first_name": user_data.get("first_name", ""),
                "last_name": user_data.get("last_name", ""),
            }
        )
    
    return JsonResponse({"ok": True})
```

### 5.4 Update `urls.py`

```python
from management_system.webhooks import clerk_webhook

urlpatterns = [
    path("webhooks/clerk/", clerk_webhook, name="clerk_webhook"),
    # ... rest of urls
]
```

---

## Part 6: Render Deployment

### 6.1 Environment Variables on Render

1. Go to Render dashboard → Your service
2. Settings → Environment
3. Add:
   ```
   CLERK_FRONTEND_API_KEY=pk_test_xxxxx
   CLERK_API_KEY=sk_test_xxxxx
   CLERK_WEBHOOK_SECRET=whsec_xxxxx
   RESEND_API_KEY=re_xxxxx
   ```

### 6.2 Configure Clerk Webhook URL

1. Clerk dashboard → Webhooks
2. Add endpoint: `https://yourdomain.com/webhooks/clerk/`
3. Subscribe to: `organization.created`, `user.created`, `user.updated`

### 6.3 Redeploy

```bash
git add .
git commit -m "feat: add Resend for email and Clerk webhook"
git push  # Render auto-deploys
```

---

## Part 7: Neon Database Considerations

Neon is PostgreSQL-compatible, so no changes needed. Just ensure:

1. `DATABASE_URL` is set in Render environment
2. Run migrations after deploying:
   ```bash
   python manage.py migrate
   ```

If syncing user data from Clerk, consider adding indexes on `email` and `clerk_user_id`:

```python
# accounts/models.py
class User(AbstractBaseUser):
    email = models.EmailField(unique=True, db_index=True)
    clerk_user_id = models.CharField(max_length=255, blank=True, null=True, db_index=True)
```

---

## Part 8: Migration Path (Recommended)

### Phase 1 (Week 1): Resend Email Only
- Replace `send_mail()` with Resend
- Test invitations and password resets
- No Django auth changes yet
- Low risk, immediate benefit

### Phase 2 (Week 2-3): Clerk SSO (Optional)
- Add Clerk as optional SSO layer
- Users can still use Django login
- Existing users unaffected

### Phase 3 (Week 4+): Full Clerk Migration
- Migrate all existing users to Clerk
- Decommission Django auth views
- Simplify codebase

---

## Part 9: Testing Checklist

### Before deploying to Render:

- [ ] Resend API key works locally
  - [ ] Test sending invitation email
  - [ ] Test sending password reset
- [ ] Environment variables set in `.env`
- [ ] No hardcoded API keys in code
- [ ] Error handling for failed emails (log gracefully)
- [ ] Email templates render correctly
- [ ] Links in emails are absolute URLs (not localhost)

### After deploying to Render:

- [ ] Invitation emails arrive (check spam)
- [ ] Password reset emails arrive
- [ ] Database migrations run successfully
- [ ] No error logs in Render dashboard

---

## Part 10: Code Snippets & Examples

### Send Company Notification Email

```python
def send_company_notification(company_id, subject, message):
    """Send email to all company admins."""
    company = Company.objects.get(id=company_id)
    admins = User.objects.filter(company=company, is_company_admin=True)
    
    for admin in admins:
        resend.Emails.send({
            "from": "noreply@yourdomain.com",
            "to": admin.email,
            "subject": subject,
            "html": f"<p>{message}</p>",
        })
```

### Resend with Try/Catch & Logging

```python
import logging

logger = logging.getLogger(__name__)

def send_email_safe(to, subject, html):
    try:
        resend.Emails.send({
            "from": "noreply@yourdomain.com",
            "to": to,
            "subject": subject,
            "html": html,
        })
        logger.info(f"Email sent to {to}")
    except Exception as e:
        logger.error(f"Failed to send email to {to}: {e}")
        # Optionally alert admins or queue for retry
```

### Clerk SDK Example (for later)

```python
from clerk_sdk import Clerk

clerk = Clerk(api_key="sk_test_xxxxx")

# Create user
user = clerk.users.create(
    email_address="user@example.com",
    password="SecurePassword123",
)

# Get user
user = clerk.users.get(user_id="user_123")

# Update org metadata
org = clerk.organizations.get(organization_id="org_123")
clerk.organizations.update(
    organization_id=org.id,
    metadata={"domain": "my-company"}
)
```

---

## Part 11: Troubleshooting

### "Resend API key not found"
- Check `.env` file exists in root
- Ensure `RESEND_API_KEY` is set
- Restart Django dev server after adding env var

### "Email sending fails with 401"
- Verify API key is correct
- Check domain is verified in Resend dashboard
- Ensure sender email matches verified domain

### "Webhook signature verification fails"
- Check `CLERK_WEBHOOK_SECRET` matches Clerk dashboard
- Ensure webhook endpoint is publicly accessible (not localhost)
- Check Render logs for request payload

### "Database connection fails on Render"
- Verify `DATABASE_URL` is set in Render environment
- Check Neon dashboard for active connections
- Ensure IP allowlist includes Render's IP range

---

## Part 12: Security Best Practices

1. **Never commit `.env`** — add to `.gitignore`
2. **Rotate API keys** if exposed
3. **Use webhook signatures** to verify Clerk/Resend events
4. **Rate-limit email sending** (e.g., 5 invites per hour per user)
5. **Sanitize email templates** to prevent injection
6. **Log email failures** for debugging
7. **Use HTTPS only** for webhook URLs on Render

---

## Summary

| Tool | Purpose | Time to Setup | Cost |
|------|---------|----------------|------|
| **Resend** | Email API | 30 min | Free tier: 100/day |
| **Clerk** | Authentication | 2 hours | Free tier: 500 users |
| **Integration** | Full setup | 4 hours | Minimal if phased |

**Recommended start**: Replace email with Resend (Phase 1) this week. Add Clerk later (Phase 3).

