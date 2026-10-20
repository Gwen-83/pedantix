(() => {
  const apiBase = window.PEDANTIX_CONFIG?.BACKEND_URL?.replace(/\/+$/, '') || '';
  const home = document.getElementById('cemantix-home');
  const play = document.getElementById('cemantix-play');
  const homeError = document.getElementById('cemantix-home-error');
  const playError = document.getElementById('cemantix-play-error');
  const guessInput = document.getElementById('cemantix-guess');
  const guessForm = document.getElementById('cemantix-guess-form');
  const difficultySelect = document.getElementById('cemantix-difficulty');
  const roomDirectory = document.getElementById('cemantix-room-directory');
  const hintsContainer = document.getElementById('cemantix-hints');
  const params = new URLSearchParams(window.location.search);
  let playerId = localStorage.getItem('cemantix_player_id');
  if (!playerId) {
    playerId = globalThis.crypto?.randomUUID?.() || `cemantix-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    localStorage.setItem('cemantix_player_id', playerId);
  }
  const playerName = (localStorage.getItem('pedantix_player_name')
    || localStorage.getItem('pedantix_auth_user')
    || 'Joueur').trim().slice(0, 24);
  let state = null;
  let gameType = null;
  let pollingTimer = null;
  let roomRefreshing = false;
  let roomBusy = false;
  let roomRefreshGeneration = 0;

  document.getElementById('cemantix-player-name').textContent = playerName;

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

  function post(path, data) {
    return request(path, { method: 'POST', body: JSON.stringify(data) });
  }

  function showError(element, message) {
    element.textContent = message;
    element.hidden = false;
  }

  function hideError(element) {
    element.hidden = true;
    element.textContent = '';
  }

  function setBusy(button, busy, busyText) {
    if (!button.dataset.label) button.dataset.label = button.textContent;
    button.disabled = busy;
    button.textContent = busy ? busyText : button.dataset.label;
  }

  function stopPolling() {
    if (pollingTimer) window.clearInterval(pollingTimer);
    pollingTimer = null;
  }

  function startPolling() {
    stopPolling();
    if (gameType !== 'room') return;
    pollingTimer = window.setInterval(refreshRoom, 1000);
  }

  async function showHome(clearActiveGame = true) {
    if (clearActiveGame && gameType === 'room' && state?.room_id) {
      stopPolling();
      try {
        await post('/api/cemantix/room/leave', {
          room_id: state.room_id,
          player_id: playerId,
        });
      } catch (error) {
        showError(playError, error.message);
        startPolling();
        return;
      }
    }
    stopPolling();
    gameType = null;
    state = null;
    home.hidden = false;
    play.hidden = true;
    if (clearActiveGame) {
      localStorage.setItem('cemantix_active_game_mode', 'home');
      localStorage.removeItem('cemantix_active_room_id');
    }
    document.getElementById('cemantix-previous-game').hidden =
      !localStorage.getItem('cemantix_solo_game_id');
    history.replaceState(null, '', window.location.pathname);
    refreshRoomDirectory();
  }

  function renderRoomDirectory(rooms) {
    roomDirectory.replaceChildren();
    if (!rooms.length) {
      const empty = document.createElement('p');
      empty.className = 'cemantix-room-empty';
      empty.textContent = 'Aucun salon ouvert pour le moment.';
      roomDirectory.append(empty);
      return;
    }
    for (const room of rooms) {
      const card = document.createElement('div');
      card.className = 'cemantix-room-card';
      const copy = document.createElement('span');
      copy.className = 'cemantix-room-card-copy';
      const title = document.createElement('strong');
      title.textContent = `Salon ${room.room_id}`;
      const details = document.createElement('small');
      details.textContent = `${room.player_count} joueur${room.player_count === 1 ? '' : 's'} · ${room.difficulty} · ${room.status === 'playing' ? 'En cours' : 'En attente'}`;
      copy.append(title, details);
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'cemantix-secondary-button';
      button.textContent = room.is_member
        ? 'Reprendre'
        : room.status === 'playing' ? 'Observer' : 'Rejoindre';
      button.disabled = !room.is_member && !['lobby', 'playing'].includes(room.status);
      if (!button.disabled) button.addEventListener('click', () => joinRoom(room.room_id));
      card.append(copy, button);
      roomDirectory.append(card);
    }
  }

  async function refreshRoomDirectory() {
    roomDirectory.textContent = 'Chargement des salons…';
    try {
      const data = await request(`/api/cemantix/rooms?player_id=${encodeURIComponent(playerId)}`);
      renderRoomDirectory(data.rooms || []);
    } catch (error) {
      roomDirectory.textContent = `Impossible de charger les salons : ${error.message}`;
    }
  }

  function showPlay() {
    home.hidden = true;
    play.hidden = false;
    hideError(playError);
  }

  function updateView() {
    if (!state) return;
    showPlay();
    const isRoom = gameType === 'room';
    const isLobby = isRoom && state.status === 'lobby';
    document.getElementById('cemantix-game-mode').textContent =
      isRoom
        ? state.player.is_spectator ? 'Défi multijoueur · Spectateur' : 'Défi multijoueur'
        : 'Partie solo';
    document.getElementById('cemantix-game-title').textContent =
      state.status === 'finished' ? 'Le mot a été trouvé' : 'Quel est le mot secret ?';
    document.getElementById('cemantix-hint').textContent = isRoom
      ? 'Même mot pour tous : une proposition par joueur à chaque manche.'
      : 'Chaque proposition révèle à quel point son sens se rapproche du mot secret.';
    document.getElementById('cemantix-lobby').hidden = !isLobby;
    document.getElementById('cemantix-round').hidden = isLobby;
    if (isLobby) renderLobby();
    else renderRound();
    if (isRoom && (state.status !== 'finished' || state.restart_available)) {
      if (!pollingTimer) startPolling();
    } else {
      stopPolling();
    }
  }

  function renderLobby() {
    const inviteUrl = new URL(window.location.href);
    inviteUrl.search = new URLSearchParams({ room: state.room_id }).toString();
    const activePlayers = state.players.filter((player) => !player.is_spectator);
    const spectators = state.players.length - activePlayers.length;
    document.getElementById('cemantix-lobby-status').textContent =
      `${activePlayers.length} joueur${activePlayers.length === 1 ? '' : 's'} dans le salon`
      + (spectators ? ` · ${spectators} spectateur${spectators === 1 ? '' : 's'}` : '')
      + '. Il en faut au moins deux pour démarrer.';
    document.getElementById('cemantix-invite-code').textContent = `Code : ${state.room_id}`;
    document.getElementById('cemantix-copy-invite').dataset.inviteUrl = inviteUrl.href;
    const list = document.getElementById('cemantix-player-list');
    list.replaceChildren(...state.players.map((player) => {
      const item = document.createElement('li');
      const name = document.createElement('span');
      name.textContent = player.name
        + (player.player_id === state.host_player_id ? ' (hôte)' : '')
        + (player.is_spectator ? ' (spectateur)' : '');
      const status = document.createElement('small');
      status.textContent = player.is_spectator ? 'En attente' : 'Présent';
      item.append(name, status);
      return item;
    }));
    const startButton = document.getElementById('cemantix-start-game');
    startButton.hidden = state.player_id !== state.host_player_id;
    startButton.disabled = !state.can_start || roomBusy;
  }

  let sortMode = 'score'; // 'score' | 'chrono'

  function renderHints(hints, hintDetails = []) {
    hintsContainer.replaceChildren();
    hintsContainer.hidden = !hints.length;
    if (!hints.length) return;
    const scoreByWord = new Map(
      (hintDetails || []).map((item) => [item.word, item.score]),
    );
    const title = document.createElement('strong');
    title.textContent = 'Mots reliés à explorer (cliquez pour tester)';
    const list = document.createElement('ul');
    for (const word of hints) {
      const item = document.createElement('li');
      const label = document.createElement('span');
      label.textContent = word;
      item.appendChild(label);
      const hintScore = scoreByWord.get(word);
      if (typeof hintScore === 'number') {
        const badge = document.createElement('small');
        badge.textContent = `${hintScore.toFixed(1)}°C`;
        item.appendChild(badge);
      }
      item.title = `Proposer « ${word} »`;
      item.addEventListener('click', () => {
        if (guessInput.disabled) return;
        guessInput.value = word;
        guessForm.requestSubmit();
      });
      list.append(item);
    }
    hintsContainer.append(title, list);
  }

  function scoreLabel(rank) {
    if (rank >= 1000) return 'Trouvé 🎯';
    if (rank >= 999) return 'Brûlant 🔥';
    if (rank >= 990) return 'Très chaud 🌶️';
    if (rank >= 900) return 'Chaud ☀️';
    if (rank > 0) return 'Tiède 🌤️';
    return 'Froid ❄️';
  }

  function scoreClass(rank, solved) {
    if (solved) return 'cemantix-score-solved';
    if (rank >= 990) return 'cemantix-score-hot';
    if (rank >= 900) return 'cemantix-score-warm';
    if (rank > 0) return 'cemantix-score-lukewarm';
    return '';
  }

  function appendGuessRow(list, guess) {
    const row = document.createElement('li');
    row.className = 'cemantix-guess-row';
    if (guess.passed) {
      const passed = document.createElement('span');
      passed.className = 'cemantix-passed';
      passed.textContent = `Manche ${guess.round} — pas de proposition`;
      row.appendChild(passed);
      list.appendChild(row);
      return;
    }

    const word = document.createElement('span');
    word.className = 'cemantix-guess-word';
    if (guess.attempt) {
      const num = document.createElement('span');
      num.className = 'cemantix-guess-attempt';
      num.textContent = `#${guess.attempt}`;
      word.appendChild(num);
    }
    word.append(document.createTextNode(guess.word));
    const score = document.createElement('span');
    score.className = 'cemantix-guess-score';
    const rank = Number.isInteger(guess.rank) ? guess.rank : 0;
    score.textContent =
      `${Number(guess.score).toFixed(1)}°C · ${rank}‰ · ${scoreLabel(rank)}`;
    const track = document.createElement('span');
    track.className = 'cemantix-score-track';
    const bar = document.createElement('span');
    bar.className = scoreClass(rank, guess.solved);
    bar.style.width = `${Math.max(4, Math.min(100, rank / 10))}%`;
    track.appendChild(bar);
    row.append(word, score, track);
    list.appendChild(row);
  }

  function renderSoloHistory(guesses) {
    const historyPanel = document.createElement('section');
    historyPanel.className = 'cemantix-player-history';

    if (guesses.length > 0) {
      const latest = guesses[guesses.length - 1];
      const latestBox = document.createElement('div');
      latestBox.className = 'cemantix-latest-guess';
      const latestLabel = document.createElement('span');
      latestLabel.className = 'cemantix-latest-label';
      latestLabel.textContent = 'Dernier mot testé';
      const latestList = document.createElement('ol');
      latestList.className = 'cemantix-guess-list';
      appendGuessRow(latestList, latest);
      latestBox.append(latestLabel, latestList);
      historyPanel.appendChild(latestBox);
    }

    const header = document.createElement('div');
    header.className = 'cemantix-history-header';
    const title = document.createElement('h2');
    title.textContent = `Vos propositions (${guesses.length})`;
    const sortBtn = document.createElement('button');
    sortBtn.type = 'button';
    sortBtn.className = 'cemantix-sort-button';
    sortBtn.textContent = sortMode === 'score' ? 'Trier : Proximité 🔥' : 'Trier : Chronologique 🕒';
    sortBtn.addEventListener('click', () => {
      sortMode = sortMode === 'score' ? 'chrono' : 'score';
      updateView();
    });
    header.append(title, sortBtn);

    const list = document.createElement('ol');
    list.className = 'cemantix-guess-list';
    const ordered = [...guesses];
    if (sortMode === 'score') {
      ordered.sort((a, b) => (b.rank - a.rank) || (b.score - a.score) || ((b.attempt || 0) - (a.attempt || 0)));
    } else {
      ordered.reverse();
    }
    ordered.forEach((guess) => appendGuessRow(list, guess));
    historyPanel.append(header, list);
    return historyPanel;
  }

  function renderRoomHistory(players) {
    const history = document.getElementById('cemantix-history');
    history.replaceChildren(...players.map((player) => {
      const panel = document.createElement('section');
      panel.className = 'cemantix-player-history';
      const title = document.createElement('h2');
      title.textContent = `${player.name}${player.is_spectator ? ' — spectateur' : ''}${player.player_id === state.winner_player_id ? ' — gagnant' : ''}`;
      const list = document.createElement('ol');
      list.className = 'cemantix-guess-list';
      player.guesses.forEach((guess) => appendGuessRow(list, guess));
      if (state.status === 'playing') {
        const currentRound = document.createElement('li');
        currentRound.className = 'cemantix-guess-row';
        const waiting = document.createElement('span');
        waiting.className = 'cemantix-passed';
        waiting.textContent = `Manche ${state.round_number} — ${
          player.has_submitted ? 'proposition envoyée' : 'en attente'
        }`;
        currentRound.appendChild(waiting);
        list.appendChild(currentRound);
      }
      panel.append(title, list);
      return panel;
    }));
  }

  function updateCountdown() {
    if (gameType !== 'room' || state?.status !== 'playing' || !state.deadline_at) return;
    const remaining = Math.max(0, Math.ceil(state.deadline_at - Date.now() / 1000));
    const minutes = Math.floor(remaining / 60);
    const seconds = String(remaining % 60).padStart(2, '0');
    const countdown = document.getElementById('cemantix-countdown');
    countdown.textContent = `${minutes}:${seconds}`;
    countdown.classList.toggle('cemantix-low-time', remaining <= 10);
    const progress = Math.max(0, Math.min(1, remaining / state.round_seconds));
    document.getElementById('cemantix-timer-bar').style.transform = `scaleX(${progress})`;
  }

  function renderRound() {
    const isRoom = gameType === 'room';
    const timerPanel = document.getElementById('cemantix-timer-panel');
    timerPanel.hidden = !isRoom || state.status !== 'playing';
    const soloActions = document.getElementById('cemantix-solo-actions');
    if (soloActions) soloActions.hidden = isRoom;
    const message = document.getElementById('cemantix-round-message');
    const scoreboard = document.getElementById('cemantix-scoreboard');
    const input = guessInput;
    const submit = guessForm.querySelector('button');

    if (isRoom && state.status === 'playing') {
      document.getElementById('cemantix-round-number').textContent = state.round_number;
      document.getElementById('cemantix-submission-count').textContent =
        `${state.submitted_count} / ${state.player_count} propositions reçues`;
      updateCountdown();
      const isSpectator = state.player.is_spectator;
      input.disabled = isSpectator || state.player.has_submitted;
      submit.disabled = isSpectator || state.player.has_submitted;
      input.placeholder = isSpectator
        ? 'Mode spectateur'
        : state.player.has_submitted ? 'En attente des autres…' : 'Votre mot…';
      message.textContent = isSpectator
        ? 'Vous observez cette manche. Vous pourrez jouer à partir de la prochaine.'
        : state.player.has_submitted
        ? 'Proposition envoyée. Les scores seront révélés à la fin de la manche.'
        : 'Une seule proposition cette manche. Le mot et son score restent cachés jusqu’à la révélation.';
      renderRoomHistory(state.players);
      renderHints(state.player.hints || [], state.player.hint_details || []);
      scoreboard.hidden = true;
      return;
    }

    document.getElementById('cemantix-history').replaceChildren();
    if (!isRoom) {
      const player = state.player;
      const isFinished = state.status === 'finished';
      renderHints(state.hints || [], state.hint_details || []);
      input.disabled = isFinished;
      submit.disabled = isFinished;
      input.placeholder = 'Votre mot…';
      const hintBtn = document.getElementById('cemantix-hint-button');
      const giveupBtn = document.getElementById('cemantix-giveup-button');
      if (hintBtn) hintBtn.disabled = isFinished || state.has_more_hints === false;
      if (giveupBtn) giveupBtn.hidden = isFinished;

      message.textContent = player.solved
        ? `Bien joué ! Vous avez trouvé le mot en ${player.attempts} proposition${player.attempts > 1 ? 's' : ''}.`
        : state.gave_up
        ? `Partie terminée après ${player.attempts} proposition${player.attempts === 1 ? '' : 's'}.`
        : `${player.attempts} proposition${player.attempts === 1 ? '' : 's'} effectuée${player.attempts === 1 ? '' : 's'}.`;
      if (player.guesses.length) {
        document.getElementById('cemantix-history').appendChild(renderSoloHistory(player.guesses));
      }
      if (isFinished) {
        scoreboard.hidden = false;
        scoreboard.replaceChildren();
        const title = document.createElement('h2');
        title.textContent = `Le mot secret était « ${state.target} »`;
        const details = document.createElement('p');
        details.textContent = 'Vous pouvez lancer une nouvelle partie quand vous le souhaitez.';
        scoreboard.append(title, details);
      } else {
        scoreboard.hidden = true;
      }
      return;
    }

    input.disabled = true;
    renderHints(state.player.hints || [], state.player.hint_details || []);
    submit.disabled = true;
    message.textContent = state.player.is_spectator
      ? 'Vous avez observé cette partie jusqu’à la fin.'
      : state.winner_player_id === state.player_id
        ? 'Bravo, vous avez trouvé le mot en premier !'
        : `${state.players.find((player) => player.player_id === state.winner_player_id)?.name || 'Un joueur'} a trouvé le mot en premier.`;
    renderRoomHistory(state.players);
    scoreboard.hidden = false;
    scoreboard.replaceChildren();
    const title = document.createElement('h2');
    title.textContent = `Le mot secret était « ${state.target} »`;
    scoreboard.appendChild(title);
    if (state.can_restart) {
      const restart = document.createElement('button');
      restart.type = 'button';
      restart.className = 'cemantix-primary-button';
      restart.id = 'cemantix-restart-room';
      restart.textContent = 'Relancer une partie';
      scoreboard.appendChild(restart);
    }
  }

  async function startSolo() {
    const button = document.getElementById('cemantix-solo-button');
    setBusy(button, true, 'Préparation…');
    hideError(homeError);
    try {
      state = await post('/api/cemantix/solo/new', {
        player_id: playerId,
        player_name: playerName,
        difficulty: difficultySelect.value,
      });
      gameType = 'solo';
      difficultySelect.value = state.difficulty || 'moyen';
      localStorage.setItem('cemantix_solo_game_id', state.game_id);
      localStorage.setItem('cemantix_active_game_mode', 'solo');
      localStorage.removeItem('cemantix_active_room_id');
      updateView();
      guessInput.focus();
    } catch (error) {
      showError(homeError, error.message);
    } finally {
      setBusy(button, false);
    }
  }

  async function resumeSolo() {
    const gameId = localStorage.getItem('cemantix_solo_game_id');
    if (!gameId) return;
    hideError(homeError);
    try {
      state = await request(`/api/cemantix/solo/${encodeURIComponent(gameId)}?player_id=${encodeURIComponent(playerId)}`);
      gameType = 'solo';
      localStorage.setItem('cemantix_active_game_mode', 'solo');
      localStorage.removeItem('cemantix_active_room_id');
      difficultySelect.value = state.difficulty || 'moyen';
      updateView();
    } catch (error) {
      localStorage.removeItem('cemantix_solo_game_id');
      showError(homeError, `Impossible de reprendre cette partie : ${error.message}`);
    }
  }

  async function createRoom() {
    const button = document.getElementById('cemantix-create-room');
    setBusy(button, true, 'Création…');
    hideError(homeError);
    try {
      state = await post('/api/cemantix/room/create', {
        player_id: playerId,
        player_name: playerName,
        difficulty: difficultySelect.value,
      });
      gameType = 'room';
      difficultySelect.value = state.difficulty || 'moyen';
      localStorage.setItem('cemantix_active_game_mode', 'room');
      localStorage.setItem('cemantix_active_room_id', state.room_id);
      history.replaceState(null, '', `${window.location.pathname}?room=${encodeURIComponent(state.room_id)}`);
      updateView();
    } catch (error) {
      showError(homeError, error.message);
    } finally {
      setBusy(button, false);
    }
  }

  async function joinRoom(roomId) {
    const cleanRoomId = roomId.trim().toUpperCase();
    if (!cleanRoomId) {
      showError(homeError, 'Saisissez le code du salon.');
      return;
    }
    hideError(homeError);
    try {
      state = await post('/api/cemantix/room/join', {
        room_id: cleanRoomId,
        player_id: playerId,
        player_name: playerName,
      });
      gameType = 'room';
      difficultySelect.value = state.difficulty || 'moyen';
      localStorage.setItem('cemantix_active_game_mode', 'room');
      localStorage.setItem('cemantix_active_room_id', state.room_id);
      history.replaceState(null, '', `${window.location.pathname}?room=${encodeURIComponent(state.room_id)}`);
      updateView();
    } catch (error) {
      showError(homeError, error.message);
    }
  }

  async function startRoom() {
    if (!state || roomBusy) return;
    roomBusy = true;
    roomRefreshGeneration += 1;
    const button = document.getElementById('cemantix-start-game');
    button.disabled = true;
    hideError(playError);
    try {
      state = await post('/api/cemantix/room/start', {
        room_id: state.room_id,
        player_id: playerId,
        player_name: playerName,
      });
      updateView();
      guessInput.focus();
    } catch (error) {
      showError(playError, error.message);
    } finally {
      roomBusy = false;
      if (state?.status === 'lobby') renderLobby();
    }
  }

  async function restartRoom() {
    if (!state || state.status !== 'finished' || !state.can_restart || roomBusy) return;
    roomBusy = true;
    roomRefreshGeneration += 1;
    hideError(playError);
    try {
      state = await post('/api/cemantix/room/restart', {
        room_id: state.room_id,
        player_id: playerId,
        player_name: playerName,
      });
      updateView();
    } catch (error) {
      showError(playError, error.message);
    } finally {
      roomBusy = false;
    }
  }

  async function submitGuess(event) {
    event.preventDefault();
    if (!state || guessInput.disabled || state.player.is_spectator) return;
    const isRoomGuess = gameType === 'room';
    if (isRoomGuess) {
      roomBusy = true;
      roomRefreshGeneration += 1;
    }
    hideError(playError);
    const guess = guessInput.value.trim();
    const submit = guessForm.querySelector('button');
    setBusy(submit, true, 'Envoi…');
    try {
      if (gameType === 'solo') {
        state = await post('/api/cemantix/solo/guess', {
          game_id: state.game_id,
          player_id: playerId,
          player_name: playerName,
          guess,
        });
        if (state.status === 'finished') localStorage.removeItem('cemantix_solo_game_id');
      } else {
        state = await post('/api/cemantix/room/guess', {
          room_id: state.room_id,
          player_id: playerId,
          player_name: playerName,
          guess,
        });
      }
      guessInput.value = '';
      updateView();
      if (!guessInput.disabled) guessInput.focus();
    } catch (error) {
      showError(playError, error.message);
      guessInput.focus();
    } finally {
      if (isRoomGuess) roomBusy = false;
      setBusy(submit, false);
      if (guessInput.disabled) submit.disabled = true;
    }
  }

  async function refreshRoom() {
    if (gameType !== 'room' || !state || roomRefreshing || roomBusy) return;
    roomRefreshing = true;
    const generation = ++roomRefreshGeneration;
    try {
      const nextState = await request(
        `/api/cemantix/room/${encodeURIComponent(state.room_id)}?player_id=${encodeURIComponent(playerId)}`,
      );
      if (generation !== roomRefreshGeneration || gameType !== 'room') return;
      state = nextState;
      updateView();
    } catch (error) {
      if (generation !== roomRefreshGeneration || gameType !== 'room') return;
      stopPolling();
      showError(playError, error.message);
    } finally {
      roomRefreshing = false;
    }
  }

  function normalizeInput(value) {
    return value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()
      .replace(/œ/g, 'oe').replace(/æ/g, 'ae').replace(/[^a-z]/g, '').slice(0, 40);
  }

  async function requestSoloHint() {
    if (gameType !== 'solo' || !state || state.status === 'finished') return;
    hideError(playError);
    try {
      state = await post('/api/cemantix/solo/hint', {
        game_id: state.game_id,
        player_id: playerId,
        player_name: playerName,
      });
      updateView();
    } catch (error) {
      showError(playError, error.message);
    }
  }

  async function giveUpSolo() {
    if (gameType !== 'solo' || !state || state.status === 'finished') return;
    hideError(playError);
    try {
      state = await post('/api/cemantix/solo/giveup', {
        game_id: state.game_id,
        player_id: playerId,
        player_name: playerName,
      });
      localStorage.removeItem('cemantix_solo_game_id');
      updateView();
    } catch (error) {
      showError(playError, error.message);
    }
  }

  document.getElementById('cemantix-solo-button').addEventListener('click', startSolo);
  document.getElementById('cemantix-resume-solo').addEventListener('click', resumeSolo);
  document.getElementById('cemantix-hint-button')?.addEventListener('click', requestSoloHint);
  document.getElementById('cemantix-giveup-button')?.addEventListener('click', giveUpSolo);
  document.getElementById('cemantix-new-solo-button')?.addEventListener('click', startSolo);
  document.getElementById('cemantix-create-room').addEventListener('click', createRoom);
  document.getElementById('cemantix-refresh-rooms').addEventListener('click', refreshRoomDirectory);
  document.getElementById('cemantix-join-room').addEventListener('click', () =>
    joinRoom(document.getElementById('cemantix-room-code').value));
  document.getElementById('cemantix-room-code').addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      joinRoom(event.currentTarget.value);
    }
  });
  document.getElementById('cemantix-start-game').addEventListener('click', startRoom);
  document.getElementById('cemantix-scoreboard').addEventListener('click', (event) => {
    if (event.target.id === 'cemantix-restart-room') restartRoom();
  });
  document.getElementById('cemantix-home-button').addEventListener('click', () => showHome(true));
  document.getElementById('cemantix-copy-invite').addEventListener('click', async (event) => {
    const url = event.currentTarget.dataset.inviteUrl;
    try {
      await navigator.clipboard.writeText(url);
      event.currentTarget.textContent = 'Lien copié !';
      window.setTimeout(() => { event.currentTarget.textContent = 'Copier le lien'; }, 1600);
    } catch {
      window.prompt('Copiez ce lien pour inviter vos amis :', url);
    }
  });
  guessForm.addEventListener('submit', submitGuess);
  guessInput.addEventListener('input', () => {
    const normalized = normalizeInput(guessInput.value);
    if (guessInput.value !== normalized) guessInput.value = normalized;
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !play.hidden) showHome();
  });

  if (params.has('room')) {
    joinRoom(params.get('room'));
  } else if (localStorage.getItem('cemantix_active_game_mode') === 'room'
    && localStorage.getItem('cemantix_active_room_id')) {
    joinRoom(localStorage.getItem('cemantix_active_room_id'));
  } else if ((localStorage.getItem('cemantix_active_game_mode') === 'solo'
    || (!localStorage.getItem('cemantix_active_game_mode')
      && localStorage.getItem('cemantix_solo_game_id')))
    && localStorage.getItem('cemantix_solo_game_id')) {
    resumeSolo();
  } else {
    localStorage.removeItem('cemantix_active_room_id');
    showHome(false);
  }
})();
