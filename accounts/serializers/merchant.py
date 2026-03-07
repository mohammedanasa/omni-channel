from ..models import Merchant, Domain
from rest_framework import serializers as drf_serializers

class MerchantSerializer(drf_serializers.ModelSerializer):
    """General serializer for listing and detail views."""
    class Meta:
        model = Merchant
        fields = ["id", "name", "owner"]  # owner returned to show relationship
        read_only_fields = ["id", "owner"]


class MerchantCreateSerializer(drf_serializers.ModelSerializer):
    """Serializer used for creating a merchant."""
    class Meta:
        model = Merchant
        fields = ["id", "name"]
        read_only_fields = ["id"]

    def create(self, validated_data):
        user = self.context["request"].user
        
        merchant = Merchant.objects.create(
            owner=user,
            name=validated_data["name"],
            schema_name=f"tenant_{merchant_uuid()}",
        )

        # Create a domain (required even if not used)
        Domain.objects.create(
            domain=f"{merchant.schema_name}.localhost",
            tenant=merchant,
            is_primary=True
        )

        return merchant


def merchant_uuid():
    """Utility for generating schema names."""
    import uuid
    return uuid.uuid4().hex



class MerchantUpdateSerializer(drf_serializers.ModelSerializer):
    """Serializer for updating merchant name"""
    class Meta:
        model = Merchant
        fields = ["name"]