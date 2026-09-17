import httpx
import asyncio
from typing import Dict, Any, List, Optional
from bot.db.cache_repo import CacheRepo
from bot.utils.logging import get_logger

logger = get_logger(__name__)

ANILIST_URL = "https://graphql.anilist.co"

# ── QUERIES ──────────────────────────────────────────
# Search by keyword (only used when user provides a query string)
ANIME_SEARCH_QUERY = """
query ($search: String, $page: Int, $perPage: Int, $isAdult: Boolean) {
  Page(page: $page, perPage: $perPage) {
    pageInfo { total currentPage lastPage hasNextPage }
    media(search: $search, type: ANIME, isAdult: $isAdult, sort: SEARCH_MATCH) {
      id
      format startDate { year }
      title { romaji english native }
      status averageScore episodes
      description(asHtml: false)
      coverImage { large extraLarge }
      bannerImage siteUrl genres
      nextAiringEpisode { airingAt episode }
    }
  }
}
"""

# Browse WITHOUT a keyword — sorted by popularity/date/trending, with optional genre
ANIME_BROWSE_QUERY = """
query ($page: Int, $perPage: Int, $isAdult: Boolean, $sort: [MediaSort], $genre: String) {
  Page(page: $page, perPage: $perPage) {
    pageInfo { total currentPage lastPage hasNextPage }
    media(type: ANIME, isAdult: $isAdult, sort: $sort, genre: $genre) {
      id
      format startDate { year }
      title { romaji english native }
      status averageScore episodes
      description(asHtml: false)
      coverImage { large extraLarge }
      bannerImage siteUrl genres
      nextAiringEpisode { airingAt episode }
    }
  }
}
"""

MANGA_SEARCH_QUERY = """
query ($search: String, $page: Int, $perPage: Int, $isAdult: Boolean) {
  Page(page: $page, perPage: $perPage) {
    pageInfo { total currentPage lastPage hasNextPage }
    media(search: $search, type: MANGA, isAdult: $isAdult) {
      id
      format startDate { year }
      title { romaji english }
      status averageScore chapters volumes
      description(asHtml: false)
      coverImage { large }
      siteUrl
    }
  }
}
"""

CHARACTER_QUERY = """
query ($search: String, $page: Int, $perPage: Int) {
  Page(page: $page, perPage: $perPage) {
    mediaCharacters: characters(search: $search) {
      id
      name { full native }
      description(asHtml: false)
      image { large }
      siteUrl
    }
  }
}
"""

STUDIO_QUERY = """
query ($search: String, $page: Int, $perPage: Int) {
  Page(page: $page, perPage: $perPage) {
    studios(search: $search) {
      id name siteUrl isAnimationStudio
    }
  }
}
"""

TRENDING_QUERY = """
query ($page: Int, $perPage: Int, $isAdult: Boolean, $genre: String) {
  Page(page: $page, perPage: $perPage) {
    media(type: ANIME, sort: TRENDING_DESC, isAdult: $isAdult, genre: $genre) {
      id
      format startDate { year }
      title { romaji english }
      status averageScore episodes
      description(asHtml: false)
      coverImage { large extraLarge }
      bannerImage siteUrl genres
    }
  }
}
"""

SCHEDULE_QUERY = """
query ($page: Int, $perPage: Int) {
  Page(page: $page, perPage: $perPage) {
    airingSchedules(notYetAiring: true, sort: TIME) {
      id airingAt episode
      media {
        id
        title { romaji english }
        siteUrl
      }
    }
  }
}
"""

ANIME_BY_ID_QUERY = """
query ($id: Int) {
  Media(id: $id, type: ANIME) {
    id
    format startDate { year }
    title { romaji english native }
    status averageScore episodes
    description(asHtml: false)
    coverImage { large extraLarge }
    bannerImage siteUrl genres
    nextAiringEpisode { airingAt episode }
  }
}
"""

# ── HTTP CLIENT ──────────────────────────────────────
async def _post(query: str, variables: Dict[str, Any], retries: int = 3) -> Dict[str, Any]:
    """Post to AniList GraphQL with retry logic. Cache hit always tried first."""
    cache_key = f"anilist:{abs(hash(query + str(variables)))}"
    cached = await CacheRepo.get(cache_key)
    if cached:
        return cached

    last_error = None
    for attempt in range(retries):
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    ANILIST_URL,
                    json={"query": query, "variables": variables},
                    headers={"Accept": "application/json", "Content-Type": "application/json"}
                )
                if resp.status_code == 429:
                    wait = int(resp.headers.get("Retry-After", 10))
                    logger.warning(f"AniList rate limited. Waiting {wait}s")
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                data = resp.json()
                if "errors" in data:
                    logger.warning(f"AniList GraphQL errors: {data['errors']}")
                    return {}
                await CacheRepo.set(cache_key, data)
                return data
        except Exception as e:
            last_error = e
            logger.warning(f"AniList request attempt {attempt+1} failed: {e}")
            if attempt < retries - 1:
                await asyncio.sleep(1.5 * (attempt + 1))

    logger.error(f"AniList request failed after {retries} attempts: {last_error}")
    return {}


# ── PUBLIC METHODS ────────────────────────────────────
class AniListFetcher:

    @classmethod
    async def search_anime(cls, search: str, page: int = 1, per_page: int = 20, is_adult: bool = False, genre: Optional[str] = None) -> Dict[str, Any]:
        """Search anime by keyword. Falls back to browse if query is empty."""
        if not search or not search.strip():
            return await cls._browse_anime(page=page, per_page=per_page, is_adult=is_adult, sort=["POPULARITY_DESC"], genre=genre)
        variables: Dict[str, Any] = {"search": search.strip(), "page": page, "perPage": per_page, "isAdult": is_adult}
        res = await _post(ANIME_SEARCH_QUERY, variables)
        return res.get("data", {}).get("Page", {})

    @classmethod
    async def _browse_anime(cls, page: int = 1, per_page: int = 30, is_adult: bool = False, sort: List[str] = None, genre: Optional[str] = None) -> Dict[str, Any]:
        """Browse anime without keyword, sorted by given criteria and optional genre."""
        if sort is None:
            sort = ["POPULARITY_DESC"]
        variables: Dict[str, Any] = {"page": page, "perPage": per_page, "isAdult": is_adult, "sort": sort}
        if genre and genre.strip():
            variables["genre"] = genre.strip()
        res = await _post(ANIME_BROWSE_QUERY, variables)
        return res.get("data", {}).get("Page", {})

    @classmethod
    async def search_manga(cls, search: str, page: int = 1, per_page: int = 10, is_adult: bool = False) -> Dict[str, Any]:
        if not search or not search.strip():
            return {}
        res = await _post(MANGA_SEARCH_QUERY, {"search": search.strip(), "page": page, "perPage": per_page, "isAdult": is_adult})
        return res.get("data", {}).get("Page", {})

    @classmethod
    async def search_character(cls, search: str, page: int = 1, per_page: int = 5) -> Dict[str, Any]:
        if not search or not search.strip():
            return {}
        res = await _post(CHARACTER_QUERY, {"search": search.strip(), "page": page, "perPage": per_page})
        return res.get("data", {}).get("Page", {})

    @classmethod
    async def search_studio(cls, search: str, page: int = 1, per_page: int = 5) -> Dict[str, Any]:
        if not search or not search.strip():
            return {}
        res = await _post(STUDIO_QUERY, {"search": search.strip(), "page": page, "perPage": per_page})
        return res.get("data", {}).get("Page", {})

    @classmethod
    async def get_trending(cls, page: int = 1, per_page: int = 10, is_adult: bool = False, genre: Optional[str] = None) -> List[Dict[str, Any]]:
        variables: Dict[str, Any] = {"page": page, "perPage": per_page, "isAdult": is_adult}
        if genre and genre.strip():
            variables["genre"] = genre.strip()
        res = await _post(TRENDING_QUERY, variables)
        return res.get("data", {}).get("Page", {}).get("media", [])

    @classmethod
    async def get_popular(cls, page: int = 1, per_page: int = 30, is_adult: bool = False, genre: Optional[str] = None) -> List[Dict[str, Any]]:
        page_data = await cls._browse_anime(page=page, per_page=per_page, is_adult=is_adult, sort=["POPULARITY_DESC"], genre=genre)
        return page_data.get("media", [])

    @classmethod
    async def get_new_releases(cls, page: int = 1, per_page: int = 30, is_adult: bool = False, genre: Optional[str] = None) -> List[Dict[str, Any]]:
        page_data = await cls._browse_anime(page=page, per_page=per_page, is_adult=is_adult, sort=["START_DATE_DESC"], genre=genre)
        return page_data.get("media", [])

    @classmethod
    async def get_airing_schedule(cls, page: int = 1, per_page: int = 10) -> List[Dict[str, Any]]:
        res = await _post(SCHEDULE_QUERY, {"page": page, "perPage": per_page})
        return res.get("data", {}).get("Page", {}).get("airingSchedules", [])

    @classmethod
    async def get_by_id(cls, anime_id: int) -> Dict[str, Any]:
        res = await _post(ANIME_BY_ID_QUERY, {"id": anime_id})
        return res.get("data", {}).get("Media", {})

