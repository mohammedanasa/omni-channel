from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import WebhookEndpointViewSet, WebhookLogViewSet, InboundWebhookView

router = DefaultRouter()
router.register("webhooks/endpoints", WebhookEndpointViewSet, basename="webhook-endpoints")
router.register("webhooks/logs", WebhookLogViewSet, basename="webhook-logs")

urlpatterns = router.urls + [
    path(
        "webhooks/inbound/<uuid:channel_link_id>/",
        InboundWebhookView.as_view(),
        name="inbound-webhook",
    ),
]
