"""Resource integrations with OAuth credentials."""

from .google_calendar import GoogleCalendarService, get_google_calendar_service

__all__ = ["GoogleCalendarService", "get_google_calendar_service"]
