from rest_framework import serializers

class TrackingSerializer(serializers.Serializer):
    HBL = serializers.CharField(max_length = 255)