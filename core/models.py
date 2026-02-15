from django.conf import settings
from django.db import models

import math

# Create your models here.

PREFERENCE_CHOICES = [
    ("liked", "I liked it"),
    ("ok", "It was ok"),
    ("disliked", "I didn't like it")
]

class Film(models.Model):
    title = models.CharField(max_length=255)
    year = models.PositiveIntegerField(blank=True, null=True)
    tmdb_id = models.PositiveIntegerField(blank=True, null=True)
    poster_path = models.CharField(max_length=255, blank=True, null=True)
    director = models.CharField(max_length=255, blank=True, null=True)

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
    tmdb_id = models.PositiveIntegerField(blank=True, null=True)
    poster_path = models.CharField(max_length=255, blank=True, null=True)
    position = models.PositiveIntegerField(default=0)  # will use this for ranking later
    watched_at = models.DateField(blank=True, null=True)
    elo = models.FloatField(default=1500.0)
    bt = models.FloatField(default=0.0)
    preference = models.CharField(
        max_length=10,
        choices=PREFERENCE_CHOICES,
        blank=True,
        null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def score10(self):
        """
        Logistic mapping of Elo to 0–10.
        1500 → 5.00
        """
        midpoint = 1500.0
        scale = 200.0

        x = (self.elo - midpoint) / scale
        score = 10.0 / (1.0 + math.exp(-x))
        return round(score, 2)

    class Meta:
        unique_together = ("user", "film")
        ordering = ["position", "-created_at"]

    def __str__(self):
        return f"{self.user.username} · {self.film} (#{self.position})"
    
class PairwiseComparison(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    winner = models.ForeignKey("Film", on_delete=models.CASCADE, related_name="wins")
    loser  = models.ForeignKey("Film", on_delete=models.CASCADE, related_name="losses")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["user", "winner", "loser"]),
        ]