import json

from django.db import connection
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View

from rest_framework import viewsets, mixins
from rest_framework.permissions import IsAuthenticated

from helpers.permissions.permissions import HasTenantAccess
from helpers.common import tenant_schema
from integrations.adapters import AdapterRegistry
from integrations.models import ChannelLink
from webhooks.models import WebhookEndpoint, WebhookLog, WebhookDirection
from webhooks.serializers import WebhookEndpointSerializer, WebhookLogSerializer


@tenant_schema("Webhook Endpoints")
class WebhookEndpointViewSet(viewsets.ModelViewSet):
    serializer_class = WebhookEndpointSerializer
    permission_classes = [IsAuthenticated, HasTenantAccess]

    def get_queryset(self):
        return WebhookEndpoint.objects.all()


@tenant_schema("Webhook Logs")
class WebhookLogViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = WebhookLogSerializer
    permission_classes = [IsAuthenticated, HasTenantAccess]

    def get_queryset(self):
        return WebhookLog.objects.all()


@method_decorator(csrf_exempt, name="dispatch")
class InboundWebhookView(View):
    """
    Receives inbound webhooks from external channels.
    URL: /api/v1/webhooks/inbound/<channel_link_id>/
    No JWT auth — uses adapter-level signature verification.
    Tenant is resolved from the ChannelLink.
    """

    def post(self, request, channel_link_id):
        try:
            # ChannelLink is in the tenant schema, but we need to find which
            # tenant it belongs to. We search across schemas using the shared
            # Channel FK → then switch to the right tenant.
            from django_tenants.utils import get_tenant_model

            # First try to find the ChannelLink in any schema.
            # Since we don't know the tenant yet, iterate tenants.
            TenantModel = get_tenant_model()
            channel_link = None

            for tenant in TenantModel.objects.exclude(schema_name="public"):
                connection.set_tenant(tenant)
                try:
                    channel_link = ChannelLink.objects.select_related(
                        "channel", "location"
                    ).get(id=channel_link_id, is_active=True)
                    break
                except ChannelLink.DoesNotExist:
                    continue

            if not channel_link:
                connection.set_schema_to_public()
                return JsonResponse({"error": "Channel link not found"}, status=404)

            # We're now on the correct tenant schema
            adapter = AdapterRegistry.get_adapter(channel_link)

            # Verify signature
            body = request.body
            headers = dict(request.headers)

            if not adapter.verify_webhook_signature(body, headers):
                return JsonResponse({"error": "Invalid signature"}, status=401)

            # Parse payload
            try:
                payload = json.loads(body) if body else {}
            except json.JSONDecodeError:
                return JsonResponse({"error": "Invalid JSON"}, status=400)

            event_type = headers.get("X-Event-Type", payload.get("event_type", "unknown"))

            # Log it
            log = WebhookLog.objects.create(
                direction=WebhookDirection.INBOUND,
                channel_slug=channel_link.channel.slug,
                event_type=event_type,
                request_headers=headers,
                request_body=payload,
            )

            # Let the adapter handle it
            result = adapter.handle_webhook(event_type, payload, headers)

            log.success = result.success
            log.response_body = json.dumps(result.to_dict())
            log.save(update_fields=["success", "response_body"])

            return JsonResponse(result.to_dict(), status=200 if result.success else 400)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
        finally:
            connection.set_schema_to_public()
