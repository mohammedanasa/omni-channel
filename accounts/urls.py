from rest_framework.routers import DefaultRouter
from .views import MerchantViewSet

router = DefaultRouter()
router.register(r"merchants", MerchantViewSet, basename="merchants")

urlpatterns = router.urls
