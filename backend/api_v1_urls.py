# project/api_v1_urls.py
from django.urls import path, include


urlpatterns = [
    # Auth nested correctly
    path("auth/", include("djoser.urls")),
    path("auth/", include("djoser.urls.jwt")),

    # Feature apps (Assuming internal urls.py are clean)
    path("", include("accounts.urls")),
    path("", include("locations.urls")),
    path("", include("products.urls")),
    # path("", include("channels.urls")),
    # path("", include("integrations.urls")),
    # path("", include("orders.urls")),
    # path("", include("webhooks.urls")),
]