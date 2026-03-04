from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model

from accounts.models import Merchant

User = get_user_model()


class BaseAPITest(APITestCase):

    def create_user(self, email="test@test.com", password="pass123", **kwargs):
        user = User.objects.create_user(
            email=email,
            password=password,
            first_name=kwargs.get("first_name", "Test"),
            last_name=kwargs.get("last_name", "User")
        )
        return user, password

    def authenticate(self, email, password):
        res = self.client.post("/api/v1/auth/jwt/create/", {
            "email": email,
            "password": password
        })

        print(self.client.headers)
        print("AUTH RESPONSE:", res)
        token = res.json()["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        return token

    def create_merchant(self, name="Merchant A"):
        res = self.client.post("/api/v1/merchants/", {"name": name})
        return res.json()["id"]   # returns merchant UUID

    def merchant_headers(self, merchant_id, location_id=None):
        headers = {"HTTP_X_TENANT_ID": merchant_id}
        if location_id:
            headers["HTTP_X_LOCATION_ID"] = location_id
        return headers

    def create_location(self, merchant_id, name="Location A"):
        res = self.client.post("/api/v1/locations/", {"name": name}, **self.merchant_headers(merchant_id))
        return res.json()["id"]
    
    def setup_user_and_merchant(self, email="test@test.com", name="Merchant X"):
        user, pwd = self.create_user(email=email)
        self.authenticate(email, pwd)
        merchant_id = self.create_merchant(name)
        return user, pwd, merchant_id

    def create_channel(self, slug="internal_pos", display_name="Internal POS",
                       channel_type="pos", direction="bidirectional",
                       adapter_class="integrations.adapters.internal.InternalPOSAdapter"):
        from channels.models import Channel
        channel, _ = Channel.objects.get_or_create(
            slug=slug,
            defaults={
                "display_name": display_name,
                "channel_type": channel_type,
                "direction": direction,
                "adapter_class": adapter_class,
            },
        )
        return channel

    def create_channel_link(self, channel, location_id, merchant_id):
        res = self.client.post(
            "/api/v1/channel-links/",
            {"channel": str(channel.id), "location": str(location_id)},
            format="json",
            **self.merchant_headers(merchant_id),
        )
        return res.json()["id"]

    def create_order(self, merchant_id, location_id, **kwargs):
        data = {
            "location": str(location_id),
            "order_type": kwargs.get("order_type", "delivery"),
            "customer_name": kwargs.get("customer_name", "Test Customer"),
            "subtotal": kwargs.get("subtotal", 1000),
            "tax_total": kwargs.get("tax_total", 100),
            "total": kwargs.get("total", 1100),
        }
        data.update(kwargs)
        res = self.client.post(
            "/api/v1/orders/",
            data,
            format="json",
            **self.merchant_headers(merchant_id),
        )
        return res.json()