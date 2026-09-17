import os
from fastapi import FastAPI, Header, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from bot.db.clients import db_clients
from bot.db.users_repo import UsersRepo, extract_franchise_name
from bot.fetchers.anilist import AniListFetcher
from webapp.backend.auth import validate_telegram_init_data

app = FastAPI(title="Anime Info Bot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GENRES = [
    "All", "Action", "Adventure", "Comedy", "Drama", "Fantasy",
    "Horror", "Mahou Shoujo", "Mecha", "Music", "Mystery",
    "Psychological", "Romance", "Sci-Fi", "Slice of Life", "Sports",
    "Supernatural", "Thriller"
]

async def get_current_user(x_init_data: Optional[str] = Header(None)) -> Dict[str, Any]:
    if not x_init_data:
        return {"id": 12345678, "first_name": "Explorer", "username": "demouser"}
    user = validate_telegram_init_data(x_init_data)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired Telegram authentication.")
    return user

@app.on_event("startup")
async def startup_event():
    await db_clients.init_clients()

@app.get("/api/discover")
async def discover_page(current_user: Dict[str, Any] = Depends(get_current_user)):
    user_id = current_user.get("id")
    trending = await AniListFetcher.get_trending(page=1, per_page=12)
    watchlist = await UsersRepo.get_watchlist(user_id, limit=12) if user_id else []
    watched = await UsersRepo.get_watched(user_id, limit=12) if user_id else []
    favorites = await UsersRepo.get_favorites(user_id, limit=12) if user_id else []

    for lst in (watchlist, watched, favorites):
        for item in lst:
            if "_id" in item: item["_id"] = str(item["_id"])

    return {
        "carousel": trending,
        "genres": GENRES,
        "watchlist": watchlist,
        "watched": watched,
        "favorites": favorites,
        "user": current_user
    }

@app.get("/api/search")
async def search_anime(
    q: str = "",
    genre: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    clean_q = q.strip()
    g_filter = genre.strip() if (genre and genre != "All") else None
    if not clean_q:
        items = await AniListFetcher.get_trending(page=1, per_page=24, genre=g_filter)
        return {"results": items}
    data = await AniListFetcher.search_anime(clean_q, page=1, per_page=24, genre=g_filter)
    return {"results": data.get("media", [])}

@app.get("/api/catalog")
async def catalog_page(
    filter: Optional[str] = "all",
    genre: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    clean_filter = (filter or "all").lower()
    g_filter = genre.strip() if (genre and genre != "All") else None

    if clean_filter == "trending":
        items = await AniListFetcher.get_trending(page=1, per_page=40, genre=g_filter)
    elif clean_filter == "new":
        items = await AniListFetcher.get_new_releases(page=1, per_page=40, genre=g_filter)
    elif clean_filter == "popular":
        items = await AniListFetcher.get_popular(page=1, per_page=40, genre=g_filter)
    else:
        # Default "all" or specific genre passed via filter
        if clean_filter != "all" and not g_filter:
            g_filter = filter
        items = await AniListFetcher.get_popular(page=1, per_page=40, genre=g_filter)

    items_sorted = sorted(
        items,
        key=lambda x: (x.get("title", {}).get("english") or x.get("title", {}).get("romaji") or "").lower()
    )

    grouped: Dict[str, list] = {}
    for item in items_sorted:
        title = item.get("title", {}).get("english") or item.get("title", {}).get("romaji") or "Unknown"
        first_char = title[0].upper() if title else "#"
        letter = first_char if first_char.isalpha() else "#"
        if letter not in grouped:
            grouped[letter] = []
        grouped[letter].append(item)

    return {"catalog": grouped, "items": items_sorted}


@app.get("/api/library")
async def get_library(current_user: Dict[str, Any] = Depends(get_current_user)):
    user_id = current_user.get("id")
    watchlist = await UsersRepo.get_watchlist(user_id, limit=100) if user_id else []
    watched = await UsersRepo.get_watched(user_id, limit=100) if user_id else []
    favorites = await UsersRepo.get_favorites(user_id, limit=100) if user_id else []

    all_items = []
    for item in watchlist:
        item["_id"] = str(item["_id"]) if "_id" in item else ""
        item["list_type"] = "watchlist"
        all_items.append(item)
    for item in watched:
        item["_id"] = str(item["_id"]) if "_id" in item else ""
        item["list_type"] = "watched"
        all_items.append(item)

    fav_ids = set(f.get("anime_id") for f in favorites)
    for f in favorites:
        if "_id" in f: f["_id"] = str(f["_id"])

    # Build franchise grouping
    franchises: Dict[str, list] = {}
    for item in all_items:
        f_name = item.get("franchise") or extract_franchise_name(item.get("title", ""))
        if f_name not in franchises:
            franchises[f_name] = []
        franchises[f_name].append(item)

    return {
        "watchlist": watchlist,
        "watched": watched,
        "favorites": favorites,
        "fav_ids": list(fav_ids),
        "franchises": franchises
    }

@app.get("/api/anime/{anime_id}")
async def get_anime_detail(anime_id: int, current_user: Dict[str, Any] = Depends(get_current_user)):
    user_id = current_user.get("id")
    data = await AniListFetcher.get_by_id(anime_id)
    if not data:
        raise HTTPException(status_code=404, detail="Anime title not found.")

    watchlist_items = await UsersRepo.get_watchlist(user_id, limit=100) if user_id else []
    watched_items = await UsersRepo.get_watched(user_id, limit=100) if user_id else []

    wl_item = next((w for w in watchlist_items if w.get("anime_id") == anime_id), None)
    wt_item = next((w for w in watched_items if w.get("anime_id") == anime_id), None)
    is_favorite = await UsersRepo.is_favorite(user_id, anime_id) if user_id else False

    data["in_watchlist"] = wl_item is not None
    data["is_watched"] = wt_item is not None
    data["is_favorite"] = is_favorite
    data["progress"] = (wl_item or wt_item or {}).get("progress", 0)

    return data

class WatchlistAddReq(BaseModel):
    anime_id: int
    title: str
    poster_image: Optional[str] = ""
    total_episodes: Optional[int] = 0
    status: Optional[str] = "watching"

@app.post("/api/watchlist")
async def add_watchlist(req: WatchlistAddReq, current_user: Dict[str, Any] = Depends(get_current_user)):
    user_id = current_user.get("id")
    success = await UsersRepo.add_to_watchlist(
        user_id, req.anime_id, req.title, req.poster_image, req.total_episodes, status=req.status or "watching"
    )
    return {"success": success}

@app.delete("/api/watchlist/{anime_id}")
async def remove_watchlist(anime_id: int, current_user: Dict[str, Any] = Depends(get_current_user)):
    user_id = current_user.get("id")
    success = await UsersRepo.remove_from_watchlist(user_id, anime_id)
    return {"success": success}

@app.patch("/api/watchlist/{anime_id}/progress")
async def update_progress(
    anime_id: int,
    delta: int = Query(1),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    user_id = current_user.get("id")
    res = await UsersRepo.update_tracker_progress(user_id, anime_id, delta=delta)
    if not res:
        raise HTTPException(status_code=404, detail="Item not in watchlist.")
    return res

class FavoriteReq(BaseModel):
    anime_id: int
    title: str
    poster_image: Optional[str] = ""

@app.post("/api/favorites/toggle")
async def toggle_favorite(req: FavoriteReq, current_user: Dict[str, Any] = Depends(get_current_user)):
    user_id = current_user.get("id")
    is_now_fav = await UsersRepo.toggle_favorite(user_id, req.anime_id, req.title, req.poster_image)
    return {"is_favorite": is_now_fav}

frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")

