from django.contrib import admin
from .models import Film, UserFilm

# Register your models here.

@admin.register(Film)
class FilmAdmin(admin.ModelAdmin):
    list_display = ("title", "year")
    search_fields = ("title",)


@admin.register(UserFilm)
class UserFilmAdmin(admin.ModelAdmin):
    list_display = ("user", "film", "position", "watched_at", "created_at")
    list_filter = ("user",)
    search_fields = ("film__title", "user__username")