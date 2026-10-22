from django.forms import BooleanField
from django.forms import CharField
from django.forms import Form
from django.forms import ValidationError
from django.utils import timezone

from .models import TermsOfService

TERMS_REQUIRED_MESSAGE = (
    "Para crear la cuenta tenés que aceptar los términos y condiciones."
)
TERMS_OUTDATED_MESSAGE = (
    "Los términos y condiciones cambiaron mientras te registrabas. "
    "Leé la versión nueva y aceptala."
)


class HeadlessUserSignupForm(Form):
    name = CharField(max_length=255, required=True)
    # Aceptación de los términos (RN-10, C-23). Se pide la versión además del
    # sí: si se publica una nueva mientras alguien completa el registro, aceptó
    # un texto que ya no es el vigente. Sin términos publicados no se exige.
    accept_terms = BooleanField(required=False)
    terms_version = CharField(max_length=20, required=False)

    def clean(self):
        cleaned = super().clean()
        self._terms = TermsOfService.objects.current()
        if self._terms is None:
            return cleaned
        if not cleaned.get("accept_terms"):
            raise ValidationError({"accept_terms": TERMS_REQUIRED_MESSAGE})
        if cleaned.get("terms_version") != self._terms.version:
            raise ValidationError({"terms_version": TERMS_OUTDATED_MESSAGE})
        return cleaned

    def signup(self, request, user):
        user.name = self.cleaned_data["name"]
        fields = ["name"]
        if self._terms is not None:
            user.terms_version = self._terms.version
            user.terms_accepted_at = timezone.now()
            fields += ["terms_version", "terms_accepted_at"]
        user.save(update_fields=fields)
