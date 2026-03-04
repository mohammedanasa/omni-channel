from rest_framework.routers import DefaultRouter
from .views import ChannelViewSet

router = DefaultRouter()
router.register("channels", ChannelViewSet, basename="channels")

urlpatterns = router.urls
