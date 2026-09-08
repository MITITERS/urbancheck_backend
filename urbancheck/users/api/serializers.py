from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from urbancheck.municipalities.api.area_serializers import OperationalAreaSerializer
from urbancheck.municipalities.api.serializers import MunicipalitySerializer
from urbancheck.municipalities.models import Municipality
from urbancheck.municipalities.models import OperationalArea
from urbancheck.users.models import User

EMAIL_TAKEN_MESSAGE = "Ya existe un usuario registrado con ese correo."
AREA_INACTIVE_MESSAGE = (
    "El área operativa está desactivada: un operario no puede existir sin un "
    "área activa que lo contenga."
)
AREA_FOREIGN_MESSAGE = "El área operativa pertenece a otra municipalidad."
PHONE_REQUIRED_MESSAGE = "Ingresá un teléfono de contacto."
NAME_REQUIRED_MESSAGE = "Ingresá el nombre del operario."


class UserSerializer(serializers.ModelSerializer[User]):
    """Perfil propio: incluye datos privados como el email."""

    municipality = MunicipalitySerializer(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "name",
            "email",
            "avatar",
            "role",
            "municipality",
            "must_change_password",
            # Lo mira el panel para frenar en la puerta a una cuenta de trabajo
            # dada de baja, en vez de dejarla entrar a una pantalla en la que
            # cada request va a devolver 403.
            "is_work_account_active",
            "is_public",
            "url",
        ]
        # La municipalidad es inmodificable una vez asignada (US-017): no se
        # expone como editable en ningún serializer de update.
        read_only_fields = [
            "email",
            "role",
            "municipality",
            "must_change_password",
            "is_work_account_active",
        ]

        extra_kwargs = {
            "url": {"view_name": "api:user-detail", "lookup_field": "pk"},
        }


class PanelUserCreateSerializer(serializers.ModelSerializer[User]):
    """Base del alta de usuarios hecha desde el panel (US-017 y US-035).

    Quien crea la cuenta define una contraseña temporal; el usuario está
    obligado a cambiarla en su primer ingreso. Las subclases fijan el rol y
    resuelven de dónde sale la municipalidad.
    """

    #: Rol con el que se crea el usuario. Lo fija cada subclase.
    role = None

    temporary_password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ["id", "name", "email", "temporary_password"]
        read_only_fields = ["id"]

    def validate_email(self, value: str) -> str:
        normalized = value.strip().lower()
        if User.objects.filter(email__iexact=normalized).exists():
            raise serializers.ValidationError(EMAIL_TAKEN_MESSAGE)
        return normalized

    def validate_temporary_password(self, value: str) -> str:
        """Aplica los validadores de contraseña de Django también en el alta."""
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value

    def get_municipality(self) -> Municipality | None:
        raise NotImplementedError

    def create(self, validated_data: dict) -> User:
        password = validated_data.pop("temporary_password")
        user = User(
            **validated_data,
            role=self.role,
            municipality=self.get_municipality(),
            must_change_password=True,
        )
        user.set_password(password)
        user.full_clean(exclude=["password"])
        user.save()
        return user


class AdminCreatesPanelUserSerializer(PanelUserCreateSerializer):
    """Alta hecha por el administrador de la plataforma, que elige el municipio.

    El admin no tiene jurisdicción propia de la cual derivarla, así que la
    municipalidad viaja en el body y es obligatoria. La comparten el alta de
    agentes (US-017) y la de validadores: si cada una lo resolviera por su
    cuenta, terminarían con validaciones distintas para el mismo campo.
    """

    municipality_id = serializers.PrimaryKeyRelatedField(
        queryset=Municipality.objects.all(),
        source="municipality",
        write_only=True,
    )

    class Meta(PanelUserCreateSerializer.Meta):
        fields = [*PanelUserCreateSerializer.Meta.fields, "municipality_id"]

    def get_municipality(self) -> Municipality:
        return self._municipality

    def create(self, validated_data: dict) -> User:
        self._municipality = validated_data.pop("municipality")
        return super().create(validated_data)


class MunicipalAgentCreateSerializer(AdminCreatesPanelUserSerializer):
    """Alta de un agente municipal, hecha por el admin de la plataforma."""

    role = User.Role.AGENTE_MUNICIPAL


class MunicipalAgentSerializer(serializers.ModelSerializer[User]):
    """Fila de la tabla de agentes municipales del panel de administración.

    Misma forma que ``ValidatorSerializer`` —estado, cifra de actividad y
    contraseña pendiente—, porque es el mismo tablero: alta, listado y baja
    lógica de una cuenta de trabajo.
    """

    municipality = MunicipalitySerializer(read_only=True)
    is_active_agent = serializers.BooleanField(
        source="is_work_account_active",
        read_only=True,
    )
    management_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "name",
            "email",
            "avatar",
            "municipality",
            "is_active_agent",
            "management_count",
            "must_change_password",
        ]
        read_only_fields = fields


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


class ValidatorCreateSerializer(PanelUserCreateSerializer):
    """Alta de un validador, hecha por el agente municipal (US-035).

    El agente no elige municipalidad: se le asigna la suya. Si el body trae una,
    se ignora — la jurisdicción se deriva siempre del usuario autenticado. Para
    el alta hecha por el admin, ver ``AdminValidatorCreateSerializer``.
    """

    role = User.Role.VALIDADOR

    def get_municipality(self) -> Municipality:
        return self.context["request"].user.municipality


class AdminValidatorCreateSerializer(AdminCreatesPanelUserSerializer):
    """Alta de un validador hecha por el admin de la plataforma.

    Mismo alta que la del agente, salvo de dónde sale la municipalidad: el admin
    no está acotado a ninguna, así que la elige y viaja en ``municipality_id``.
    """

    role = User.Role.VALIDADOR


class ValidatorSerializer(serializers.ModelSerializer[User]):
    """Fila de la tabla de validadores del panel.

    La municipalidad viaja siempre, aunque para el agente sea constante: es la
    que el admin necesita para distinguir filas de municipios distintos, y una
    sola forma de la respuesta es más fácil de sostener que dos.
    """

    validation_count = serializers.IntegerField(read_only=True)
    is_active_validator = serializers.BooleanField(
        source="is_work_account_active",
        read_only=True,
    )
    municipality = MunicipalitySerializer(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "name",
            "email",
            "avatar",
            "municipality",
            "is_active_validator",
            "validation_count",
            "must_change_password",
        ]
        read_only_fields = fields


class OperatorAreaFieldMixin(serializers.Serializer):
    """Resolución y validación del área operativa de un operario (US-044).

    Hereda de ``Serializer`` y no es una clase suelta: solo así el metaclass de
    DRF recoge ``operational_area_id`` como campo declarado. Sobre una clase
    plana, DRF lo construye desde el modelo como campo de solo lectura y el
    área nunca llega a ``validated_data``.

    Compartida por el alta y por el cambio de área: son la misma regla —el área
    tiene que estar activa y ser de la jurisdicción de quien opera— y si cada
    una la escribiera por su cuenta, terminarían divergiendo.

    El queryset arranca sin filtrar por estado a propósito: con
    ``OperationalArea.objects.active()`` un área desactivada respondería "no
    existe", y el escenario 4 pide decir que está desactivada.
    """

    operational_area_id = serializers.PrimaryKeyRelatedField(
        queryset=OperationalArea.objects.all(),
        source="operational_area",
        write_only=True,
    )

    def validate_operational_area_id(self, area: OperationalArea) -> OperationalArea:
        if not area.is_active:
            raise serializers.ValidationError(AREA_INACTIVE_MESSAGE)
        # La jurisdicción se comprueba acá y no con un queryset acotado por lo
        # mismo que arriba: un área de otro municipio tiene que fallar como
        # validación de campo con un motivo legible. El admin de la plataforma
        # no está acotado a ninguna, así que para él no hay nada que comparar.
        user = self.context["request"].user
        if user.municipality_id and area.municipality_id != user.municipality_id:
            raise serializers.ValidationError(AREA_FOREIGN_MESSAGE)
        return area


class OperatorCreateSerializer(OperatorAreaFieldMixin, PanelUserCreateSerializer):
    """Alta de un operario, hecha por el agente municipal (US-044).

    Reutiliza entero el circuito de invitación de US-035: contraseña temporal
    definida por quien da el alta y ``must_change_password`` hasta que el
    operario la cambie en su primer ingreso.

    La municipalidad **se deriva del área** y nunca se acepta del cliente, así
    que este alta no necesita la variante "el admin elige municipalidad" que sí
    tienen agentes y validadores: el admin elige el área, y el municipio viene
    con ella.
    """

    role = User.Role.OPERARIO

    # ``User.name`` es opcional a nivel de modelo —un vecino puede registrarse
    # sin nombre—, pero el alta de un operario no: quien mira la bandeja del
    # área tiene que saber a quién está dando de alta (US-044, escenario 2).
    name = serializers.CharField(
        required=True,
        allow_blank=False,
        error_messages={
            "required": NAME_REQUIRED_MESSAGE,
            "blank": NAME_REQUIRED_MESSAGE,
        },
    )
    phone = serializers.CharField(
        required=True,
        allow_blank=False,
        error_messages={
            "required": PHONE_REQUIRED_MESSAGE,
            "blank": PHONE_REQUIRED_MESSAGE,
        },
    )

    class Meta(PanelUserCreateSerializer.Meta):
        fields = [
            *PanelUserCreateSerializer.Meta.fields,
            "phone",
            "operational_area_id",
        ]

    def get_municipality(self) -> Municipality:
        return self._area.municipality

    def create(self, validated_data: dict) -> User:
        self._area = validated_data["operational_area"]
        return super().create(validated_data)


class OperatorSerializer(serializers.ModelSerializer[User]):
    """Fila de la tabla de operarios de un área (US-044).

    Misma forma que ``ValidatorSerializer`` —estado, cifra de actividad y
    contraseña pendiente—, porque es el mismo tablero, con el área y el teléfono
    de más.
    """

    municipality = MunicipalitySerializer(read_only=True)
    operational_area = OperationalAreaSerializer(read_only=True)
    is_active_operator = serializers.BooleanField(
        source="is_work_account_active",
        read_only=True,
    )
    closed_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "name",
            "email",
            "phone",
            "avatar",
            "municipality",
            "operational_area",
            "is_active_operator",
            "closed_count",
            "must_change_password",
        ]
        read_only_fields = fields


class OperatorUpdateSerializer(
    OperatorAreaFieldMixin,
    serializers.ModelSerializer[User],
):
    """Edición de un operario: datos de contacto y traslado de área.

    El email no se edita: es la identidad con la que inicia sesión. El rol y la
    municipalidad tampoco — esta última se deriva del área, así que cambiar de
    área dentro de la misma jurisdicción es lo único que la puede mover, y no
    la mueve.
    """

    phone = serializers.CharField(
        required=False,
        allow_blank=False,
        error_messages={"blank": PHONE_REQUIRED_MESSAGE},
    )
    # En la edición el área es opcional: se cambia el teléfono sin trasladar a
    # nadie. Cuando viaja, la valida el mixin igual que en el alta.
    operational_area_id = serializers.PrimaryKeyRelatedField(
        queryset=OperationalArea.objects.all(),
        source="operational_area",
        write_only=True,
        required=False,
    )

    class Meta:
        model = User
        fields = ["id", "name", "phone", "operational_area_id"]
        read_only_fields = ["id"]

    def update(self, instance: User, validated_data: dict) -> User:
        for field, value in validated_data.items():
            setattr(instance, field, value)
        # ``full_clean`` y no un ``save()`` pelado: es lo que vuelve a correr las
        # reglas del modelo —área obligatoria, área de la propia municipalidad—
        # sobre el estado resultante.
        instance.full_clean(exclude=["password"])
        instance.save()
        return instance
