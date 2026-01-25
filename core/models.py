from django.conf import settings
from django.db import models

# Create your models here.

class Film(models.Model):
    title = models.CharField(max_length=255)
    year = models.PositiveIntegerField(blank=True, null=True)

    # optional fields for later expansion
    # external_id = models.CharField(max_length=100, blank=True, null=True)  # e.g. TMDB/IMDB
    # poster_url = models.URLField(blank=True, null=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        if self.year:
            return f"{self.title} ({self.year})"
        return self.title


class UserFilm(models.Model):
    """
    A film in a given user's personal list.
    'position' will eventually represent ranking order (1 = top of list).
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    film = models.ForeignKey(Film, on_delete=models.CASCADE)
    position = models.PositiveIntegerField(default=0)  # will use this for ranking later
    watched_at = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "film")
        ordering = ["position", "-created_at"]

    def __str__(self):
        return f"{self.user.username} · {self.film} (#{self.position})"