from django.forms import CharField, Form


class HeadlessUserSignupForm(Form):
    name = CharField(max_length=255, required=True)

    def signup(self, request, user):
        user.name = self.cleaned_data["name"]
        user.save(update_fields=["name"])
