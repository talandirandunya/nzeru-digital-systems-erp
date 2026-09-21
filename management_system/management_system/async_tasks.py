import threading
import logging
from functools import wraps

logger = logging.getLogger(__name__)

def async_task(func):
    """Decorator to execute a function asynchronously in a background thread."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        def run():
            try:
                func(*args, **kwargs)
            except Exception as e:
                logger.error("Background task %s failed: %s", func.__name__, e, exc_info=True)
        
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        return thread
    return wrapper


@async_task
def send_email_in_background(company, subject, body, recipient_list, html_message=None):
    """Background task to send emails without blocking the main request thread."""
    from accounts.views import send_company_email
    send_company_email(company, subject, body, recipient_list, html_message)
