from rest_framework import status
from rest_framework.decorators import action
from rest_framework.mixins import CreateModelMixin
from rest_framework.mixins import ListModelMixin
from rest_framework.mixins import RetrieveModelMixin
from rest_framework.mixins import UpdateModelMixin
from rest_framework.parsers import JSONParser
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from urbancheck.users.models import User

from .permissions import IsMunicipalAgent
from .permissions import IsPlatformAdmin
from .serializers import MunicipalAgentCreateSerializer
from .serializers import MunicipalAgentSerializer
from .serializers import PublicUserSerializer
from .serializers import UserSerializer
from .serializers import ValidatorCreateSerializer
from .serializers import ValidatorSerializer

# Acciones que escriben sobre el usuario: siempre acotadas al propio.
WRITE_ACTIONS = frozenset({"update", "partial_update"})


class UserViewSet(RetrieveModelMixin, ListModelMixin, UpdateModelMixin, GenericViewSet):
    serializer_class = UserSerializer
    queryset = User.objects.all()
    lookup_field = "pk"

    def get_queryset(self, *args, **kwargs):
        # El detalle es público (US-027), pero editar sigue siendo solo sobre uno
        # mismo: acotamos el queryset en lugar de sumar un permiso de objeto.
        if getattr(self, "action", None) in WRITE_ACTIONS:
            return self.queryset.filter(id=self.request.user.id)
        return self.queryset

    def get_serializer_class(self):
        if getattr(self, "action", None) == "retrieve":
            return PublicUserSerializer
        return UserSerializer

    def retrieve(self, request, *args, **kwargs):
        """Perfil público, salvo que sea el propio (ahí devolvemos todo)."""
        instance = self.get_object()
        if instance.id == request.user.id:
            serializer = UserSerializer(instance, context={"request": request})
        else:
            serializer = PublicUserSerializer(instance, context={"request": request})
        return Response(serializer.data)

    @action(
        detail=False,
        methods=["get", "patch"],
        parser_classes=[MultiPartParser, JSONParser],
    )
    def me(self, request):
        if request.method == "PATCH":
            serializer = UserSerializer(
                request.user,
                data=request.data,
                partial=True,
                context={"request": request},
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(status=status.HTTP_200_OK, data=serializer.data)
        serializer = UserSerializer(request.user, context={"request": request})
        return Response(status=status.HTTP_200_OK, data=serializer.data)


class MunicipalAgentViewSet(CreateModelMixin, ListModelMixin, GenericViewSet):
    """Alta y listado de agentes municipales (US-017).

    Restringido al administrador de la plataforma: es quien habilita a cada
    municipio a operar el panel.
    """

    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    queryset = (
        User.objects.filter(role=User.Role.AGENTE_MUNICIPAL)
        .select_related("municipality")
        .order_by("name", "email")
    )

    def get_serializer_class(self):
        if self.action == "create":
            return MunicipalAgentCreateSerializer
        return MunicipalAgentSerializer

    def create(self, request, *args, **kwargs):
        """Responde con el agente ya serializado para lectura.

        El serializer de alta es de escritura (recibe la contraseña temporal),
        así que la respuesta usa el de lectura y nunca devuelve la contraseña.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        agent = serializer.save()
        return Response(
            MunicipalAgentSerializer(agent, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class ValidatorViewSet(CreateModelMixin, ListModelMixin, GenericViewSet):
    """Gestión de validadores por parte del agente municipal (US-035).

    El listado pasa por la capa de jurisdicción de US-034: un agente solo ve
    —y solo puede activar o desactivar— validadores de su propia municipalidad.
    """

    permission_classes = [IsAuthenticated, IsMunicipalAgent]

    def get_queryset(self):
        return (
            User.objects.filter(role=User.Role.VALIDADOR)
            .for_user(self.request.user)
            .with_validation_count()
            .order_by("name", "email")
        )

    def get_serializer_class(self):
        if self.action == "create":
            return ValidatorCreateSerializer
        return ValidatorSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validator = serializer.save()
        # Se relee por el queryset anotado: ``validation_count`` viene de una
        # anotación y sobre la instancia recién creada no existiría. DRF omite
        # en silencio un campo read_only sin atributo, así que el bug no
        # avisaría.
        validator = self.get_queryset().get(pk=validator.pk)
        return Response(
            self._read_serializer(validator, request).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        """Baja lógica: el validador conserva su acceso como ciudadano común.

        No se borra el registro ni se desactiva la cuenta entera, y el historial
        de validaciones ya ejecutadas queda intacto.
        """
        return self._set_validator_active(request, active=False)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        return self._set_validator_active(request, active=True)

    def _set_validator_active(self, request, *, active: bool) -> Response:
        validator = self.get_object()
        validator.is_validator_active = active
        validator.save(update_fields=["is_validator_active"])
        validator = self.get_queryset().get(pk=validator.pk)
        return Response(self._read_serializer(validator, request).data)

    def _read_serializer(self, validator, request) -> ValidatorSerializer:
        return ValidatorSerializer(validator, context={"request": request})
