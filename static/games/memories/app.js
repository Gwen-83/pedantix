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
      pollingTimer = window.setInterval(refreshSolo, 1000);
    }
  }

  function formatTime(seconds) {
    const minutes = Math.floor(seconds / 60);
    return `${String(minutes).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
  }

  function setScreen(screen) {
    home.hidden = screen !== 'home';
    setup.hidden = screen !== 'setup';
    gamePanel.hidden = screen !== 'game';
  }

  function enterGame(nextMode, nextState) {
    mode = nextMode;
    state = nextState;
    setScreen('game');
    document.getElementById('memory-mode-label').textContent =
      mode === 'solo' ? 'Partie solo' : `Multijoueur · salon ${state.room_id}`;
    document.getElementById('memory-round-heading').textContent =
      `${state.grid_size} × ${state.grid_size} · ${state.total_pairs} paires`;
    render();
    startPolling();
    if (mode === 'room') localStorage.setItem('memories_active_room_id', state.room_id);
    else localStorage.setItem('memories_solo_game_id', state.game_id);
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
      || state.pending_mismatch_until != null
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
      button.textContent = card.face || '?';
      button.setAttribute('aria-label', card.face
        ? `Carte ${card.index + 1} : ${card.face}${card.matched ? ', paire trouvée' : ''}`
        : `Carte ${card.index + 1}, face cachée`);
      button.disabled = locked || card.face != null || card.matched;
      button.classList.toggle('is-hidden', !card.face);
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
      document.getElementById('memory-finished-title').textContent = 'Bravo, toutes les paires sont trouvées !';
      document.getElementById('memory-finished-summary').textContent =
        `${state.matched_pairs} paires en ${state.moves} coups et ${formatTime(state.elapsed_seconds)} · ${state.points} points.`;
      document.getElementById('memory-replay').hidden = false;
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
    document.getElementById('memory-time').textContent = formatTime(state.elapsed_seconds);
    const currentTurnBox = document.getElementById('memory-current-turn-box');
    currentTurnBox.hidden = mode !== 'room';
    document.getElementById('memory-current-turn').textContent = state.turn_player_name || '';
    renderScoreboard();
    let message;
    if (mode === 'solo') {
      message = state.pending_mismatch_until != null
        ? 'Pas de paire : observez les cartes avant qu’elles se retournent.'
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

  async function refreshSolo() {
    if (!state || mode !== 'solo' || refreshing || busy) return;
    refreshing = true;
    try {
      state = await request(
        `/api/memories/solo/${encodeURIComponent(state.game_id)}?player_id=${encodeURIComponent(playerId)}`,
      );
      render();
      if (state.status === 'finished') stopPolling();
    } catch (error) {
      showError('memory-game-error', error);
    } finally {
      refreshing = false;
    }
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
    const roomId = state.room_id;
    const gameId = state.game_id;
    const requestRevision = ++roomStateRevision;
    busy = true;
    clearError('memory-game-error');
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
      roomStateRevision = requestRevision + 1;
      render();
      if (mode === 'solo' && state.status === 'finished') stopPolling();
      else if (mode === 'room') scheduleRoomPolling();
    } catch (error) {
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
      enterGame('solo', nextState);
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
  document.getElementById('memory-ready').addEventListener('click', () => setReady(!state?.player?.ready));
  document.getElementById('memory-start').addEventListener('click', startRoom);
  document.getElementById('memory-leave').addEventListener('click', showHome);
  document.getElementById('memory-home-button').addEventListener('click', showHome);
  document.getElementById('memory-replay').addEventListener('click', () => {
    if (mode === 'solo') startSolo();
    else restartRoom();
  });
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
  if (requestedRoom) openRoomFromUrl(requestedRoom);
  else if (requestedMode === 'solo' && localStorage.getItem('memories_solo_game_id')) {
    resumeSoloFromUrl(localStorage.getItem('memories_solo_game_id'));
  } else refreshRooms();
})();
