import datetime
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from bot.fetchers.anilist import AniListFetcher
from bot.fetchers.filler_list import FillerFetcher
from bot.db.users_repo import UsersRepo
from bot.utils.formatting import format_anime_card, escape_html, clean_synopsis

def _title(item: dict) -> str:
    return item.get("title", {}).get("english") or item.get("title", {}).get("romaji") or "Unknown"

def _cover(item: dict) -> str:
    return item.get("coverImage", {}).get("extraLarge") or item.get("coverImage", {}).get("large") or ""

def _format_year_type(item: dict) -> str:
    year = item.get("startDate", {}).get("year") if isinstance(item.get("startDate"), dict) else None
    fmt = item.get("format") or ""
    meta = []
    if year: meta.append(str(year))
    if fmt: meta.append(fmt)
    return f" ({' · '.join(meta)})" if meta else ""

def _build_search_results_markup(media_list: list, query: str, page: int, has_next: bool) -> InlineKeyboardMarkup:
    buttons = []
    for idx, item in enumerate(media_list, start=1):
        title_str = _title(item)
        meta_str = _format_year_type(item)
        display_label = f"{idx}. {title_str}{meta_str}"
        if len(display_label) > 42:
            display_label = display_label[:39] + "..."
        buttons.append([InlineKeyboardButton(display_label, callback_data=f"anime_sel:{item['id']}:{query[:20]}:{page}")])

    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("‹ Prev", callback_data=f"anime_page:{query[:20]}:{page-1}"))
    if has_next:
        nav.append(InlineKeyboardButton("Next ›", callback_data=f"anime_page:{query[:20]}:{page+1}"))
    if nav:
        buttons.append(nav)

    return InlineKeyboardMarkup(buttons)

def _build_detail_card_markup(anime_id: int, query: str = "", page: int = 1) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("[+] Watchlist", callback_data=f"wl_add:{anime_id}"),
            InlineKeyboardButton("★ Favorite", callback_data=f"fav_add:{anime_id}"),
            InlineKeyboardButton("✓ Watched", callback_data=f"wl_watched:{anime_id}")
        ]
    ]
    if query:
        buttons.append([InlineKeyboardButton("‹ Back to Results", callback_data=f"anime_page:{query[:20]}:{page}")])

    return InlineKeyboardMarkup(buttons)


def register_info_handlers(app: Client):

    # ── /anime ──────────────────────────────────────
    @app.on_message(filters.command("anime"))
    async def anime_cmd(client: Client, message: Message):
        if len(message.command) < 2:
            await message.reply_text("• Usage: <code>/anime &lt;title&gt;</code>\n• Example: <code>/anime Death Note</code>")
            return
        query = " ".join(message.command[1:])
        msg = await message.reply_text("› Searching titles...")
        data = await AniListFetcher.search_anime(query, page=1, per_page=5)
        media_list = data.get("media", [])
        page_info = data.get("pageInfo", {})
        if not media_list:
            await msg.edit_text("[-] No anime found matching that query. Please check title spelling.")
            return

        has_next = page_info.get("hasNextPage", False) or len(media_list) >= 5
        text = f"<b>Search Results for:</b> <i>\"{escape_html(query)}\"</i> (Page 1)\nSelect a title to view details:"
        markup = _build_search_results_markup(media_list, query, 1, has_next)
        await msg.edit_text(text, reply_markup=markup)

    # Search result selection callback
    @app.on_callback_query(filters.regex(r"^anime_sel:(\d+):(.*):(\d+)$"))
    async def anime_select_cb(client: Client, cb: CallbackQuery):
        match = cb.data.split(":", 3)
        anime_id = int(match[1])
        query = match[2]
        page = int(match[3])

        item = await AniListFetcher.get_by_id(anime_id)
        if not item:
            await cb.answer("Could not load details.", show_alert=True)
            return

        text = format_anime_card(_title(item), item.get("status"), item.get("averageScore"), item.get("description"), item.get("siteUrl"))
        markup = _build_detail_card_markup(anime_id, query, page)
        cover = _cover(item)

        await cb.answer()
        if cover:
            try:
                await cb.message.delete()
                await cb.message.reply_photo(photo=cover, caption=text, reply_markup=markup)
            except Exception:
                await cb.message.edit_text(text, reply_markup=markup)
        else:
            await cb.message.edit_text(text, reply_markup=markup)

    # Pagination callback for /anime search results
    @app.on_callback_query(filters.regex(r"^anime_page:(.*):(\d+)$"))
    async def anime_page_cb(client: Client, cb: CallbackQuery):
        match = cb.data.split(":", 2)
        query = match[1]
        page = int(match[2])
        if page < 1: page = 1

        data = await AniListFetcher.search_anime(query, page=page, per_page=5)
        media_list = data.get("media", [])
        page_info = data.get("pageInfo", {})
        if not media_list:
            await cb.answer("No additional results available.", show_alert=False)
            return

        has_next = page_info.get("hasNextPage", False) or len(media_list) >= 5
        text = f"<b>Search Results for:</b> <i>\"{escape_html(query)}\"</i> (Page {page})\nSelect a title to view details:"
        markup = _build_search_results_markup(media_list, query, page, has_next)

        await cb.answer()
        # If previous message was a photo message, delete and reply text
        if cb.message.photo:
            await cb.message.delete()
            await cb.message.reply_text(text, reply_markup=markup)
        else:
            await cb.message.edit_text(text, reply_markup=markup)

    # ── /manga ──────────────────────────────────────
    @app.on_message(filters.command("manga"))
    async def manga_cmd(client: Client, message: Message):
        if len(message.command) < 2:
            await message.reply_text("• Usage: <code>/manga &lt;title&gt;</code>\n• Example: <code>/manga Berserk</code>")
            return
        query = " ".join(message.command[1:])
        msg = await message.reply_text("› Searching manga...")
        data = await AniListFetcher.search_manga(query, page=1, per_page=5)
        media_list = data.get("media", [])
        page_info = data.get("pageInfo", {})
        if not media_list:
            await msg.edit_text("[-] No manga found matching that title.")
            return

        has_next = page_info.get("hasNextPage", False) or len(media_list) >= 5
        text = f"<b>Manga Search Results for:</b> <i>\"{escape_html(query)}\"</i> (Page 1)\nSelect a title to view details:"
        markup = _build_search_results_markup(media_list, query, 1, has_next)
        await msg.edit_text(text, reply_markup=markup)

    # ── /character ──────────────────────────────────
    @app.on_message(filters.command("character"))
    async def character_cmd(client: Client, message: Message):
        if len(message.command) < 2:
            await message.reply_text("• Usage: <code>/character &lt;name&gt;</code>\n• Example: <code>/character Gojo Satoru</code>")
            return
        query = " ".join(message.command[1:])
        msg = await message.reply_text("› Searching character...")
        data = await AniListFetcher.search_character(query, page=1, per_page=1)
        chars = data.get("mediaCharacters") or data.get("characters") or []
        if not chars:
            await msg.edit_text("[-] Character not found.")
            return
        c = chars[0]
        name = c.get("name", {}).get("full") or "Unknown"
        desc = clean_synopsis(c.get("description") or "No description available.", limit=400)
        text = f"<b>{escape_html(name)}</b>\n\n<i>{desc}</i>"
        image = c.get("image", {}).get("large")
        await msg.delete()
        if image:
            await message.reply_photo(photo=image, caption=text)
        else:
            await message.reply_text(text)

    # ── /studio ──────────────────────────────────────
    @app.on_message(filters.command("studio"))
    async def studio_cmd(client: Client, message: Message):
        if len(message.command) < 2:
            await message.reply_text("• Usage: <code>/studio &lt;name&gt;</code>\n• Example: <code>/studio MAPPA</code>")
            return
        query = " ".join(message.command[1:])
        msg = await message.reply_text("› Searching studio...")
        data = await AniListFetcher.search_studio(query, page=1, per_page=5)
        studios = data.get("studios", [])
        if not studios:
            await msg.edit_text("[-] Studio not found.")
            return
        s = studios[0]
        kind = "Animation Studio" if s.get("isAnimationStudio") else "Studio"
        text = f"<b>{kind}: {escape_html(s.get('name', 'Unknown'))}</b>"
        if s.get("siteUrl"):
            text += f'\n› <a href="{escape_html(s["siteUrl"])}">Official Profile</a>'
        await msg.delete()
        await message.reply_text(text)

    # ── /schedule ────────────────────────────────────
    @app.on_message(filters.command("schedule"))
    async def schedule_cmd(client: Client, message: Message):
        msg = await message.reply_text("› Loading upcoming schedule...")
        schedules = await AniListFetcher.get_airing_schedule(page=1, per_page=10)
        if not schedules:
            await msg.edit_text("[-] No upcoming airing schedule found.")
            return
        text = "<b>Upcoming Broadcast Schedule</b>\n\n"
        for item in schedules:
            media = item.get("media", {})
            title = media.get("title", {}).get("english") or media.get("title", {}).get("romaji") or "Unknown"
            ep = item.get("episode", "?")
            airing_at = item.get("airingAt")
            time_str = ""
            if airing_at:
                dt = datetime.datetime.utcfromtimestamp(airing_at)
                time_str = f" — {dt.strftime('%b %d, %H:%M UTC')}"
            text += f"• <b>{escape_html(title)}</b> | Ep {ep}{time_str}\n"
        await msg.edit_text(text)

    # ── /filler ──────────────────────────────────────
    @app.on_message(filters.command("filler"))
    async def filler_cmd(client: Client, message: Message):
        if len(message.command) < 2:
            await message.reply_text("• Usage: <code>/filler &lt;anime title&gt;</code>\n• Example: <code>/filler Naruto Shippuden</code>")
            return
        query = " ".join(message.command[1:])
        msg = await message.reply_text(f"› Loading filler breakdown for <b>{escape_html(query)}</b>...")
        info = await FillerFetcher.get_filler_info(query)
        if not info:
            await msg.edit_text(
                f"[-] No filler breakdown found for <b>{escape_html(query)}</b>.\n"
                "Please try the standard English title."
            )
            return

        filler_ranges = FillerFetcher.format_episode_ranges(info.get("filler_episodes", []))
        mixed_ranges = FillerFetcher.format_episode_ranges(info.get("mixed_episodes", []))

        text = (
            f"<b>{escape_html(info['title'])} — Filler Guide</b>\n\n"
            f"• Total Episodes: <b>{info['total_episodes']}</b>\n"
            f"• Filler Episodes: <b>{info['filler_count']} ({info['filler_percentage']})</b>\n\n"
            f"<b>Filler Episodes:</b>\n<code>{filler_ranges}</code>\n"
        )
        if info.get("mixed_episodes"):
            text += f"\n<b>Mixed Episodes:</b>\n<code>{mixed_ranges}</code>\n"
        text += f'\n› <a href="{escape_html(info["source_url"])}">Source: AnimeFillerList</a>'

        await msg.edit_text(text)

