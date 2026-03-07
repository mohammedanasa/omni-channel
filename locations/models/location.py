from django.db import models
from common.models import BaseUUIDModel

class Location(BaseUUIDModel):
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    pincode = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
