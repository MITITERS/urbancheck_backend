from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
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

from .permissions import IsPanelUser
from .permissions import IsPlatformAdmin
from .serializers import AdminValidatorCreateSerializer
from .serializers import MunicipalAgentCreateSerializer
from .serializers import MunicipalAgentSerializer
from .serializers import PublicUserSerializer
from .serializers import UserSerializer
from .serializers import ValidatorCreateSerializer
from .serializers import ValidatorSerializer

# Acciones que escriben sobre el usuario: siempre acotadas al propio.
WRITE_ACTIONS = frozenset({"update", "partial_update"})

# Filtro por estado de la cuenta de trabajo: ``?state=active|inactive``. El
# panel lo usa para separar en dos pestañas las cuentas habilitadas de las
# archivadas, de modo que las dadas de baja no viajen siquiera en la respuesta
# del listado principal.
STATE_PARAM = "state"
STATE_ACTIVE = "active"
STATE_INACTIVE = "inactive"


INACTIVE_MUNICIPALITY_MESSAGE = (
    "No se puede reactivar esta cuenta: su municipalidad está dada de baja. "
    "Volvé a darla de alta primero."
)

MUNICIPALITY_PARAM = "municipality"


def ensure_can_be_reactivated(user) -> None:
    """Frena la reactivación de una cuenta sin municipalidad activa.

    Vale para las dos pantallas: la regla es de la cuenta de trabajo, no de un
    endpoint. Responde ``400`` y no ``403`` porque a quien la ejecuta no le
    falta permiso —es el admin, o el agente de esa jurisdicción—; lo que falta
    es una condición del dato.
    """
    if not user.can_be_reactivated:
        raise ValidationError({"detail": INACTIVE_MUNICIPALITY_MESSAGE})


def filter_by_municipality(queryset, query_params):
    """Acota por ``?municipality=<id>``. Solo tiene sentido para el admin.

    Un valor que no sea un id se ignora, igual que el estado: un parámetro mal
    escrito en la URL no tiene por qué tumbar el listado. Sin esta guarda,
    ``filter(municipality_id="abc")`` es un ``500``.
    """
    municipality = query_params.get(MUNICIPALITY_PARAM)
    if not municipality or not municipality.isdigit():
        return queryset
    return queryset.filter(municipality_id=municipality)


def filter_by_state(queryset, query_params):
    """Acota por ``?state=``. Un valor desconocido no filtra ni rompe.

    Sin el parámetro devuelve las dos, que es lo que hacía antes de existir: un
    cliente que no lo manda sigue viendo el listado completo.
    """
    state = query_params.get(STATE_PARAM)
    if state == STATE_ACTIVE:
        return queryset.filter(is_work_account_active=True)
    if state == STATE_INACTIVE:
        return queryset.filter(is_work_account_active=False)
    return queryset


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
    """Alta, listado y baja lógica de agentes municipales (US-017).

    Restringido al administrador de la plataforma: es quien habilita a cada
    municipio a operar el panel, y el único que puede dejar de habilitarlo.

    Es el mismo tablero que el de validadores, con una diferencia de alcance:
    al validador lo gestionan los dos roles del panel, cada uno en su
    jurisdicción; al agente solo el admin, que no está acotado a ninguna.
    """

    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def get_queryset(self):
        queryset = (
            User.objects.filter(role=User.Role.AGENTE_MUNICIPAL)
            .select_related("municipality")
            .with_management_count()
            .order_by("name", "email")
        )
        # Solo en el listado: activar y desactivar tienen que poder alcanzar a
        # la cuenta esté del lado que esté, o reactivar desde el archivado
        # respondería 404.
        if self.action == "list":
            params = self.request.query_params
            queryset = filter_by_municipality(queryset, params)
            queryset = filter_by_state(queryset, params)
        return queryset

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
        # Se relee por el queryset anotado, como en el alta de validadores:
        # ``management_count`` es una anotación, y un campo read_only sin
        # atributo lo omite DRF en silencio en vez de fallar.
        agent = self.get_queryset().get(pk=agent.pk)
        return Response(
            self._read_serializer(agent, request).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        """Baja lógica: el agente deja de operar el panel, y nada más.

        No se borra el registro ni se le cierra la cuenta: puede iniciar sesión
        —el panel se lo dice y lo deja salir— y todo lo que gestionó sigue en el
        historial de cada reporte, con su nombre.
        """
        return self._set_agent_active(request, active=False)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        """Reactiva al agente, si su municipalidad sigue en pie."""
        return self._set_agent_active(request, active=True)

    def _set_agent_active(self, request, *, active: bool) -> Response:
        agent = self.get_object()
        if active:
            ensure_can_be_reactivated(agent)
        agent.is_work_account_active = active
        agent.save(update_fields=["is_work_account_active"])
        agent = self.get_queryset().get(pk=agent.pk)
        return Response(self._read_serializer(agent, request).data)

    def _read_serializer(self, agent, request) -> MunicipalAgentSerializer:
        return MunicipalAgentSerializer(agent, context={"request": request})


class ValidatorViewSet(CreateModelMixin, ListModelMixin, GenericViewSet):
    """Gestión de validadores, por el agente municipal (US-035) o por el admin.

    Los dos hacen lo mismo; lo único que cambia es el alcance y de dónde sale la
    municipalidad:

    - El **agente** pasa por la capa de jurisdicción de US-034: solo ve —y solo
      puede activar o desactivar— validadores de su propia municipalidad, y las
      altas se le asignan a esa municipalidad sin poder elegir.
    - El **admin de la plataforma** no está acotado a ningún municipio: ve
      todos, puede filtrar por ``?municipality=<id>`` y elige la municipalidad
      en cada alta.

    Un ciudadano o un validador autenticado recibe ``403`` por ``IsPanelUser``.
    """

    permission_classes = [IsAuthenticated, IsPanelUser]

    def get_queryset(self):
        user = self.request.user
        qs = User.objects.filter(role=User.Role.VALIDADOR)
        if user.is_platform_admin:
            qs = filter_by_municipality(qs, self.request.query_params)
        else:
            qs = qs.for_user(user)
        qs = (
            qs.select_related("municipality")
            .with_validation_count()
            .order_by("name", "email")
        )
        if self.action == "list":
            qs = filter_by_state(qs, self.request.query_params)
        return qs

    def get_serializer_class(self):
        if self.action != "create":
            return ValidatorSerializer
        # De dónde sale la municipalidad depende de quién da el alta: el agente
        # tiene la suya, el admin la elige.
        if self.request.user.is_platform_admin:
            return AdminValidatorCreateSerializer
        return ValidatorCreateSerializer

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
        """Reactiva al validador, si su municipalidad sigue en pie."""
        return self._set_validator_active(request, active=True)

    def _set_validator_active(self, request, *, active: bool) -> Response:
        validator = self.get_object()
        if active:
            ensure_can_be_reactivated(validator)
        validator.is_work_account_active = active
        validator.save(update_fields=["is_work_account_active"])
        validator = self.get_queryset().get(pk=validator.pk)
        return Response(self._read_serializer(validator, request).data)

    def _read_serializer(self, validator, request) -> ValidatorSerializer:
        return ValidatorSerializer(validator, context={"request": request})
