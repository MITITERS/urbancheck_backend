from rest_framework import serializers

from urbancheck.users.models import User


class UserSerializer(serializers.ModelSerializer[User]):
    class Meta:
        model = User
        fields = ["id", "name", "email", "avatar", "role", "url"]
        read_only_fields = ["email", "role"]

        extra_kwargs = {
            "url": {"view_name": "api:user-detail", "lookup_field": "pk"},
        }
