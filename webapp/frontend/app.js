/**
 * Anime Info — Mini App
 * Premium UI with integrated catalog, genre filtering,
 * Library tab (Watchlist, Watched, Favorites, Franchises),
 * multi-episode +/- progress controls, and smooth state updates.
 */

const tg = window.Telegram?.WebApp;
if (tg) {
  tg.expand();
  if (tg.setHeaderColor) tg.setHeaderColor("#0d0e12");
  if (tg.setBackgroundColor) tg.setBackgroundColor("#0d0e12");
}

const INIT_DATA = tg?.initData || "";
const API_HEADERS = {
  "Content-Type": "application/json",
  "X-Init-Data": INIT_DATA
};

// ── IN-MEMORY CACHE & STATE ──
const state = {
  currentScreen: "home",
  previousScreen: "home",
  activeFilter: "trending",
  activeGenre: "All",
  activeLibTab: "watchlist",
  discoverCache: null,
  catalogCache: {},
  libraryData: null,
  searchCache: {},
  detailCache: {},
  watchlistSet: new Set(),
  watchedSet: new Set(),
  favoritesSet: new Set(),
  searchTimer: null
};

// ── LOADER & TOAST FEEDBACK ──
const loader = {
  start() {
    const el = document.getElementById("top-loader");
    if (el) {
      el.classList.remove("complete");
      el.classList.add("active");
    }
  },
  done() {
    const el = document.getElementById("top-loader");
    if (el) {
      el.classList.remove("active");
      el.classList.add("complete");
    }
  }
};

let toastTimeout = null;
function notify(text, duration = 2200) {
  const el = document.getElementById("toast");
  if (!el) return;
  el.textContent = text;
  el.classList.remove("hidden");
  el.classList.add("show");
  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => {
    el.classList.remove("show");
    setTimeout(() => el.classList.add("hidden"), 200);
  }, duration);
}

// ── API REQUEST HELPER ──
async function request(endpoint, options = {}) {
  loader.start();
  try {
    const res = await fetch(endpoint, { headers: API_HEADERS, ...options });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn(`[API] ${endpoint} failed:`, err);
    throw err;
  } finally {
    loader.done();
  }
}

// ── UTILITY HELPERS ──
function cleanTitle(item) {
  return item?.title?.english || item?.title?.romaji || item?.title || "Unknown";
}

function getCover(item) {
  return item?.coverImage?.extraLarge || item?.coverImage?.large || item?.poster_image || "";
}

function stripTags(html = "") {
  return html.replace(/<[^>]+>/g, "").trim();
}

// ── NAVIGATION CONTROLLER ──
function navigateTo(screenName, saveHistory = true) {
  if (saveHistory) state.previousScreen = state.currentScreen;
  state.currentScreen = screenName;

  document.querySelectorAll(".screen").forEach(s => s.classList.remove("active"));
  const target = document.getElementById(`screen-${screenName}`);
  if (target) target.classList.add("active");

  document.querySelectorAll(".nav-item").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.screen === screenName);
  });

  window.scrollTo({ top: 0, behavior: "instant" });
}

document.querySelectorAll(".nav-item").forEach(btn => {
  btn.addEventListener("click", () => {
    const screen = btn.dataset.screen;
    navigateTo(screen);
    if (screen === "library") {
      loadLibrary();
    } else if (screen === "home") {
      loadDiscover();
    }
  });
});

document.getElementById("back-btn")?.addEventListener("click", () => {
  navigateTo(state.previousScreen || "home", false);
});


// ── CARD COMPONENT FOR DISCOVER & CATALOG ──
function createCard(item) {
  const id = item.id || item.anime_id;
  const title = cleanTitle(item);
  const cover = getCover(item);
  const score = item.averageScore ? (item.averageScore / 10).toFixed(1) : null;
  const progress = item.progress;

  const card = document.createElement("div");
  card.className = "card-item";
  card.innerHTML = `
    ${cover ? `<img src="${cover}" alt="${title}" loading="lazy">` : `<div style="height:160px;background:#15171e"></div>`}
    ${score ? `<span class="card-score">★ ${score}</span>` : ""}
    ${progress !== undefined ? `<span class="card-badge">Ep ${progress}</span>` : ""}
    <div class="card-title">${title}</div>
  `;

  card.addEventListener("click", () => openDetail(id, item));
  return card;
}

// ── DISCOVER & INTEGRATED CATALOG SCREEN ──
async function loadDiscover(forceRefresh = false) {
  try {
    const data = await request("/api/discover");
    state.discoverCache = data;

    // Hydrate user sets
    if (data.watchlist) state.watchlistSet = new Set(data.watchlist.map(w => w.anime_id));
    if (data.watched) state.watchedSet = new Set(data.watched.map(w => w.anime_id));
    if (data.favorites) state.favoritesSet = new Set(data.favorites.map(f => f.anime_id));

    renderDiscoverHeader(data);
  } catch (err) {
    console.warn("Discover fetch error:", err);
  }

  // Load integrated catalog (default filter: 'all')
  loadCatalog(state.activeFilter);
}

function renderDiscoverHeader(data) {
  const user = data.user;
  const greetEl = document.getElementById("user-greeting");
  if (greetEl && user?.first_name) {
    greetEl.textContent = `Welcome, ${user.first_name}`;
  }

  // Render carousel
  const carousel = document.getElementById("carousel");
  if (carousel && data.carousel) {
    carousel.innerHTML = "";
    data.carousel.forEach(item => carousel.appendChild(createCard(item)));
    if (!data.carousel.length) {
      carousel.innerHTML = `<p class="status-msg">No trending titles available.</p>`;
    }
  }
}

// Filter chips listener (All / Trending / New Releases / Popular / Genres...)
document.querySelectorAll(".filter-chip").forEach(chip => {
  chip.addEventListener("click", () => {
    document.querySelectorAll(".filter-chip").forEach(c => c.classList.remove("active"));
    chip.classList.add("active");
    state.activeFilter = chip.dataset.filter;
    loadCatalog(state.activeFilter);
  });
});

async function loadCatalog(filter = "all") {
  const container = document.getElementById("catalog-content");

  if (state.catalogCache[filter]) {
    renderCatalog(state.catalogCache[filter]);
    return;
  }

  container.innerHTML = `
    <div class="loading-state">
      <div class="spinner-ring"></div>
      <span>Loading catalog titles...</span>
    </div>
  `;

  try {
    const data = await request(`/api/catalog?filter=${encodeURIComponent(filter)}`);
    const catalog = data.catalog || {};
    state.catalogCache[filter] = catalog;
    renderCatalog(catalog);
  } catch (err) {
    container.innerHTML = `<p class="status-msg" style="padding:16px">Failed to load catalog.</p>`;
  }
}

function renderCatalog(grouped) {
  const container = document.getElementById("catalog-content");
  container.innerHTML = "";

  // Sort letters so '#' comes first, followed by A-Z
  const letters = Object.keys(grouped).sort((a, b) => {
    if (a === "#") return -1;
    if (b === "#") return 1;
    return a.localeCompare(b);
  });

  if (!letters.length) {
    container.innerHTML = `<p class="status-msg" style="padding:16px">No titles available in this category.</p>`;
    return;
  }

  letters.forEach(letter => {
    const header = document.createElement("div");
    header.className = "letter-divider";
    header.textContent = `— ${letter}`;
    container.appendChild(header);

    const grid = document.createElement("div");
    grid.className = "grid-layout";
    grouped[letter].forEach(item => grid.appendChild(createCard(item)));
    container.appendChild(grid);
  });
}


// ── SEARCH CONTROLLER ──
const searchInput = document.getElementById("search-input");
const searchClear = document.getElementById("search-clear");
const searchWrap = document.getElementById("search-results-wrap");
const searchResults = document.getElementById("search-results");
const searchCount = document.getElementById("search-count");
const homeContent = document.getElementById("home-content");

if (searchInput) {
  searchInput.addEventListener("input", (e) => {
    const q = e.target.value.trim();
    if (searchClear) searchClear.classList.toggle("hidden", !q);

    clearTimeout(state.searchTimer);
    if (!q) {
      searchWrap.classList.add("hidden");
      homeContent.classList.remove("hidden");
      return;
    }

    state.searchTimer = setTimeout(() => executeSearch(q), 300);
  });
}

if (searchClear) {
  searchClear.addEventListener("click", () => {
    if (searchInput) searchInput.value = "";
    searchClear.classList.add("hidden");
    searchWrap.classList.add("hidden");
    homeContent.classList.remove("hidden");
  });
}

async function executeSearch(query) {
  searchWrap.classList.remove("hidden");
  homeContent.classList.add("hidden");

  if (state.searchCache[query]) {
    renderSearchResults(state.searchCache[query]);
    return;
  }

  searchResults.innerHTML = `<div class="loading-state" style="grid-column:1/-1"><div class="spinner-ring"></div><span>Searching titles...</span></div>`;

  try {
    const data = await request(`/api/search?q=${encodeURIComponent(query)}`);
    const results = data.results || [];
    state.searchCache[query] = results;
    renderSearchResults(results);
  } catch (err) {
    searchResults.innerHTML = `<p class="status-msg">Search request failed.</p>`;
  }
}

function renderSearchResults(results) {
  if (searchCount) searchCount.textContent = `${results.length} found`;
  searchResults.innerHTML = "";
  if (results.length) {
    results.forEach(item => searchResults.appendChild(createCard(item)));
  } else {
    searchResults.innerHTML = `<p class="status-msg">No results matching that title.</p>`;
  }
}

// ── LIBRARY CONTROLLER (WATCHLIST, WATCHED, FAVORITES, FRANCHISES) ──
document.querySelectorAll(".lib-tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".lib-tab").forEach(t => t.classList.remove("active"));
    tab.classList.add("active");
    state.activeLibTab = tab.dataset.tab;
    renderLibraryView();
  });
});

async function loadLibrary() {
  const container = document.getElementById("library-content");
  container.innerHTML = `
    <div class="loading-state">
      <div class="spinner-ring"></div>
      <span>Loading your library...</span>
    </div>
  `;

  try {
    const data = await request("/api/library");
    state.libraryData = data;
    
    // Sync sets
    state.watchlistSet = new Set((data.watchlist || []).map(w => w.anime_id));
    state.watchedSet = new Set((data.watched || []).map(w => w.anime_id));
    state.favoritesSet = new Set(data.fav_ids || []);

    renderLibraryView();
  } catch (err) {
    container.innerHTML = `<p class="status-msg" style="padding:20px">Failed to load library data.</p>`;
  }
}

function renderLibraryView() {
  const container = document.getElementById("library-content");
  if (!container || !state.libraryData) return;
  container.innerHTML = "";

  const tab = state.activeLibTab;

  if (tab === "watchlist") {
    renderLibraryItemsList(container, state.libraryData.watchlist || [], "Your Watchlist is empty. Add titles while browsing!");
  } else if (tab === "watched") {
    renderLibraryItemsList(container, state.libraryData.watched || [], "No completed or watched series yet.");
  } else if (tab === "favorites") {
    renderLibraryItemsList(container, state.libraryData.favorites || [], "No favorites added yet.");
  } else if (tab === "franchises") {
    renderFranchisesList(container, state.libraryData.franchises || {});
  }
}

function renderLibraryItemsList(container, items, emptyMsg) {
  if (!items || !items.length) {
    container.innerHTML = `<p class="status-msg" style="padding:24px">${emptyMsg}</p>`;
    return;
  }

  const list = document.createElement("div");
  list.className = "library-list";

  items.forEach(item => {
    list.appendChild(createLibraryCard(item));
  });

  container.appendChild(list);
}

function createLibraryCard(item) {
  const id = item.anime_id || item.id;
  const title = cleanTitle(item);
  const cover = getCover(item);
  const progress = item.progress || 0;
  const total = item.total_episodes ? item.total_episodes : "?";
  const isWatched = item.status === "completed" || state.watchedSet.has(id);
  const isFav = state.favoritesSet.has(id);

  const card = document.createElement("div");
  card.className = "lib-card";
  card.innerHTML = `
    <div class="lib-card-left" onclick="openDetail(${id})">
      ${cover ? `<img src="${cover}" alt="${title}">` : `<div style="width:60px;height:84px;background:#1a1c24;border-radius:8px"></div>`}
    </div>
    <div class="lib-card-main">
      <div class="lib-card-title" onclick="openDetail(${id})">${title}</div>
      <div class="lib-card-status">
        <span class="badge ${isWatched ? "badge-watched" : "badge-watching"}">
          ${isWatched ? "✓ Watched" : `Ep ${progress} / ${total}`}
        </span>
      </div>

      <!-- Multi-episode progress increment / decrement buttons -->
      <div class="multi-ep-controls">
        <span class="ep-ctrl-label">Progress:</span>
        <button class="ep-btn dec" data-delta="-10">-10</button>
        <button class="ep-btn dec" data-delta="-3">-3</button>
        <button class="ep-btn dec" data-delta="-1">-1</button>
        <button class="ep-btn inc" data-delta="1">+1</button>
        <button class="ep-btn inc" data-delta="3">+3</button>
        <button class="ep-btn inc" data-delta="10">+10</button>
      </div>

      <div class="lib-card-actions">
        <button class="lib-act-btn ${isWatched ? "active" : ""}" id="btn-mark-watched-${id}">
          ${isWatched ? "✓ Completed" : "Mark Watched"}
        </button>
        <button class="lib-act-btn ${isFav ? "is-fav" : ""}" id="btn-fav-${id}">
          ${isFav ? "★ Favorited" : "☆ Favorite"}
        </button>
        <button class="lib-act-btn remove" id="btn-remove-${id}">
          Remove
        </button>
      </div>
    </div>
  `;

  // Multi-ep progress button handlers
  card.querySelectorAll(".ep-btn").forEach(btn => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const delta = intVal(btn.dataset.delta);
      try {
        const res = await request(`/api/watchlist/${id}/progress?delta=${delta}`, { method: "PATCH" });
        notify(`Progress: Ep ${res.progress}${res.status === "completed" ? " (Completed!)" : ""}`);
        loadLibrary();
      } catch (err) {
        notify("Could not update progress.");
      }
    });
  });

  // Mark Watched toggle
  card.querySelector(`#btn-mark-watched-${id}`).addEventListener("click", async (e) => {
    e.stopPropagation();
    const newStatus = isWatched ? "watching" : "completed";
    await request("/api/watchlist", {
      method: "POST",
      body: JSON.stringify({
        anime_id: id,
        title: title,
        poster_image: cover,
        total_episodes: item.total_episodes || 0,
        status: newStatus
      })
    });
    notify(newStatus === "completed" ? "Marked as Watched! 🎉" : "Moved to Watchlist.");
    loadLibrary();
  });

  // Favorite toggle
  card.querySelector(`#btn-fav-${id}`).addEventListener("click", async (e) => {
    e.stopPropagation();
    await toggleFavAction(id, title, cover);
    loadLibrary();
  });

  // Remove button
  card.querySelector(`#btn-remove-${id}`).addEventListener("click", async (e) => {
    e.stopPropagation();
    await request(`/api/watchlist/${id}`, { method: "DELETE" });
    notify("Removed from library.");
    loadLibrary();
  });

  return card;
}

function renderFranchisesList(container, franchises) {
  const fNames = Object.keys(franchises).sort();
  if (!fNames.length) {
    container.innerHTML = `<p class="status-msg" style="padding:24px">No franchise groups saved in your library.</p>`;
    return;
  }

  const list = document.createElement("div");
  list.className = "franchise-list";

  fNames.forEach(fName => {
    const items = franchises[fName];
    const groupCard = document.createElement("div");
    groupCard.className = "franchise-group-card";

    groupCard.innerHTML = `
      <div class="franchise-header">
        <div class="franchise-info">
          <span class="franchise-title">${fName}</span>
          <span class="franchise-count">${items.length} ${items.length === 1 ? 'Title' : 'Titles'}</span>
        </div>
        <span class="franchise-arrow">▼</span>
      </div>
      <div class="franchise-body hidden"></div>
    `;

    const header = groupCard.querySelector(".franchise-header");
    const body = groupCard.querySelector(".franchise-body");
    const arrow = groupCard.querySelector(".franchise-arrow");

    header.addEventListener("click", () => {
      const isHidden = body.classList.toggle("hidden");
      arrow.textContent = isHidden ? "▼" : "▲";
    });

    items.forEach(item => {
      body.appendChild(createLibraryCard(item));
    });

    list.appendChild(groupCard);
  });

  container.appendChild(list);
}

function intVal(str) {
  return parseInt(str, 10) || 0;
}

// ── DETAIL SCREEN ──
async function openDetail(animeId, preliminaryData = null) {
  navigateTo("detail");
  const container = document.getElementById("detail-content");

  if (preliminaryData) {
    renderDetailView(preliminaryData, false);
  } else {
    container.innerHTML = `
      <div class="loading-state" style="padding-top:60px">
        <div class="spinner-ring"></div>
        <span>Loading details...</span>
      </div>
    `;
  }

  if (state.detailCache[animeId]) {
    renderDetailView(state.detailCache[animeId], true);
    return;
  }

  try {
    const fullData = await request(`/api/anime/${animeId}`);
    state.detailCache[animeId] = fullData;
    renderDetailView(fullData, true);
  } catch (err) {
    if (!preliminaryData) {
      container.innerHTML = `<p class="status-msg" style="padding:24px">Unable to retrieve anime details.</p>`;
    }
  }
}

function renderDetailView(item, isHydrated = true) {
  const container = document.getElementById("detail-content");
  const id = item.id || item.anime_id;
  const title = cleanTitle(item);
  const cover = getCover(item);
  const banner = item.bannerImage || cover;
  const score = item.averageScore ? `${(item.averageScore / 10).toFixed(1)} / 10` : "Unrated";
  const status = item.status || "Unknown";
  const eps = item.episodes ? `${item.episodes} Episodes` : "Ongoing";
  const genres = (item.genres || []).map(g => `<span class="tag-item">${g}</span>`).join("");
  const description = stripTags(item.description || "No synopsis available.");
  
  const inWatchlist = item.in_watchlist !== undefined ? item.in_watchlist : state.watchlistSet.has(id);
  const isWatched = item.is_watched !== undefined ? item.is_watched : state.watchedSet.has(id);
  const isFavorite = item.is_favorite !== undefined ? item.is_favorite : state.favoritesSet.has(id);
  const progress = item.progress || 0;

  // Sync quick fav button in top nav
  const quickFav = document.getElementById("detail-fav-quick");
  if (quickFav) {
    quickFav.textContent = isFavorite ? "★" : "☆";
    quickFav.classList.toggle("is-fav", isFavorite);
    quickFav.onclick = () => toggleFavAction(id, title, cover);
  }

  // Build Chronological Watch Order related titles HTML
  let chronoHTML = "";
  const chronoList = item.relations_chronological || [];
  if (chronoList.length > 0) {
    const cardsHTML = chronoList.map(rel => {
      const rId = rel.id;
      const rTitle = rel.title || "Unknown";
      const rCover = rel.coverImage?.large || rel.coverImage?.extraLarge || "";
      const rYear = rel.year ? rel.year : "TBA";
      const rFmt = rel.format || "";
      const rTag = rel.is_current ? "Selected" : (rel.relation_type || "Related");
      const isCurr = rel.is_current ? "active-title" : "";

      return `
        <div class="chrono-card ${isCurr}" onclick="openDetail(${rId})">
          ${rCover ? `<img src="${rCover}" alt="${rTitle}" loading="lazy">` : `<div style="height:110px;background:#15171e"></div>`}
          <span class="chrono-tag ${rel.is_current ? "tag-curr" : ""}">${rTag}</span>
          <div class="chrono-title">${rTitle}</div>
          <div class="chrono-meta">${rYear} ${rFmt ? `· ${rFmt}` : ""}</div>
        </div>
      `;
    }).join("");

    chronoHTML = `
      <div class="detail-section-label" style="margin-top:16px;">Chronological Watch Order & Related Series:</div>
      <div class="horizontal-scroll chrono-scroll">
        ${cardsHTML}
      </div>
    `;
  }

  container.innerHTML = `
    ${banner ? `<img class="detail-banner-img" src="${banner}" alt="${title}" loading="lazy">` : ""}

    <div class="detail-header-block">
      ${cover ? `<img class="detail-poster-img" src="${cover}" alt="${title}">` : ""}
      <div class="detail-meta-block">
        <h2 class="detail-name">${title}</h2>
        <div class="detail-stat">Score: <span>★ ${score}</span></div>
        <div class="detail-stat">Status: <span>${status}</span></div>
        <div class="detail-stat">Length: <span>${eps}</span></div>
        <div class="detail-stat">Progress: <span>Ep ${progress}</span></div>
      </div>
    </div>

    ${genres ? `<div class="tag-cloud">${genres}</div>` : ""}

    <p class="detail-summary collapsed" id="summary-text">${description}</p>
    <button class="expand-toggle" id="summary-toggle">Show more ›</button>

    ${chronoHTML}

    <!-- Episode Progress Multi-Buttons -->
    <div class="detail-section-label">Update Episode Progress:</div>
    <div class="detail-ep-grid">
      <button class="ep-btn dec" data-delta="-10">-10</button>
      <button class="ep-btn dec" data-delta="-3">-3</button>
      <button class="ep-btn dec" data-delta="-1">-1</button>
      <button class="ep-btn inc" data-delta="1">+1</button>
      <button class="ep-btn inc" data-delta="3">+3</button>
      <button class="ep-btn inc" data-delta="10">+10</button>
    </div>

    <div class="action-grid" style="margin-top:16px;">
      <button class="btn-primary ${inWatchlist ? "in-list" : ""}" id="btn-watchlist-toggle">
        ${inWatchlist ? "✓ In Watchlist" : "+ Add to Watchlist"}
      </button>
      <button class="btn-secondary ${isWatched ? "is-watched" : ""}" id="btn-watched-toggle">
        ${isWatched ? "✓ Marked Watched" : "✓ Mark as Watched"}
      </button>
      <button class="btn-secondary ${isFavorite ? "is-fav" : ""}" id="btn-fav-toggle">
        ${isFavorite ? "★ Favorited" : "☆ Favorite"}
      </button>


      ${item.siteUrl ? `
        <a class="btn-link" href="${item.siteUrl}" target="_blank">
          View Profile on AniList ›
        </a>
      ` : ""}
    </div>
  `;


  // Synopsis expansion
  const toggleBtn = document.getElementById("summary-toggle");
  const summaryEl = document.getElementById("summary-text");
  if (toggleBtn && summaryEl) {
    toggleBtn.addEventListener("click", () => {
      const isCollapsed = summaryEl.classList.toggle("collapsed");
      toggleBtn.textContent = isCollapsed ? "Show more ›" : "Show less ‹";
    });
  }

  // Multi-ep progress handlers on detail page
  container.querySelectorAll(".detail-ep-grid .ep-btn").forEach(btn => {
    btn.addEventListener("click", async () => {
      const delta = intVal(btn.dataset.delta);
      try {
        // Ensure added to watchlist if updating progress
        if (!inWatchlist && !isWatched) {
          await request("/api/watchlist", {
            method: "POST",
            body: JSON.stringify({
              anime_id: id, title: title, poster_image: cover, total_episodes: item.episodes || 0, status: "watching"
            })
          });
        }
        const res = await request(`/api/watchlist/${id}/progress?delta=${delta}`, { method: "PATCH" });
        notify(`Progress updated: Episode ${res.progress}${res.status === "completed" ? " (Completed!)" : ""}`);
        state.detailCache[id] = null;
        openDetail(id);
      } catch (err) {
        notify("Could not update progress.");
      }
    });
  });

  // Watchlist action handler
  const wlBtn = document.getElementById("btn-watchlist-toggle");
  if (wlBtn) {
    wlBtn.addEventListener("click", async () => {
      const currentlyIn = wlBtn.classList.contains("in-list");
      if (currentlyIn) {
        wlBtn.classList.remove("in-list");
        wlBtn.textContent = "+ Add to Watchlist";
        state.watchlistSet.delete(id);
        notify("Removed from watchlist.");
        await request(`/api/watchlist/${id}`, { method: "DELETE" }).catch(() => {});
      } else {
        wlBtn.classList.add("in-list");
        wlBtn.textContent = "✓ In Watchlist";
        state.watchlistSet.add(id);
        notify("Added to watchlist.");
        await request("/api/watchlist", {
          method: "POST",
          body: JSON.stringify({
            anime_id: id, title: title, poster_image: cover, total_episodes: item.episodes || 0, status: "watching"
          })
        }).catch(() => {});
      }
    });
  }

  // Watched toggle action handler
  const wtBtn = document.getElementById("btn-watched-toggle");
  if (wtBtn) {
    wtBtn.addEventListener("click", async () => {
      const currentlyWatched = wtBtn.classList.contains("is-fav");
      const newStatus = currentlyWatched ? "watching" : "completed";
      await request("/api/watchlist", {
        method: "POST",
        body: JSON.stringify({
          anime_id: id, title: title, poster_image: cover, total_episodes: item.episodes || 0, status: newStatus
        })
      });
      notify(newStatus === "completed" ? "Marked as Watched! 🎉" : "Moved to Watchlist.");
      state.detailCache[id] = null;
      openDetail(id);
    });
  }

  // Favorite toggle action
  const favBtn = document.getElementById("btn-fav-toggle");
  if (favBtn) {
    favBtn.addEventListener("click", () => toggleFavAction(id, title, cover));
  }
}

async function toggleFavAction(id, title, cover) {
  const favBtn = document.getElementById("btn-fav-toggle");
  const quickFav = document.getElementById("detail-fav-quick");

  try {
    const res = await request("/api/favorites/toggle", {
      method: "POST",
      body: JSON.stringify({ anime_id: id, title: title, poster_image: cover })
    });

    const isFav = res.is_favorite;
    if (isFav) {
      state.favoritesSet.add(id);
      notify("Saved to favorites.");
    } else {
      state.favoritesSet.delete(id);
      notify("Removed from favorites.");
    }

    if (favBtn) {
      favBtn.classList.toggle("is-fav", isFav);
      favBtn.textContent = isFav ? "★ Favorited" : "☆ Favorite";
    }
    if (quickFav) {
      quickFav.classList.toggle("is-fav", isFav);
      quickFav.textContent = isFav ? "★" : "☆";
    }
  } catch (e) {
    notify("Could not update favorites.");
  }
}

// ── INITIALIZATION ──
document.addEventListener("DOMContentLoaded", () => {
  loadDiscover();
});

