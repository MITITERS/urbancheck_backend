
from typing import ClassVar

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import BooleanField
from django.db.models import CharField
from django.db.models import EmailField
from django.db.models import ForeignKey
from django.db.models import ImageField
from django.db.models import TextChoices
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from urbancheck.municipalities.models import PHONE_INVALID_MESSAGE
from urbancheck.municipalities.models import PHONE_REGEX

from .managers import UserManager


class User(AbstractUser):
    """
    Default custom user model for UrbanCheck.
    If adding fields that need to be filled at user signup,
    check forms.SignupForm and forms.SocialSignupForms accordingly.
    """

    class Role(TextChoices):
        """Los cinco roles de la plataforma (US-017, ampliado por US-044).

        ``ADMIN_PLATAFORMA`` y ``AGENTE_MUNICIPAL`` operan el panel web;
        ``VALIDADOR``, ``OPERARIO`` y ``CIUDADANO`` usan la app móvil. El valor
        ``municipal`` de la iteración anterior se migró a ``agente_municipal``.
        """

        CIUDADANO = "ciudadano", _("Ciudadano")
        ADMIN_PLATAFORMA = "admin_plataforma", _("Administrador de la plataforma")
        AGENTE_MUNICIPAL = "agente_municipal", _("Agente municipal")
        VALIDADOR = "validador", _("Validador")
        OPERARIO = "operario", _("Operario")

    #: Roles que tienen acceso al panel web municipal.
    PANEL_ROLES = frozenset({Role.ADMIN_PLATAFORMA, Role.AGENTE_MUNICIPAL})

    #: Roles que deben pertenecer sí o sí a una municipalidad. El operario la
    #: hereda de su área operativa y no la elige (US-044).
    MUNICIPALITY_BOUND_ROLES = frozenset(
        {Role.AGENTE_MUNICIPAL, Role.VALIDADOR, Role.OPERARIO},
    )

    #: Cuentas de trabajo: operan el circuito en vez de usarlo como vecinos.
    #: Quien además quiera reportar se crea una cuenta personal. Es el
    #: complemento exacto de ``CIUDADANO``, y se declara por extensión a
    #: propósito: agregar un rol nuevo obliga a decidir de qué lado cae.
    WORK_ROLES = frozenset(
        {
            Role.ADMIN_PLATAFORMA,
            Role.AGENTE_MUNICIPAL,
            Role.VALIDADOR,
            Role.OPERARIO,
        },
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
    # Baja lógica de una cuenta de trabajo. Es independiente de ``is_active`` de
    # Django a propósito: la cuenta sigue existiendo y pudiendo iniciar sesión,
    # y lo que pierde es la capacidad de trabajar —validar en terreno, u operar
    # el panel—, no el acceso. Lo que un validador dado de baja no recupera es
    # reportar: eso lo decide el rol, no esta bandera.
    #
    # Es una sola bandera para los dos roles a propósito: la pregunta que
    # responde es la misma —"¿esta cuenta de trabajo sigue habilitada?"— y dos
    # campos habrían divergido. Quién puede darla de baja sí cambia: al
    # validador lo dan de baja los dos roles del panel (US-035), y al agente
    # municipal solo el administrador de la plataforma (US-017).
    is_work_account_active = BooleanField(
        _("work account active"),
        default=True,
        help_text=_("Solo aplica a validadores, operarios y agentes municipales."),
    )
    # Contraseña temporal entregada en el alta: mientras esté en True el usuario
    # solo puede cambiar su contraseña.
    must_change_password = BooleanField(
        _("must change password"),
        default=False,
        help_text=_("El usuario todavía usa la contraseña temporal del alta."),
    )
    # Teléfono de contacto. Obligatorio en el alta de un operario (US-044) y
    # vacío para el resto: nadie más lo carga hoy, así que el campo es opcional
    # a nivel de modelo y la obligatoriedad la impone el serializer del alta.
    phone = CharField(
        _("phone"),
        max_length=30,
        blank=True,
        default="",
        validators=[RegexValidator(regex=PHONE_REGEX, message=PHONE_INVALID_MESSAGE)],
    )
    # Área operativa del operario (US-044). Es obligatoria para ese rol y nula
    # para todos los demás: la municipalidad se deriva del área y nunca se
    # acepta como parámetro del cliente.
    #
    # ``PROTECT`` y no ``SET_NULL``: un operario sin área no puede existir, así
    # que borrar el área tendría que dejarlo en un estado inválido. Las áreas no
    # se borran —se desactivan—, de modo que este candado no estorba a nadie.
    operational_area = ForeignKey(
        "municipalities.OperationalArea",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="operators",
        verbose_name=_("operational area"),
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
                        "Un agente municipal, validador u operario debe pertenecer "
                        "a una municipalidad.",
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
        self._clean_operational_area()

    def _clean_operational_area(self) -> None:
        """El área operativa es del operario, y solo de él (US-044).

        Las tres reglas van juntas porque son la misma: un operario existe
        dentro de un área, cualquier otro rol no tiene ninguna, y el área
        pertenece a la municipalidad del usuario. Si vivieran en el serializer
        del alta, un cambio de área hecho desde el shell o desde el admin de
        Django podría dejar a un operario mirando la bandeja de otro municipio.
        """
        if self.role == self.Role.OPERARIO and self.operational_area_id is None:
            raise ValidationError(
                {
                    "operational_area": _(
                        "Un operario debe pertenecer a un área operativa.",
                    ),
                },
            )
        if self.role != self.Role.OPERARIO and self.operational_area_id:
            raise ValidationError(
                {
                    "operational_area": _(
                        "Solo un operario puede pertenecer a un área operativa.",
                    ),
                },
            )
        if (
            self.operational_area_id
            and self.operational_area.municipality_id != self.municipality_id
        ):
            raise ValidationError(
                {
                    "operational_area": _(
                        "El área operativa pertenece a otra municipalidad.",
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
            and self.is_work_account_active
            and not self.must_change_password
        )

    @property
    def is_operator(self) -> bool:
        return self.role == self.Role.OPERARIO

    @property
    def can_work_as_operator(self) -> bool:
        """Única verificación de acceso del operario a su bandeja (US-045).

        Espejo de ``can_operate_panel``, con una condición más: además del rol y
        de la baja lógica de la cuenta, el área tiene que seguir operativa. Un
        operario cuya dependencia fue desactivada no tiene trabajo que mirar, y
        el escenario 9 de US-044 pide que se lo diga en lugar de mostrarle una
        bandeja vacía.

        La contraseña temporal **no** entra acá, por lo mismo que en el panel:
        el operario tiene que poder entrar justamente para cambiarla, y la app
        lo manda a esa pantalla mirando ``must_change_password``.
        """
        return (
            self.is_operator
            and self.is_work_account_active
            and self.operational_area is not None
            and self.operational_area.is_active
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
    def can_be_reactivated(self) -> bool:
        """Si su cuenta de trabajo se puede volver a habilitar.

        No alcanza con que alguien apriete el botón: la cuenta trabaja **para**
        una municipalidad, así que mientras esa municipalidad esté dada de baja
        no hay nada que habilitar. Es el complemento de la baja en cascada de
        ``deactivate_municipality()``: si la baja del municipio archiva a su
        personal, reactivar a una persona sin reactivar el municipio dejaría
        justo el estado que esa cascada existe para evitar.
        """
        return self.municipality is not None and self.municipality.is_active

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
        """Su rol es de panel.

        **No** alcanza para operarlo: eso lo decide ``can_operate_panel``, que
        además mira la baja lógica.
        """
        return self.role in self.PANEL_ROLES or self.is_superuser

    @property
    def can_operate_panel(self) -> bool:
        """Única verificación de acceso al panel municipal (US-017).

        Espejo exacto de ``can_validate``: primero el rol, después la baja
        lógica. Un agente dado de baja conserva la cuenta y puede iniciar
        sesión, pero el panel no le responde nada.

        La contraseña temporal **no** entra acá, a diferencia de la validación:
        el agente tiene que poder entrar justamente para cambiarla. Ese redirect
        lo resuelve el panel con ``must_change_password``.
        """
        return self.is_panel_user and self.is_work_account_active

    def get_absolute_url(self) -> str:
        """Get URL for user's detail view.

        Returns:
            str: URL for user detail.

        """
        return reverse("users:detail", kwargs={"pk": self.id})
