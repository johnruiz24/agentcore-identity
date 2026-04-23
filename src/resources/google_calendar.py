"""Google Calendar resource service for accessing calendar events."""

import logging
from typing import Dict, List, Optional, Any
import datetime
import httpx

logger = logging.getLogger(__name__)


class GoogleCalendarService:
    """Service for accessing Google Calendar using OAuth credentials.

    Provides calendar operations (list events, create, update, delete)
    using access tokens obtained through AgentCore Identity delegation.
    """

    # Google Calendar API base URL
    API_BASE_URL = "https://www.googleapis.com/calendar/v3"

    def __init__(self):
        """Initialize Google Calendar service."""
        logger.info("GoogleCalendarService initialized")

    async def get_events(
        self,
        token: str,
        calendar_id: str = "primary",
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
        max_results: int = 10,
        order_by: str = "startTime",
    ) -> Dict[str, Any]:
        """Fetch calendar events using OAuth token.

        Args:
            token: OAuth access token
            calendar_id: Calendar ID (default: "primary")
            time_min: Minimum time (RFC 3339 format)
            time_max: Maximum time (RFC 3339 format)
            max_results: Maximum events to return
            order_by: Ordering (startTime or updated)

        Returns:
            Dictionary with events list

        Raises:
            ValueError: If API call fails
        """
        url = f"{self.API_BASE_URL}/calendars/{calendar_id}/events"
        headers = {"Authorization": f"Bearer {token}"}

        params = {
            "maxResults": max_results,
            "orderBy": order_by,
            "singleEvents": True,
        }

        if time_min:
            params["timeMin"] = time_min
        if time_max:
            params["timeMax"] = time_max

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=headers, params=params)
                response.raise_for_status()

                data = response.json()
                events = data.get("items", [])

                logger.info(f"Retrieved {len(events)} calendar events")

                return {"events": events, "count": len(events)}

            except httpx.HTTPError as e:
                logger.error(f"Failed to get calendar events: {e}")
                raise ValueError(f"Failed to fetch events: {str(e)}")

    async def get_events_for_date(
        self, token: str, date: Optional[str] = None, calendar_id: str = "primary"
    ) -> Dict[str, Any]:
        """Get calendar events for a specific date.

        Args:
            token: OAuth access token
            date: Date in YYYY-MM-DD format (default: today)
            calendar_id: Calendar ID (default: "primary")

        Returns:
            Dictionary with events for the date

        Raises:
            ValueError: If API call fails
        """
        if date is None:
            date = datetime.date.today().isoformat()

        # Parse date
        parsed_date = datetime.datetime.strptime(date, "%Y-%m-%d")
        time_min = parsed_date.isoformat() + "Z"
        time_max = (parsed_date + datetime.timedelta(days=1)).isoformat() + "Z"

        return await self.get_events(
            token, calendar_id=calendar_id, time_min=time_min, time_max=time_max
        )

    async def create_event(
        self,
        token: str,
        calendar_id: str,
        title: str,
        description: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        attendees: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Create a calendar event.

        Args:
            token: OAuth access token
            calendar_id: Calendar ID
            title: Event title
            description: Event description
            start_time: Start time (RFC 3339 format)
            end_time: End time (RFC 3339 format)
            attendees: List of attendee emails

        Returns:
            Created event details

        Raises:
            ValueError: If creation fails
        """
        url = f"{self.API_BASE_URL}/calendars/{calendar_id}/events"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        # Build event object
        event = {
            "summary": title,
        }

        if description:
            event["description"] = description

        if start_time and end_time:
            event["start"] = {"dateTime": start_time}
            event["end"] = {"dateTime": end_time}

        if attendees:
            event["attendees"] = [{"email": email} for email in attendees]

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, headers=headers, json=event)
                response.raise_for_status()

                created = response.json()
                logger.info(f"Created calendar event: {created.get('id')}")

                return created

            except httpx.HTTPError as e:
                logger.error(f"Failed to create event: {e}")
                raise ValueError(f"Failed to create event: {str(e)}")

    async def update_event(
        self,
        token: str,
        calendar_id: str,
        event_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update an existing calendar event.

        Args:
            token: OAuth access token
            calendar_id: Calendar ID
            event_id: Event ID to update
            title: New event title
            description: New event description
            start_time: New start time
            end_time: New end time

        Returns:
            Updated event details

        Raises:
            ValueError: If update fails
        """
        url = f"{self.API_BASE_URL}/calendars/{calendar_id}/events/{event_id}"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        # Get current event first
        async with httpx.AsyncClient() as client:
            try:
                get_response = await client.get(url, headers=headers)
                get_response.raise_for_status()
                event = get_response.json()

                # Update fields
                if title:
                    event["summary"] = title
                if description:
                    event["description"] = description
                if start_time:
                    event["start"] = {"dateTime": start_time}
                if end_time:
                    event["end"] = {"dateTime": end_time}

                # Send update
                put_response = await client.put(url, headers=headers, json=event)
                put_response.raise_for_status()

                updated = put_response.json()
                logger.info(f"Updated calendar event: {event_id}")

                return updated

            except httpx.HTTPError as e:
                logger.error(f"Failed to update event: {e}")
                raise ValueError(f"Failed to update event: {str(e)}")

    async def delete_event(
        self, token: str, calendar_id: str, event_id: str
    ) -> bool:
        """Delete a calendar event.

        Args:
            token: OAuth access token
            calendar_id: Calendar ID
            event_id: Event ID to delete

        Returns:
            True if successful

        Raises:
            ValueError: If deletion fails
        """
        url = f"{self.API_BASE_URL}/calendars/{calendar_id}/events/{event_id}"
        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient() as client:
            try:
                response = await client.delete(url, headers=headers)
                response.raise_for_status()

                logger.info(f"Deleted calendar event: {event_id}")
                return True

            except httpx.HTTPError as e:
                logger.error(f"Failed to delete event: {e}")
                raise ValueError(f"Failed to delete event: {str(e)}")

    async def get_calendar_list(self, token: str) -> Dict[str, Any]:
        """Get list of calendars accessible to user.

        Args:
            token: OAuth access token

        Returns:
            Dictionary with calendars list

        Raises:
            ValueError: If API call fails
        """
        url = f"{self.API_BASE_URL}/users/me/calendarList"
        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=headers)
                response.raise_for_status()

                data = response.json()
                calendars = data.get("items", [])

                logger.info(f"Retrieved {len(calendars)} calendars")

                return {"calendars": calendars, "count": len(calendars)}

            except httpx.HTTPError as e:
                logger.error(f"Failed to list calendars: {e}")
                raise ValueError(f"Failed to list calendars: {str(e)}")


# Global instance
_service = GoogleCalendarService()


def get_google_calendar_service() -> GoogleCalendarService:
    """Get global Google Calendar service instance.

    Returns:
        Global GoogleCalendarService instance
    """
    return _service
