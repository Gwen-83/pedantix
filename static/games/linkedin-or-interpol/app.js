(() => {
  const apiBase =
    window.PEDANTIX_CONFIG?.BACKEND_URL?.replace(/\/+$/, "") || "";
  const params = new URLSearchParams(window.location.search);

  const homeSection = document.getElementById("linkedin-home");
  const playSection = document.getElementById("linkedin-play");
  const homeError = document.getElementById("linkedin-home-error");
  const playError = document.getElementById("linkedin-play-error");

  const soloModeSelect = document.getElementById("linkedin-solo-mode");
  const roundCountGroup = document.getElementById("linkedin-round-count-group");
  const roundCountSelect = document.getElementById("linkedin-round-count");
  const roomRoundCountSelect = document.getElementById(
    "linkedin-room-round-count",
  );
  const soloCardDesc = document.getElementById("linkedin-solo-card-desc");

  const playerIdKey = "linkedin_player_id";
  const soloGameIdKey = "linkedin_solo_game_id";
  const collectionKey = "linkedin_or_interpol_collection_v1";

  let cachedCatalog = null;
  let catalogFilter = "all";
  let catalogSearchQuery = "";
  let lastDiscoveredPersonId = null;

  let playerId = localStorage.getItem(playerIdKey);
  if (!playerId) {
    playerId =
      globalThis.crypto?.randomUUID?.() ||
      `linkedin-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
    localStorage.setItem(playerIdKey, playerId);
  }

  const playerName = (
    localStorage.getItem("pedantix_player_name") ||
    localStorage.getItem("pedantix_auth_user") ||
    "Joueur"
  )
    .trim()
    .slice(0, 24);

  document.getElementById("linkedin-player-name").textContent = playerName;

  let state = null;
  let gameType = null; // 'solo' | 'room'
  let busy = false;
  let pollTimer = null;
  let pollInFlight = false;

  async function request(path, options = {}) {
    const response = await fetch(`${apiBase}${path}`, {
      ...options,
      headers: {
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...options.headers,
      },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || `Erreur serveur (${response.status}).`);
    }
    return data;
  }

  function post(path, payload) {
    return request(path, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  function playerPayload() {
    return {
      player_id: playerId,
      player_name: playerName,
    };
  }

  function showError(element, message) {
    if (!element) return;
    element.textContent = message;
    element.hidden = false;
  }

  function hideError(element) {
    if (!element) return;
    element.textContent = "";
    element.hidden = true;
  }

  function syncSoloModeControls() {
    const isInfinite = soloModeSelect.value === "solo-infinite";
    roundCountGroup.hidden = isInfinite;
    soloCardDesc.textContent = isInfinite
      ? "Enchaînez les portraits sans limite de manches et battez votre record de série sans faute."
      : `Identifiez ${roundCountSelect.value} portraits anonymes et découvrez leur véritable activité après chaque réponse.`;

    const leaderboardModeSelect = document.getElementById(
      "linkedin-leaderboard-mode",
    );
    if (leaderboardModeSelect) {
      leaderboardModeSelect.value = isInfinite ? "infini" : "classique";
    }
    refreshLeaderboard();
  }

  function syncResumeButton() {
    const savedId = localStorage.getItem(soloGameIdKey);
    document.getElementById("linkedin-previous-game").hidden = !savedId;
  }

  function labelChoice(choice) {
    return choice === "linkedin" ? "💼 LinkedIn" : "🚨 Interpol";
  }

  function getRoundResult() {
    if (!state) return null;
    if (gameType === "solo") {
      return state.result || null;
    }
    return state.last_round || null;
  }

  async function refreshLeaderboard() {
    const list = document.getElementById("linkedin-leaderboard");
    const title = document.getElementById("linkedin-leaderboard-title");
    const desc = document.getElementById("linkedin-leaderboard-desc");
    const modeSelect = document.getElementById("linkedin-leaderboard-mode");
    if (!list) return;

    const mode = modeSelect
      ? modeSelect.value
      : soloModeSelect?.value === "solo-infinite"
        ? "infini"
        : "classique";

    if (title) {
      title.textContent =
        mode === "infini"
          ? "Classement solo · Mode infini"
          : "Classement solo · Classique";
    }
    if (desc) {
      desc.textContent =
        mode === "infini"
          ? "Meilleures séries sans la moindre erreur. Le classement récompense la régularité."
          : "Meilleurs scores sur les parties à manches fixes.";
    }

    try {
      const data = await request(
        `/api/game-leaderboard?game_id=linkedin-or-interpol&difficulty=${encodeURIComponent(mode)}`,
      );
      const records = data.records || [];
      list.replaceChildren();
      if (!records.length) {
        const empty = document.createElement("li");
        empty.className = "shared-solo-leaderboard-empty";
        empty.textContent =
          mode === "infini"
            ? "Aucune série enregistrée pour le moment. Lancez une partie infinie !"
            : "Aucun score enregistré pour le moment. Lancez une partie !";
        list.append(empty);
        return;
      }
      records.forEach((record, index) => {
        const item = document.createElement("li");
        const rank = document.createElement("span");
        rank.className = "shared-solo-leaderboard-rank";
        rank.textContent = `${index + 1}.`;

        const name = document.createElement("span");
        name.className = "shared-solo-leaderboard-player";
        name.textContent = record.player_name || "Joueur";

        const detail = document.createElement("span");
        detail.className = "shared-solo-leaderboard-detail";
        const pts = Number(record.points ?? record.best_score ?? record.best_streak ?? 0);
        if (mode === "infini") {
          const played = record.metrics?.rounds || record.attempts;
          detail.textContent = played
            ? `🔥 Série de ${pts} · ${played} portrait${played > 1 ? "s" : ""}`
            : `🔥 Série de ${pts}`;
        } else {
          const rounds = record.metrics?.rounds || record.attempts || 10;
          const streak = record.metrics?.best_streak ?? record.best_streak;
          detail.textContent =
            streak > 0
              ? `${pts} / ${rounds} pts · série max ${streak}`
              : `${pts} / ${rounds} pts`;
        }

        item.append(rank, name, detail);
        list.append(item);
      });
    } catch (error) {
      list.replaceChildren();
      const empty = document.createElement("li");
      empty.className = "shared-solo-leaderboard-empty";
      empty.textContent = `Classement indisponible : ${error.message}`;
      list.append(empty);
    }
  }

  function getCollectionKey() {
    if (playerName && playerName !== "Joueur") {
      return `linkedin_collection_${encodeURIComponent(playerName.toLowerCase())}`;
    }
    return collectionKey;
  }

  function loadCollectionState() {
    try {
      const key = getCollectionKey();
      let raw = localStorage.getItem(key);
      if (!raw && key !== collectionKey) {
        raw = localStorage.getItem(collectionKey);
        if (raw) localStorage.setItem(key, raw);
      }
      return raw ? JSON.parse(raw) : {};
    } catch {
      return {};
    }
  }

  function saveCollectionState(collection) {
    localStorage.setItem(getCollectionKey(), JSON.stringify(collection));
  }

  function updateCollectionBadges(collection) {
    const col = collection || loadCollectionState();
    const found = Object.values(col).filter((entry) => entry?.found).length;
    const total = cachedCatalog?.length || 174;
    const pct = Math.min(100, Math.round((found / total) * 100));

    const countBadge = document.getElementById("linkedin-catalog-count-badge");
    if (countBadge) {
      countBadge.textContent = `${found}/${total}`;
    }

    const homeDesc = document.getElementById("linkedin-home-collection-desc");
    if (homeDesc) {
      homeDesc.textContent = `${found} sur ${total} portraits débloqués (${pct}%) au fil de vos enquêtes.`;
    }
  }

  function recordCollectionEntry(resultOrList) {
    if (!resultOrList) return { count: 0, isNew: false };
    const items = Array.isArray(resultOrList) ? resultOrList : [resultOrList];
    const collection = loadCollectionState();
    let isNew = false;
    let modified = false;

    for (const res of items) {
      const personId = res.person_id || res.id;
      if (!personId) continue;
      const existing = collection[personId];
      if (!existing || !existing.found) {
        isNew = true;
        lastDiscoveredPersonId = personId;
      }
      const name =
        res.full_name ||
        `${res.name || ""} ${res.surname || ""}`.trim() ||
        existing?.name ||
        "Profil";

      const currentGameId = state?.game_id || state?.room_id || null;
      const alreadyCountedInRound =
        existing &&
        existing.last_seen_game === currentGameId &&
        existing.last_seen_round === res.round_number;

      collection[personId] = {
        seen: Number(existing?.seen || 0) + (alreadyCountedInRound ? 0 : 1),
        found: true,
        name,
        answer: res.answer || res.label || existing?.answer,
        discovered_at: existing?.discovered_at || new Date().toISOString(),
        last_seen_game: currentGameId,
        last_seen_round: res.round_number,
      };
      modified = true;
    }

    if (modified) {
      saveCollectionState(collection);
      updateCollectionBadges(collection);
    }
    return { isNew };
  }

  function renderCollectionSummary(catalog, collection) {
    const summary = document.getElementById("linkedin-catalog-summary");
    const progressBar = document.getElementById(
      "linkedin-catalog-progress-bar",
    );
    if (!summary) return;

    const found = catalog.filter((entry) => collection[entry.id]?.found).length;
    const total = catalog.length || 174;
    const pct = Math.min(100, Math.round((found / total) * 100));
    const ultraFound = catalog.filter(
      (entry) => entry.rarity_rank === 1 && collection[entry.id]?.found,
    ).length;
    const ultraTotal = catalog.filter(
      (entry) => entry.rarity_rank === 1,
    ).length;

    summary.innerHTML = `<strong>${found}</strong> / ${total} profils découverts (${pct}%) · <strong>${ultraFound}</strong> / ${ultraTotal} ultra-rares`;

    if (progressBar) {
      progressBar.style.width = `${pct}%`;
    }

    const tabBtns = document.querySelectorAll(".linkedin-tab-btn");
    tabBtns.forEach((btn) => {
      const filter = btn.dataset.catalogFilter;
      if (filter === "all") btn.textContent = `Tous (${total})`;
      else if (filter === "known") btn.textContent = `Découverts (${found})`;
      else if (filter === "locked")
        btn.textContent = `À découvrir (${total - found})`;
    });
  }

  function renderCatalogGrid(catalog, collection) {
    const grid = document.getElementById("linkedin-catalog-grid");
    if (!grid) return;

    const query = catalogSearchQuery.trim().toLowerCase();
    const filtered = catalog.filter((entry) => {
      const isKnown = Boolean(collection[entry.id]?.found);
      if (catalogFilter === "known" && !isKnown) return false;
      if (catalogFilter === "locked" && isKnown) return false;
      if (query) {
        if (!isKnown) return false;
        const fullName =
          `${entry.name || ""} ${entry.surname || ""}`.toLowerCase();
        if (!fullName.includes(query)) return false;
      }
      return true;
    });

    if (!filtered.length) {
      const empty = document.createElement("div");
      empty.className = "linkedin-catalog-empty";
      empty.textContent = query
        ? "Aucun profil débloqué ne correspond à cette recherche."
        : catalogFilter === "known"
          ? "Aucun profil découvert pour le moment. Jouez pour enrichir votre collection !"
          : "Félicitations ! Vous avez débloqué tous les profils de cette catégorie.";
      grid.replaceChildren(empty);
      return;
    }

    grid.replaceChildren(
      ...filtered.map((entry) => {
        const card = document.createElement("article");
        const known = Boolean(collection[entry.id]?.found);
        card.className = `linkedin-catalog-card ${known ? "is-known" : "is-locked"} rarity-${entry.rarity_rank || 4}`;

        const imageWrap = document.createElement("div");
        imageWrap.className = `linkedin-catalog-image-wrap ${known ? "is-known" : "is-locked"}`;

        if (known) {
          const img = document.createElement("img");
          img.className = "linkedin-catalog-photo";
          img.src = entry.image_url || "";
          img.loading = "lazy";
          const fullName =
            `${entry.name || ""} ${entry.surname || ""}`.trim() || "Profil";
          img.alt = fullName;
          imageWrap.append(img);

          const typePill = document.createElement("span");
          const isLinkedIn = entry.label === "linkedin";
          typePill.className = `linkedin-catalog-type-pill ${isLinkedIn ? "linkedin" : "interpol"}`;
          typePill.textContent = isLinkedIn ? "💼 LinkedIn" : "🚨 Interpol";
          imageWrap.append(typePill);
        } else {
          // Dark mystery silhouette avatar
          const silhouette = document.createElement("div");
          silhouette.className = "linkedin-catalog-avatar-silhouette";
          silhouette.setAttribute("aria-hidden", "true");
          silhouette.innerHTML = `
            <svg viewBox="0 0 100 100" class="linkedin-silhouette-svg">
              <circle cx="50" cy="36" r="22" fill="#000000" />
              <path d="M18 92 C18 66 32 56 50 56 C68 56 82 66 82 92 Z" fill="#000000" />
            </svg>
            <span class="linkedin-silhouette-lock">🔒</span>
          `;
          const unknownPill = document.createElement("span");
          unknownPill.className = "linkedin-catalog-type-pill is-unknown";
          unknownPill.textContent = "❓ Mystère";
          imageWrap.append(silhouette, unknownPill);
        }

        const header = document.createElement("div");
        header.className = "linkedin-catalog-card-header";

        const title = document.createElement("p");
        title.className = `linkedin-catalog-card-name ${known ? "" : "is-masked"}`;
        const displayName = known
          ? `${entry.name || ""} ${entry.surname || ""}`.trim() || "Profil"
          : "???";
        title.textContent = displayName;
        title.title = displayName;

        const rarity = document.createElement("span");
        rarity.className = `linkedin-catalog-card-rarity rarity-${entry.rarity_rank || 4}`;
        rarity.textContent = entry.rarity_label || "Commune";
        header.append(title, rarity);

        const meta = document.createElement("div");
        meta.className = "linkedin-catalog-card-meta";

        const badge = document.createElement("span");
        badge.className = `linkedin-catalog-card-badge ${known ? "is-discovered" : "unknown"}`;
        badge.textContent = known ? "✓ Découvert" : "🔒 Non découvert";

        const views = document.createElement("span");
        if (known) {
          const count = collection[entry.id]?.seen || entry.seen_total || 1;
          views.textContent = `Vu ${count} fois`;
        } else {
          views.textContent = "À débloquer";
        }
        meta.append(badge, views);

        card.append(imageWrap, header, meta);
        return card;
      }),
    );
  }

  async function openCatalog() {
    const overlay = document.getElementById("linkedin-catalog-overlay");
    if (!overlay) return;
    try {
      const collection = loadCollectionState();
      if (!cachedCatalog) {
        const response = await request("/api/linkedin-or-interpol/catalog");
        cachedCatalog = response.catalog || [];
      }
      renderCollectionSummary(cachedCatalog, collection);
      renderCatalogGrid(cachedCatalog, collection);
      overlay.hidden = false;
    } catch (error) {
      showError(homeError, error.message);
      overlay.hidden = true;
    }
  }

  function closeCatalog() {
    const overlay = document.getElementById("linkedin-catalog-overlay");
    if (overlay) overlay.hidden = true;
  }

  async function refreshRooms() {
    const directory = document.getElementById("linkedin-room-directory");
    if (!directory) return;
    try {
      const data = await request(
        `/api/linkedin-or-interpol/rooms?player_id=${encodeURIComponent(playerId)}`,
      );
      const rooms = data.rooms || [];
      directory.replaceChildren();
      if (!rooms.length) {
        const empty = document.createElement("p");
        empty.className = "linkedin-room-empty";
        empty.textContent = "Aucun salon public ouvert pour le moment.";
        directory.append(empty);
        return;
      }
      rooms.forEach((room) => {
        const card = document.createElement("div");
        card.className = "linkedin-room-card";

        const copy = document.createElement("div");
        copy.className = "linkedin-room-card-copy";
        const title = document.createElement("strong");
        title.textContent = `Salon ${room.room_id}${room.host_name ? ` · Hôte : ${room.host_name}` : ""}`;
        const meta = document.createElement("small");
        const statusLabel =
          room.status === "playing"
            ? `Manche ${room.round_number}/${room.round_count}`
            : "En attente de joueurs";
        meta.textContent = `${statusLabel} · ${room.player_count}/${room.max_players} joueurs · ${room.round_count} manches`;
        copy.append(title, meta);

        const joinBtn = document.createElement("button");
        joinBtn.type = "button";
        joinBtn.className = room.is_member
          ? "linkedin-primary-button"
          : "linkedin-secondary-button";
        joinBtn.textContent = room.is_member
          ? "Reprendre"
          : room.status === "playing"
            ? "Observer"
            : "Rejoindre";
        joinBtn.addEventListener("click", () => joinRoom(room.room_id));

        card.append(copy, joinBtn);
        directory.append(card);
      });
    } catch (error) {
      directory.replaceChildren();
      const empty = document.createElement("p");
      empty.className = "linkedin-room-empty";
      empty.textContent = `Impossible de charger les salons : ${error.message}`;
      directory.append(empty);
    }
  }

  function stopPolling() {
    if (pollTimer) {
      window.clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  function startPolling() {
    stopPolling();
    if (gameType !== "room") return;
    pollTimer = window.setInterval(async () => {
      if (pollInFlight || busy || !state?.room_id || playSection.hidden) return;
      pollInFlight = true;
      try {
        state = await request(
          `/api/linkedin-or-interpol/room/${encodeURIComponent(state.room_id)}?player_id=${encodeURIComponent(playerId)}`,
        );
        renderGame();
      } catch (error) {
        showError(playError, error.message);
      } finally {
        pollInFlight = false;
      }
    }, 1200);
  }

  function showPlayPanel() {
    homeSection.hidden = true;
    playSection.hidden = false;
    hideError(homeError);
    hideError(playError);
    renderGame();
  }

  async function leaveToHome() {
    stopPolling();
    lastDiscoveredPersonId = null;
    if (gameType === "room" && state?.room_id) {
      try {
        await post("/api/linkedin-or-interpol/room/leave", {
          room_id: state.room_id,
          player_id: playerId,
        });
      } catch (error) {
        showError(playError, error.message);
        return;
      }
    }
    state = null;
    gameType = null;
    playSection.hidden = true;
    homeSection.hidden = false;
    hideError(homeError);
    hideError(playError);
    history.replaceState(null, "", window.location.pathname);
    syncResumeButton();
    refreshLeaderboard();
    refreshRooms();
  }

  async function startSolo() {
    if (busy) return;
    busy = true;
    lastDiscoveredPersonId = null;
    hideError(homeError);
    hideError(playError);
    const mode =
      soloModeSelect.value === "solo-infinite" ? "solo-infinite" : "solo";
    const roundCount = Number(roundCountSelect.value) || 10;
    try {
      state = await post("/api/linkedin-or-interpol/solo/new", {
        ...playerPayload(),
        mode,
        round_count: roundCount,
      });
      localStorage.setItem(soloGameIdKey, state.game_id);
      gameType = "solo";
      history.replaceState(null, "", window.location.pathname);
      showPlayPanel();
    } catch (error) {
      showError(playSection.hidden ? homeError : playError, error.message);
    } finally {
      busy = false;
      renderGame();
    }
  }

  async function resumeSolo() {
    const savedId = localStorage.getItem(soloGameIdKey);
    if (!savedId) return startSolo();
    if (busy) return;
    busy = true;
    lastDiscoveredPersonId = null;
    hideError(homeError);
    try {
      state = await request(
        `/api/linkedin-or-interpol/solo/${encodeURIComponent(savedId)}?player_id=${encodeURIComponent(playerId)}`,
      );
      if (state.status === "finished") {
        localStorage.removeItem(soloGameIdKey);
        syncResumeButton();
        busy = false;
        return startSolo();
      }
      gameType = "solo";
      showPlayPanel();
    } catch (error) {
      localStorage.removeItem(soloGameIdKey);
      syncResumeButton();
      showError(homeError, error.message);
    } finally {
      busy = false;
      renderGame();
    }
  }

  async function createRoom() {
    if (busy) return;
    busy = true;
    hideError(homeError);
    const roundCount = Number(roomRoundCountSelect.value) || 10;
    try {
      state = await post("/api/linkedin-or-interpol/room/create", {
        ...playerPayload(),
        round_count: roundCount,
      });
      gameType = "room";
      history.replaceState(
        null,
        "",
        `${window.location.pathname}?room=${encodeURIComponent(state.room_id)}`,
      );
      showPlayPanel();
      startPolling();
    } catch (error) {
      showError(homeError, error.message);
    } finally {
      busy = false;
      renderGame();
    }
  }

  async function joinRoom(rawCode) {
    const code = (rawCode || "").trim().toUpperCase();
    if (!code) {
      showError(homeError, "Saisissez un code de salon à 6 caractères.");
      return;
    }
    if (busy) return;
    busy = true;
    hideError(homeError);
    try {
      state = await post("/api/linkedin-or-interpol/room/join", {
        ...playerPayload(),
        room_id: code,
      });
      gameType = "room";
      history.replaceState(
        null,
        "",
        `${window.location.pathname}?room=${encodeURIComponent(state.room_id)}`,
      );
      showPlayPanel();
      startPolling();
    } catch (error) {
      showError(homeError, error.message);
    } finally {
      busy = false;
      renderGame();
    }
  }

  async function startRoomGame() {
    if (busy || gameType !== "room" || !state?.room_id) return;
    busy = true;
    hideError(playError);
    renderGame();
    try {
      state = await post("/api/linkedin-or-interpol/room/start", {
        ...playerPayload(),
        room_id: state.room_id,
      });
    } catch (error) {
      showError(playError, error.message);
    } finally {
      busy = false;
      renderGame();
    }
  }

  async function submitChoice(choice) {
    if (busy || !state || state.status !== "playing") return;
    if (gameType === "solo" && state.awaiting_next) return;
    if (
      gameType === "room" &&
      (state.is_spectator ||
        state.player?.submitted ||
        state.awaiting_next_round)
    )
      return;

    busy = true;
    hideError(playError);
    renderGame();
    try {
      if (gameType === "solo") {
        state = await post("/api/linkedin-or-interpol/solo/guess", {
          ...playerPayload(),
          game_id: state.game_id,
          guess: choice,
        });
        recordCollectionEntry(state.result || null);
        if (state.status === "finished") {
          recordCollectionEntry(state.results || state.result);
          localStorage.removeItem(soloGameIdKey);
          syncResumeButton();
          refreshLeaderboard();
          window.setTimeout(refreshLeaderboard, 500);
        }
      } else {
        state = await post("/api/linkedin-or-interpol/room/guess", {
          ...playerPayload(),
          room_id: state.room_id,
          guess: choice,
        });
        recordCollectionEntry(state.last_round || null);
        if (state.status === "finished") {
          refreshLeaderboard();
          window.setTimeout(refreshLeaderboard, 500);
        }
      }
    } catch (error) {
      showError(playError, error.message);
    } finally {
      busy = false;
      renderGame();
    }
  }

  async function advanceNextRound() {
    if (busy || !state || state.status !== "playing") return;
    busy = true;
    lastDiscoveredPersonId = null;
    hideError(playError);
    renderGame();
    try {
      if (gameType === "solo") {
        state = await post("/api/linkedin-or-interpol/solo/next", {
          ...playerPayload(),
          game_id: state.game_id,
        });
      } else {
        state = await post("/api/linkedin-or-interpol/room/next", {
          ...playerPayload(),
          room_id: state.room_id,
        });
      }
    } catch (error) {
      showError(playError, error.message);
    } finally {
      busy = false;
      renderGame();
    }
  }

  async function restartRoomGame() {
    if (busy || gameType !== "room" || !state?.room_id) return;
    busy = true;
    hideError(playError);
    renderGame();
    try {
      state = await post("/api/linkedin-or-interpol/room/restart", {
        ...playerPayload(),
        room_id: state.room_id,
      });
    } catch (error) {
      showError(playError, error.message);
    } finally {
      busy = false;
      renderGame();
    }
  }

  function renderLobby() {
    const lobby = document.getElementById("linkedin-lobby");
    const isLobby = gameType === "room" && state?.status === "lobby";
    lobby.hidden = !isLobby;
    if (!isLobby) return;

    document.getElementById("linkedin-lobby-status").textContent =
      state.can_start
        ? `${state.player_count}/${state.max_players} joueurs prêts · ${state.round_count} manches.`
        : `${state.player_count}/${state.max_players} joueurs · Il faut au moins 2 joueurs pour lancer la partie.`;
    document.getElementById("linkedin-invite-code").textContent = state.room_id;

    const inviteUrl = new URL(window.location.href);
    inviteUrl.search = new URLSearchParams({ room: state.room_id }).toString();
    document.getElementById("linkedin-copy-invite").dataset.inviteUrl =
      inviteUrl.href;

    const list = document.getElementById("linkedin-player-list");
    list.replaceChildren(
      ...state.players.map((player) => {
        const item = document.createElement("li");
        const name = document.createElement("span");
        name.textContent = `${player.name}${player.player_id === state.host_player_id ? " · Hôte" : ""}`;
        const badge = document.createElement("small");
        badge.textContent = player.is_spectator ? "Observateur" : "Prêt";
        item.append(name, badge);
        return item;
      }),
    );

    const startBtn = document.getElementById("linkedin-start-game");
    startBtn.hidden = state.host_player_id !== playerId;
    startBtn.disabled = !state.can_start || busy;
  }

  function renderRevealCard(roundResult) {
    const mysteryBanner = document.getElementById("linkedin-mystery-banner");
    const revealCard = document.getElementById("linkedin-reveal-card");
    const verdictBadge = document.getElementById("linkedin-verdict-badge");
    const answerPill = document.getElementById("linkedin-answer-pill");
    const personName = document.getElementById("linkedin-person-name");
    const personDescription = document.getElementById(
      "linkedin-person-description",
    );
    const specialMessage = document.getElementById("linkedin-special-message");
    const photoBadge = document.getElementById("linkedin-photo-badge");
    const discoveryBadge = document.getElementById("linkedin-discovery-badge");

    if (!roundResult) {
      mysteryBanner.hidden = false;
      revealCard.hidden = true;
      revealCard.classList.remove("is-correct", "is-wrong");
      personName.textContent = "";
      personDescription.textContent = "";
      specialMessage.hidden = true;
      specialMessage.textContent = "";
      photoBadge.textContent = "Portrait mystère";
      if (discoveryBadge) discoveryBadge.hidden = true;
      return;
    }

    mysteryBanner.hidden = true;
    revealCard.hidden = false;

    // S'assurer que le profil dévoilé est bien enregistré dans la collection
    recordCollectionEntry(roundResult);

    if (discoveryBadge) {
      const isNew = Boolean(
        roundResult.person_id &&
          roundResult.person_id === lastDiscoveredPersonId,
      );
      discoveryBadge.hidden = !isNew;
    }

    const ownResult =
      gameType === "room"
        ? roundResult.guesses?.find((entry) => entry.player_id === playerId)
        : roundResult;
    const isCorrect = Boolean(ownResult?.correct);

    revealCard.classList.toggle("is-correct", isCorrect);
    revealCard.classList.toggle("is-wrong", !isCorrect);

    if (gameType === "room" && state.is_spectator) {
      verdictBadge.textContent = "Dossier révélé";
      verdictBadge.className = "linkedin-verdict-badge is-correct";
    } else {
      verdictBadge.textContent = isCorrect ? "✓ Bien vu ! (+1 pt)" : "✗ Raté !";
      verdictBadge.className = `linkedin-verdict-badge ${isCorrect ? "is-correct" : "is-wrong"}`;
    }

    const answer = roundResult.answer;
    answerPill.textContent =
      answer === "linkedin" ? "💼 Profil LinkedIn" : "🚨 Notice Interpol";
    answerPill.className = `linkedin-answer-pill ${answer === "linkedin" ? "is-linkedin" : "is-interpol"}`;

    photoBadge.textContent =
      answer === "linkedin" ? "💼 LinkedIn" : "🚨 Interpol";

    const fullName =
      roundResult.full_name ||
      `${roundResult.name || ""} ${roundResult.surname || ""}`.trim() ||
      "Identité révélée";
    personName.textContent = fullName;
    personDescription.textContent =
      roundResult.description || "Aucune description complémentaire.";

    const message = ownResult?.message || roundResult.message;
    if (message) {
      specialMessage.textContent = message;
      specialMessage.hidden = false;
    } else {
      specialMessage.textContent = "";
      specialMessage.hidden = true;
    }
  }

  function renderMultiplayerRoundGuesses(roundResult) {
    const container = document.getElementById("linkedin-round-guesses");
    const list = document.getElementById("linkedin-round-guesses-list");
    if (
      gameType !== "room" ||
      !roundResult ||
      !Array.isArray(roundResult.guesses)
    ) {
      container.hidden = true;
      list.replaceChildren();
      return;
    }
    container.hidden = false;
    list.replaceChildren(
      ...roundResult.guesses.map((entry) => {
        const item = document.createElement("li");
        const name = document.createElement("strong");
        name.textContent = entry.name;

        const tag = document.createElement("span");
        tag.className = `linkedin-guess-tag ${entry.correct ? "is-correct" : "is-wrong"}`;
        const choiceLabel = entry.guess
          ? labelChoice(entry.guess)
          : "Sans réponse";
        tag.textContent = `${choiceLabel} · ${entry.correct ? "+1 pt" : "0 pt"}`;

        item.append(name, tag);
        return item;
      }),
    );
  }

  function renderLivePlayers() {
    const container = document.getElementById("linkedin-live-players");
    const list = document.getElementById("linkedin-live-players-list");
    const counter = document.getElementById("linkedin-answered-counter");

    if (gameType !== "room" || !state) {
      container.hidden = true;
      list.replaceChildren();
      return;
    }

    container.hidden = false;
    const activePlayers = state.players.filter(
      (player) => !player.is_spectator,
    );
    counter.textContent = `${state.answered_count || 0}/${activePlayers.length} ont répondu`;

    const sorted = [...state.players].sort(
      (left, right) =>
        right.score - left.score || left.name.localeCompare(right.name, "fr"),
    );
    list.replaceChildren(
      ...sorted.map((player) => {
        const item = document.createElement("li");
        const left = document.createElement("span");
        left.textContent = `${player.name}${player.player_id === state.host_player_id ? " (hôte)" : ""}`;

        const right = document.createElement("small");
        if (player.is_spectator) {
          right.textContent = "Observateur";
        } else if (state.status === "playing" && !state.awaiting_next_round) {
          right.textContent = player.submitted
            ? `✓ Répondu · ${player.score} pt${player.score === 1 ? "" : "s"}`
            : `En réflexion… · ${player.score} pt${player.score === 1 ? "" : "s"}`;
        } else {
          right.textContent = `${player.score} pt${player.score === 1 ? "" : "s"} · série ${player.best_streak || 0}`;
        }

        item.append(left, right);
        return item;
      }),
    );
  }

  function renderFinalScoreboard() {
    const card = document.getElementById("linkedin-final-card");
    const title = document.getElementById("linkedin-final-title");
    const summary = document.getElementById("linkedin-final-summary");
    const rankings = document.getElementById("linkedin-final-rankings");
    const replaySoloBtn = document.getElementById("linkedin-replay-solo");
    const restartRoomBtn = document.getElementById("linkedin-restart-room");

    if (!state || state.status !== "finished") {
      card.hidden = true;
      rankings.replaceChildren();
      return;
    }

    card.hidden = false;
    replaySoloBtn.hidden = gameType !== "solo";
    restartRoomBtn.hidden = !(
      gameType === "room" && state.host_player_id === playerId
    );
    restartRoomBtn.disabled = busy;

    if (gameType === "solo") {
      if (state.mode === "solo-infinite") {
        title.textContent = "Fin de série !";
        summary.textContent = `Vous avez atteint une série de ${state.best_streak} bonne${state.best_streak > 1 ? "s" : ""} réponse${state.best_streak > 1 ? "s" : ""} d’affilée.`;
      } else {
        title.textContent = "Partie solo terminée";
        summary.textContent = `Score final : ${state.score} / ${state.round_count} · Meilleure série : ${state.best_streak}.`;
      }
      rankings.replaceChildren();
      const item = document.createElement("li");
      const name = document.createElement("span");
      name.textContent = playerName;
      const score = document.createElement("strong");
      score.textContent =
        state.mode === "solo-infinite"
          ? `🔥 Série record : ${state.best_streak}`
          : `${state.score} / ${state.round_count} pts`;
      item.append(name, score);
      rankings.append(item);
      return;
    }

    const activePlayers = state.players.filter(
      (player) => !player.is_spectator,
    );
    const sorted = [...activePlayers].sort(
      (left, right) =>
        right.score - left.score || right.best_streak - left.best_streak,
    );
    const winner = sorted[0];
    title.textContent = winner
      ? `Victoire de ${winner.name} !`
      : "Partie terminée";
    summary.textContent = `Match #${state.match_number || 1} terminé sur ${state.round_count} manches.`;

    rankings.replaceChildren(
      ...sorted.map((player, index) => {
        const item = document.createElement("li");
        const label = document.createElement("span");
        label.textContent = `${index + 1}. ${player.name}`;
        const score = document.createElement("strong");
        score.textContent = `${player.score} / ${state.round_count} pts · série max ${player.best_streak || 0}`;
        item.append(label, score);
        return item;
      }),
    );
  }

  function renderHistory() {
    const card = document.getElementById("linkedin-history-card");
    const list = document.getElementById("linkedin-history-list");
    const historyItems = gameType === "solo" ? state?.results || [] : [];

    if (!historyItems.length) {
      card.hidden = true;
      list.replaceChildren();
      return;
    }

    card.hidden = false;
    list.replaceChildren(
      ...[...historyItems].reverse().map((entry) => {
        const item = document.createElement("article");
        item.className = "linkedin-history-item";

        const img = document.createElement("img");
        img.className = "linkedin-history-thumb";
        img.src = entry.image_url || "";
        img.alt = entry.full_name || "Portrait";

        const copy = document.createElement("div");
        copy.className = "linkedin-history-copy";

        const title = document.createElement("strong");
        const badge = entry.answer === "linkedin" ? "💼" : "🚨";
        const verdict = entry.correct ? "✓" : "✗";
        title.textContent = `${verdict} ${badge} ${entry.full_name || entry.name || "Profil"}`;

        const desc = document.createElement("small");
        desc.textContent = entry.description || "";

        copy.append(title, desc);
        item.append(img, copy);
        return item;
      }),
    );
  }

  function renderGame() {
    if (!state) return;

    const isLobby = gameType === "room" && state.status === "lobby";
    renderLobby();
    document.getElementById("linkedin-round").hidden = isLobby;
    document.getElementById("linkedin-new-solo").hidden = gameType !== "solo";

    const modeLabel = document.getElementById("linkedin-game-mode");
    const gameTitle = document.getElementById("linkedin-game-title");

    if (gameType === "room") {
      modeLabel.textContent = `Salon multijoueur · ${state.room_id}`;
      gameTitle.textContent = isLobby
        ? `Salon ${state.room_id}`
        : state.status === "finished"
          ? "Résultats de la partie"
          : `Manche ${state.round_number} sur ${state.round_count}`;
    } else {
      modeLabel.textContent =
        state.mode === "solo-infinite"
          ? "Solo · Série infinie"
          : "Solo · Classique";
      gameTitle.textContent =
        state.status === "finished"
          ? "Bilan de votre partie"
          : state.mode === "solo-infinite"
            ? `Portrait #${state.round_number}`
            : `Manche ${state.round_number} sur ${state.round_count}`;
    }

    if (isLobby) return;

    const ownScore =
      gameType === "room" ? (state.player?.score ?? 0) : (state.score ?? 0);
    const ownStreak =
      gameType === "room" ? (state.player?.streak ?? 0) : (state.streak ?? 0);
    const ownBest =
      gameType === "room"
        ? (state.player?.best_streak ?? 0)
        : (state.best_streak ?? 0);

    document.getElementById("linkedin-stat-round").textContent =
      state.round_count
        ? `${state.round_number} / ${state.round_count}`
        : `#${state.round_number}`;
    document.getElementById("linkedin-stat-score").textContent =
      `${ownScore} pt${ownScore === 1 ? "" : "s"}`;
    document.getElementById("linkedin-stat-streak").textContent =
      `🔥 ${ownStreak}`;
    document.getElementById("linkedin-stat-best").textContent = `${ownBest}`;

    const progressTrack = document.getElementById("linkedin-progress-track");
    const progressBar = document.getElementById("linkedin-progress-bar");
    if (state.round_count) {
      progressTrack.hidden = false;
      const pct = Math.min(
        100,
        Math.round((state.round_number / state.round_count) * 100),
      );
      progressBar.style.width = `${pct}%`;
    } else {
      progressTrack.hidden = true;
    }

    document.getElementById("linkedin-spectator-banner").hidden = !(
      gameType === "room" && state.is_spectator
    );

    const roundResult = getRoundResult();
    const person = roundResult?.person || state.current_person;
    const imageEl = document.getElementById("linkedin-person-image");
    if (person?.image_url && imageEl.getAttribute("src") !== person.image_url) {
      imageEl.src = person.image_url;
    }

    renderRevealCard(roundResult);

    // Choice buttons state
    const choicesCard = document.getElementById("linkedin-choices-card");
    if (choicesCard) {
      choicesCard.hidden = state.status === "finished";
    }

    const linkedinBtn = document.getElementById("linkedin-choice-linkedin");
    const interpolBtn = document.getElementById("linkedin-choice-interpol");
    const waitingStatus = document.getElementById("linkedin-waiting-status");

    const submittedInRoom =
      gameType === "room" && Boolean(state.player?.submitted);
    const ownGuess =
      gameType === "room"
        ? roundResult?.guesses?.find((g) => g.player_id === playerId)?.guess ||
          state.player?.guess
        : roundResult?.guess;

    const disableChoices = Boolean(
      busy ||
      state.status !== "playing" ||
      roundResult ||
      submittedInRoom ||
      (gameType === "room" && state.is_spectator),
    );

    linkedinBtn.disabled = disableChoices;
    interpolBtn.disabled = disableChoices;

    [linkedinBtn, interpolBtn].forEach((btn) => {
      const choice = btn.dataset.choice;
      btn.classList.toggle("is-selected", ownGuess === choice);
      btn.classList.toggle(
        "is-correct-answer",
        Boolean(roundResult && roundResult.answer === choice),
      );
      btn.classList.toggle(
        "is-wrong-guess",
        Boolean(
          roundResult &&
          ownGuess === choice &&
          roundResult.answer !== choice &&
          roundResult.special_case !== "friend",
        ),
      );
    });

    if (
      gameType === "room" &&
      submittedInRoom &&
      !roundResult &&
      state.status === "playing"
    ) {
      waitingStatus.hidden = false;
      waitingStatus.textContent = `Votre choix (${labelChoice(ownGuess)}) est verrouillé. En attente des autres joueurs (${state.answered_count}/${state.player_count})…`;
    } else {
      waitingStatus.hidden = true;
      waitingStatus.textContent = "";
    }

    // Next round button
    const nextCard = document.getElementById("linkedin-next-card");
    const nextButton = document.getElementById("linkedin-next-button");
    const waitingHost = document.getElementById("linkedin-waiting-host");

    const canSoloNext =
      gameType === "solo" &&
      state.status === "playing" &&
      Boolean(state.awaiting_next);
    const canRoomNext =
      gameType === "room" &&
      state.status === "playing" &&
      Boolean(state.awaiting_next_round);

    if (canSoloNext) {
      nextCard.hidden = false;
      nextButton.hidden = false;
      nextButton.disabled = busy;
      nextButton.textContent = "Personne suivante →";
      waitingHost.hidden = true;
    } else if (canRoomNext) {
      nextCard.hidden = false;
      const isHost = state.host_player_id === playerId;
      nextButton.hidden = !isHost;
      nextButton.disabled = busy;
      nextButton.textContent = "Manche suivante →";
      waitingHost.hidden = isHost;
    } else {
      nextCard.hidden = true;
    }

    renderMultiplayerRoundGuesses(roundResult);
    renderLivePlayers();
    renderFinalScoreboard();
    renderHistory();
  }

  // Event listeners
  soloModeSelect.addEventListener("change", syncSoloModeControls);
  roundCountSelect.addEventListener("change", syncSoloModeControls);

  document
    .getElementById("linkedin-open-catalog")
    ?.addEventListener("click", openCatalog);
  document
    .getElementById("linkedin-home-open-catalog")
    ?.addEventListener("click", openCatalog);
  document
    .getElementById("linkedin-close-catalog")
    ?.addEventListener("click", closeCatalog);
  document
    .getElementById("linkedin-catalog-overlay")
    ?.addEventListener("click", (event) => {
      if (event.target === event.currentTarget) closeCatalog();
    });

  document.querySelectorAll(".linkedin-tab-btn").forEach((btn) => {
    btn.addEventListener("click", (event) => {
      document
        .querySelectorAll(".linkedin-tab-btn")
        .forEach((b) => b.classList.remove("active"));
      event.currentTarget.classList.add("active");
      catalogFilter = event.currentTarget.dataset.catalogFilter || "all";
      if (cachedCatalog) {
        renderCatalogGrid(cachedCatalog, loadCollectionState());
      }
    });
  });

  document
    .getElementById("linkedin-catalog-search")
    ?.addEventListener("input", (event) => {
      catalogSearchQuery = event.target.value || "";
      if (cachedCatalog) {
        renderCatalogGrid(cachedCatalog, loadCollectionState());
      }
    });

  document
    .getElementById("linkedin-leaderboard-mode")
    ?.addEventListener("change", refreshLeaderboard);

  document
    .getElementById("linkedin-solo-button")
    .addEventListener("click", startSolo);
  document
    .getElementById("linkedin-resume-solo")
    .addEventListener("click", resumeSolo);
  document
    .getElementById("linkedin-new-solo")
    .addEventListener("click", startSolo);
  document
    .getElementById("linkedin-replay-solo")
    .addEventListener("click", startSolo);

  document
    .getElementById("linkedin-home-button")
    .addEventListener("click", leaveToHome);
  document
    .getElementById("linkedin-back-home")
    .addEventListener("click", leaveToHome);

  document
    .getElementById("linkedin-create-room")
    .addEventListener("click", createRoom);
  document
    .getElementById("linkedin-join-room")
    .addEventListener("click", () => {
      joinRoom(document.getElementById("linkedin-room-code").value);
    });
  document
    .getElementById("linkedin-room-code")
    .addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        joinRoom(event.currentTarget.value);
      }
    });
  document
    .getElementById("linkedin-refresh-rooms")
    .addEventListener("click", refreshRooms);
  document
    .getElementById("linkedin-start-game")
    .addEventListener("click", startRoomGame);
  document
    .getElementById("linkedin-restart-room")
    .addEventListener("click", restartRoomGame);

  document
    .getElementById("linkedin-copy-invite")
    .addEventListener("click", async (event) => {
      const button = event.currentTarget;
      const url = button.dataset.inviteUrl;
      if (!url) return;
      try {
        await navigator.clipboard.writeText(url);
        button.textContent = "Lien copié !";
        window.setTimeout(() => {
          button.textContent = "Copier le lien";
        }, 1800);
      } catch {
        showError(playError, "Impossible de copier automatiquement le lien.");
      }
    });

  document
    .getElementById("linkedin-choice-linkedin")
    .addEventListener("click", () => submitChoice("linkedin"));
  document
    .getElementById("linkedin-choice-interpol")
    .addEventListener("click", () => submitChoice("interpol"));
  document
    .getElementById("linkedin-next-button")
    .addEventListener("click", advanceNextRound);

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      const overlay = document.getElementById("linkedin-catalog-overlay");
      if (overlay && !overlay.hidden) {
        closeCatalog();
        return;
      }
    }
    if (playSection.hidden || !state || state.status !== "playing") return;
    if (
      event.target instanceof HTMLInputElement ||
      event.target instanceof HTMLSelectElement ||
      event.target instanceof HTMLTextAreaElement
    ) {
      return;
    }
    const key = event.key.toLowerCase();
    const nextButton = document.getElementById("linkedin-next-button");
    const nextCard = document.getElementById("linkedin-next-card");
    if (
      (key === "enter" || key === " ") &&
      !nextCard.hidden &&
      !nextButton.hidden &&
      !nextButton.disabled
    ) {
      event.preventDefault();
      advanceNextRound();
      return;
    }
    if (key === "l" || key === "1") {
      const btn = document.getElementById("linkedin-choice-linkedin");
      if (!btn.disabled) {
        event.preventDefault();
        submitChoice("linkedin");
      }
    } else if (key === "i" || key === "2") {
      const btn = document.getElementById("linkedin-choice-interpol");
      if (!btn.disabled) {
        event.preventDefault();
        submitChoice("interpol");
      }
    }
  });

  // Initialisation
  syncSoloModeControls();
  syncResumeButton();
  updateCollectionBadges();
  refreshLeaderboard();
  refreshRooms();

  request("/api/linkedin-or-interpol/catalog")
    .then((data) => {
      cachedCatalog = data.catalog || [];
      updateCollectionBadges();
    })
    .catch(() => {});

  const requestedRoom = params.get("room");
  if (requestedRoom) {
    joinRoom(requestedRoom);
  }
})();
