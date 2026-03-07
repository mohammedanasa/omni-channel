from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema, extend_schema_view

TENANT_HEADER = OpenApiParameter(
    name="X-Tenant-ID",
    type=OpenApiTypes.STR,
    location=OpenApiParameter.HEADER,
    required=True,
    description="Merchant UUID for tenant selection"
)

LOCATION_HEADER = OpenApiParameter(name="X-Location-ID", type=str, location="header",
                                   required=False,
                                   description="Optional Location ID to scope products")


CHANNEL_LINK_HEADER = OpenApiParameter(
    name="X-Channel-Link-ID",
    type=OpenApiTypes.STR,
    location=OpenApiParameter.HEADER,
    required=False,
    description="Optional ChannelLink UUID for channel-specific operations",
)


def tenant_schema(tag, *extra_params):
    """
    DRY decorator that applies X-Tenant-ID (and any extra params)
    to every standard ViewSet action that exists on the class.

    Usage:
        @tenant_schema("Products", LOCATION_HEADER)
        class ProductViewSet(viewsets.ModelViewSet): ...
    """
    ALL_ACTIONS = ["list", "retrieve", "create", "update", "partial_update", "destroy"]
    params = [TENANT_HEADER, *extra_params]

    def decorator(cls):
        actions = [a for a in ALL_ACTIONS if hasattr(cls, a)]
        return extend_schema_view(
            **{action: extend_schema(tags=[tag], parameters=params) for action in actions}
        )(cls)

    return decorator