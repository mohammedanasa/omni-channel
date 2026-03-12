from django.db import models
from django.core.exceptions import ValidationError
from common.models import BaseUUIDModel
from .menu import Menu


class MenuAvailability(BaseUUIDModel):
    """Daypart availability window for a menu."""

    menu = models.ForeignKey(Menu, on_delete=models.CASCADE, related_name="availabilities")
    day_of_week = models.IntegerField(
        choices=[
            (0, "Monday"),
            (1, "Tuesday"),
            (2, "Wednesday"),
            (3, "Thursday"),
            (4, "Friday"),
            (5, "Saturday"),
            (6, "Sunday"),
        ]
    )
    start_time = models.TimeField()
    end_time = models.TimeField()
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("menu", "day_of_week", "start_time")
        ordering = ["day_of_week", "start_time"]
        verbose_name_plural = "Menu availabilities"

    def __str__(self):
        day = self.get_day_of_week_display()
        return f"{self.menu.name} — {day} {self.start_time}-{self.end_time}"

    def clean(self):
        super().clean()
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError("end_time must be after start_time.")
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError("end_date must be on or after start_date.")
