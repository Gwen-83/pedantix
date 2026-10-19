(() => {
  const apiBase = window.PEDANTIX_CONFIG?.BACKEND_URL?.replace(/\/+$/, '') || '';
  const params = new URLSearchParams(window.location.search);
  const home = document.getElementById('plongee-home');
  const gamePanel = document.getElementById('plongee-game');
  const homeError = document.getElementById('plongee-home-error');
  const gameError = document.getElementById('plongee-game-error');
  const answerForm = document.getElementById('plongee-answer-form');
  const answerInput = document.getElementById('plongee-answer');
  const gameIdKey = 'plongee_solo_game_id';
  let playerId = localStorage.getItem('plongee_player_id');
  if (!playerId) {
    playerId = globalThis.crypto?.randomUUID?.() || `plongee-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    localStorage.setItem('plongee_player_id', playerId);
  }
  const playerName = (localStorage.getItem('pedantix_player_name')
    || localStorage.getItem('pedantix_auth_user')
    || 'Joueur').trim().slice(0, 24);
  let state = null;
  let gameType = null;
  let roomBusy = false;
  let stateReceivedAt = Date.now();

  document.getElementById('plongee-player-name').textContent = playerName;
  document.getElementById('plongee-solo-resume').hidden = !localStorage.getItem(gameIdKey);

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

  const post = (path, data) => request(path, { method: 'POST', body: JSON.stringify(data) });
  const playerData = () => ({ player_id: playerId, player_name: playerName });

  function showError(element, message) {
    element.textContent = message;
    element.hidden = false;
  }

  function hideError(element) {
    element.hidden = true;
    element.textContent = '';
  }

  function showHome() {
    gameType = null;
    state = null;
    gamePanel.hidden = true;
    home.hidden = false;
    hideError(homeError);
    history.replaceState(null, '', window.location.pathname);
    refreshRooms();
  }

  function setMode(mode) {
    document.querySelectorAll('[data-mode]').forEach((button) => {
      const selected = button.dataset.mode === mode;
      button.classList.toggle('active', selected);
      button.setAttribute('aria-pressed', String(selected));
    });
    document.getElementById('plongee-solo-actions').hidden = mode !== 'solo';
    document.getElementById('plongee-multi-actions').hidden = mode !== 'multi';
  }

  async function refreshRooms() {
    const directory = document.getElementById('plongee-room-directory');
    try {
      const { rooms } = await request(`/api/plongee/rooms?player_id=${encodeURIComponent(playerId)}`);
      directory.replaceChildren();
      if (!rooms.length) {
        directory.textContent = 'Aucun salon en attente.';
        return;
      }
      rooms.forEach((room) => {
        const card = document.createElement('div');
        card.className = 'plongee-room-card';
        const label = document.createElement('span');
        label.textContent = `${room.room_id} · ${room.player_count} joueur${room.player_count === 1 ? '' : 's'}`;
        const join = document.createElement('button');
        join.type = 'button';
        join.textContent = room.is_member ? 'Reprendre' : 'Rejoindre';
        join.addEventListener('click', () => joinRoom(room.room_id));
        card.append(label, join);
        directory.append(card);
      });
    } catch (error) {
      directory.textContent = `Impossible de charger les salons : ${error.message}`;
    }
  }

  async function startSolo() {
    hideError(homeError);
    try {
      state = await post('/api/plongee/solo/new', playerData());
      localStorage.setItem(gameIdKey, state.game_id);
      gameType = 'solo';
      showGame();
    } catch (error) {
      showError(homeError, error.message);
    }
  }

  async function resumeSolo() {
    const gameId = localStorage.getItem(gameIdKey);
    if (!gameId) return startSolo();
    try {
      state = await request(`/api/plongee/solo/${encodeURIComponent(gameId)}?player_id=${encodeURIComponent(playerId)}`);
      gameType = 'solo';
      showGame();
    } catch (error) {
      localStorage.removeItem(gameIdKey);
      showError(homeError, error.message);
    }
  }

  async function createRoom() {
    hideError(homeError);
    try {
      state = await post('/api/plongee/room/create', playerData());
      gameType = 'room';
      history.replaceState(null, '', `${window.location.pathname}?room=${encodeURIComponent(state.room_id)}`);
      showGame();
    } catch (error) {
      showError(homeError, error.message);
    }
  }

  async function joinRoom(roomId) {
    hideError(homeError);
    const code = roomId.trim().toUpperCase();
    if (!code) {
      showError(homeError, 'Saisissez le code du salon.');
      return;
    }
    try {
      state = await post('/api/plongee/room/join', { ...playerData(), room_id: code });
      gameType = 'room';
      history.replaceState(null, '', `${window.location.pathname}?room=${encodeURIComponent(code)}`);
      showGame();
    } catch (error) {
      showError(homeError, error.message);
    }
  }

  function showGame() {
    stateReceivedAt = Date.now();
    home.hidden = true;
    gamePanel.hidden = false;
    hideError(gameError);
    updateView();
  }

  function renderLobby() {
    document.getElementById('plongee-lobby').hidden = false;
    document.getElementById('plongee-round').hidden = true;
    document.getElementById('plongee-game-mode').textContent = 'Salon multijoueur';
    document.getElementById('plongee-round-label').textContent = `Salon ${state.room_id}`;
    document.getElementById('plongee-invite-code').textContent = state.room_id;
    const invite = new URL(window.location.href);
    invite.search = new URLSearchParams({ room: state.room_id }).toString();
    document.getElementById('plongee-copy-link').dataset.invite = invite.href;
    const list = document.getElementById('plongee-player-list');
    list.replaceChildren(...state.players.map((player) => {
      const item = document.createElement('li');
      const name = document.createElement('span');
      name.textContent = player.name + (player.player_id === state.host_player_id ? ' (hôte)' : '');
      const status = document.createElement('small');
      status.textContent = 'Prêt';
      item.append(name, status);
      return item;
    }));
    document.getElementById('plongee-lobby-status').textContent =
      state.players.length < 2 ? 'Il faut au moins deux joueurs pour démarrer.' : 'Tout le monde est prêt.';
    const start = document.getElementById('plongee-start-room');
    start.hidden = state.player_id !== state.host_player_id;
    start.disabled = state.players.length < 2 || roomBusy;
  }

  function renderResults(results, title) {
    const container = document.getElementById('plongee-results');
    container.hidden = !results;
    container.replaceChildren();
    if (!results) return;
    const heading = document.createElement('h3');
    heading.textContent = title;
    const list = document.createElement('ul');
    results.forEach((result) => {
      const item = document.createElement('li');
      const name = gameType === 'room'
        ? `${result.name} : ${result.answer || 'Pas de réponse'}`
        : `Manche ${result.round_number} : ${result.timed_out ? 'temps écoulé' : result.answer}`;
      const label = document.createElement('span');
      label.textContent = name;
      const score = document.createElement('strong');
      score.textContent = `${result.score} pts`;
      item.append(label, score);
      list.append(item);
    });
    container.append(heading, list);
  }

  function renderScoreboard() {
    const board = document.getElementById('plongee-scoreboard');
    board.replaceChildren();
    const players = gameType === 'room'
      ? [...state.players].sort((a, b) => b.score - a.score)
      : [{ name: playerName, score: state.score }];
    players.forEach((player, index) => {
      const item = document.createElement('span');
      item.textContent = `${index + 1}. ${player.name} · ${player.score} pts`;
      board.append(item);
    });
  }

  function updateView() {
    if (!state) return;
    if (gameType === 'solo' && state.status === 'finished') {
      localStorage.removeItem(gameIdKey);
      document.getElementById('plongee-solo-resume').hidden = true;
    }
    const isLobby = gameType === 'room' && state.status === 'lobby';
    document.getElementById('plongee-lobby').hidden = !isLobby;
    document.getElementById('plongee-round').hidden = isLobby;
    if (isLobby) {
      renderLobby();
      return;
    }
    document.getElementById('plongee-game-mode').textContent = gameType === 'solo' ? 'Plongée en solo' : 'Plongée multijoueur';
    document.getElementById('plongee-round-label').textContent =
      state.status === 'finished' ? 'Plongée terminée' : `Manche ${state.round_number} / ${state.round_count}`;
    document.getElementById('plongee-round-number').textContent =
      state.status === 'finished' ? 'BILAN DE LA PLONGÉE' : `QUESTION ${state.round_number} / ${state.round_count}`;
    document.getElementById('plongee-prompt').textContent =
      state.prompt || 'Bravo, la plongée est terminée !';
    document.getElementById('plongee-score').textContent = state.score.toLocaleString('fr-FR');
    document.getElementById('plongee-depth').textContent = `${Math.round(state.score * 4)} m`;
    document.getElementById('plongee-depth-bar').style.width = `${Math.min(100, state.score / 7)}%`;
    const hasAnswered = gameType === 'solo'
      ? state.result?.round_number === state.round_number && !state.result?.timed_out
      : state.has_answered;
    answerInput.disabled = state.status === 'finished' || hasAnswered || state.time_left <= 0;
    answerForm.querySelector('button').disabled = answerInput.disabled;
    document.getElementById('plongee-answer-feedback').textContent = state.status === 'finished'
      ? 'Votre score final est affiché ci-dessus.'
      : hasAnswered
        ? gameType === 'solo'
          ? `Réponse validée : ${state.result.score}/100${state.result.known_answer ? '' : ' · réponse inédite, rareté neutre'}`
          : 'Réponse enregistrée. Les résultats s’afficheront à la fin de la manche.'
        : state.time_left <= 0
          ? 'Manche terminée. Attendez les résultats.'
          : gameType === 'room'
            ? `${state.answer_count}/${state.players.length} réponses envoyées.`
            : 'Réponse libre : une proposition avant la fin du compte à rebours.';
    document.getElementById('plongee-timer').textContent = String(Math.max(0, state.time_left));

    const lastRound = gameType === 'room' ? state.last_round : null;
    if (lastRound) {
      renderResults(lastRound.results, `Résultats de la manche ${lastRound.round_number}`);
    } else if (gameType === 'solo' && state.results.length) {
      renderResults(state.results, 'Vos réponses');
    } else {
      renderResults(null, '');
    }
    renderScoreboard();
    const next = document.getElementById('plongee-next');
    const canAdvanceSolo = gameType === 'solo'
      && hasAnswered
      && state.status !== 'finished';
    const canAdvanceRoom = gameType === 'room'
      && !!state.last_round
      && state.player_id === state.host_player_id;
    next.hidden = !canAdvanceSolo && !canAdvanceRoom;
    next.textContent = state.round_number === state.round_count ? 'Terminer la plongée' : 'Manche suivante →';
  }

  async function refreshState() {
    if (!state || gameType !== 'room' && gameType !== 'solo') return;
    try {
      if (gameType === 'solo') {
        state = await request(`/api/plongee/solo/${encodeURIComponent(state.game_id)}?player_id=${encodeURIComponent(playerId)}`);
      } else {
        state = await request(`/api/plongee/room/${encodeURIComponent(state.room_id)}?player_id=${encodeURIComponent(playerId)}`);
      }
      stateReceivedAt = Date.now();
      updateView();
    } catch (error) {
      showError(gameError, error.message);
    }
  }

  async function submitAnswer(event) {
    event.preventDefault();
    if (!state || answerInput.disabled) return;
    const button = answerForm.querySelector('button');
    button.disabled = true;
    hideError(gameError);
    try {
      const common = { ...playerData(), answer: answerInput.value };
      if (gameType === 'solo') {
        state = await post('/api/plongee/solo/guess', { ...common, game_id: state.game_id });
      } else {
        state = await post('/api/plongee/room/guess', { ...common, room_id: state.room_id });
      }
      answerInput.value = '';
      stateReceivedAt = Date.now();
      updateView();
    } catch (error) {
      showError(gameError, error.message);
      updateView();
    }
  }

  async function advance() {
    if (!state) return;
    const next = document.getElementById('plongee-next');
    next.disabled = true;
    try {
      if (gameType === 'solo') {
        state = await post('/api/plongee/solo/next', { ...playerData(), game_id: state.game_id });
      } else {
        state = await post('/api/plongee/room/next', { ...playerData(), room_id: state.room_id });
      }
      stateReceivedAt = Date.now();
      updateView();
    } catch (error) {
      showError(gameError, error.message);
    } finally {
      next.disabled = false;
    }
  }

  document.querySelectorAll('[data-mode]').forEach((button) => {
    button.addEventListener('click', () => setMode(button.dataset.mode));
  });
  document.getElementById('plongee-solo-start').addEventListener('click', startSolo);
  document.getElementById('plongee-solo-resume').addEventListener('click', resumeSolo);
  document.getElementById('plongee-room-create').addEventListener('click', createRoom);
  document.getElementById('plongee-room-join-form').addEventListener('submit', (event) => {
    event.preventDefault();
    joinRoom(document.getElementById('plongee-room-code').value);
  });
  document.getElementById('plongee-room-refresh').addEventListener('click', refreshRooms);
  document.getElementById('plongee-start-room').addEventListener('click', async () => {
    roomBusy = true;
    updateView();
    try {
      state = await post('/api/plongee/room/start', { ...playerData(), room_id: state.room_id });
      stateReceivedAt = Date.now();
      updateView();
    } catch (error) {
      showError(gameError, error.message);
    } finally {
      roomBusy = false;
      updateView();
    }
  });
  document.getElementById('plongee-copy-link').addEventListener('click', async (event) => {
    try {
      await navigator.clipboard.writeText(event.currentTarget.dataset.invite);
      event.currentTarget.textContent = 'Lien copié !';
    } catch {
      showError(gameError, 'Impossible de copier le lien. Vous pouvez copier le code du salon.');
    }
  });
  document.getElementById('plongee-exit').addEventListener('click', showHome);
  answerForm.addEventListener('submit', submitAnswer);
  document.getElementById('plongee-next').addEventListener('click', advance);
  window.setInterval(() => {
    if (!state || gamePanel.hidden || state.status !== 'playing') return;
    const elapsed = Math.floor((Date.now() - stateReceivedAt) / 1000);
    const remaining = Math.max(0, state.time_left - elapsed);
    document.getElementById('plongee-timer').textContent = String(remaining);
  }, 250);
  window.setInterval(() => {
    if (
      state
      && !gamePanel.hidden
      && (gameType === 'room' ? state.status !== 'finished' : state.status === 'playing')
    ) refreshState();
  }, 1000);

  setMode(params.has('room') ? 'multi' : 'solo');
  if (params.has('room')) joinRoom(params.get('room'));
  else refreshRooms();
})();
