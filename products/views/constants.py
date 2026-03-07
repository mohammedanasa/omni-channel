from drf_spectacular.utils import OpenApiParameter, OpenApiTypes


CHANNEL_HEADER = OpenApiParameter(
    name="X-Channel",
    type=OpenApiTypes.STR,
    location=OpenApiParameter.HEADER,
    required=False,
    description="Channel name (e.g. 'ubereats', 'doordash')",
)

PRODUCT_TYPE_FILTER = OpenApiParameter(
    name="product_type",
    type=OpenApiTypes.INT,
    location=OpenApiParameter.QUERY,
    required=False,
    description=(
        "Filter products by type. "
        "1 = Main product, "
        "2 = Modifier item, "
        "3 = Modifier group, "
        "4 = Bundle group"
    ),
    enum=[1, 2, 3, 4],
)
