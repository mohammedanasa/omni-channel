from rest_framework import serializers
from menus.models import MenuAvailability


class MenuAvailabilityReadSerializer(serializers.ModelSerializer):
    """Read-only serializer for nesting availabilities inside menus."""
    day_name = serializers.CharField(source="get_day_of_week_display", read_only=True)

    class Meta:
        model = MenuAvailability
        fields = [
            "id", "day_of_week", "day_name",
            "start_time", "end_time", "start_date", "end_date",
        ]
        read_only_fields = fields


class MenuAvailabilitySerializer(serializers.ModelSerializer):
    """Write serializer for creating availabilities."""
    day_name = serializers.CharField(source="get_day_of_week_display", read_only=True)

    class Meta:
        model = MenuAvailability
        fields = [
            "id", "menu", "day_of_week", "day_name",
            "start_time", "end_time", "start_date", "end_date",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate(self, attrs):
        start_time = attrs.get("start_time")
        end_time = attrs.get("end_time")
        if start_time and end_time and end_time <= start_time:
            raise serializers.ValidationError(
                {"end_time": "end_time must be after start_time."}
            )
        start_date = attrs.get("start_date")
        end_date = attrs.get("end_date")
        if start_date and end_date and end_date < start_date:
            raise serializers.ValidationError(
                {"end_date": "end_date must be on or after start_date."}
            )
        return attrs
