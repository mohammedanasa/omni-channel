from rest_framework.routers import DefaultRouter
from .views import ChannelLinkViewSet, ProductChannelConfigViewSet

router = DefaultRouter()
router.register("channel-links", ChannelLinkViewSet, basename="channel-links")
router.register(
    "product-channel-configs",
    ProductChannelConfigViewSet,
    basename="product-channel-configs",
)

urlpatterns = router.urls
