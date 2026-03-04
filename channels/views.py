from rest_framework import viewsets, mixins
from rest_framework.permissions import IsAuthenticated

from .models import Channel
from .serializers import ChannelSerializer


class ChannelViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Read-only viewset for browsing available channels."""

    queryset = Channel.objects.filter(is_active=True)
    serializer_class = ChannelSerializer
    permission_classes = [IsAuthenticated]
