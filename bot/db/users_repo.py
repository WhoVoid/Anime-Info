from typing import List, Dict, Any, Optional
import re
from bot.db.clients import db_clients

def extract_franchise_name(title: str) -> str:
    """Extract a base franchise name from an anime title (e.g., 'Naruto Shippuden' -> 'Naruto')."""
    if not title:
        return "Other"
    # Clean common suffixes like Season 2, Part 2, Movie, OVA, 2nd Season, etc.
    clean = re.sub(r'(?i)\s+(:|-)?\s*(season|\d+nd|\d+rd|\d+th|\d+st|part|movie|ova|ona|tv|specials?).*', '', title).strip()
    clean = re.sub(r'\s+\d+$', '', clean).strip()
    return clean if clean else title.strip()

class UsersRepo:
    @staticmethod
    async def ensure_user(user_id: int, username: Optional[str] = None):
        db = db_clients.users_db
        if db is None: return
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"user_id": user_id, "username": username}},
            upsert=True
        )

    @staticmethod
    async def add_to_watchlist(user_id: int, anime_id: int, title: str, poster_image: str = "", total_episodes: int = 0, status: str = "watching", franchise: str = "") -> bool:
        db = db_clients.users_db
        if db is None: return False
        await UsersRepo.ensure_user(user_id)
        franchise_name = franchise or extract_franchise_name(title)
        doc = {
            "user_id": user_id,
            "anime_id": anime_id,
            "title": title,
            "poster_image": poster_image,
            "progress": 0,
            "total_episodes": total_episodes,
            "status": status,
            "franchise": franchise_name
        }
        res = await db.watchlist.update_one(
            {"user_id": user_id, "anime_id": anime_id},
            {"$set": doc},
            upsert=True
        )
        return res.upserted_id is not None or res.modified_count > 0

    @staticmethod
    async def remove_from_watchlist(user_id: int, anime_id: int) -> bool:
        db = db_clients.users_db
        if db is None: return False
        res = await db.watchlist.delete_one({"user_id": user_id, "anime_id": anime_id})
        return res.deleted_count > 0

    @staticmethod
    async def get_watchlist(user_id: int, skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
        db = db_clients.users_db
        if db is None: return []
        cursor = db.watchlist.find({"user_id": user_id, "status": {"$ne": "completed"}}).skip(skip).limit(limit)
        return await cursor.to_list(length=limit)

    @staticmethod
    async def get_watched(user_id: int, skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
        db = db_clients.users_db
        if db is None: return []
        cursor = db.watchlist.find({"user_id": user_id, "status": "completed"}).skip(skip).limit(limit)
        return await cursor.to_list(length=limit)

    @staticmethod
    async def set_status(user_id: int, anime_id: int, status: str) -> bool:
        db = db_clients.users_db
        if db is None: return False
        res = await db.watchlist.update_one(
            {"user_id": user_id, "anime_id": anime_id},
            {"$set": {"status": status}}
        )
        return res.modified_count > 0

    @staticmethod
    async def update_tracker_progress(user_id: int, anime_id: int, delta: int = 1) -> Optional[Dict[str, Any]]:
        db = db_clients.users_db
        if db is None: return None
        item = await db.watchlist.find_one({"user_id": user_id, "anime_id": anime_id})
        if not item:
            return None
        current_prog = item.get("progress", 0)
        new_progress = max(0, current_prog + delta)
        total = item.get("total_episodes", 0)
        
        status = item.get("status", "watching")
        if total > 0 and new_progress >= total:
            status = "completed"
        elif delta < 0 and status == "completed":
            status = "watching"

        await db.watchlist.update_one(
            {"user_id": user_id, "anime_id": anime_id},
            {"$set": {"progress": new_progress, "status": status}}
        )
        return {"progress": new_progress, "status": status, "total_episodes": total}

    @staticmethod
    async def toggle_favorite(user_id: int, anime_id: int, title: str, poster_image: str = "") -> bool:
        db = db_clients.users_db
        if db is None: return False
        await UsersRepo.ensure_user(user_id)
        franchise_name = extract_franchise_name(title)
        existing = await db.favorites.find_one({"user_id": user_id, "anime_id": anime_id})
        if existing:
            await db.favorites.delete_one({"user_id": user_id, "anime_id": anime_id})
            return False  # removed
        else:
            await db.favorites.insert_one({
                "user_id": user_id,
                "anime_id": anime_id,
                "title": title,
                "poster_image": poster_image,
                "franchise": franchise_name
            })
            return True  # added

    @staticmethod
    async def get_favorites(user_id: int, skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
        db = db_clients.users_db
        if db is None: return []
        cursor = db.favorites.find({"user_id": user_id}).skip(skip).limit(limit)
        return await cursor.to_list(length=limit)

    @staticmethod
    async def is_favorite(user_id: int, anime_id: int) -> bool:
        db = db_clients.users_db
        if db is None: return False
        item = await db.favorites.find_one({"user_id": user_id, "anime_id": anime_id})
        return item is not None

    @staticmethod
    async def delete_user_data(user_id: int) -> bool:
        db = db_clients.users_db
        if db is None: return False
        await db.users.delete_one({"user_id": user_id})
        await db.watchlist.delete_many({"user_id": user_id})
        await db.favorites.delete_many({"user_id": user_id})
        return True


