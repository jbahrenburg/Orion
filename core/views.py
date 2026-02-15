from django.shortcuts import render
from django.contrib import messages
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.db import transaction, models
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponseBadRequest
from django.urls import reverse
from django.db.models import Max
from collections import defaultdict


from .forms import SignUpForm, LoginForm, AddFilmForm
from .models import UserFilm, Film, PairwiseComparison
from .services.tmdb import search_movies, get_director
from .services.ratings import elo_update, elo_to_10

PREF_ORDER = ("liked", "ok", "disliked")

def _tier_queryset(request, user_film, tier: str):
    return (
        UserFilm.objects
        .filter(user=request.user, preference=tier)
        .exclude(id=user_film.id)
        .order_by("position")
        .select_related("film")
    )


def _tier_start(user, tier: str) -> int:
    """How many films are in tiers above this tier."""
    idx = PREF_ORDER.index(tier)
    above = PREF_ORDER[:idx]
    if not above:
        return 0
    return UserFilm.objects.filter(user=user, preference__in=above).count()

def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))

BANDS = {
    "liked":    (6.67, 10.00),
    "ok":       (3.33, 6.67),
    "disliked": (0.00, 3.33),
}

def tier_banded_score(elo: float, tier: str, min_elo: float, max_elo: float) -> float:
    lo, hi = BANDS[tier]
    if max_elo <= min_elo:
        # if only 1 film in tier, put it in the middle of the band
        return (lo + hi) / 2.0

    t = clamp01((elo - min_elo) / (max_elo - min_elo))
    return lo + t * (hi - lo)

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
    user_films = list(
        UserFilm.objects.filter(user=request.user).select_related("film")
    )

    # group Elo by tier
    tier_elos = defaultdict(list)
    for uf in user_films:
        if uf.preference in ("liked", "ok", "disliked"):
            tier_elos[uf.preference].append(uf.elo)

    tier_minmax = {}
    for tier, elos in tier_elos.items():
        tier_minmax[tier] = (min(elos), max(elos))

    # attach display score (tier-banded)
    for uf in user_films:
        tier = uf.preference if uf.preference in ("liked", "ok", "disliked") else "ok"
        mn, mx = tier_minmax.get(tier, (uf.elo, uf.elo))
        uf.display_score10 = round(tier_banded_score(uf.elo, tier, mn, mx), 2)

    # IMPORTANT: ordering should also respect tier first
    pref_rank = {"liked": 0, "ok": 1, "disliked": 2}
    user_films.sort(key=lambda uf: (pref_rank.get(uf.preference, 1), -uf.elo))

    return render(request, "core/film_list.html", {"user_films": user_films})


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
    user_film = get_object_or_404(UserFilm, id=user_film_id, user=request.user)

    # ---- 1) Preference step (qualifier) ----
    if request.method == "POST":
        pref_value = request.POST.get("preference")
        if pref_value in PREF_ORDER:
            user_film.preference = pref_value
            user_film.save(update_fields=["preference"])

            # initialize ranking state (binary search within tier)
            tier_qs = _tier_queryset(request, user_film, user_film.preference)
            request.session["rank_state"] = {
                "target_uf_id": user_film.id,
                "tier": user_film.preference,
                "lo": 0,
                "hi": tier_qs.count(),  # number of candidates in the tier
            }
            return redirect("rank_film", user_film_id=user_film.id)

    # ---- 2) Comparison step ----
    state = request.session.get("rank_state")
    comparison = None

    # Only run placement if user has preference AND session is for this film
    if user_film.preference and state and state.get("target_uf_id") == user_film.id:
        tier = state["tier"]
        lo = state["lo"]
        hi = state["hi"]

        tier_qs = _tier_queryset(request, user_film, tier)
        n = tier_qs.count()

        # Safety clamp in case list changed
        lo = max(0, min(lo, n))
        hi = max(0, min(hi, n))

        if request.method == "POST":
            choice = request.POST.get("choice")
            if choice in ("new", "comparison") and n > 0 and lo < hi:
                mid = (lo + hi) // 2
                comp = tier_qs[mid]  # the one we compared against

                winner_uf = user_film if choice == "new" else comp
                loser_uf  = comp if choice == "new" else user_film

                with transaction.atomic():
                    # record outcome
                    PairwiseComparison.objects.create(
                        user=request.user, winner=winner_uf.film, loser=loser_uf.film
                    )

                    # Elo update (lock both rows)
                    locked = (
                        UserFilm.objects.select_for_update()
                        .filter(user=request.user, id__in=[winner_uf.id, loser_uf.id])
                    )
                    locked_map = {uf.id: uf for uf in locked}
                    w = locked_map[winner_uf.id]
                    l = locked_map[loser_uf.id]
                    w.elo, l.elo = elo_update(w.elo, l.elo, k=24.0)
                    w.save(update_fields=["elo"])
                    l.save(update_fields=["elo"])

                # Update bounds for binary search
                # If new film wins, it belongs ABOVE comp => search left half
                if choice == "new":
                    hi = mid
                else:
                    lo = mid + 1

                state["lo"], state["hi"] = lo, hi
                request.session["rank_state"] = state

                # If finished, finalize insertion
                if lo >= hi:
                    insert_index_in_tier = lo  # 0..n
                    tier_start = _tier_start(request.user, tier)

                    # Convert to global position
                    insert_pos = tier_start + insert_index_in_tier

                    with transaction.atomic():
                        UserFilm.objects.filter(
                            user=request.user,
                            position__gte=insert_pos
                        ).exclude(id=user_film.id).update(position=models.F("position") + 1)

                        user_film.position = insert_pos
                        user_film.save(update_fields=["position"])

                    # Clear state and return to list
                    request.session.pop("rank_state", None)
                    return redirect("film_list")

                return redirect("rank_film", user_film_id=user_film.id)

        # If not posting a choice, render the current comparison
        if n > 0 and lo < hi:
            mid = (lo + hi) // 2
            comparison = tier_qs[mid]

        # If tier empty or bounds done, just insert at tier boundary
        elif n == 0:
            tier_start = _tier_start(request.user, tier)
            insert_pos = tier_start

            with transaction.atomic():
                UserFilm.objects.filter(
                    user=request.user,
                    position__gte=insert_pos
                ).exclude(id=user_film.id).update(position=models.F("position") + 1)

                user_film.position = insert_pos
                user_film.save(update_fields=["position"])

            request.session.pop("rank_state", None)
            return redirect("film_list")

    return render(
        request,
        "core/rank_film.html",
        {"user_film": user_film, "comparison": comparison},
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