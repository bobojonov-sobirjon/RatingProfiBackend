from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from .models import UpcomingEvent


class UpcomingEventSerializer(serializers.ModelSerializer):
    """
    Serializer для ближайших мероприятий
    """
    event_type_display = serializers.CharField(
        source='get_event_type_display',
        read_only=True
    )
    status_display = serializers.CharField(
        source='get_status_display',
        read_only=True
    )
    created_by_name = serializers.SerializerMethodField()
    
    @extend_schema_field(str)
    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() if hasattr(obj.created_by, 'get_full_name') else str(obj.created_by)
        return None
    
    class Meta:
        model = UpcomingEvent
        fields = [
            'id',
            'poster',
            'organization_name',
            'event_type',
            'event_type_display',
            'announcement',
            'event_date',
            'event_location',
            'city',
            'registration_phone',
            'about_event',
            'status',
            'status_display',
            'created_by',
            'created_by_name',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'created_by',
            'created_at',
            'updated_at',
        ]
