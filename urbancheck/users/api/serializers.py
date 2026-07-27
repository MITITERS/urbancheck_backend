from rest_framework import serializers

from urbancheck.users.models import User


class UserSerializer(serializers.ModelSerializer[User]):
    """Perfil propio: incluye datos privados como el email."""

    class Meta:
        model = User
        fields = ["id", "name", "email", "avatar", "role", "is_public", "url"]
        read_only_fields = ["email", "role"]

        extra_kwargs = {
            "url": {"view_name": "api:user-detail", "lookup_field": "pk"},
        }


class PublicUserSerializer(serializers.ModelSerializer[User]):
    """Perfil público de otro usuario (US-027).

    Si el usuario marcó su perfil como privado, se devuelven solo nombre y avatar:
    ``date_joined`` y ``report_count`` viajan en ``null`` para que el cliente sepa
    que no hay nada más que mostrar sin tener que inferirlo.
    """

    date_joined = serializers.SerializerMethodField()
    report_count = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "name", "avatar", "is_public", "date_joined", "report_count"]
        read_only_fields = fields

    def get_date_joined(self, obj) -> str | None:
        if not obj.is_public:
            return None
        return obj.date_joined.isoformat()

    def get_report_count(self, obj) -> int | None:
        if not obj.is_public:
            return None
        return obj.reports.count()
