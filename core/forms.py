from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User
from .models import Film, UserFilm


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add a shared CSS class to all fields
        for field in self.fields.values():
            field.widget.attrs.update({
                "class": "form-input",
            })


class LoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({
                "class": "form-input",
            })

class AddFilmForm(forms.Form):
    title = forms.CharField(max_length=255, label="Film title")
    year = forms.IntegerField(required=False, label="Year (optional)")
    watched_at = forms.DateField(
        required=False,
        label="Date watched (optional)",
        widget=forms.DateInput(attrs={"type": "date"})
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({"class": "form-input"})

    def clean_year(self):
        year = self.cleaned_data.get("year")
        if year and (year < 1888 or year > 3000):
            raise forms.ValidationError("Please enter a realistic year.")
        return year

    def save(self):
        """
        Returns the UserFilm instance for this user + film.
        For now, we just append to the end of the list.
        Later, we’ll insert with ranking logic.
        """
        title = self.cleaned_data["title"].strip()
        year = self.cleaned_data.get("year")
        watched_at = self.cleaned_data.get("watched_at")

        film, _ = Film.objects.get_or_create(title=title, year=year)

        # Determine the next position (append to end)
        last_entry = (
            UserFilm.objects.filter(user=self.user)
            .order_by("-position")
            .first()
        )
        next_position = (last_entry.position + 1) if last_entry else 1

        user_film, created = UserFilm.objects.get_or_create(
            user=self.user,
            film=film,
            defaults={
                "position": next_position,
                "watched_at": watched_at,
            },
        )

        if not created:
            # If it already existed, we might update watched_at
            if watched_at:
                user_film.watched_at = watched_at
                user_film.save()

        return user_film