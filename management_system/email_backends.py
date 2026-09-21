import json
import logging
from typing import List

import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.message import EmailMessage
from django.core.mail.message import sanitize_address

logger = logging.getLogger(__name__)


class ResendEmailBackend(BaseEmailBackend):
    """Send Django email through Resend's transactional email API."""

    API_URL = 'https://api.resend.com/emails'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.api_key = getattr(settings, 'RESEND_API_KEY', '')
        if not self.api_key:
            raise ValueError('RESEND_API_KEY must be configured to use ResendEmailBackend.')

    def send_messages(self, email_messages: List[EmailMessage]):
        if not email_messages:
            return 0

        sent_count = 0
        for message in email_messages:
            if self._send(message):
                sent_count += 1
        return sent_count

    def _send(self, message: EmailMessage) -> bool:
        if not message.recipients():
            return False

        payload = self._build_payload(message)
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }

        response = requests.post(self.API_URL, headers=headers, json=payload, timeout=15)
        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.error('Resend email send failed: %s %s', exc, response.text if response is not None else '')
            if not self.fail_silently:
                raise
            return False

        return True

    def _build_payload(self, message: EmailMessage) -> dict:
        from_email = message.from_email or getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@example.com')

        payload = {
            'from': from_email,
            'to': [sanitize_address(addr, message.encoding) for addr in message.to or []],
            'subject': message.subject or '',
        }

        if getattr(message, 'reply_to', None):
            payload['reply_to'] = [sanitize_address(addr, message.encoding) for addr in message.reply_to]

        if message.cc:
            payload['cc'] = [sanitize_address(addr, message.encoding) for addr in message.cc]
        if message.bcc:
            payload['bcc'] = [sanitize_address(addr, message.encoding) for addr in message.bcc]

        if getattr(message, 'alternatives', None):
            # Preserve HTML alternatives along with plain text body.
            payload['html'] = message.alternatives[0][0]
            if message.body:
                payload['text'] = message.body
        else:
            payload['text'] = message.body or ''

        if getattr(message, 'extra_headers', None):
            headers = {k: v for k, v in message.extra_headers.items() if k.lower() != 'content-type'}
            if headers:
                payload['headers'] = headers

        return payload
