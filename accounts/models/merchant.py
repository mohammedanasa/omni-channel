from django.db import models
from common.models import BaseUUIDModel
from django_tenants.models import TenantMixin

from .user import User


class Merchant(BaseUUIDModel, TenantMixin):
    name = models.CharField(max_length=100)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="merchants")

    auto_create_schema = True

    def __str__(self):
        return self.name
