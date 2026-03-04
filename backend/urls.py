from django.contrib import admin
from django.urls import path,include
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView


# urlpatterns = [
#     path("admin/", admin.site.urls),

#     # Authentication (Djoser)
#     path("api/v1/auth/", include("djoser.urls")),
#     path("api/v1/auth/", include("djoser.urls.jwt")),

#     # Accounts/Merchants
#     path("api/v1/", include("accounts.urls")),

#     # Locations
#     path("api/v1/", include("locations.urls")),

#     # Products
#     path("api/v1/", include("products.urls")),

#     # OpenAPI Schema & Docs
#     path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
#     path('api/v1/test/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
#     path('api/v1/docs/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
# ]

urlpatterns = [
    path("admin/", admin.site.urls),
    
    # Versioning Entry Points
    # Use parentheses () for the function call and [] for the list inside
    path("api/v1/", include([
        path("", include("backend.api_v1_urls")),
        path('schema/', SpectacularAPIView.as_view(), name='schema'),
        path('docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
        path('redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    ])),
]