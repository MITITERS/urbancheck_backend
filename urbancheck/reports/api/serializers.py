from rest_framework import serializers

from urbancheck.reports.models import Comment
from urbancheck.reports.models import Like
from urbancheck.reports.models import Report
from urbancheck.reports.models import ReportStatusHistory
from urbancheck.users.models import User


class AuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "name", "avatar"]


class StatusHistorySerializer(serializers.ModelSerializer):
    changed_by = AuthorSerializer(read_only=True)

    class Meta:
        model = ReportStatusHistory
        fields = ["status", "created_at", "changed_by"]


class CommentSerializer(serializers.ModelSerializer):
    author = AuthorSerializer(read_only=True)

    class Meta:
        model = Comment
        fields = ["id", "author", "text", "created_at"]
        read_only_fields = ["id", "author", "created_at"]


class ReportListSerializer(serializers.ModelSerializer):
    author = AuthorSerializer(read_only=True)
    like_count = serializers.IntegerField(read_only=True)
    comment_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Report
        fields = [
            "id",
            "photo",
            "description",
            "category",
            "status",
            "author",
            "like_count",
            "comment_count",
            "created_at",
        ]


class ReportDetailSerializer(ReportListSerializer):
    is_liked = serializers.SerializerMethodField()
    comments = CommentSerializer(many=True, read_only=True)
    status_history = StatusHistorySerializer(many=True, read_only=True)

    class Meta(ReportListSerializer.Meta):
        fields = ReportListSerializer.Meta.fields + [
            "latitude",
            "longitude",
            "address",
            "is_liked",
            "comments",
            "status_history",
        ]

    def get_is_liked(self, obj):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return Like.objects.filter(report=obj, user=request.user).exists()
        return False


class ReportCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Report
        fields = [
            "id",
            "photo",
            "description",
            "category",
            "latitude",
            "longitude",
            "address",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs):
        if not attrs.get("photo"):
            raise serializers.ValidationError({"photo": "La foto es obligatoria."})
        has_coords = attrs.get("latitude") is not None and attrs.get("longitude") is not None
        has_address = bool(attrs.get("address", "").strip())
        if not has_coords and not has_address:
            raise serializers.ValidationError(
                {"location": "Debés proporcionar coordenadas GPS o una dirección."}
            )
        return attrs
