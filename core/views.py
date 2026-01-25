from django.shortcuts import render
from django.contrib import messages
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404

from .forms import SignUpForm, LoginForm, AddFilmForm
from .models import UserFilm

# Create your views here.
def landing_page(request):
    return render(request, "core/landing.html")

def signup(request):
    if request.user.is_authenticated:
        return redirect("landing")

    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            auth_login(request, user)
            messages.success(request, "Welcome! Your account has been created.")
            return redirect("landing")
    else:
        form = SignUpForm()

    return render(request, "core/signup.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("landing")

    if request.method == "POST":
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            auth_login(request, user)
            messages.success(request, "Signed in successfully.")
            return redirect("landing")
    else:
        form = LoginForm(request)

    return render(request, "core/login.html", {"form": form})


@login_required
def logout_view(request):
    auth_logout(request)
    messages.info(request, "You’ve been signed out.")
    return redirect("landing")

@login_required
def film_list(request):
    films = UserFilm.objects.filter(user=request.user).select_related("film")
    return render(request, "core/film_list.html", {"user_films": films})


@login_required
def add_film(request):
    if request.method == "POST":
        form = AddFilmForm(request.user, request.POST)
        if form.is_valid():
            user_film = form.save()
            user_film_count = UserFilm.objects.filter(user = request.user).count()
            messages.success(
                request,
                f"Added '{user_film.film}' to your list."
            )
            if user_film_count == 1:
                return redirect("film_list")
            else:
                return redirect("rank_film", user_film_id=user_film.id)
    else:
        form = AddFilmForm(request.user)

    return render(request, "core/add_film.html", {"form": form})

@login_required
def rank_film(request, user_film_id):
    user_film = get_object_or_404(
        UserFilm,
        id=user_film_id,
        user=request.user)
    return render(request, "core/rank_film.html", {"user_film": user_film})
