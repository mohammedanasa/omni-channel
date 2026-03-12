from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import MenuViewSet

app_name = "menus"

router = DefaultRouter()
router.register(r"menus", MenuViewSet, basename="menu")

urlpatterns = [
    path("", include(router.urls)),
]
