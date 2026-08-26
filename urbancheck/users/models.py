
from typing import ClassVar

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import BooleanField
from django.db.models import CharField
from django.db.models import EmailField
from django.db.models import ForeignKey
from django.db.models import ImageField
from django.db.models import TextChoices
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from .managers import UserManager


class User(AbstractUser):
    """
    Default custom user model for UrbanCheck.
    If adding fields that need to be filled at user signup,
    check forms.SignupForm and forms.SocialSignupForms accordingly.
    """

    class Role(TextChoices):
        """Los cuatro roles de la plataforma (US-017).

        ``ADMIN_PLATAFORMA`` y ``AGENTE_MUNICIPAL`` operan el panel web;
        ``VALIDADOR`` y ``CIUDADANO`` usan la app móvil. El valor ``municipal``
        de la iteración anterior se migró a ``agente_municipal``.
        """

        CIUDADANO = "ciudadano", _("Ciudadano")
        ADMIN_PLATAFORMA = "admin_plataforma", _("Administrador de la plataforma")
        AGENTE_MUNICIPAL = "agente_municipal", _("Agente municipal")
        VALIDADOR = "validador", _("Validador")

    #: Roles que tienen acceso al panel web municipal.
    PANEL_ROLES = frozenset({Role.ADMIN_PLATAFORMA, Role.AGENTE_MUNICIPAL})

    #: Roles que deben pertenecer sí o sí a una municipalidad.
    MUNICIPALITY_BOUND_ROLES = frozenset({Role.AGENTE_MUNICIPAL, Role.VALIDADOR})

    #: Cuentas de trabajo: operan el circuito en vez de usarlo como vecinos.
    #: Quien además quiera reportar se crea una cuenta personal. Es el
    #: complemento exacto de ``CIUDADANO``, y se declara por extensión a
    #: propósito: agregar un rol nuevo obliga a decidir de qué lado cae.
    WORK_ROLES = frozenset(
        {Role.ADMIN_PLATAFORMA, Role.AGENTE_MUNICIPAL, Role.VALIDADOR},
    )

    # First and last name do not cover name patterns around the globe
    name = CharField(_("Name of User"), blank=True, max_length=255)
    first_name = None  # type: ignore[assignment]
    last_name = None  # type: ignore[assignment]
    email = EmailField(_("email address"), unique=True)
    username = None  # type: ignore[assignment]
    role = CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.CIUDADANO,
    )
    # Jurisdicción del usuario. Obligatoria para agentes y validadores, nula
    # para ciudadanos y para el administrador de la plataforma, que no está
    # acotado a un municipio. Una vez asignada no se modifica (US-017).
    municipality = ForeignKey(
        "municipalities.Municipality",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="users",
        verbose_name=_("municipality"),
    )
    # Baja lógica del validador (US-035). Es independiente de ``is_active`` de
    # Django a propósito: el validador dado de baja sigue entrando a la app y
    # consultando reportes, solo pierde la capacidad de validar. Lo que no
    # recupera es reportar: eso lo decide el rol, no esta bandera (ver
    # ``can_create_reports``).
    is_validator_active = BooleanField(
        _("validator active"),
        default=True,
        help_text=_("Solo aplica a usuarios con rol Validador."),
    )
    # Contraseña temporal entregada en el alta: mientras esté en True el usuario
    # solo puede cambiar su contraseña.
    must_change_password = BooleanField(
        _("must change password"),
        default=False,
        help_text=_("El usuario todavía usa la contraseña temporal del alta."),
    )
    avatar = ImageField(upload_to="avatars/", blank=True)
    # Perfil público: si es False, otros usuarios solo ven nombre y avatar.
    is_public = BooleanField(
        _("public profile"),
        default=True,
        help_text=_(
            "Si se desactiva, otros usuarios no ven tus reportes ni tus estadísticas.",
        ),
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects: ClassVar[UserManager] = UserManager()

    def clean(self) -> None:
        """La regla de municipalidad por rol vive acá, no solo en el serializer.

        Así ningún alta —admin de Django, shell, comando de management— puede
        crear un agente sin jurisdicción o un ciudadano con una asignada.
        """
        super().clean()
        if self.role in self.MUNICIPALITY_BOUND_ROLES and self.municipality_id is None:
            raise ValidationError(
                {
                    "municipality": _(
                        "Un agente municipal o validador debe pertenecer a una "
                        "municipalidad.",
                    ),
                },
            )
        if self.role not in self.MUNICIPALITY_BOUND_ROLES and self.municipality_id:
            raise ValidationError(
                {
                    "municipality": _(
                        "Este rol no puede estar asociado a una municipalidad.",
                    ),
                },
            )

    @property
    def is_platform_admin(self) -> bool:
        """El superusuario cuenta como admin de plataforma.

        Es lo que hace arrancable el sistema: la primera municipalidad la crea
        el superusuario creado por ``createsuperuser``, antes de que exista
        ningún usuario con el rol.
        """
        return self.role == self.Role.ADMIN_PLATAFORMA or self.is_superuser

    @property
    def is_municipal_agent(self) -> bool:
        return self.role == self.Role.AGENTE_MUNICIPAL

    @property
    def can_validate(self) -> bool:
        """Única verificación de capacidad de validación (US-035).

        La consumen la acción de validar en terreno (US-036) y la bandeja de
        pendientes (US-037): tiene que vivir en un solo lugar o las dos van a
        divergir. Son tres condiciones y las tres importan: el rol, la baja
        lógica y que ya haya cambiado la contraseña temporal del alta.
        """
        return (
            self.role == self.Role.VALIDADOR
            and self.is_validator_active
            and not self.must_change_password
        )

    @property
    def participates_as_citizen(self) -> bool:
        """Si puede participar como vecino: reportar, comentar y dar me gusta.

        Solo el vecino participa. Las cuentas de trabajo operan el circuito: el
        validador verifica en terreno lo que reportan los vecinos, el agente lo
        gestiona desde el panel y el administrador opera la plataforma. Un
        reporte, un comentario o un me gusta propios los pondrían de los dos
        lados del mismo caso, y sobre un reporte que además van a resolver, un
        comentario del municipio no se distingue del de un vecino. Quien además
        quiera usar UrbanCheck como vecino se crea una cuenta personal, igual
        que en ``sees_only_own_municipality``.

        Las tres acciones comparten una sola verificación a propósito: son la
        misma pregunta, y separarlas era garantizar que se fueran divergiendo.
        Leer no está alcanzado: el personal municipal sigue viendo el feed, el
        detalle y los comentarios de su jurisdicción.

        Es una regla del rol y no del estado de la cuenta: el validador dado de
        baja tampoco participa, porque la cuenta sigue siendo de trabajo.
        """
        return self.role not in self.WORK_ROLES

    @property
    def sees_only_own_municipality(self) -> bool:
        """Si la app le muestra únicamente reportes de su jurisdicción.

        El validador y el agente son personal municipal, no vecinos con un
        permiso extra: su cuenta es de trabajo y no ve nada de otros municipios,
        ni en la app ni en el panel. Quien además quiera usar UrbanCheck como
        ciudadano se crea una cuenta personal.

        Son exactamente los roles atados a una municipalidad: el administrador
        de la plataforma también es cuenta de trabajo, pero no está acotado a
        ningún municipio, así que esta regla no lo alcanza.
        """
        return self.role in self.MUNICIPALITY_BOUND_ROLES

    @property
    def sees_every_municipality(self) -> bool:
        """Si el panel le muestra los datos de todas las jurisdicciones.

        Es la excepción a ``JurisdictionScopedMixin``, y la única: el
        administrador de la plataforma la opera entera, así que acotarlo a un
        municipio no tendría a cuál. Vive acá y no en el mixin para que la lista
        de quién cruza jurisdicciones sea una sola y se lea de un vistazo.

        Es el complemento de ``sees_only_own_municipality`` dentro del panel:
        el agente ve lo suyo, el admin ve todo.
        """
        return self.is_platform_admin

    @property
    def is_panel_user(self) -> bool:
        """Puede acceder al panel web municipal."""
        return self.role in self.PANEL_ROLES or self.is_superuser

    def get_absolute_url(self) -> str:
        """Get URL for user's detail view.

        Returns:
            str: URL for user detail.

        """
        return reverse("users:detail", kwargs={"pk": self.id})
