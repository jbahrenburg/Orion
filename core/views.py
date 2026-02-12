from django.shortcuts import render
from django.contrib import messages
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.db import transaction, models
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponseBadRequest
from django.urls import reverse
from django.db.models import Max


from .forms import SignUpForm, LoginForm, AddFilmForm
from .models import UserFilm, Film
from .services.tmdb import search_movies, get_director

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
    comparison = (
        UserFilm.objects
        .filter(user=request.user)
        .exclude(id=user_film.id)
        .select_related("film")
        .first()
    )

    if request.method == "POST":
        pref_value = request.POST.get("preference")
        if pref_value in ("liked", "ok", "disliked"):
            user_film.preference = pref_value
            user_film.save()
            return redirect("rank_film", user_film_id=user_film.id)
        choice = request.POST.get("choice")
        if comparison and choice == "new":
            with transaction.atomic():
                old_pos = user_film.position
                new_pos = comparison.position
                if old_pos > new_pos:
                    UserFilm.objects.filter(
                        user = request.user,
                        position__gte = new_pos,
                        position__lt = old_pos,
                    ).exclude(id=user_film.id).update(
                        position = models.F("position")+1
                    )
                    user_film.position = new_pos
                    user_film.save()
        return redirect("film_list")

    return render(request,
                  "core/rank_film.html",
                  {"user_film":     user_film,
                   "comparison":    comparison,
                   },
                )

@login_required
def tmdb_search(request):
    q = request.GET.get("q", "").strip()
    year_str = request.GET.get("year", "").strip()

    year = None
    if year_str.isdigit():
        year = int(year_str)

    results = search_movies(q, year=year)
    return JsonResponse({"results": results})

@login_required
def film_search(request):
    q = request.GET.get("q", "").strip()

    results = search_movies(q) if q else []

    user_films = (
        UserFilm.objects
        .filter(user=request.user, film__tmdb_id__isnull=False)
        .select_related("film")
    )
    owned_by_tmdb = {uf.film.tmdb_id: uf for uf in user_films}

    for r in results:
        uf = owned_by_tmdb.get(r["tmdb_id"])
        r["owned"] = bool(uf)
        r["preference"] = uf.preference if uf else None
        r["director"] = get_director(r["tmdb_id"])

    return render(request, "core/film_search.html", {
        "q": q,
        "results": results,
    })

@login_required
def add_tmdb_film(request, tmdb_id: int):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    title = (request.POST.get("title") or "").strip()
    year_str = (request.POST.get("year") or "").strip()
    poster_path = (request.POST.get("poster_path") or "").strip() or None

    year = int(year_str) if year_str.isdigit() else None
    if not title:
        return HttpResponseBadRequest("Missing title")
    
    print(get_director(tmdb_id))

    # 1) Create/get the Film (correct model)
    film, created = Film.objects.get_or_create(
        tmdb_id=tmdb_id,
        defaults={
            "title": title,
            "year": year,
            "poster_path": poster_path,
            "director": get_director(tmdb_id),
        }
    )

    if not created and not film.director:
        film.director = get_director(tmdb_id)
        # optional: also backfill year/poster if missing
        if not film.year and year:
            film.year = year
        if not film.poster_path and poster_path:
            film.poster_path = poster_path
        film.save()

    # 2) Create/get UserFilm for THIS user (since rank_film expects user_film_id)
    # Put it at end for now; rank_film will move it if needed
    max_pos = (
        UserFilm.objects
        .filter(user=request.user)
        .aggregate(Max("position"))
        .get("position__max")
    )
    next_pos = (max_pos or 0) + 1

    user_film, created = UserFilm.objects.get_or_create(
        user=request.user,
        film=film,
        defaults={"position": next_pos},
    )

    # 3) Redirect using the correct keyword arg name
    return redirect("rank_film", user_film_id=user_film.id)