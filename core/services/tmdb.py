from django.conf import settings
import requests
from functools import lru_cache

TMDB_SEARCH_URL = "https://api.themoviedb.org/3/search/movie"
TMDB_CREDITS_URL = "https://api.themoviedb.org/3/movie/{movie_id}/credits"

@lru_cache(maxsize=512)
def get_director(movie_id: int) -> str | None:
    if not settings.TMDB_API_KEY:
        raise RuntimeError("TMDB_API_KEY is not set in Django settings.")

    url = TMDB_CREDITS_URL.format(movie_id=movie_id)
    resp = requests.get(url, params={"api_key": settings.TMDB_API_KEY}, timeout=8)
    resp.raise_for_status()
    data = resp.json()

    for person in data.get("crew", []):
        if person.get("job") == "Director":
            return person.get("name")

    return None

def search_movies(query: str, year: int | None = None, *, limit: int = 8) -> list[dict]:
    query = (query or "").strip()
    if len(query) < 2:
        return []
    
    if not settings.TMDB_API_KEY:
            raise RuntimeError("TMDB_API_KEY is not set in Django settings")
    
    params = {
         "api_key": settings.TMDB_API_KEY,
         "query": query,
         "include_adult": "false", 
         "language": "en-US",
    }
    if year:
        params["year"] = year
    
    resp = requests.get(TMDB_SEARCH_URL, params=params, timeout=8)
    resp.raise_for_status()
    data = resp.json()

    results = []
    for item in data.get("results", [])[:limit]:
        title = item.get("title")
        tmdb_id = item.get("id")
        release_date = item.get("release_date")
        poster_path = item.get("poster_path")

        movie_year = int(release_date[:4]) if release_date and len(release_date) >= 4  else None

        if not title or not tmdb_id:
            continue

        results.append({
             "tmdb_id": tmdb_id,
             "title": title,
             "year": movie_year,
             "poster_path": poster_path,
        })

    return results