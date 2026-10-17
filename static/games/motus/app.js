(() => {
  const apiBase = window.PEDANTIX_CONFIG?.BACKEND_URL?.replace(/\/+$/, '') || '';
  const home = document.getElementById('motus-home');
  const play = document.getElementById('motus-play');
  const homeError = document.getElementById('motus-home-error');
  const playError = document.getElementById('motus-play-error');
  const guessInput = document.getElementById('motus-guess');
  const guessForm = document.getElementById('motus-guess-form');
  const keyboard = document.getElementById('motus-keyboard');
  const difficultySelect = document.getElementById('motus-difficulty');
  const roomDirectory = document.getElementById('motus-room-directory');
  const alphabet = 'AZERTYUIOPQSDFGHJKLMWXCVBN';
  const params = new URLSearchParams(window.location.search);
  let playerId = localStorage.getItem('motus_player_id');
  if (!playerId) {
    playerId = globalThis.crypto?.randomUUID?.() || `motus-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    localStorage.setItem('motus_player_id', playerId);
  }
  const playerName = (localStorage.getItem('pedantix_player_name')
    || localStorage.getItem('pedantix_auth_user')
    || 'Joueur').trim().slice(0, 24);
  let state = null;
  let gameType = null;
  let pollingTimer = null;
  let renderedGuesses = '';
  let roomBusy = false;
  let entry = [];
  let lockedLetters = {};

  document.getElementById('motus-player-name').textContent = playerName;

  async function request(path, options = {}) {
    const response = await fetch(`${apiBase}${path}`, {
      ...options,
      headers: {
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...options.headers,
      },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || 'Une erreur est survenue. Réessayez.');
    }
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
    pollingTimer = window.setInterval(refreshRoom, 1800);
  }

  function showHome(clearActiveGame = true) {
    stopPolling();
    gameType = null;
    state = null;
    home.hidden = false;
    play.hidden = true;
    if (clearActiveGame) {
      localStorage.setItem('motus_active_game_mode', 'home');
      localStorage.removeItem('motus_active_room_id');
    }
    const hasSavedGame = !!localStorage.getItem('motus_solo_game_id');
    document.getElementById('motus-previous-game').hidden = !hasSavedGame;
    history.replaceState(null, '', window.location.pathname);
    refreshRoomDirectory();
  }

  function renderRoomDirectory(rooms) {
    roomDirectory.replaceChildren();
    if (!rooms.length) {
      const empty = document.createElement('p');
      empty.className = 'motus-room-empty';
      empty.textContent = 'Aucun salon ouvert pour le moment.';
      roomDirectory.append(empty);
      return;
    }
    for (const room of rooms) {
      const card = document.createElement('div');
      card.className = 'motus-room-card';
      const copy = document.createElement('span');
      copy.className = 'motus-room-card-copy';
      const title = document.createElement('strong');
      title.textContent = `Salon ${room.room_id}`;
      const details = document.createElement('small');
      details.textContent = `${room.player_count} joueur${room.player_count === 1 ? '' : 's'} · ${room.difficulty} · ${room.status === 'playing' ? 'En cours' : 'En attente'}`;
      copy.append(title, details);
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'motus-secondary-button';
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
      const data = await request(`/api/motus/rooms?player_id=${encodeURIComponent(playerId)}`);
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
    document.getElementById('motus-game-mode').textContent = isRoom
      ? state.player.is_spectator ? 'Défi multijoueur · Spectateur' : 'Défi multijoueur'
      : 'Partie solo';
    document.getElementById('motus-game-title').textContent = state.status === 'finished'
      ? 'Partie terminée'
      : 'Trouvez le mot';
    document.getElementById('motus-hint').textContent = `Le mot fait ${state.word_length} lettres. Sa première lettre est révélée. Vous avez ${state.max_attempts} essais.`;
    document.getElementById('motus-lobby').hidden = !isRoom || state.status !== 'lobby';
    document.getElementById('motus-round').hidden = state.status === 'lobby';
    if (isRoom && state.status === 'lobby') renderLobby();
    if (state.status !== 'lobby') renderRound();
  }

  function renderLobby() {
    const roomId = state.room_id;
    const inviteUrl = new URL(window.location.href);
    inviteUrl.search = new URLSearchParams({ room: roomId }).toString();
    const activePlayers = state.players.filter((player) => !player.is_spectator);
    const spectators = state.players.length - activePlayers.length;
    document.getElementById('motus-lobby-status').textContent =
      `${activePlayers.length} joueur${activePlayers.length === 1 ? '' : 's'} dans le salon`
      + (spectators ? ` · ${spectators} spectateur${spectators === 1 ? '' : 's'}` : '')
      + '. Il en faut au moins deux pour démarrer.';
    document.getElementById('motus-invite-code').textContent = `Code : ${roomId}`;
    document.getElementById('motus-copy-invite').dataset.inviteUrl = inviteUrl.href;
    const list = document.getElementById('motus-player-list');
    list.replaceChildren(...state.players.map((player) => {
      const item = document.createElement('li');
      const name = document.createElement('span');
      name.textContent = player.name
        + (player.player_id === state.host_player_id ? ' (hôte)' : '')
        + (player.is_spectator ? ' (spectateur)' : '');
      const status = document.createElement('small');
      status.textContent = player.is_spectator ? 'En attente' : 'Prêt';
      item.append(name, status);
      return item;
    }));
    const startButton = document.getElementById('motus-start-game');
    startButton.hidden = state.player.player_id !== state.host_player_id;
    startButton.disabled = !state.can_start || roomBusy;
  }

  function renderRound() {
    const player = state.player;
    const guessesKey = JSON.stringify(player.guesses);
    if (guessesKey !== renderedGuesses) {
      lockedLetters = getLockedLetters(player.guesses, state.first_letter);
      entry = Array(state.word_length).fill('');
      for (const [index, letter] of Object.entries(lockedLetters)) {
        entry[Number(index)] = letter;
      }
      renderKeyboard(player.guesses);
      renderedGuesses = guessesKey;
    }

    const message = document.getElementById('motus-round-message');
    const isSpectator = player.is_spectator;
    const roundFinished = isSpectator || player.finished || state.status === 'finished';
    guessInput.disabled = roundFinished;
    const displayedEntry = entry.map((letter) => letter || ' ').join('');
    if (guessInput.value !== displayedEntry) guessInput.value = displayedEntry;
    guessForm.querySelector('button').disabled =
      roundFinished || entry.some((letter) => !letter);
    guessInput.placeholder = `${state.first_letter}_____`;
    renderBoard(player.guesses, state.first_letter, state.max_attempts, entry);

    if (isSpectator) {
      message.textContent = 'Vous observez cette partie. Vous pourrez jouer au prochain redémarrage.';
    } else if (state.status === 'finished') {
      message.textContent = state.target
        ? `Le mot était ${state.target}.`
        : 'La partie est terminée.';
    } else if (player.solved) {
      message.textContent = `Bien joué ! Mot trouvé en ${player.guesses.length} essai${player.guesses.length > 1 ? 's' : ''}. En attente des autres joueurs…`;
    } else if (player.finished) {
      message.textContent = 'Plus d’essais. En attente des autres joueurs…';
    } else {
      message.textContent = `${state.max_attempts - player.guesses.length} essai${state.max_attempts - player.guesses.length > 1 ? 's' : ''} restant${state.max_attempts - player.guesses.length > 1 ? 's' : ''}.`;
    }

    renderScoreboard();
  }

  function getLockedLetters(guesses, firstLetter) {
    const locked = { 0: firstLetter };
    for (const guess of guesses) {
      guess.feedback.forEach((feedback, index) => {
        if (feedback === 'correct') locked[index] = guess.word[index].toUpperCase();
      });
    }
    return locked;
  }

  function renderBoard(guesses, firstLetter, maxAttempts, currentEntry) {
    const board = document.getElementById('motus-board');
    board.replaceChildren();
    for (let rowIndex = 0; rowIndex < maxAttempts; rowIndex += 1) {
      const row = document.createElement('div');
      row.className = 'motus-board-row';
      row.setAttribute('role', 'row');
      const guess = guesses[rowIndex];
      for (let column = 0; column < state.word_length; column += 1) {
        const tile = document.createElement('span');
        tile.className = 'motus-tile';
        tile.setAttribute('role', 'gridcell');
        if (guess) {
          tile.textContent = guess.word[column].toUpperCase();
          tile.classList.add(`motus-${guess.feedback[column]}`);
        } else if (rowIndex === guesses.length) {
          const typedLetter = currentEntry[column];
          const hintLetter = lockedLetters[column];
          if (typedLetter) {
            tile.textContent = typedLetter;
            tile.classList.add(
              hintLetter && typedLetter === hintLetter ? 'motus-hint-tile' : 'motus-entry-tile',
            );
          } else if (hintLetter) {
            tile.textContent = hintLetter;
            tile.classList.add('motus-hint-tile');
          } else if (column === 0) {
            tile.textContent = firstLetter;
            tile.classList.add('motus-hint-tile');
          }
          if (column > 0 && !guessInput.disabled) {
            tile.style.cursor = 'pointer';
            tile.addEventListener('click', () => {
              guessInput.focus();
              guessInput.setSelectionRange(column, column);
            });
          }
        } else if (column === 0) {
          tile.textContent = firstLetter;
          tile.classList.add('motus-hint-tile');
        }
        row.appendChild(tile);
      }
      board.appendChild(row);
    }
  }

  function renderKeyboard(guesses) {
    const keyStatus = {};
    const priority = { absent: 1, present: 2, correct: 3 };
    for (const guess of guesses) {
      guess.word.split('').forEach((letter, index) => {
        const status = guess.feedback[index];
        if (!keyStatus[letter] || priority[status] > priority[keyStatus[letter]]) keyStatus[letter] = status;
      });
    }
    keyboard.replaceChildren();
    for (const letter of alphabet) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = `motus-key${keyStatus[letter] ? ` motus-${keyStatus[letter]}` : ''}`;
      button.textContent = letter;
      button.dataset.letter = letter;
      keyboard.appendChild(button);
    }
    for (const [label, action] of [['⌫', 'backspace'], ['Entrée', 'submit']]) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'motus-key motus-key-wide';
      button.textContent = label;
      button.dataset.action = action;
      keyboard.appendChild(button);
    }
  }

  function renderScoreboard() {
    const scoreboard = document.getElementById('motus-scoreboard');
    if (gameType !== 'room') {
      if (state.status === 'finished') {
        scoreboard.hidden = false;
        scoreboard.replaceChildren();
        const title = document.createElement('h2');
        title.textContent = state.player.solved
          ? `Bravo ! ${state.player.score} points`
          : 'Partie terminée';
        const details = document.createElement('p');
        details.textContent = `Le mot était ${state.target}.`;
        const restart = document.createElement('button');
        restart.type = 'button';
        restart.className = 'motus-primary-button';
        restart.id = 'motus-new-game';
        restart.textContent = 'Nouvelle partie';
        scoreboard.append(title, details, restart);
      } else {
        scoreboard.hidden = true;
      }
      return;
    }

    scoreboard.hidden = false;
    scoreboard.replaceChildren();
    const title = document.createElement('h2');
    title.textContent = state.status === 'finished' ? 'Résultats du défi' : 'Joueurs';
    const results = document.createElement('ol');
    const ordered = [...state.players].sort((a, b) =>
      Number(a.is_spectator) - Number(b.is_spectator)
      || Number(b.solved) - Number(a.solved)
      || (b.score - a.score)
      || (a.attempts - b.attempts)
      || a.name.localeCompare(b.name));
    for (const player of ordered) {
      const item = document.createElement('li');
      const result = player.is_spectator
        ? 'Spectateur · en attente du prochain match'
        : player.solved
        ? `${player.score} pts · ${player.attempts} essai${player.attempts > 1 ? 's' : ''}`
        : player.finished ? 'Mot non trouvé' : `${player.attempts} / ${state.max_attempts} essais`;
      item.textContent = `${player.name} — ${result}`;
      results.appendChild(item);
    }
    scoreboard.append(title, results);
    if (state.can_restart) {
      const restart = document.createElement('button');
      restart.type = 'button';
      restart.className = 'motus-primary-button';
      restart.id = 'motus-restart-room';
      restart.textContent = 'Relancer une partie';
      scoreboard.appendChild(restart);
    }
  }

  function nextEditableIndex(startIndex) {
    for (let index = Math.max(0, startIndex); index < entry.length; index += 1) {
      if (index > 0 && !entry[index]) return index;
    }
    for (let index = 1; index < Math.min(startIndex, entry.length); index += 1) {
      if (index > 0 && !entry[index]) return index;
    }
    return entry.length;
  }

  function effectiveEntry() {
    return entry.map((letter, idx) => letter || lockedLetters[idx] || '');
  }

  function updateEntry(nextIndex) {
    guessInput.value = entry.map((letter) => letter || ' ').join('');
    renderBoard(state.player.guesses, state.first_letter, state.max_attempts, entry);
    const full = effectiveEntry();
    guessForm.querySelector('button').disabled =
      state.player.finished || state.player.is_spectator || full.some((letter) => !letter);
    guessInput.focus();
    guessInput.setSelectionRange(nextIndex, nextIndex);
  }

  function insertEntryText(text, start, end) {
    const letters = normalizeInput(text);
    if (!letters) return;
    if (start !== end) {
      for (let index = start; index < end; index += 1) {
        if (index > 0) entry[index] = '';
      }
    }
    let index = Math.max(start, 1);
    if (letters.length === state.word_length && letters[0] === state.first_letter) {
      index = 0;
    }
    for (const letter of letters) {
      if (index >= entry.length) break;
      if (index === 0) {
        index += 1;
        continue;
      }
      entry[index] = letter;
      index += 1;
    }
    updateEntry(nextEditableIndex(index));
  }

  function deleteEntryText(start, end, direction) {
    let changed = false;
    let nextIndex = start;
    if (start !== end) {
      for (let index = start; index < end; index += 1) {
        if (index > 0) {
          entry[index] = '';
          changed = true;
        }
      }
    } else {
      let index = direction < 0 ? start - 1 : start;
      while (
        index >= 0
        && index < entry.length
        && (index === 0 || !entry[index])
      ) {
        index += direction;
      }
      if (index >= 0 && index < entry.length) {
        entry[index] = '';
        changed = true;
        nextIndex = index;
      }
    }
    if (changed) updateEntry(nextIndex);
  }

  function editEntry(inputEvent) {
    if (guessInput.disabled) return;
    const start = guessInput.selectionStart ?? entry.length;
    const end = guessInput.selectionEnd ?? start;
    if (inputEvent.inputType.startsWith('insert') && inputEvent.data) {
      inputEvent.preventDefault();
      insertEntryText(inputEvent.data, start, end);
    } else if (inputEvent.inputType === 'deleteContentBackward') {
      inputEvent.preventDefault();
      deleteEntryText(start, end, -1);
    } else if (inputEvent.inputType === 'deleteContentForward') {
      inputEvent.preventDefault();
      deleteEntryText(start, end, 1);
    }
  }

  function renderBoardFromState() {
    renderedGuesses = '';
    updateView();
  }

  async function startSolo() {
    const button = document.getElementById('motus-solo-button');
    setBusy(button, true, 'Préparation…');
    hideError(homeError);
    try {
      state = await post('/api/motus/solo/new', {
        player_id: playerId,
        player_name: playerName,
        difficulty: difficultySelect.value,
      });
      gameType = 'solo';
      renderedGuesses = '';
      localStorage.setItem('motus_solo_game_id', state.game_id);
      localStorage.setItem('motus_active_game_mode', 'solo');
      localStorage.removeItem('motus_active_room_id');
      updateView();
      guessInput.focus();
    } catch (error) {
      showError(homeError, error.message);
    } finally {
      setBusy(button, false);
    }
  }

  async function resumeSolo() {
    const gameId = localStorage.getItem('motus_solo_game_id');
    if (!gameId) return;
    hideError(homeError);
    try {
      state = await request(`/api/motus/solo/${encodeURIComponent(gameId)}?player_id=${encodeURIComponent(playerId)}`);
      gameType = 'solo';
      localStorage.setItem('motus_active_game_mode', 'solo');
      localStorage.removeItem('motus_active_room_id');
      difficultySelect.value = state.difficulty || 'moyen';
      renderedGuesses = '';
      updateView();
    } catch (error) {
      localStorage.removeItem('motus_solo_game_id');
      showError(homeError, `Impossible de reprendre cette partie : ${error.message}`);
    }
  }

  async function createRoom() {
    const button = document.getElementById('motus-create-room');
    setBusy(button, true, 'Création…');
    hideError(homeError);
    try {
      state = await post('/api/motus/room/create', {
        player_id: playerId,
        player_name: playerName,
        difficulty: difficultySelect.value,
      });
      gameType = 'room';
      renderedGuesses = '';
      localStorage.setItem('motus_active_game_mode', 'room');
      localStorage.setItem('motus_active_room_id', state.room_id);
      history.replaceState(null, '', `${window.location.pathname}?room=${encodeURIComponent(state.room_id)}`);
      updateView();
      startPolling();
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
      state = await post('/api/motus/room/join', {
        room_id: cleanRoomId,
        player_id: playerId,
        player_name: playerName,
      });
      gameType = 'room';
      localStorage.setItem('motus_active_game_mode', 'room');
      localStorage.setItem('motus_active_room_id', state.room_id);
      difficultySelect.value = state.difficulty || 'moyen';
      renderedGuesses = '';
      history.replaceState(null, '', `${window.location.pathname}?room=${encodeURIComponent(state.room_id)}`);
      updateView();
      startPolling();
    } catch (error) {
      showError(homeError, error.message);
    }
  }

  async function startRoom() {
    if (!state || roomBusy) return;
    roomBusy = true;
    const button = document.getElementById('motus-start-game');
    button.disabled = true;
    hideError(playError);
    try {
      state = await post('/api/motus/room/start', {
        room_id: state.room_id,
        player_id: playerId,
        player_name: playerName,
      });
      renderedGuesses = '';
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
    hideError(playError);
    try {
      state = await post('/api/motus/room/restart', {
        room_id: state.room_id,
        player_id: playerId,
        player_name: playerName,
      });
      renderedGuesses = '';
      updateView();
    } catch (error) {
      showError(playError, error.message);
    } finally {
      roomBusy = false;
    }
  }

  async function submitGuess(event) {
    event.preventDefault();
    if (!state || state.player.finished || state.player.is_spectator) return;
    hideError(playError);
    const full = effectiveEntry();
    if (full.some((letter) => !letter)) {
      showError(playError, 'Complétez les cases vides avant de valider.');
      return;
    }
    const guess = full.join('');
    const submit = guessForm.querySelector('button');
    setBusy(submit, true, '…');
    try {
      if (gameType === 'solo') {
        state = await post('/api/motus/solo/guess', {
          game_id: state.game_id,
          player_id: playerId,
          player_name: playerName,
          guess,
        });
        localStorage.setItem('motus_solo_game_id', state.game_id);
      } else {
        state = await post('/api/motus/room/guess', {
          room_id: state.room_id,
          player_id: playerId,
          player_name: playerName,
          guess,
        });
      }
      renderedGuesses = '';
      updateView();
      if (state.status === 'finished' && gameType === 'solo') {
        localStorage.removeItem('motus_solo_game_id');
      }
      if (!state.player.finished) guessInput.focus();
    } catch (error) {
      showError(playError, error.message);
      guessInput.focus();
    } finally {
      setBusy(submit, false);
      if (state?.player.finished) submit.disabled = true;
    }
  }

  async function refreshRoom() {
    if (gameType !== 'room' || !state || roomBusy) return;
    try {
      const nextState = await request(
        `/api/motus/room/${encodeURIComponent(state.room_id)}?player_id=${encodeURIComponent(playerId)}`,
      );
      const becameFinished = state.status !== 'finished' && nextState.status === 'finished';
      state = nextState;
      if (becameFinished) renderedGuesses = '';
      updateView();
      if (state.status === 'finished' && !state.restart_available) stopPolling();
    } catch (error) {
      stopPolling();
      showError(playError, error.message);
    }
  }

  function normalizeInput(value) {
    return value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase().replace(/[^A-Z]/g, '').slice(0, 6);
  }

  document.getElementById('motus-solo-button').addEventListener('click', startSolo);
  document.getElementById('motus-resume-solo').addEventListener('click', resumeSolo);
  document.getElementById('motus-create-room').addEventListener('click', createRoom);
  document.getElementById('motus-refresh-rooms').addEventListener('click', refreshRoomDirectory);
  document.getElementById('motus-join-room').addEventListener('click', () =>
    joinRoom(document.getElementById('motus-room-code').value));
  document.getElementById('motus-room-code').addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      joinRoom(event.currentTarget.value);
    }
  });
  document.getElementById('motus-start-game').addEventListener('click', startRoom);
  document.getElementById('motus-home-button').addEventListener('click', showHome);
  document.getElementById('motus-copy-invite').addEventListener('click', async (event) => {
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
  guessInput.addEventListener('beforeinput', editEntry);
  keyboard.addEventListener('click', (event) => {
    const button = event.target.closest('button');
    if (!button || guessInput.disabled) return;
    if (button.dataset.action === 'submit') {
      guessForm.requestSubmit();
    } else if (button.dataset.action === 'backspace') {
      const start = guessInput.selectionStart ?? entry.length;
      const end = guessInput.selectionEnd ?? start;
      deleteEntryText(start, end, -1);
    } else if (button.dataset.letter) {
      const start = guessInput.selectionStart ?? entry.length;
      const end = guessInput.selectionEnd ?? start;
      insertEntryText(button.dataset.letter, start, end);
    }
  });
  document.getElementById('motus-scoreboard').addEventListener('click', (event) => {
    if (event.target.id === 'motus-new-game') startSolo();
    if (event.target.id === 'motus-restart-room') restartRoom();
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !play.hidden) showHome();
  });

  if (params.has('room')) {
    joinRoom(params.get('room'));
  } else if (localStorage.getItem('motus_active_game_mode') === 'room'
    && localStorage.getItem('motus_active_room_id')) {
    joinRoom(localStorage.getItem('motus_active_room_id'));
  } else if ((localStorage.getItem('motus_active_game_mode') === 'solo'
    || (!localStorage.getItem('motus_active_game_mode')
      && localStorage.getItem('motus_solo_game_id')))
    && localStorage.getItem('motus_solo_game_id')) {
    resumeSolo();
  } else {
    localStorage.removeItem('motus_active_room_id');
    showHome(false);
  }
})();
