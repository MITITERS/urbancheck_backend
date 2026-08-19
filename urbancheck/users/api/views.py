from rest_framework import status
from rest_framework.decorators import action
from rest_framework.mixins import ListModelMixin
from rest_framework.mixins import RetrieveModelMixin
from rest_framework.mixins import UpdateModelMixin
from rest_framework.parsers import JSONParser
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from urbancheck.users.models import User

from .serializers import PublicUserSerializer
from .serializers import UserSerializer

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
