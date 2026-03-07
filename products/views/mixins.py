import uuid as _uuid

from locations.models import Location


class HeaderContextMixin:
    """Extracts X-Location-ID and X-Channel from request headers."""

    def _get_location_from_header(self):
        location_id = self.request.META.get('HTTP_X_LOCATION_ID')
        if location_id:
            try:
                _uuid.UUID(str(location_id))
            except ValueError:
                return None
            try:
                return Location.objects.get(id=location_id)
            except Location.DoesNotExist:
                return None
        return None

    def _get_channel_from_header(self):
        channel = self.request.META.get('HTTP_X_CHANNEL')
        return channel.lower() if channel else None
