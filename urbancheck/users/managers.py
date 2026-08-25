from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.db.models import Count
from django.db.models import Q
from django.db.models import QuerySet

if TYPE_CHECKING:
    from .models import User  # noqa: F401


class UserQuerySet(QuerySet):
    """Consultas de usuarios acotadas por jurisdicción (US-034)."""

    def for_user(self, user) -> UserQuerySet:
        """Usuarios de la municipalidad de ``user``.

        Mismo criterio y mismo default seguro que ``Report.objects.for_user``:
        sin municipalidad, ningún usuario.
        """
        municipality_id = getattr(user, "municipality_id", None)
        if not municipality_id:
            return self.none()
        return self.filter(municipality_id=municipality_id)

    def with_validation_count(self) -> UserQuerySet:
        """Anota cuántas validaciones en terreno ejecutó cada usuario.

        Se cuenta por el historial de estados: toda salida de «Pendiente de
        validación» hecha por el usuario es una validación o un rechazo. Va como
        anotación y no como consulta por fila para no producir un N+1 en la
        tabla del panel.
        """
        # Import local: ``reports`` importa ``users`` a través del modelo, así
        # que a nivel de módulo esto sería una dependencia circular.
        from urbancheck.reports.models import Report  # noqa: PLC0415

        return self.annotate(
            validation_count=Count(
                "reportstatushistory",
                filter=Q(
                    reportstatushistory__previous_status=(
                        Report.Status.PENDIENTE_VALIDACION
                    ),
                ),
                distinct=True,
            ),
        )


class UserManager(DjangoUserManager["User"].from_queryset(UserQuerySet)):
    """Custom manager for the User model."""

    def _create_user(self, email: str, password: str | None, **extra_fields):
        """
        Create and save a user with the given email and password.
        """
        if not email:
            msg = "The given email must be set"
            raise ValueError(msg)
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.password = make_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra_fields):  # type: ignore[override]
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email: str, password: str | None = None, **extra_fields):  # type: ignore[override]
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            msg = "Superuser must have is_staff=True."
            raise ValueError(msg)
        if extra_fields.get("is_superuser") is not True:
            msg = "Superuser must have is_superuser=True."
            raise ValueError(msg)

        return self._create_user(email, password, **extra_fields)
