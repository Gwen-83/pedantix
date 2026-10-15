(() => {
  const apiBase = window.PEDANTIX_CONFIG?.BACKEND_URL?.replace(/\/+$/, '') || '';
  const home = document.getElementById('bito-home');
  const game = document.getElementById('bito-game');
  const homeError = document.getElementById('bito-home-error');
  const gameError = document.getElementById('bito-game-error');
  const roomDirectory = document.getElementById('bito-room-directory');
  const playerIdKey = 'bitoguessr_player_id';
  let playerId = localStorage.getItem(playerIdKey);
  if (!playerId) {
    playerId = globalThis.crypto?.randomUUID?.()
      || `bito-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    localStorage.setItem(playerIdKey, playerId);
  }
  const playerName = (localStorage.getItem('pedantix_player_name')
    || localStorage.getItem('pedantix_auth_user')
    || 'Joueur').trim().slice(0, 24);
  const params = new URLSearchParams(window.location.search);
  let state = null;
  let gameType = null;
  let busy = false;
  let refreshing = false;
  let pollTimer = null;

  document.getElementById('bito-player-name').textContent = playerName;

  async function request(path, options = {}) {
    const response = await fetch(`${apiBase}${path}`, {
      ...options,
      headers: {
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...options.headers,
      },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || `Erreur serveur (${response.status}).`);
    return data;
  }

  function post(path, data) {
    return request(path, { method: 'POST', body: JSON.stringify(data) });
  }

  function setError(element, message) {
    element.textContent = message;
    element.hidden = false;
  }

  function clearError(element) {
    element.textContent = '';
    element.hidden = true;
  }

  function setBusy(button, value, label) {
    if (!button.dataset.label) button.dataset.label = button.textContent;
    button.disabled = value;
    button.textContent = value ? label : button.dataset.label;
  }

  function setView(inGame) {
    home.hidden = inGame;
    game.hidden = !inGame;
  }

  function setUrl(query = '') {
    history.replaceState(null, '', `${window.location.pathname}${query}`);
  }

  function formatPrompt(value) {
    const digits = state.difficulty === 'difficile' ? 2 : 0;
    return `${Number(value).toLocaleString('fr-FR', {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    })} cm`;
  }

  function renderPlayerList(players) {
    const list = document.getElementById('bito-player-list');
    list.replaceChildren(...players.map((player) => {
      const item = document.createElement('li');
      const name = document.createElement('span');
      name.textContent = `${player.name}${player.player_id === state.host_player_id ? ' · hôte' : ''}`;
      const status = document.createElement('small');
      status.textContent = player.submitted
        ? 'Réponse validée'
        : `${player.score} point${player.score === 1 ? '' : 's'}`;
      item.append(name, status);
      return item;
    }));
  }

  function renderLobby() {
    const lobby = document.getElementById('bito-lobby');
    lobby.hidden = state.status !== 'lobby';
    if (state.status !== 'lobby') return;
    document.getElementById('bito-lobby-status').textContent =
      `${state.player_count}/${state.max_players} joueurs · ${state.round_count} manches · mode ${state.difficulty}. Il faut deux joueurs pour démarrer.`;
    document.getElementById('bito-invite-code').textContent = state.room_id;
    const invite = new URL(window.location.href);
    invite.search = new URLSearchParams({ room: state.room_id }).toString();
    document.getElementById('bito-copy-invite').dataset.inviteUrl = invite.href;
    renderPlayerList(state.players);
    const startButton = document.getElementById('bito-start-room');
    startButton.hidden = state.host_player_id !== playerId;
    startButton.disabled = !state.can_start || busy;
  }

  function renderResult(result) {
    const section = document.getElementById('bito-result');
    section.replaceChildren();
    section.hidden = !result;
    if (!result) return;

    const ownResult = gameType === 'room'
      ? result.guesses.find((guess) => guess.player_id === playerId)
      : result;
    const heading = document.createElement('h2');
    heading.textContent = ownResult?.correct ? 'Bien vu !' : 'Raté pour cette fois';
    const detail = document.createElement('p');
    const earned = ownResult?.score || 0;
    detail.textContent = `${result.answer} était une réponse valable · ${formatPrompt(result.prompt_cm)} · +${earned} point${earned === 1 ? '' : 's'}.`;
    section.append(heading, detail);

    if (gameType === 'room' && Array.isArray(result.guesses)) {
      const ranking = document.createElement('ol');
      [...result.guesses]
        .sort((left, right) => right.score - left.score || left.name.localeCompare(right.name, 'fr'))
        .forEach((guess) => {
          const item = document.createElement('li');
          item.textContent = `${guess.name} · ${guess.guess || 'sans réponse'} · ${guess.correct ? 'juste' : 'faux'} · +${guess.score}`;
          ranking.append(item);
        });
      section.append(ranking);
    }

    if (gameType === 'solo' && state.status === 'playing') {
      const nextButton = document.createElement('button');
      nextButton.type = 'button';
      nextButton.className = 'bito-primary';
      nextButton.textContent = 'Question suivante';
      nextButton.addEventListener('click', nextSolo);
      section.append(nextButton);
    }
    if (gameType === 'room' && state.status === 'playing' && state.host_player_id === playerId) {
      const nextButton = document.createElement('button');
      nextButton.type = 'button';
      nextButton.className = 'bito-primary';
      nextButton.textContent = 'Manche suivante';
      nextButton.addEventListener('click', nextRoom);
      section.append(nextButton);
    }
  }

  function renderScoreboard() {
    const section = document.getElementById('bito-scoreboard');
    section.replaceChildren();
    section.hidden = state.status !== 'finished';
    if (section.hidden) return;

    const heading = document.createElement('h2');
    heading.textContent = 'Partie terminée';
    section.append(heading);
    const rows = gameType === 'room'
      ? [...state.players].sort((left, right) => right.score - left.score)
      : [{ name: playerName, score: state.score }];
    const list = document.createElement('ol');
    rows.forEach((player) => {
      const item = document.createElement('li');
      item.textContent = `${player.name} · ${player.score} point${player.score === 1 ? '' : 's'}`;
      list.append(item);
    });
    section.append(list);
    const replay = document.createElement('button');
    replay.type = 'button';
    replay.className = 'bito-primary';
    replay.textContent = 'Retour aux jeux';
    replay.addEventListener('click', leaveGame);
    section.append(replay);
  }

  function renderQuestion() {
    const question = document.getElementById('bito-question');
    const options = document.getElementById('bito-options');
    const waiting = document.getElementById('bito-waiting');
    const prompt = document.getElementById('bito-prompt');
    const result = gameType === 'solo' ? state.result : state.last_round;
    const isLobby = state.status === 'lobby';
    const isComplete = Boolean(result);
    const submitted = gameType === 'room' && state.player?.submitted;

    question.hidden = isLobby || state.status === 'finished' || isComplete;
    options.replaceChildren();
    waiting.hidden = true;

    if (!question.hidden) {
      prompt.textContent = formatPrompt(state.prompt_cm);
      if (submitted) {
        waiting.textContent = 'Réponse enregistrée. En attente des autres joueurs…';
        waiting.hidden = false;
      } else {
        state.options.forEach((country) => {
          const button = document.createElement('button');
          button.type = 'button';
          button.className = 'bito-option';
          button.textContent = country;
          button.disabled = busy;
          button.addEventListener('click', () => submitGuess(country));
          options.append(button);
        });
      }
    }
    renderResult(result);
  }

  function render() {
    if (!state) return;
    setView(true);
    const roundNumber = state.round_number || 1;
    document.getElementById('bito-game-title').textContent =
      `Manche ${roundNumber} sur ${state.round_count}`;
    document.getElementById('bito-mode-label').textContent =
      gameType === 'room' ? `Salon ${state.room_id}` : 'Partie solo';
    const score = gameType === 'room'
      ? state.player?.score || 0
      : state.score || 0;
    document.getElementById('bito-score').textContent =
      `${score} point${score === 1 ? '' : 's'}`;
    document.getElementById('bito-difficulty-label').textContent =
      state.difficulty === 'difficile' ? 'Difficile · valeur précise' : 'Normal · moyenne arrondie';
    renderLobby();
    renderQuestion();
    renderScoreboard();
    if (state.status === 'finished') {
      clearInterval(pollTimer);
      pollTimer = null;
      loadStats();
    }
  }

  async function loadStats() {
    const personal = document.getElementById('bito-personal-stats');
    const leaderboard = document.getElementById('bito-leaderboard');
    try {
      const [stats, scores] = await Promise.all([
        request(`/api/user/stats?username=${encodeURIComponent(playerName)}&game_id=bitoguessr`),
        request('/api/scores?game_id=bitoguessr'),
      ]);
      personal.replaceChildren();
      [
        [`${stats.games_played || 0}`, 'parties terminées'],
        [`${stats.wins || 0}`, 'victoires'],
        [`${(stats.game_metrics?.avg_score ?? 0).toLocaleString('fr-FR')}`, 'score moyen'],
      ].forEach(([value, label]) => {
        const card = document.createElement('div');
        card.className = 'bito-stat-card';
        const number = document.createElement('strong');
        number.textContent = value;
        const caption = document.createElement('small');
        caption.textContent = label;
        card.append(number, caption);
        personal.append(card);
      });
      leaderboard.replaceChildren();
      (scores || []).slice(0, 5).forEach((entry) => {
        const item = document.createElement('li');
        item.textContent = `${entry.player_name} · ${entry.score} point${entry.score === 1 ? '' : 's'}`;
        leaderboard.append(item);
      });
      if (!leaderboard.children.length) {
        const empty = document.createElement('li');
        empty.textContent = 'Aucun score enregistré pour le moment.';
        leaderboard.append(empty);
      }
    } catch (error) {
      personal.textContent = `Statistiques indisponibles : ${error.message}`;
      leaderboard.replaceChildren();
      const item = document.createElement('li');
      item.textContent = 'Classement indisponible.';
      leaderboard.append(item);
    }
  }

  function renderRoomDirectory(rooms) {
    roomDirectory.replaceChildren();
    if (!rooms.length) {
      roomDirectory.textContent = 'Aucun salon ouvert pour le moment.';
      return;
    }
    rooms.forEach((room) => {
      const card = document.createElement('div');
      card.className = 'bito-room-card';
      const details = document.createElement('span');
      const title = document.createElement('strong');
      title.textContent = `Salon ${room.room_id}`;
      const summary = document.createElement('small');
      summary.textContent = `${room.player_count}/${room.max_players} joueurs · ${room.round_count} manches · ${room.difficulty} · ${room.status === 'playing' ? 'en cours' : 'en attente'}`;
      details.append(title, summary);
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'bito-secondary';
      button.textContent = room.is_member ? 'Reprendre' : 'Rejoindre';
      button.addEventListener('click', () => joinRoom(room.room_id));
      card.append(details, button);
      roomDirectory.append(card);
    });
  }

  async function refreshRooms() {
    roomDirectory.textContent = 'Chargement des salons…';
    try {
      const data = await request(`/api/bitoguessr/rooms?player_id=${encodeURIComponent(playerId)}`);
      renderRoomDirectory(data.rooms || []);
    } catch (error) {
      roomDirectory.textContent = `Impossible de charger les salons : ${error.message}`;
    }
  }

  async function startSolo() {
    const button = document.getElementById('bito-start-solo');
    setBusy(button, true, 'Préparation…');
    clearError(homeError);
    try {
      state = await post('/api/bitoguessr/solo/new', {
        player_id: playerId,
        player_name: playerName,
        difficulty: document.getElementById('bito-solo-difficulty').value,
      });
      gameType = 'solo';
      setUrl(`?mode=solo&game_id=${encodeURIComponent(state.game_id)}`);
      render();
    } catch (error) {
      setError(homeError, error.message);
    } finally {
      setBusy(button, false);
    }
  }

  async function resumeSolo(gameId) {
    try {
      state = await request(`/api/bitoguessr/solo/${encodeURIComponent(gameId)}?player_id=${encodeURIComponent(playerId)}`);
      gameType = 'solo';
      render();
    } catch (error) {
      setError(homeError, `Impossible de reprendre la partie : ${error.message}`);
      setUrl();
    }
  }

  async function submitGuess(country) {
    if (busy || !state) return;
    busy = true;
    clearError(gameError);
    render();
    try {
      if (gameType === 'solo') {
        state = await post('/api/bitoguessr/solo/guess', {
          player_id: playerId,
          player_name: playerName,
          game_id: state.game_id,
          guess: country,
        });
      } else {
        state = await post('/api/bitoguessr/room/guess', {
          room_id: state.room_id,
          player_id: playerId,
          player_name: playerName,
          guess: country,
        });
      }
      render();
    } catch (error) {
      setError(gameError, error.message);
    } finally {
      busy = false;
      render();
    }
  }

  async function nextSolo() {
    if (busy) return;
    busy = true;
    clearError(gameError);
    try {
      state = await post('/api/bitoguessr/solo/next', {
        player_id: playerId,
        player_name: playerName,
        game_id: state.game_id,
      });
      render();
    } catch (error) {
      setError(gameError, error.message);
    } finally {
      busy = false;
      render();
    }
  }

  async function createRoom() {
    const count = document.getElementById('bito-room-round-count');
    if (!count.reportValidity()) return;
    const button = document.getElementById('bito-create-room');
    setBusy(button, true, 'Création…');
    clearError(homeError);
    try {
      state = await post('/api/bitoguessr/room/create', {
        player_id: playerId,
        player_name: playerName,
        difficulty: document.getElementById('bito-room-difficulty').value,
        round_count: Number(count.value),
      });
      enterRoom();
    } catch (error) {
      setError(homeError, error.message);
    } finally {
      setBusy(button, false);
    }
  }

  async function joinRoom(roomId) {
    const code = (roomId || document.getElementById('bito-room-code').value).trim().toUpperCase();
    if (!code) {
      setError(homeError, 'Saisissez le code du salon.');
      return;
    }
    clearError(homeError);
    try {
      state = await post('/api/bitoguessr/room/join', {
        room_id: code,
        player_id: playerId,
        player_name: playerName,
      });
      enterRoom();
    } catch (error) {
      setError(homeError, error.message);
    }
  }

  function enterRoom() {
    gameType = 'room';
    setUrl(`?room=${encodeURIComponent(state.room_id)}`);
    render();
    startPolling();
  }

  async function resumeRoom(roomId) {
    try {
      state = await request(`/api/bitoguessr/room/${encodeURIComponent(roomId)}?player_id=${encodeURIComponent(playerId)}`);
      enterRoom();
    } catch (error) {
      setError(homeError, `Impossible de rejoindre ce salon : ${error.message}`);
      setUrl();
    }
  }

  async function startRoom() {
    if (busy) return;
    busy = true;
    clearError(gameError);
    render();
    try {
      state = await post('/api/bitoguessr/room/start', {
        room_id: state.room_id,
        player_id: playerId,
        player_name: playerName,
      });
      render();
    } catch (error) {
      setError(gameError, error.message);
    } finally {
      busy = false;
      render();
    }
  }

  async function nextRoom() {
    if (busy) return;
    busy = true;
    clearError(gameError);
    try {
      state = await post('/api/bitoguessr/room/next', {
        room_id: state.room_id,
        player_id: playerId,
        player_name: playerName,
      });
      render();
    } catch (error) {
      setError(gameError, error.message);
    } finally {
      busy = false;
      render();
    }
  }

  async function refreshRoom() {
    if (refreshing || gameType !== 'room' || !state) return;
    refreshing = true;
    try {
      const latest = await request(
        `/api/bitoguessr/room/${encodeURIComponent(state.room_id)}?player_id=${encodeURIComponent(playerId)}`,
      );
      state = latest;
      render();
    } catch (error) {
      setError(gameError, `Connexion au salon interrompue : ${error.message}`);
      clearInterval(pollTimer);
      pollTimer = null;
    } finally {
      refreshing = false;
    }
  }

  function startPolling() {
    clearInterval(pollTimer);
    pollTimer = window.setInterval(refreshRoom, 2000);
  }

  function leaveGame() {
    clearInterval(pollTimer);
    pollTimer = null;
    state = null;
    gameType = null;
    setView(false);
    setUrl();
    clearError(gameError);
    refreshRooms();
  }

  document.getElementById('bito-start-solo').addEventListener('click', startSolo);
  document.getElementById('bito-create-room').addEventListener('click', createRoom);
  document.getElementById('bito-join-room').addEventListener('click', () => joinRoom());
  document.getElementById('bito-room-code').addEventListener('keydown', (event) => {
    if (event.key === 'Enter') joinRoom();
  });
  document.getElementById('bito-refresh-rooms').addEventListener('click', refreshRooms);
  document.getElementById('bito-start-room').addEventListener('click', startRoom);
  document.getElementById('bito-leave').addEventListener('click', leaveGame);
  document.getElementById('bito-copy-invite').addEventListener('click', async (event) => {
    try {
      await navigator.clipboard.writeText(event.currentTarget.dataset.inviteUrl);
      event.currentTarget.textContent = 'Lien copié';
      window.setTimeout(() => { event.currentTarget.textContent = 'Copier le lien'; }, 1600);
    } catch (error) {
      setError(gameError, `Copie impossible : ${error.message}`);
    }
  });

  refreshRooms();
  loadStats();
  if (params.has('room')) {
    resumeRoom(params.get('room'));
  } else if (params.get('mode') === 'solo' && params.has('game_id')) {
    resumeSolo(params.get('game_id'));
  }
})();
