(() => {
  const apiBase = window.PEDANTIX_CONFIG?.BACKEND_URL?.replace(/\/+$/, '') || '';
  const home = document.getElementById('sudoku-home');
  const play = document.getElementById('sudoku-play');
  const homeError = document.getElementById('sudoku-home-error');
  const playError = document.getElementById('sudoku-play-error');
  const difficultySelect = document.getElementById('sudoku-difficulty');
  const roomDifficultySelect = document.getElementById('sudoku-room-difficulty');
  const roomInput = document.getElementById('sudoku-room-code');
  const roomDirectory = document.getElementById('sudoku-room-directory');
  const params = new URLSearchParams(window.location.search);
  let playerId = localStorage.getItem('sudoku_player_id');
  if (!playerId) {
    playerId = globalThis.crypto?.randomUUID?.()
      || `sudoku-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    localStorage.setItem('sudoku_player_id', playerId);
  }
  const playerName = (localStorage.getItem('pedantix_player_name')
    || localStorage.getItem('pedantix_auth_user')
    || 'Joueur').trim().slice(0, 24);

  let state = null;
  let gameType = null;
  let pollingTimer = null;
  let countdownTimer = null;
  let roomBusy = false;
  let pendingWrites = 0;
  let writeRevision = 0;
  let writeQueue = Promise.resolve();
  let selectedCell = [0, 0];
  let notes = {};
  let notesMode = false;
  let elapsedTimer = null;

  document.getElementById('sudoku-player-name').textContent = playerName;

  function formatLeaderboardTime(seconds) {
    const minutes = Math.floor(seconds / 60);
    return `${minutes}:${String(seconds % 60).padStart(2, '0')}`;
  }

  async function refreshLeaderboard() {
    const list = document.getElementById('sudoku-leaderboard');
    const title = document.getElementById('sudoku-leaderboard-title');
    const difficulty = difficultySelect.value;
    title.textContent = `Meilleurs temps · ${difficulty[0].toUpperCase()}${difficulty.slice(1)}`;
    try {
      const data = await request(
        `/api/game-leaderboard?game_id=sudoku&difficulty=${encodeURIComponent(difficulty)}`,
      );
      list.replaceChildren();
      if (!data.records.length) {
        const empty = document.createElement('li');
        empty.className = 'shared-solo-leaderboard-empty';
        empty.textContent = 'Aucune partie résolue pour le moment.';
        list.append(empty);
        return;
      }
      data.records.forEach((record, index) => {
        const item = document.createElement('li');
        const rank = document.createElement('span');
        rank.className = 'shared-solo-leaderboard-rank';
        rank.textContent = `${index + 1}.`;
        const name = document.createElement('span');
        name.className = 'shared-solo-leaderboard-player';
        name.textContent = record.player_name;
        const detail = document.createElement('span');
        detail.className = 'shared-solo-leaderboard-detail';
        detail.textContent = `${formatLeaderboardTime(record.duration_seconds)} · ${record.attempts} erreur${record.attempts === 1 ? '' : 's'}`;
        item.append(rank, name, detail);
        list.append(item);
      });
    } catch (error) {
      list.replaceChildren();
      const item = document.createElement('li');
      item.className = 'shared-solo-leaderboard-empty';
      item.textContent = `Classement indisponible : ${error.message}`;
      list.append(item);
    }
  }

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
    if (!button.dataset.originalHtml) button.dataset.originalHtml = button.innerHTML;
    button.disabled = busy;
    button.innerHTML = busy ? busyText : button.dataset.originalHtml;
  }

  function stopTimers() {
    if (pollingTimer) window.clearInterval(pollingTimer);
    if (countdownTimer) window.clearInterval(countdownTimer);
    if (elapsedTimer) window.clearInterval(elapsedTimer);
    pollingTimer = null;
    countdownTimer = null;
    elapsedTimer = null;
  }

  async function showHome(clearActiveGame = true) {
    if (clearActiveGame && gameType === 'room' && state?.room_id) {
      stopTimers();
      try {
        await post('/api/sudoku/room/leave', {
          room_id: state.room_id,
          player_id: playerId,
        });
      } catch (error) {
        showError(playError, error.message);
        if (gameType === 'room') updateView();
        return;
      }
    }
    stopTimers();
    state = null;
    gameType = null;
    home.hidden = false;
    play.hidden = true;
    if (clearActiveGame) {
      localStorage.setItem('sudoku_active_game_mode', 'home');
      localStorage.removeItem('sudoku_active_room_id');
    }
    document.getElementById('sudoku-previous-game').hidden =
      !localStorage.getItem('sudoku_solo_game_id');
    history.replaceState(null, '', window.location.pathname);
    refreshLeaderboard();
    refreshRoomDirectory();
  }

  function renderRoomDirectory(rooms) {
    roomDirectory.replaceChildren();
    if (!rooms.length) {
      const empty = document.createElement('p');
      empty.className = 'sudoku-room-empty';
      empty.textContent = 'Aucun salon ouvert pour le moment.';
      roomDirectory.append(empty);
      return;
    }
    for (const room of rooms) {
      const card = document.createElement('div');
      card.className = 'sudoku-room-card';
      const copy = document.createElement('span');
      copy.className = 'sudoku-room-card-copy';
      const title = document.createElement('strong');
      title.textContent = `Salon ${room.room_id}`;
      const details = document.createElement('small');
      const spectators = room.spectator_count
        ? ` · ${room.spectator_count} observateur${room.spectator_count === 1 ? '' : 's'}`
        : '';
      details.textContent = `${room.player_count} joueur${room.player_count === 1 ? '' : 's'}${spectators} · ${room.difficulty} · ${room.status === 'playing' ? 'En cours' : 'En attente'}`;
      copy.append(title, details);
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'sudoku-secondary-button';
      button.textContent = room.is_member
        ? 'Reprendre'
        : room.status === 'lobby' ? 'Rejoindre' : 'Observer';
      button.disabled = !room.is_member && !['lobby', 'playing'].includes(room.status);
      if (!button.disabled) button.addEventListener('click', () => joinRoom(room.room_id));
      card.append(copy, button);
      roomDirectory.append(card);
    }
  }

  async function refreshRoomDirectory() {
    roomDirectory.textContent = 'Chargement des salons…';
    try {
      const data = await request(`/api/sudoku/rooms?player_id=${encodeURIComponent(playerId)}`);
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

  function ownPlayer() {
    if (gameType === 'solo') return state;
    return state?.player;
  }

  function roomPayload() {
    return { room_id: state.room_id, player_id: playerId, player_name: playerName };
  }

  function cloneBoard(board) {
    return board.map((row) => row.slice());
  }

  function hasConflict(board, row, column) {
    const value = board[row][column];
    if (!value) return false;
    for (let index = 0; index < 9; index += 1) {
      if ((index !== column && board[row][index] === value)
        || (index !== row && board[index][column] === value)) return true;
    }
    const startRow = Math.floor(row / 3) * 3;
    const startColumn = Math.floor(column / 3) * 3;
    for (let y = startRow; y < startRow + 3; y += 1) {
      for (let x = startColumn; x < startColumn + 3; x += 1) {
        if ((y !== row || x !== column) && board[y][x] === value) return true;
      }
    }
    return false;
  }

  function isFixed(row, column) {
    return state.puzzle[row][column] !== 0;
  }

  function notesStorageKey() {
    return gameType === 'solo'
      ? `sudoku_notes_solo_${state.game_id}`
      : `sudoku_notes_room_${state.room_id}_${playerId}`;
  }

  function loadNotes() {
    const key = notesStorageKey();
    const stored = localStorage.getItem(key);
    if (!stored) {
      notes = {};
      return;
    }
    let saved;
    try {
      saved = JSON.parse(stored);
    } catch {
      localStorage.removeItem(key);
      notes = {};
      return;
    }
    notes = {};
    if (!saved || typeof saved !== 'object' || Array.isArray(saved)) return;
    for (const [cell, digits] of Object.entries(saved)) {
      if (!/^[0-8]:[0-8]$/.test(cell) || !Array.isArray(digits)) continue;
      const validDigits = [...new Set(digits.filter(
        (digit) => Number.isInteger(digit) && digit >= 1 && digit <= 9,
      ))].sort();
      if (validDigits.length) notes[cell] = validDigits;
    }
  }

  function saveNotes() {
    localStorage.setItem(notesStorageKey(), JSON.stringify(notes));
  }

  function setNotesMode(enabled) {
    notesMode = enabled;
    const button = document.getElementById('sudoku-notes-toggle');
    button.setAttribute('aria-pressed', String(notesMode));
    button.textContent = `✎ Mode notes : ${notesMode ? 'activé' : 'désactivé'}`;
    document.querySelectorAll('#sudoku-number-pad .sudoku-number-button').forEach((key) => {
      key.setAttribute(
        'aria-label',
        `${notesMode ? 'Basculer la note' : 'Entrer'} ${key.textContent}`,
      );
    });
  }

  function toggleNotesMode() {
    if (!canEdit()) return;
    setNotesMode(!notesMode);
  }

  function toggleNote(digit) {
    if (!canEdit()) return;
    const [row, column] = selectedCell;
    if (isFixed(row, column) || state.board[row][column]) {
      showError(playError, 'Les notes sont disponibles uniquement dans une case vide.');
      return;
    }
    hideError(playError);
    const key = `${row}:${column}`;
    const cellNotes = new Set(notes[key] || []);
    if (cellNotes.has(digit)) cellNotes.delete(digit);
    else cellNotes.add(digit);
    if (cellNotes.size) notes[key] = [...cellNotes].sort();
    else delete notes[key];
    saveNotes();
    renderGrid();
  }

  function canEdit() {
    if (!state || state.status !== 'playing') return false;
    return !ownPlayer()?.is_spectator
      && !ownPlayer()?.solved
      && !ownPlayer()?.eliminated;
  }

  function renderGrid() {
    const player = ownPlayer();
    const board = state.status === 'finished' && state.solution && !player?.eliminated
      ? state.solution
      : state.board;
    const incorrectCells = new Set(
      (player?.incorrect_cells || []).map(([row, column]) => `${row}:${column}`),
    );
    const [selectedRow, selectedColumn] = selectedCell;
    const selectedValue = board[selectedRow]?.[selectedColumn] || 0;
    const grid = document.getElementById('sudoku-grid');
    grid.replaceChildren();
    for (let row = 0; row < 9; row += 1) {
      for (let column = 0; column < 9; column += 1) {
        const cell = document.createElement('button');
        const value = board[row][column];
        cell.type = 'button';
        cell.className = 'sudoku-cell';
        cell.dataset.row = String(row);
        cell.dataset.column = String(column);
        cell.setAttribute('role', 'gridcell');
        const cellNotes = notes[`${row}:${column}`] || [];
        cell.setAttribute('aria-label', `Ligne ${row + 1}, colonne ${column + 1}${value ? `, ${value}` : cellNotes.length ? `, notes ${cellNotes.join(', ')}` : ', vide'}`);
        if (value) {
          cell.textContent = value;
        } else if (cellNotes.length) {
          const noteGrid = document.createElement('span');
          noteGrid.className = 'sudoku-cell-notes';
          noteGrid.setAttribute('aria-hidden', 'true');
          for (let digit = 1; digit <= 9; digit += 1) {
            const note = document.createElement('span');
            note.textContent = cellNotes.includes(digit) ? String(digit) : '';
            noteGrid.append(note);
          }
          cell.append(noteGrid);
        }
        if (isFixed(row, column) || state.status === 'finished') cell.classList.add('sudoku-fixed');
        if (row === selectedRow || column === selectedColumn
          || (Math.floor(row / 3) === Math.floor(selectedRow / 3)
            && Math.floor(column / 3) === Math.floor(selectedColumn / 3))) {
          cell.classList.add('sudoku-related');
        }
        if (value && value === selectedValue) cell.classList.add('sudoku-same-value');
        if (hasConflict(board, row, column)) cell.classList.add('sudoku-conflict');
        if (incorrectCells.has(`${row}:${column}`)) cell.classList.add('sudoku-incorrect');
        if (row === selectedRow && column === selectedColumn) cell.classList.add('sudoku-selected');
        cell.disabled = !canEdit();
        cell.addEventListener('click', () => {
          selectedCell = [row, column];
          renderGrid();
        });
        grid.append(cell);
      }
    }
    grid.setAttribute('aria-busy', String(pendingWrites > 0));
  }

  function renderNumberPad() {
    const pad = document.getElementById('sudoku-number-pad');
    pad.replaceChildren();
    for (let digit = 1; digit <= 9; digit += 1) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'sudoku-number-button';
      button.textContent = String(digit);
      button.setAttribute('aria-label', `Entrer ${digit}`);
      button.disabled = !canEdit();
      button.addEventListener('click', () => notesMode ? toggleNote(digit) : setCell(digit));
      pad.append(button);
    }
    document.getElementById('sudoku-clear-cell').disabled = !canEdit();
  }

  function updateCountdown() {
    if (!state?.deadline_at) return;
    const remaining = Math.max(0, Math.ceil(state.deadline_at - Date.now() / 1000));
    const minutes = Math.floor(remaining / 60);
    const seconds = String(remaining % 60).padStart(2, '0');
    const countdown = document.getElementById('sudoku-countdown');
    countdown.textContent = `${minutes}:${seconds}`;
    countdown.classList.toggle('sudoku-low-time', remaining <= 20);
    document.getElementById('sudoku-timer-description').textContent =
      `${state.solved_count} joueur${state.solved_count === 1 ? '' : 's'} déjà arrivé${state.solved_count === 1 ? '' : 's'} au but`;
  }

  function renderPlayers() {
    const list = document.getElementById('sudoku-player-list');
    list.replaceChildren(...state.players.map((player) => {
      const item = document.createElement('li');
      const name = document.createElement('span');
      name.textContent = player.name + (player.player_id === state.host_player_id ? ' (hôte)' : '');
      const status = document.createElement('small');
      status.textContent = player.is_spectator
        ? 'Observateur · en attente de la prochaine partie'
        : player.solved
        ? `Terminé · ${player.points} pt${player.points === 1 ? '' : 's'}`
        : player.eliminated ? 'Éliminé · 0 vie' : `${player.lives} vies restantes`;
      if (player.is_spectator) item.classList.add('sudoku-spectator');
      item.append(name, status);
      return item;
    }));
  }

  function renderLobby() {
    document.getElementById('sudoku-game-mode').textContent = `Multijoueur · ${state.difficulty}`;
    document.getElementById('sudoku-game-title').textContent = `Salon ${state.room_id}`;
    document.getElementById('sudoku-game-hint').textContent =
      'La même grille pour tout le monde, mais chacun joue sur son propre plateau.';
    document.getElementById('sudoku-lobby').hidden = false;
    document.getElementById('sudoku-round').hidden = true;
    const activeCount = state.players.filter((player) => !player.is_spectator).length;
    const spectatorCount = state.players.length - activeCount;
    document.getElementById('sudoku-lobby-status').textContent =
      `${activeCount} joueur${activeCount === 1 ? '' : 's'}${spectatorCount ? ` · ${spectatorCount} observateur${spectatorCount === 1 ? '' : 's'}` : ''} dans le salon. Au moins deux joueurs sont nécessaires.`;
    document.getElementById('sudoku-invite-code').textContent = `Code : ${state.room_id}`;
    const inviteUrl = new URL(window.location.href);
    inviteUrl.search = new URLSearchParams({ room: state.room_id }).toString();
    document.getElementById('sudoku-copy-invite').dataset.inviteUrl = inviteUrl.href;
    renderPlayers();
    const startButton = document.getElementById('sudoku-start-game');
    startButton.hidden = playerId !== state.host_player_id;
    startButton.disabled = !state.can_start || roomBusy;
  }

  function renderRanking() {
    const section = document.getElementById('sudoku-ranking-section');
    section.hidden = !state.ranking?.length;
    if (section.hidden) return;
    const ranking = document.getElementById('sudoku-ranking');
    ranking.replaceChildren(...state.ranking.map((entry) => {
      const item = document.createElement('li');
      item.textContent = `${entry.rank}. ${entry.name} — ${entry.points} point${entry.points === 1 ? '' : 's'}`;
      return item;
    }));
  }

  function renderRound() {
    const room = gameType === 'room';
    const player = ownPlayer();
    const isSpectator = room && player?.is_spectator;
    document.getElementById('sudoku-lobby').hidden = true;
    document.getElementById('sudoku-round').hidden = false;
    document.getElementById('sudoku-game-mode').textContent = room
      ? `Multijoueur · ${state.difficulty}`
      : `Solo · ${state.difficulty}`;
    document.getElementById('sudoku-game-title').textContent = isSpectator
      ? 'Vous observez la partie'
      : player?.eliminated ? 'Vous êtes éliminé'
        : state.status === 'finished' ? 'Grille résolue !' : 'Complétez la grille.';
    document.getElementById('sudoku-game-hint').textContent = 'Chaque chiffre doit apparaître une seule fois par ligne, colonne et carré 3×3.';
    const lives = document.getElementById('sudoku-lives');
    lives.textContent = isSpectator
      ? `Grille observée : ${state.observed_player?.name || 'un joueur actif'} · vous rejoindrez la prochaine partie.`
      : `Vies restantes : ${player.lives} / 3`;
    lives.classList.toggle('sudoku-eliminated', !isSpectator && player.eliminated);
    document.getElementById('sudoku-notes-toggle').disabled = !canEdit();
    document.getElementById('sudoku-timer-panel').hidden = !room || !state.deadline_at;
    if (room && state.deadline_at && state.status === 'playing') updateCountdown();
    const message = document.getElementById('sudoku-round-message');
    if (isSpectator) {
      message.textContent = state.status === 'finished'
        ? 'La partie est terminée. Vous rejoindrez la prochaine partie lorsque l’hôte la relancera.'
        : `Vous observez en direct la grille de ${state.observed_player?.name || 'un joueur actif'}.`;
    } else if (player?.eliminated) {
      message.textContent = 'Trois erreurs : vous êtes éliminé. Les chiffres incorrects restent affichés en rouge.';
    } else if (!room) {
      message.textContent = state.solved
        ? `Bravo ! Vous avez résolu la grille en ${state.elapsed_seconds} secondes.`
        : 'À vous de jouer : il n’y a pas de limite de temps.';
    } else if (state.status === 'finished') {
      if (player.solved) message.textContent = `Vous avez terminé à la ${player.rank}${player.rank === 1 ? 're' : 'e'} place et gagné ${player.points} point${player.points === 1 ? '' : 's'}.`;
      else message.textContent = state.finish_reason === 'time'
        ? 'Le délai de trois minutes est écoulé. La solution est affichée ci-dessous.'
        : 'Le podium est complet. La solution est affichée ci-dessous.';
    } else if (player.solved) {
      message.textContent = `Vous êtes ${player.rank}${player.rank === 1 ? 're' : 'e'} ! Vous gagnez ${player.points} point${player.points === 1 ? '' : 's'}. Le jeu continue pour les autres.`;
    } else if (state.deadline_at) {
      message.textContent = 'Un joueur a trouvé la solution : dépêchez-vous pour entrer dans le podium !';
    } else {
      message.textContent = 'Le chronomètre de 3 minutes commencera après la première résolution.';
    }
    renderGrid();
    renderNumberPad();

    const scoreboard = document.getElementById('sudoku-scoreboard');
    scoreboard.hidden = !(room && !isSpectator && player.solved);
    if (!scoreboard.hidden) {
      const place = player.rank === 1 ? '1re' : `${player.rank}e`;
      scoreboard.textContent = `Votre place : ${place} · points gagnés : ${player.points}`;
    }
    renderRanking();
    const restartButton = document.getElementById('sudoku-restart-game');
    if (room) {
      restartButton.textContent = 'Nouvelle grille';
      restartButton.hidden = state.status !== 'finished' || playerId !== state.host_player_id;
      restartButton.disabled = roomBusy;
    } else {
      restartButton.textContent = 'Nouvelle grille solo';
      restartButton.hidden = state.status !== 'finished';
      restartButton.disabled = false;
    }
  }

  function updateView() {
    if (!state) return;
    showPlay();
    if (state.status === 'lobby') renderLobby();
    else renderRound();
    if (gameType === 'room') {
      if (!pollingTimer) pollingTimer = window.setInterval(refreshRoom, 1400);
      if (state.status === 'playing' && state.deadline_at && !countdownTimer) {
        countdownTimer = window.setInterval(updateCountdown, 250);
      }
      if ((state.status !== 'playing' || !state.deadline_at) && countdownTimer) {
        window.clearInterval(countdownTimer);
        countdownTimer = null;
      }
    } else if (gameType === 'solo' && state.status === 'playing' && !elapsedTimer) {
      elapsedTimer = window.setInterval(() => {
        if (state?.status === 'playing') {
          state.elapsed_seconds += 1;
          document.getElementById('sudoku-game-hint').textContent =
            `Temps écoulé : ${formatElapsed(state.elapsed_seconds)} · Chaque chiffre doit apparaître une seule fois par ligne, colonne et carré 3×3.`;
        }
      }, 1000);
    } else if (state.status === 'finished' && elapsedTimer) {
      window.clearInterval(elapsedTimer);
      elapsedTimer = null;
    }
  }

  function formatElapsed(seconds) {
    return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
  }

  async function createSolo() {
    const button = document.getElementById('sudoku-solo-button');
    setBusy(button, true, 'Création…');
    hideError(homeError);
    try {
      state = await post('/api/sudoku/solo/new', {
        player_id: playerId,
        player_name: playerName,
        difficulty: difficultySelect.value,
      });
      gameType = 'solo';
      localStorage.setItem('sudoku_solo_game_id', state.game_id);
      localStorage.setItem('sudoku_active_game_mode', 'solo');
      localStorage.removeItem('sudoku_active_room_id');
      selectedCell = [0, 0];
      loadNotes();
      setNotesMode(false);
      updateView();
    } catch (error) {
      showError(homeError, error.message);
    } finally {
      setBusy(button, false);
    }
  }

  async function resumeSolo() {
    const gameId = localStorage.getItem('sudoku_solo_game_id');
    if (!gameId) return;
    hideError(homeError);
    try {
      state = await request(`/api/sudoku/solo/${encodeURIComponent(gameId)}?player_id=${encodeURIComponent(playerId)}`);
      gameType = 'solo';
      localStorage.setItem('sudoku_active_game_mode', 'solo');
      localStorage.removeItem('sudoku_active_room_id');
      selectedCell = [0, 0];
      loadNotes();
      setNotesMode(false);
      difficultySelect.value = state.difficulty;
      updateView();
    } catch (error) {
      localStorage.removeItem('sudoku_solo_game_id');
      showError(homeError, `Impossible de reprendre cette partie : ${error.message}`);
    }
  }

  async function createRoom() {
    const button = document.getElementById('sudoku-create-room');
    setBusy(button, true, 'Création…');
    hideError(homeError);
    try {
      state = await post('/api/sudoku/room/create', {
        player_id: playerId,
        player_name: playerName,
        difficulty: roomDifficultySelect.value,
      });
      enterRoom();
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
      state = await post('/api/sudoku/room/join', {
        room_id: cleanRoomId,
        player_id: playerId,
        player_name: playerName,
      });
      enterRoom();
    } catch (error) {
      showError(homeError, error.message);
    }
  }

  function enterRoom() {
    gameType = 'room';
    difficultySelect.value = state.difficulty;
    roomDifficultySelect.value = state.difficulty;
    selectedCell = [0, 0];
    loadNotes();
    setNotesMode(false);
    localStorage.setItem('sudoku_active_game_mode', 'room');
    localStorage.setItem('sudoku_active_room_id', state.room_id);
    history.replaceState(null, '', `${window.location.pathname}?room=${encodeURIComponent(state.room_id)}`);
    updateView();
  }

  async function startRoom() {
    if (!state || roomBusy) return;
    roomBusy = true;
    const button = document.getElementById('sudoku-start-game');
    button.disabled = true;
    try {
      state = await post('/api/sudoku/room/start', roomPayload());
      updateView();
    } catch (error) {
      showError(playError, error.message);
    } finally {
      roomBusy = false;
      if (state?.status === 'lobby') renderLobby();
    }
  }

  async function restartRoom() {
    if (gameType !== 'room' || state?.status !== 'finished' || roomBusy) return;
    roomBusy = true;
    const button = document.getElementById('sudoku-restart-game');
    button.disabled = true;
    try {
      state = await post('/api/sudoku/room/restart', roomPayload());
      selectedCell = [0, 0];
      notes = {};
      saveNotes();
      setNotesMode(false);
      updateView();
    } catch (error) {
      showError(playError, error.message);
    } finally {
      roomBusy = false;
      if (state?.status === 'finished') renderRound();
      else if (state?.status === 'lobby') renderLobby();
    }
  }

  function setCell(value) {
    if (!canEdit()) return;
    if (notesMode && value !== 0) {
      toggleNote(value);
      return;
    }
    const [row, column] = selectedCell;
    if (isFixed(row, column)) {
      showError(playError, 'Sélectionnez une case vide de la grille de départ.');
      return;
    }
    hideError(playError);
    const board = cloneBoard(state.board);
    board[row][column] = value;
    state.board = board;
    const revision = ++writeRevision;
    updateView();
    const writeGameType = gameType;
    const gameSnapshot = gameType === 'solo' ? state.game_id : state.room_id;
    const operation = async () => {
      pendingWrites += 1;
      roomBusy = gameType === 'room';
      try {
        const updated = writeGameType === 'solo'
          ? await post('/api/sudoku/solo/cell', {
            game_id: gameSnapshot, player_id: playerId, player_name: playerName, row, column, value,
          })
          : await post('/api/sudoku/room/cell', {
            room_id: gameSnapshot, player_id: playerId, player_name: playerName, row, column, value,
          });
        if (revision === writeRevision) {
            delete notes[`${row}:${column}`];
            saveNotes();
            state = updated;
          if (writeGameType === 'solo' && state.status === 'finished') {
            localStorage.removeItem('sudoku_solo_game_id');
          }
          updateView();
        }
      } catch (error) {
        if (revision === writeRevision) {
          showError(playError, error.message);
          try {
            state = writeGameType === 'solo'
              ? await request(`/api/sudoku/solo/${encodeURIComponent(gameSnapshot)}?player_id=${encodeURIComponent(playerId)}`)
              : await request(`/api/sudoku/room/${encodeURIComponent(gameSnapshot)}?player_id=${encodeURIComponent(playerId)}`);
            updateView();
            showError(playError, error.message);
          } catch (refreshError) {
            showError(playError, refreshError.message);
          }
        }
      } finally {
        pendingWrites -= 1;
        roomBusy = writeGameType === 'room' && pendingWrites > 0;
      }
    };
    writeQueue = writeQueue.then(operation, operation);
  }

  async function refreshRoom() {
    if (gameType !== 'room' || !state || roomBusy || pendingWrites) return;
    try {
      state = await request(
        `/api/sudoku/room/${encodeURIComponent(state.room_id)}?player_id=${encodeURIComponent(playerId)}`,
      );
      updateView();
    } catch (error) {
      if (pollingTimer) window.clearInterval(pollingTimer);
      pollingTimer = null;
      showError(playError, error.message);
    }
  }

  function handleKeydown(event) {
    if (play.hidden || !state || event.ctrlKey || event.metaKey || event.altKey) return;
    if (gameType === 'room' && ownPlayer()?.is_spectator) return;
    const [row, column] = selectedCell;
    if (/^[1-9]$/.test(event.key)) {
      event.preventDefault();
      if (notesMode) toggleNote(Number(event.key));
      else setCell(Number(event.key));
      return;
    }
    if (event.key.toLowerCase() === 'n') {
      event.preventDefault();
      toggleNotesMode();
      return;
    }
    if (event.key === 'Backspace' || event.key === 'Delete' || event.key === '0') {
      event.preventDefault();
      setCell(0);
      return;
    }
    const moves = {
      ArrowUp: [-1, 0],
      ArrowDown: [1, 0],
      ArrowLeft: [0, -1],
      ArrowRight: [0, 1],
    };
    if (moves[event.key]) {
      event.preventDefault();
      const [dy, dx] = moves[event.key];
      selectedCell = [Math.max(0, Math.min(8, row + dy)), Math.max(0, Math.min(8, column + dx))];
      renderGrid();
    }
  }

  document.getElementById('sudoku-solo-button').addEventListener('click', createSolo);
  difficultySelect.addEventListener('change', refreshLeaderboard);
  document.getElementById('sudoku-resume-solo').addEventListener('click', resumeSolo);
  document.getElementById('sudoku-create-room').addEventListener('click', createRoom);
  document.getElementById('sudoku-join-room').addEventListener('click', () => joinRoom(roomInput.value));
  document.getElementById('sudoku-refresh-rooms').addEventListener('click', refreshRoomDirectory);
  roomInput.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      joinRoom(roomInput.value);
    }
  });
  document.getElementById('sudoku-start-game').addEventListener('click', startRoom);
  document.getElementById('sudoku-restart-game').addEventListener('click', () => {
    if (gameType === 'solo') createSolo();
    else restartRoom();
  });
  document.getElementById('sudoku-home-button').addEventListener('click', () => {
    showHome(true);
  });
  document.getElementById('sudoku-copy-invite').addEventListener('click', async (event) => {
    const url = event.currentTarget.dataset.inviteUrl;
    try {
      await navigator.clipboard.writeText(url);
      event.currentTarget.textContent = 'Lien copié !';
      window.setTimeout(() => { event.currentTarget.textContent = 'Copier le lien'; }, 1600);
    } catch {
      window.prompt('Copiez ce lien pour inviter vos amis :', url);
    }
  });
  document.getElementById('sudoku-clear-cell').addEventListener('click', () => setCell(0));
  document.getElementById('sudoku-notes-toggle').addEventListener('click', toggleNotesMode);
  document.addEventListener('keydown', handleKeydown);
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !play.hidden) showHome();
  });

  if (params.has('room')) {
    roomInput.value = params.get('room');
    joinRoom(params.get('room'));
  } else if (localStorage.getItem('sudoku_active_game_mode') === 'room'
    && localStorage.getItem('sudoku_active_room_id')) {
    joinRoom(localStorage.getItem('sudoku_active_room_id'));
  } else if ((localStorage.getItem('sudoku_active_game_mode') === 'solo'
    || (!localStorage.getItem('sudoku_active_game_mode')
      && localStorage.getItem('sudoku_solo_game_id')))
    && localStorage.getItem('sudoku_solo_game_id')) {
    resumeSolo();
  } else {
    localStorage.removeItem('sudoku_active_room_id');
    showHome(false);
  }
  refreshLeaderboard();
})();
