(() => {
  const apiBase = window.PEDANTIX_CONFIG?.BACKEND_URL?.replace(/\/+$/, '') || '';
  const home = document.getElementById('memory-home');
  const setup = document.getElementById('memory-multiplayer-setup');
  const gamePanel = document.getElementById('memory-game');
  const lobby = document.getElementById('memory-lobby');
  const playing = document.getElementById('memory-playing');
  const finished = document.getElementById('memory-finished');
  const board = document.getElementById('memory-board');
  const playerName = (
    localStorage.getItem('pedantix_auth_user')
    || localStorage.getItem('pedantix_player_name')
    || 'Joueur'
  ).trim().slice(0, 24) || 'Joueur';
  let playerId = localStorage.getItem('memories_player_id');
  if (!playerId) {
    playerId = globalThis.crypto?.randomUUID?.()
      || `memories-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    localStorage.setItem('memories_player_id', playerId);
  }
  let state = null;
  let mode = null;
  let busy = false;
  let pollingTimer = null;
  let roomPollingInterval = null;
  let soloMismatchTimer = null;
  let soloMismatchHideAt = null;
  let soloClockTimer = null;
  let soloStartedAt = null;
  let soloFlips = [];
  let soloLocalMode = false;
  let soloResultSaving = false;
  let refreshing = false;
  let roomStateRevision = 0;

  document.getElementById('memory-player-name').textContent = playerName;

  async function request(path, options = {}) {
    const response = await fetch(`${apiBase}${path}`, {
      ...options,
      headers: {
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...options.headers,
      },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || 'Une erreur est survenue. Réessayez.');
    return data;
  }

  function post(path, body) {
    return request(path, { method: 'POST', body: JSON.stringify(body) });
  }

  function playerPayload() {
    return { player_id: playerId, player_name: playerName };
  }

  function showError(id, error) {
    const element = document.getElementById(id);
    element.textContent = error.message || String(error);
    element.hidden = false;
  }

  function clearError(id) {
    const element = document.getElementById(id);
    element.textContent = '';
    element.hidden = true;
  }

  function setBusy(button, value, label) {
    if (!button) return;
    if (!button.dataset.label) button.dataset.label = button.textContent;
    button.disabled = value;
    button.textContent = value ? label : button.dataset.label;
  }

  function stopPolling() {
    if (pollingTimer) window.clearInterval(pollingTimer);
    pollingTimer = null;
    roomPollingInterval = null;
    if (soloMismatchTimer) window.clearTimeout(soloMismatchTimer);
    soloMismatchTimer = null;
    soloMismatchHideAt = null;
    if (soloClockTimer) window.clearInterval(soloClockTimer);
    soloClockTimer = null;
    refreshing = false;
  }

  function scheduleRoomPolling() {
    const interval = state?.status === 'finished' ? 3000 : 900;
    if (pollingTimer && roomPollingInterval === interval) return;
    if (pollingTimer) window.clearInterval(pollingTimer);
    roomPollingInterval = interval;
    pollingTimer = window.setInterval(refreshRoom, interval);
  }

  function startPolling() {
    stopPolling();
    if (mode === 'room') {
      scheduleRoomPolling();
    } else if (mode === 'solo') {
      if (soloStartedAt == null) {
        soloStartedAt = Date.now() - (state.elapsed_ms ?? state.elapsed_seconds * 1000);
      }
      updateSoloClock();
      if (state.status === 'playing') {
        soloClockTimer = window.setInterval(updateSoloClock, 100);
        scheduleSoloMismatchHide();
      }
    }
  }

  function formatTime(seconds) {
    const minutes = Math.floor(seconds / 60);
    return `${String(minutes).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
  }

  function formatPreciseTime(milliseconds) {
    const value = Math.max(0, Math.floor(milliseconds));
    return `${formatTime(Math.floor(value / 1000))}.${String(value % 1000).padStart(3, '0')}`;
  }

  function updateSoloClock() {
    if (!state || mode !== 'solo') return;
    const elapsed = state.status === 'finished'
      ? state.elapsed_ms
      : Math.max(0, Date.now() - soloStartedAt);
    document.getElementById('memory-time').textContent = formatPreciseTime(elapsed);
  }

  function scheduleSoloMismatchHide(delayOverride = null) {
    if (soloMismatchTimer) window.clearTimeout(soloMismatchTimer);
    soloMismatchTimer = null;
    if (
      mode !== 'solo'
      || state?.status !== 'playing'
      || state.pending_mismatch_until == null
    ) {
      soloMismatchHideAt = null;
      return;
    }
    if (soloMismatchHideAt == null) {
      const remaining = Number(state.pending_mismatch_remaining_ms);
      const delay = Number.isFinite(remaining)
        ? Math.max(0, remaining)
        : Math.max(0, state.pending_mismatch_until * 1000 - Date.now());
      soloMismatchHideAt = Date.now() + delay;
    }
    const untilHide = Math.max(0, soloMismatchHideAt - Date.now());
    soloMismatchTimer = window.setTimeout(() => {
      if (!state || mode !== 'solo' || state.pending_mismatch_until == null) {
        soloMismatchHideAt = null;
        return;
      }
      if (busy) {
        scheduleSoloMismatchHide(50);
        return;
      }
      if (soloMismatchHideAt > Date.now()) {
        scheduleSoloMismatchHide();
        return;
      }
      state.cards.forEach((card) => {
        if (card.matched) return;
        card.face = null;
        card.opened = false;
      });
      state.pending_mismatch_until = null;
      state.pending_mismatch_remaining_ms = null;
      soloMismatchHideAt = null;
      render();
    }, delayOverride ?? untilHide);
  }

  function readSoloProgress(gameId) {
    const saved = localStorage.getItem('memories_solo_progress');
    if (!saved) return null;
    try {
      const progress = JSON.parse(saved);
      if (
        progress.game_id === gameId
        && Number.isFinite(progress.started_at)
        && Array.isArray(progress.flips)
        && progress.flips.length <= 2000
        && progress.flips.every((index) => Number.isInteger(index))
      ) return progress;
      return null;
    } catch (error) {
      console.warn('Progression Memory locale illisible :', error);
      localStorage.removeItem('memories_solo_progress');
      return null;
    }
  }

  function saveSoloProgress() {
    if (!soloLocalMode || !state || soloStartedAt == null) return;
    localStorage.setItem('memories_solo_progress', JSON.stringify({
      game_id: state.game_id,
      started_at: soloStartedAt,
      flips: soloFlips,
    }));
  }

  function resetLocalSoloState() {
    state.cards = state.deck.map((face, index) => ({
      index,
      face: null,
      matched: false,
      opened: false,
    }));
    state.status = 'playing';
    state.matched_pairs = 0;
    state.moves = 0;
    state.points = 0;
    state.pending_mismatch_until = null;
    state.pending_mismatch_remaining_ms = null;
    state.finished_at = null;
    state.result_saved = false;
  }

  function applyLocalSoloFlip(index, record = true, shouldRender = true) {
    if (
      !state
      || !soloLocalMode
      || state.status !== 'playing'
      || !Number.isInteger(index)
      || index < 0
      || index >= state.cards.length
    ) return false;

    const card = state.cards[index];
    if (state.pending_mismatch_until != null) {
      if (card.opened || card.matched) return false;
      state.cards.forEach((openCard) => {
        if (openCard.opened && !openCard.matched) {
          openCard.face = null;
          openCard.opened = false;
        }
      });
      state.pending_mismatch_until = null;
      state.pending_mismatch_remaining_ms = null;
      soloMismatchHideAt = null;
    }
    if (card.matched || card.opened) return false;

    card.face = state.deck[index];
    card.opened = true;
    if (record) soloFlips.push(index);
    const openedCards = state.cards.filter((item) => item.opened && !item.matched);
    if (openedCards.length === 2) {
      state.moves += 1;
      const [first, second] = openedCards;
      if (first.face === second.face) {
        first.matched = true;
        second.matched = true;
        first.opened = false;
        second.opened = false;
        state.matched_pairs += 1;
        state.points += 100;
        if (state.matched_pairs === state.total_pairs) {
          state.status = 'finished';
          state.elapsed_ms = Math.max(0, Date.now() - soloStartedAt);
          state.elapsed_seconds = Math.floor(state.elapsed_ms / 1000);
        }
      } else {
        state.pending_mismatch_until = Date.now() / 1000 + 1.2;
        state.pending_mismatch_remaining_ms = 1200;
      }
    }

    if (record) saveSoloProgress();
    if (shouldRender) {
      render();
      if (state.status === 'finished') {
        stopPolling();
        void finishSoloResult();
      } else {
        scheduleSoloMismatchHide();
      }
    }
    return true;
  }

  async function finishSoloResult() {
    if (
      !state
      || !soloLocalMode
      || state.status !== 'finished'
      || state.result_saved
      || soloResultSaving
    ) return;
    soloResultSaving = true;
    const deck = state.deck;
    clearError('memory-game-error');
    try {
      const result = await post('/api/memories/solo/finish', {
        ...playerPayload(),
        game_id: state.game_id,
        flips: soloFlips,
        elapsed_ms: state.elapsed_ms,
      });
      state = { ...result, deck };
      render();
      refreshSoloLeaderboard();
    } catch (error) {
      showError('memory-game-error', error);
    } finally {
      soloResultSaving = false;
      render();
    }
  }

  function setScreen(screen) {
    home.hidden = screen !== 'home';
    setup.hidden = screen !== 'setup';
    gamePanel.hidden = screen !== 'game';
  }

  function enterGame(nextMode, nextState, soloProgress = null) {
    mode = nextMode;
    state = nextState;
    soloStartedAt = null;
    soloFlips = [];
    soloLocalMode = false;
    soloResultSaving = false;
    if (mode === 'solo' && Array.isArray(state.deck)) {
      if (state.status === 'finished') {
        if (!state.result_saved) {
          soloLocalMode = true;
          soloStartedAt = Date.now() - (state.elapsed_ms || 0);
          soloFlips = readSoloProgress(state.game_id)?.flips ?? [];
        }
      } else if (state.status === 'playing') {
        const savedProgress = soloProgress?.game_id === state.game_id
          ? soloProgress
          : readSoloProgress(state.game_id);
        const cleanServerGame = state.moves === 0
          && state.matched_pairs === 0
          && !state.cards.some((card) => card.opened || card.matched);
        if (cleanServerGame) {
          soloLocalMode = true;
          soloStartedAt = savedProgress?.started_at ?? Date.now() - (state.elapsed_ms || 0);
          soloFlips = savedProgress?.flips ?? [];
          const serverState = { ...state, cards: state.cards };
          resetLocalSoloState();
          const restored = soloFlips.every((index) => applyLocalSoloFlip(index, false, false));
          if (restored) {
            saveSoloProgress();
          } else {
            console.error('La progression Memory locale ne correspond pas à la partie.');
            state = serverState;
            soloLocalMode = false;
            soloFlips = [];
            soloStartedAt = null;
            localStorage.removeItem('memories_solo_progress');
          }
        }
      }
    }
    setScreen('game');
    document.getElementById('memory-mode-label').textContent =
      mode === 'solo' ? 'Concours solo chronométré' : `Multijoueur · salon ${state.room_id}`;
    document.getElementById('memory-round-heading').textContent =
      `${state.grid_size} × ${state.grid_size} · ${state.total_pairs} paires`;
    render();
    if (state.record_save_error) {
      showError('memory-game-error', new Error(state.record_save_error));
    }
    startPolling();
    if (mode === 'room') localStorage.setItem('memories_active_room_id', state.room_id);
    else localStorage.setItem('memories_solo_game_id', state.game_id);
    if (mode === 'solo' && soloLocalMode && state.status === 'finished') {
      stopPolling();
      void finishSoloResult();
    }
  }

  function renderLobby() {
    lobby.hidden = false;
    playing.hidden = true;
    finished.hidden = true;
    document.getElementById('memory-invite-code').textContent = state.room_id;
    document.getElementById('memory-lobby-summary').textContent =
      `${state.player_count} joueur${state.player_count === 1 ? '' : 's'} · grille ${state.grid_size} × ${state.grid_size} · ${state.total_pairs} paires. Confirmez tous votre présence avant le lancement.`;
    document.getElementById('memory-player-list').replaceChildren(...state.players.map((player) => {
      const item = document.createElement('li');
      const name = document.createElement('span');
      name.textContent = `${player.name}${player.player_id === state.host_player_id ? ' · hôte' : ''}`;
      const ready = document.createElement('small');
      ready.textContent = player.ready ? 'Prêt' : 'En attente de confirmation';
      item.append(name, ready);
      return item;
    }));
    const ready = document.getElementById('memory-ready');
    ready.disabled = busy;
    ready.textContent = state.player.ready ? 'Présence confirmée · annuler' : 'Confirmer ma présence';
    const start = document.getElementById('memory-start');
    start.hidden = state.host_player_id !== playerId;
    start.disabled = busy || !state.can_start;
  }

  function renderScoreboard() {
    const scores = document.getElementById('memory-scoreboard');
    scores.hidden = mode !== 'room';
    scores.replaceChildren();
    if (mode !== 'room') return;
    state.scores.forEach((score) => {
      const item = document.createElement('li');
      const name = document.createElement('span');
      name.textContent = `${score.name}${score.player_id === state.turn_player_id ? ' · joue' : ''}`;
      const detail = document.createElement('small');
      detail.textContent = `${score.pairs} paire${score.pairs === 1 ? '' : 's'} · ${score.points} pts`;
      item.append(name, detail);
      scores.append(item);
    });
  }

  function renderBoard() {
    board.style.setProperty('--memory-grid-size', state.grid_size);
    const isOwnTurn = mode === 'solo' || state.turn_player_id === playerId;
    const locked = busy || state.status !== 'playing'
      || (state.pending_mismatch_until != null && mode !== 'solo')
      || (mode === 'room' && !isOwnTurn);
    const buttons = Array.from(board.children);
    if (
      buttons.length !== state.cards.length
      || buttons.some((button, index) => button.dataset.index !== String(index))
    ) {
      board.replaceChildren(...state.cards.map((card) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'memory-card';
        button.dataset.index = String(card.index);
        button.addEventListener('click', () => {
          const index = Number(button.dataset.index);
          if (Number.isInteger(index)) flipCard(index);
        });
        return button;
      }));
    }
    state.cards.forEach((card) => {
      const button = board.children[card.index];
      const face = card.face || '?';
      if (button.textContent !== face) button.textContent = face;
      const label = card.face
        ? `Carte ${card.index + 1} : ${card.face}${card.matched ? ', paire trouvée' : ''}`
        : `Carte ${card.index + 1}, face cachée`;
      if (button.getAttribute('aria-label') !== label) {
        button.setAttribute('aria-label', label);
      }
      const disabled = locked || card.face != null || card.matched;
      if (button.disabled !== disabled) button.disabled = disabled;
      button.classList.toggle('is-hidden', !card.face);
      button.classList.toggle('is-revealed', card.face != null);
      button.classList.toggle('is-matched', card.matched);
    });
  }

  function renderFinished() {
    playing.hidden = true;
    lobby.hidden = true;
    finished.hidden = false;
    const finalScores = document.getElementById('memory-final-scores');
    finalScores.replaceChildren();
    if (mode === 'solo') {
      document.getElementById('memory-finished-title').textContent =
        state.record?.is_record ? 'Nouveau record personnel !' : 'Toutes les paires sont trouvées !';
      document.getElementById('memory-finished-summary').textContent =
        `${state.matched_pairs} paires en ${formatPreciseTime(state.elapsed_ms)} et ${state.moves} coups.`;
      document.getElementById('memory-replay').hidden = false;
      document.getElementById('memory-retry-save').hidden =
        !soloLocalMode || state.result_saved || soloResultSaving;
      return;
    }
    const winners = new Set(state.winner_ids);
    document.getElementById('memory-finished-title').textContent =
      winners.size === 1
        ? `Victoire de ${state.players.find((player) => winners.has(player.player_id))?.name || 'un joueur'} !`
        : 'Égalité !';
    document.getElementById('memory-finished-summary').textContent =
      `${state.total_pairs} paires découvertes en ${state.moves} coups et ${formatTime(state.elapsed_seconds)}.`;
    state.scores.forEach((score) => {
      const item = document.createElement('li');
      item.textContent = `${score.name} · ${score.pairs} paire${score.pairs === 1 ? '' : 's'} · ${score.moves} coups · ${score.points} pts${winners.has(score.player_id) ? ' · gagnant' : ''}`;
      finalScores.append(item);
    });
    const replay = document.getElementById('memory-replay');
    replay.hidden = state.host_player_id !== playerId;
    replay.textContent = 'Rejouer · retourner au salon';
  }

  function render() {
    if (!state) return;
    if (mode === 'room' && state.status === 'lobby') {
      renderLobby();
      return;
    }
    lobby.hidden = true;
    playing.hidden = false;
    finished.hidden = true;
    document.getElementById('memory-pairs').textContent =
      `${state.matched_pairs} / ${state.total_pairs}`;
    document.getElementById('memory-moves').textContent = String(state.moves);
    if (mode === 'solo') updateSoloClock();
    else {
      document.getElementById('memory-time').textContent = formatTime(state.elapsed_seconds);
    }
    const currentTurnBox = document.getElementById('memory-current-turn-box');
    currentTurnBox.hidden = mode !== 'room';
    document.getElementById('memory-current-turn').textContent = state.turn_player_name || '';
    renderScoreboard();
    let message;
    if (mode === 'solo') {
      message = state.pending_mismatch_until != null
        ? 'Pas de paire : cliquez sur une autre carte pour retourner immédiatement les deux cartes.'
        : 'Retournez deux cartes pour retrouver une paire.';
    } else if (state.pending_mismatch_until != null) {
      message = 'Pas de paire : les cartes vont se retourner, puis la main passera.';
    } else if (state.turn_player_id === playerId) {
      message = 'C’est votre tour : choisissez deux cartes.';
    } else {
      message = `Au tour de ${state.turn_player_name}…`;
    }
    document.getElementById('memory-game-message').textContent = message;
    renderBoard();
    if (state.status === 'finished') renderFinished();
  }

  async function refreshRoom() {
    if (!state || mode !== 'room' || refreshing || busy) return;
    refreshing = true;
    const revision = roomStateRevision;
    const roomId = state.room_id;
    try {
      const nextState = await request(
        `/api/memories/room/${encodeURIComponent(roomId)}?player_id=${encodeURIComponent(playerId)}`,
      );
      if (
        revision !== roomStateRevision
        || mode !== 'room'
        || state?.room_id !== roomId
      ) return;
      state = nextState;
      render();
      scheduleRoomPolling();
    } catch (error) {
      showError('memory-game-error', error);
    } finally {
      refreshing = false;
    }
  }

  async function flipCard(index) {
    if (!state || busy) return;
    if (mode === 'solo' && soloLocalMode) {
      clearError('memory-game-error');
      applyLocalSoloFlip(index);
      return;
    }
    const roomId = state.room_id;
    const gameId = state.game_id;
    const requestRevision = ++roomStateRevision;
    busy = true;
    clearError('memory-game-error');
    board.children[index]?.classList.add('is-loading');
    renderBoard();
    try {
      if (mode === 'solo') {
        state = await post('/api/memories/solo/flip', {
          ...playerPayload(), game_id: gameId, index,
        });
      } else {
        state = await post('/api/memories/room/flip', {
          ...playerPayload(), room_id: roomId, index,
        });
      }
      board.children[index]?.classList.remove('is-loading');
      roomStateRevision = requestRevision + 1;
      render();
      if (mode === 'solo') scheduleSoloMismatchHide();
      if (mode === 'solo' && state.status === 'finished') {
        stopPolling();
        refreshSoloLeaderboard();
      }
      else if (mode === 'room') scheduleRoomPolling();
    } catch (error) {
      board.children[index]?.classList.remove('is-loading');
      showError('memory-game-error', error);
    } finally {
      busy = false;
      render();
    }
  }

  async function startSolo() {
    const button = document.getElementById('memory-solo-start');
    setBusy(button, true, 'Préparation…');
    clearError('memory-home-error');
    try {
      const gridSize = Number(document.getElementById('memory-grid-size').value);
      const nextState = await post('/api/memories/solo/new', {
        ...playerPayload(), grid_size: gridSize,
      });
      localStorage.removeItem('memories_solo_progress');
      const progress = { game_id: nextState.game_id, started_at: Date.now(), flips: [] };
      enterGame('solo', nextState, progress);
      history.replaceState(null, '', `${window.location.pathname}?mode=solo`);
    } catch (error) {
      showError('memory-home-error', error);
    } finally {
      setBusy(button, false);
    }
  }

  async function createRoom() {
    const button = document.getElementById('memory-create-room');
    setBusy(button, true, 'Création…');
    clearError('memory-setup-error');
    try {
      const nextState = await post('/api/memories/room/create', {
        ...playerPayload(),
        grid_size: Number(document.getElementById('memory-grid-size').value),
      });
      enterGame('room', nextState);
      history.replaceState(null, '', `${window.location.pathname}?room=${encodeURIComponent(state.room_id)}`);
    } catch (error) {
      showError('memory-setup-error', error);
    } finally {
      setBusy(button, false);
    }
  }

  async function joinRoom(rawRoomId) {
    const roomId = rawRoomId.trim().toUpperCase();
    if (!roomId) {
      showError('memory-setup-error', new Error('Saisissez le code du salon.'));
      return;
    }
    clearError('memory-setup-error');
    try {
      const nextState = await post('/api/memories/room/join', {
        ...playerPayload(), room_id: roomId,
      });
      enterGame('room', nextState);
      history.replaceState(null, '', `${window.location.pathname}?room=${encodeURIComponent(state.room_id)}`);
    } catch (error) {
      showError('memory-setup-error', error);
    }
  }

  async function setReady(ready) {
    if (!state || mode !== 'room' || busy) return;
    busy = true;
    try {
      state = await post('/api/memories/room/ready', {
        ...playerPayload(), room_id: state.room_id, ready,
      });
      render();
    } catch (error) {
      showError('memory-game-error', error);
    } finally {
      busy = false;
      render();
    }
  }

  async function startRoom() {
    if (!state || mode !== 'room' || busy) return;
    busy = true;
    const button = document.getElementById('memory-start');
    button.disabled = true;
    try {
      state = await post('/api/memories/room/start', {
        ...playerPayload(), room_id: state.room_id,
      });
      render();
    } catch (error) {
      showError('memory-game-error', error);
    } finally {
      busy = false;
      render();
    }
  }

  async function restartRoom() {
    if (!state || mode !== 'room' || busy) return;
    busy = true;
    try {
      state = await post('/api/memories/room/restart', {
        ...playerPayload(), room_id: state.room_id,
      });
      render();
      scheduleRoomPolling();
    } catch (error) {
      showError('memory-game-error', error);
    } finally {
      busy = false;
      render();
    }
  }

  async function refreshRooms() {
    const container = document.getElementById('memory-room-list');
    container.textContent = 'Chargement des salons…';
    try {
      const data = await request(`/api/memories/rooms?player_id=${encodeURIComponent(playerId)}`);
      container.replaceChildren();
      if (!data.rooms.length) {
        container.textContent = 'Aucun salon ouvert. Créez-en un et invitez vos amis !';
        return;
      }
      data.rooms.forEach((room) => {
        const item = document.createElement('div');
        item.className = 'memory-room-item';
        const details = document.createElement('span');
        const title = document.createElement('strong');
        title.textContent = `Salon ${room.room_id} · ${room.host_name}`;
        const subtitle = document.createElement('small');
        subtitle.textContent = `${room.player_count}/${room.max_players} joueurs · grille ${room.grid_size} × ${room.grid_size} · ${room.status === 'lobby' ? 'en attente' : 'en cours'}`;
        details.append(title, subtitle);
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'memory-secondary';
        const isFull = room.player_count >= room.max_players;
        button.textContent = room.is_member
          ? 'Reprendre'
          : isFull ? 'Salon complet' : 'Rejoindre';
        button.disabled = !room.is_member
          && (room.status !== 'lobby' || isFull);
        button.addEventListener('click', () => joinRoom(room.room_id));
        item.append(details, button);
        container.append(item);
      });
    } catch (error) {
      container.textContent = `Impossible de charger les salons : ${error.message}`;
    }
  }

  async function refreshSoloLeaderboard() {
    const gridSize = Number(document.getElementById('memory-grid-size').value);
    const title = document.getElementById('memory-leaderboard-title');
    const list = document.getElementById('memory-leaderboard');
    title.textContent = `Meilleurs temps · grille ${gridSize} × ${gridSize}`;
    list.replaceChildren();
    const loading = document.createElement('li');
    loading.textContent = 'Chargement du classement…';
    list.append(loading);
    try {
      const data = await request(`/api/memories/solo/leaderboard?grid_size=${gridSize}`);
      list.replaceChildren();
      if (!data.records.length) {
        const empty = document.createElement('li');
        empty.textContent = 'Aucun temps enregistré pour cette grille. À vous de jouer !';
        list.append(empty);
        return;
      }
      data.records.forEach((record) => {
        const item = document.createElement('li');
        const name = document.createElement('span');
        name.textContent = record.username;
        const time = document.createElement('strong');
        time.textContent = `${formatPreciseTime(record.elapsed_ms)} · ${record.moves} coups`;
        item.append(name, time);
        list.append(item);
      });
    } catch (error) {
      list.replaceChildren();
      const item = document.createElement('li');
      item.textContent = `Impossible de charger le classement : ${error.message}`;
      list.append(item);
    }
  }

  async function showHome() {
    if (mode === 'room' && state?.room_id) {
      stopPolling();
      try {
        await post('/api/memories/room/leave', {
          room_id: state.room_id,
          player_id: playerId,
        });
      } catch (error) {
        showError('memory-game-error', error);
        startPolling();
        return;
      }
    }
    stopPolling();
    state = null;
    mode = null;
    localStorage.removeItem('memories_active_room_id');
    localStorage.removeItem('memories_solo_game_id');
    localStorage.removeItem('memories_solo_progress');
    history.replaceState(null, '', window.location.pathname);
    setScreen('home');
    refreshRooms();
  }

  async function openRoomFromUrl(roomId) {
    try {
      const joined = await post('/api/memories/room/join', {
        ...playerPayload(), room_id: roomId,
      });
      enterGame('room', joined);
    } catch (error) {
      showError('memory-home-error', error);
    }
  }

  async function resumeSoloFromUrl(gameId) {
    try {
      const existing = await request(
        `/api/memories/solo/${encodeURIComponent(gameId)}?player_id=${encodeURIComponent(playerId)}`,
      );
      enterGame('solo', existing);
    } catch (error) {
      showError('memory-home-error', error);
    }
  }

  document.getElementById('memory-solo-start').addEventListener('click', startSolo);
  document.getElementById('memory-open-multiplayer').addEventListener('click', () => {
    home.hidden = true;
    setup.hidden = false;
  });
  document.getElementById('memory-setup-back').addEventListener('click', () => {
    setup.hidden = true;
    home.hidden = false;
  });
  document.getElementById('memory-create-room').addEventListener('click', createRoom);
  document.getElementById('memory-join-room').addEventListener('click', () => {
    joinRoom(document.getElementById('memory-room-code').value);
  });
  document.getElementById('memory-room-code').addEventListener('keydown', (event) => {
    if (event.key === 'Enter') joinRoom(event.currentTarget.value);
  });
  document.getElementById('memory-refresh-rooms').addEventListener('click', refreshRooms);
  document.getElementById('memory-grid-size').addEventListener('change', refreshSoloLeaderboard);
  document.getElementById('memory-ready').addEventListener('click', () => setReady(!state?.player?.ready));
  document.getElementById('memory-start').addEventListener('click', startRoom);
  document.getElementById('memory-leave').addEventListener('click', showHome);
  document.getElementById('memory-home-button').addEventListener('click', showHome);
  document.getElementById('memory-replay').addEventListener('click', () => {
    if (mode === 'solo') startSolo();
    else restartRoom();
  });
  document.getElementById('memory-retry-save').addEventListener('click', finishSoloResult);
  document.getElementById('memory-copy-invite').addEventListener('click', async (event) => {
    const url = new URL(window.location.href);
    url.search = new URLSearchParams({ room: state.room_id }).toString();
    try {
      await navigator.clipboard.writeText(url.href);
      event.currentTarget.textContent = 'Lien copié !';
      window.setTimeout(() => { event.currentTarget.textContent = 'Copier le lien'; }, 1500);
    } catch {
      window.prompt('Copiez ce lien pour inviter vos amis :', url.href);
    }
  });

  const params = new URLSearchParams(window.location.search);
  const requestedRoom = params.get('room');
  const requestedMode = params.get('mode');
  refreshSoloLeaderboard();
  if (requestedRoom) openRoomFromUrl(requestedRoom);
  else if (requestedMode === 'solo' && localStorage.getItem('memories_solo_game_id')) {
    resumeSoloFromUrl(localStorage.getItem('memories_solo_game_id'));
  } else refreshRooms();
})();
