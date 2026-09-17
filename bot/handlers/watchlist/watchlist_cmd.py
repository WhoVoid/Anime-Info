from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from bot.db.users_repo import UsersRepo
from bot.fetchers.anilist import AniListFetcher
from bot.utils.formatting import escape_html

def register_watchlist_handlers(app: Client):

    # ── /watchlist ──────────────────────────────────
    @app.on_message(filters.command("watchlist"))
    async def watchlist_cmd(client: Client, message: Message):
        user_id = message.from_user.id if message.from_user else None
        if not user_id:
            return
        items = await UsersRepo.get_watchlist(user_id, skip=0, limit=20)
        if not items:
            await message.reply_text("[-] Your watchlist is currently empty.\nUse /anime &lt;title&gt; to add entries.")
            return

        text = "<b>Your Watchlist (Currently Watching)</b>\n\n"
        buttons = []
        for idx, item in enumerate(items, start=1):
            title = escape_html(item.get("title", "Unknown"))
            progress = item.get("progress", 0)
            total = item.get("total_episodes") or "?"
            anime_id = item.get("anime_id")
            text += f"{idx}. <b>{title}</b> — Ep {progress}/{total}\n"
            buttons.append([
                InlineKeyboardButton(f"+1 Ep", callback_data=f"tr_d:{anime_id}:1::1"),
                InlineKeyboardButton(f"+3 Ep", callback_data=f"tr_d:{anime_id}:3::1"),
                InlineKeyboardButton(f"+10 Ep", callback_data=f"tr_d:{anime_id}:10::1"),
                InlineKeyboardButton("✓ Watched", callback_data=f"wl_watched:{anime_id}")
            ])

        await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

    # ── /watched ────────────────────────────────────
    @app.on_message(filters.command("watched"))
    async def watched_cmd(client: Client, message: Message):
        user_id = message.from_user.id if message.from_user else None
        if not user_id:
            return
        items = await UsersRepo.get_watched(user_id, skip=0, limit=20)
        if not items:
            await message.reply_text("[-] No watched series marked as completed yet.")
            return

        text = "<b>Your Watched & Completed Series</b>\n\n"
        buttons = []
        for idx, item in enumerate(items, start=1):
            title = escape_html(item.get("title", "Unknown"))
            total = item.get("total_episodes") or "?"
            anime_id = item.get("anime_id")
            text += f"{idx}. <b>{title}</b> ({total} eps)\n"
            buttons.append([
                InlineKeyboardButton(f"Move to Watchlist", callback_data=f"wl_add:{anime_id}"),
                InlineKeyboardButton("[-] Remove", callback_data=f"wl_rem:{anime_id}")
            ])

        await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

    # ── /favorites ──────────────────────────────────
    @app.on_message(filters.command("favorites"))
    async def favorites_cmd(client: Client, message: Message):
        user_id = message.from_user.id if message.from_user else None
        if not user_id:
            return
        items = await UsersRepo.get_favorites(user_id, skip=0, limit=20)
        if not items:
            await message.reply_text("[-] No favorites saved yet.\nTap ★ Favorite on any anime card to add it.")
            return

        text = "<b>Favorite Titles</b>\n\n"
        for idx, item in enumerate(items, start=1):
            title = escape_html(item.get("title", "Unknown"))
            text += f"{idx}. <b>{title}</b>\n"

        await message.reply_text(text)

    # ── CALLBACK HANDLER ────────────────────────────
    @app.on_callback_query(filters.regex(r"^(wl_add|wl_rem|fav_add|wl_watched|tr_d):"))
    async def watchlist_callbacks(client: Client, callback: CallbackQuery):
        user_id = callback.from_user.id
        parts = callback.data.split(":")
        action = parts[0]
        anime_id = int(parts[1])

        # Fetch metadata from AniList if adding
        item_data = await AniListFetcher.get_by_id(anime_id)
        title = item_data.get("title", {}).get("english") or item_data.get("title", {}).get("romaji") or f"Anime #{anime_id}"
        poster = item_data.get("coverImage", {}).get("extraLarge") or item_data.get("coverImage", {}).get("large") or ""
        total_episodes = item_data.get("episodes") or 0

        if action == "wl_add":
            added = await UsersRepo.add_to_watchlist(user_id, anime_id, title=title, poster_image=poster, total_episodes=total_episodes, status="watching")
            if added:
                await callback.answer("Added to your watchlist.", show_alert=False)
            else:
                await callback.answer("Moved to watchlist.", show_alert=False)

        elif action == "wl_watched":
            await UsersRepo.add_to_watchlist(user_id, anime_id, title=title, poster_image=poster, total_episodes=total_episodes, status="completed")
            await callback.answer("Marked as Watched / Completed! ✓", show_alert=False)

        elif action == "wl_rem":
            removed = await UsersRepo.remove_from_watchlist(user_id, anime_id)
            if removed:
                await callback.answer("Removed from list.", show_alert=False)
                try:
                    await callback.message.edit_text("✓ List updated.")
                except Exception:
                    pass
            else:
                await callback.answer("Entry not found.", show_alert=False)

        elif action == "fav_add":
            is_fav = await UsersRepo.toggle_favorite(user_id, anime_id, title=title, poster_image=poster)
            if is_fav:
                await callback.answer("★ Added to favorites.", show_alert=False)
            else:
                await callback.answer("Removed from favorites.", show_alert=False)

        elif action == "tr_d":
            delta = int(parts[2])
            # ensure title is in watchlist
            await UsersRepo.add_to_watchlist(user_id, anime_id, title=title, poster_image=poster, total_episodes=total_episodes, status="watching")
            res = await UsersRepo.update_tracker_progress(user_id, anime_id, delta=delta)
            if res:
                prog = res["progress"]
                status = res["status"]
                msg_status = " (Completed! 🎉)" if status == "completed" else ""
                await callback.answer(f"Progress updated ({'+' if delta > 0 else ''}{delta}): Episode {prog}{msg_status}", show_alert=False)
            else:
                await callback.answer("Unable to update progress.", show_alert=False)

