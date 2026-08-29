"""Best-effort desktop notification adapter."""

from __future__ import annotations

def notify(title: str, message: str) -> None:
    """Display one desktop notification through the optional platform backend.

    The backend is imported only when a notification is requested. Importing
    the application or synchronization engine therefore remains possible on
    systems where ``plyer`` is unavailable.
    """
    from plyer import notification

    notification.notify(title=title, message=message, app_name="Apollo Sync")
