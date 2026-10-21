(() => {
  const apiBase = window.PEDANTIX_CONFIG?.BACKEND_URL?.replace(/\/+$/, '') || '';
  const home = document.getElementById('chiffrantix-home');
  const play = document.getElementById('chiffrantix-play');
  const homeError = document.getElementById('chiffrantix-home-error');
  const playError = document.getElementById('chiffrantix-play-error');
  const guessInput = document.getElementById('chiffrantix-guess');
  const guessForm = document.getElementById('chiffrantix-guess-form');
  const difficultySelect = document.getElementById('chiffrantix-difficulty');
  const categorySelect = document.getElementById('chiffrantix-category');
  const roomDirectory = document.getElementById('chiffrantix-room-directory');
  const tokensBoard = document.getElementById('chiffrantix-tokens-board');
  const solutionCard = document.getElementById('chiffrantix-solution-card');
  const hintButton = document.getElementById('chiffrantix-hint-button');
  const params = new URLSearchParams(window.location.search);

  const CATEGORY_LABELS = {
    toutes: '📚 Toutes thématiques',
    histoire: '🏛️ Histoire',
    geographie: '🌍 Géographie',
    sciences: '🔬 Sciences',
    astronomie: '🪐 Astronomie',
    nature: '🦁 Nature',
    monuments: '🗼 Monuments',
    arts_culture: '🎨 Arts & Culture',
    sport: '🏆 Sport',
    societe: '⚖️ Société',
    tech_jeux: '💻 Tech & Jeux',
  };

  const DIFFICULTY_LABELS = {
    facile: '🟢 Facile',
    moyen: '🟡 Moyen',
    difficile: '🔴 Difficile',
    toutes: '🎲 Mixte',
  };

  let playerId = localStorage.getItem('chiffrantix_player_id');
  if (!playerId) {
    playerId = globalThis.crypto?.randomUUID?.() || `chiffrantix-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    localStorage.setItem('chiffrantix_player_id', playerId);
  }
  const playerName = (localStorage.getItem('pedantix_player_name')
    || localStorage.getItem('pedantix_auth_user')
    || 'Joueur').trim().slice(0, 24);
  const leaderboardDifficultySelect = document.getElementById('chiffrantix-leaderboard-difficulty');

  let state = null;
  let gameType = null;
  let pollingTimer = null;
  let roomRefreshing = false;
  let roomBusy = false;
  let roomRefreshGeneration = 0;

  document.getElementById('chiffrantix-player-name').textContent = playerName;

  function formatLeaderboardTime(seconds) {
    const minutes = Math.floor(seconds / 60);
    return `${minutes}:${String(seconds % 60).padStart(2, '0')}`;
  }

  async function refreshLeaderboard() {
    const list = document.getElementById('chiffrantix-leaderboard');
    const title = document.getElementById('chiffrantix-leaderboard-title');
    const difficulty = leaderboardDifficultySelect.value;
    title.textContent = `Classement solo · ${DIFFICULTY_LABELS[difficulty]}`;
    try {
      const data = await request(
        `/api/game-leaderboard?game_id=chiffrantix&difficulty=${encodeURIComponent(difficulty)}`,
      );
      list.replaceChildren();
      if (!data.records.length) {
        const empty = document.createElement('li');
        empty.className = 'shared-solo-leaderboard-empty';
        empty.textContent = 'Aucune question résolue pour le moment.';
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
        detail.textContent = `${record.attempts} proposition${record.attempts === 1 ? '' : 's'} · ${formatLeaderboardTime(record.duration_seconds)}`;
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
    pollingTimer = window.setInterval(refreshRoom, 1200);
  }

  async function showHome(clearActiveGame = true) {
    if (clearActiveGame && gameType === 'room' && state?.room_id) {
      stopPolling();
      try {
        await post('/api/chiffrantix/room/leave', {
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
      localStorage.setItem('chiffrantix_active_game_mode', 'home');
      localStorage.removeItem('chiffrantix_active_room_id');
    }
    document.getElementById('chiffrantix-previous-game').hidden =
      !localStorage.getItem('chiffrantix_solo_game_id');
    history.replaceState(null, '', window.location.pathname);
    refreshLeaderboard();
    refreshRoomDirectory();
  }

  function showPlay() {
    home.hidden = true;
    play.hidden = false;
    hideError(playError);
  }

  function renderRoomDirectory(rooms) {
    roomDirectory.replaceChildren();
    if (!rooms.length) {
      const empty = document.createElement('p');
      empty.className = 'chiffrantix-room-empty';
      empty.textContent = 'Aucun salon ouvert pour le moment.';
      roomDirectory.append(empty);
      return;
    }
    for (const room of rooms) {
      const card = document.createElement('div');
      card.className = 'chiffrantix-room-card';
      const copy = document.createElement('span');
      copy.className = 'chiffrantix-room-card-copy';
      const title = document.createElement('strong');
      title.textContent = `Salon ${room.room_id} (${room.host_name})`;
      const details = document.createElement('small');
      const catLabel = CATEGORY_LABELS[room.category] || room.category;
      details.textContent = `${room.player_count} joueur${room.player_count === 1 ? '' : 's'} · ${catLabel} · ${room.status === 'playing' ? 'En cours' : 'En attente'}`;
      copy.append(title, details);
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'chiffrantix-secondary-button';
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
      const data = await request(`/api/chiffrantix/rooms?player_id=${encodeURIComponent(playerId)}`);
      renderRoomDirectory(data.rooms || []);
    } catch (error) {
      roomDirectory.textContent = `Impossible de charger les salons : ${error.message}`;
    }
  }

  function renderTokens(tokens) {
    tokensBoard.replaceChildren();
    for (const tok of tokens) {
      if (tok.type === 'space') continue;
      if (tok.type === 'punct') {
        const span = document.createElement('span');
        span.className = 'chiffrantix-token-punct';
        span.textContent = tok.text;
        tokensBoard.append(span);
        continue;
      }

      const wordEl = document.createElement('span');
      wordEl.className = 'chiffrantix-token-word';
      if (tok.revealed) {
        wordEl.classList.add('is-revealed');
        wordEl.textContent = tok.text;
      } else {
        wordEl.classList.add('is-masked');
        wordEl.style.cursor = 'pointer';
        const minWidth = Math.max(32, tok.length * 11 + 14);
        wordEl.style.minWidth = `${minWidth}px`;
        if (tok.heat && tok.heat >= 48) {
          wordEl.classList.add(tok.heat >= 80 ? 'is-hot' : 'is-warm');
          wordEl.textContent = tok.close_word || `${tok.length}`;
          const badge = document.createElement('span');
          badge.className = 'chiffrantix-token-heat-badge';
          badge.textContent = `${Math.round(tok.heat)}°`;
          wordEl.append(badge);
          wordEl.title = `Proche de « ${tok.close_word || ''} » (${tok.heat}/100) · Mot de ${tok.length} lettres`;
        } else {
          wordEl.textContent = `${tok.length}`;
          wordEl.title = `Mot masqué de ${tok.length} lettre${tok.length > 1 ? 's' : ''} (cliquer pour cibler)`;
        }
        wordEl.addEventListener('click', () => {
          if (!guessInput.disabled) {
            guessInput.placeholder = `Mot de ${tok.length} lettre${tok.length > 1 ? 's' : ''}${tok.close_word ? ` (proche de « ${tok.close_word} »)` : ''}…`;
            guessInput.focus();
          }
        });
      }
      tokensBoard.append(wordEl);
    }
  }

  function scoreLabel(guess) {
    if (guess.status === 'match') {
      return `Révélé (${guess.count}×)`;
    }
    const s = Number(guess.score || 0);
    if (s >= 80) return `${s.toFixed(1)}° · Brûlant 🔥`;
    if (s >= 65) return `${s.toFixed(1)}° · Très chaud 🌶️`;
    if (s >= 48) return `${s.toFixed(1)}° · Chaud ☀️`;
    if (s >= 30) return `${s.toFixed(1)}° · Tiède 🌤️`;
    if (s >= 18) return `${s.toFixed(1)}° · Frais 💧`;
    if (s > 0) return `${s.toFixed(1)}° · Froid ❄️`;
    return 'Froid';
  }

  function scoreClass(guess) {
    if (guess.status === 'match') return 'chiffrantix-score-solved';
    const s = Number(guess.score || 0);
    if (s >= 80) return 'chiffrantix-score-hot';
    if (s >= 48) return 'chiffrantix-score-warm';
    return '';
  }

  function renderHistory(guesses) {
    const historyEl = document.getElementById('chiffrantix-history');
    historyEl.replaceChildren();
    if (!guesses || !guesses.length) return;

    const section = document.createElement('section');
    section.className = 'chiffrantix-player-history';
    const heading = document.createElement('h2');
    heading.textContent = `Vos mots testés (${guesses.length})`;
    const list = document.createElement('ol');
    list.className = 'chiffrantix-guess-list';

    for (const g of guesses) {
      const row = document.createElement('li');
      row.className = 'chiffrantix-guess-row';

      const num = document.createElement('span');
      num.className = 'chiffrantix-guess-num';
      num.textContent = `#${g.attempt}`;

      const word = document.createElement('span');
      word.className = 'chiffrantix-guess-word';
      word.textContent = g.word;

      const score = document.createElement('span');
      score.className = 'chiffrantix-guess-score';
      score.textContent = scoreLabel(g);

      const track = document.createElement('span');
      track.className = 'chiffrantix-score-track';
      const bar = document.createElement('span');
      bar.className = scoreClass(g);
      const pct = g.status === 'match' ? 100 : Math.max(4, Math.min(100, Number(g.score || 0)));
      bar.style.width = `${pct}%`;
      track.append(bar);

      row.append(num, word, score, track);
      list.append(row);
    }

    section.append(heading, list);
    historyEl.append(section);
  }

  function renderScoreboard() {
    const scoreboard = document.getElementById('chiffrantix-scoreboard');
    const columns = document.querySelector('.chiffrantix-columns');
    if (gameType !== 'room' || !state?.players) {
      scoreboard.hidden = true;
      columns?.classList.remove('has-scoreboard');
      return;
    }

    scoreboard.hidden = false;
    columns?.classList.add('has-scoreboard');
    scoreboard.replaceChildren();

    const heading = document.createElement('h2');
    heading.textContent = 'Course des joueurs';
    const list = document.createElement('ul');
    list.className = 'chiffrantix-scoreboard-list';

    for (const p of state.players) {
      const item = document.createElement('li');
      item.className = 'chiffrantix-scoreboard-item';
      const left = document.createElement('strong');
      left.textContent = p.name + (p.is_spectator ? ' (spectateur)' : '');
      const right = document.createElement('span');
      if (p.solved) {
        right.textContent = `🏆 Trouvé en ${p.attempts} coup${p.attempts > 1 ? 's' : ''}`;
      } else {
        right.textContent = `${p.progress_pct}% (${p.revealed_words_count}/${p.total_words}) · ${p.attempts} essai${p.attempts > 1 ? 's' : ''}`;
      }
      item.append(left, right);
      list.append(item);
    }

    scoreboard.append(heading, list);
  }

  function renderLobby() {
    const inviteUrl = new URL(window.location.href);
    inviteUrl.search = new URLSearchParams({ room: state.room_id }).toString();
    const activePlayers = state.players.filter((p) => !p.is_spectator);
    const spectators = state.players.length - activePlayers.length;
    document.getElementById('chiffrantix-lobby-status').textContent =
      `${activePlayers.length} joueur${activePlayers.length === 1 ? '' : 's'} dans le salon`
      + (spectators ? ` · ${spectators} spectateur${spectators === 1 ? '' : 's'}` : '')
      + '. Il en faut au moins deux pour démarrer.';
    document.getElementById('chiffrantix-invite-code').textContent = `Code : ${state.room_id}`;
    document.getElementById('chiffrantix-copy-invite').dataset.inviteUrl = inviteUrl.href;

    const list = document.getElementById('chiffrantix-player-list');
    list.replaceChildren(...state.players.map((player) => {
      const item = document.createElement('li');
      const name = document.createElement('span');
      name.textContent = player.name
        + (player.player_id === state.host_player_id ? ' (hôte)' : '')
        + (player.is_spectator ? ' (spectateur)' : '');
      const status = document.createElement('small');
      status.textContent = player.is_spectator ? 'Observateur' : 'Prêt';
      item.append(name, status);
      return item;
    }));

    const startButton = document.getElementById('chiffrantix-start-game');
    startButton.hidden = state.player_id !== state.host_player_id;
    startButton.disabled = !state.can_start || roomBusy;
  }

  function renderRound() {
    const isRoom = gameType === 'room';
    const isFinished = state.status === 'finished' || state.player.solved;

    document.getElementById('chiffrantix-category-badge').textContent =
      CATEGORY_LABELS[state.category] || `📚 ${state.category}`;
    document.getElementById('chiffrantix-difficulty-badge').textContent =
      DIFFICULTY_LABELS[state.question_difficulty] || DIFFICULTY_LABELS[state.difficulty] || '🟡 Moyen';

    document.getElementById('chiffrantix-answer-value').textContent = state.answer;

    const rev = state.player.revealed_words_count;
    const tot = state.player.total_words;
    const pct = state.player.progress_pct;
    const att = state.player.attempts;

    document.getElementById('chiffrantix-progress-text').textContent =
      `${rev} / ${tot} mots découverts (${pct}%)`;
    document.getElementById('chiffrantix-attempts-text').textContent =
      `${att} essai${att === 1 ? '' : 's'}`;
    document.getElementById('chiffrantix-progress-bar').style.width = `${pct}%`;

    renderTokens(state.tokens || []);
    hintButton.hidden = isRoom || isFinished;

    if (isFinished && state.solution) {
      solutionCard.hidden = false;
      const solutionHeading = document.getElementById('chiffrantix-solution-heading');
      if (isRoom) {
        solutionHeading.textContent = state.winner_player_id === playerId
          ? `Bravo ! Vous remportez la manche en ${att} coups !`
          : `${state.winner_name || 'Un joueur'} a trouvé la question en premier !`;
      } else {
        solutionHeading.textContent = `Bravo ! Question reconstituée en ${att} coup${att === 1 ? '' : 's'} !`;
      }
      document.getElementById('chiffrantix-solution-question').textContent =
        `${state.solution.question} → ${state.solution.answer}`;
      document.getElementById('chiffrantix-solution-explanation').textContent =
        state.solution.explanation || '';
      const sourceLink = document.getElementById('chiffrantix-source-link');
      sourceLink.href = state.solution.source_url || 'https://fr.wikipedia.org';
      document.getElementById('chiffrantix-source-title').textContent =
        state.solution.source_title || 'Wikipédia';

      document.getElementById('chiffrantix-next-button').hidden = isRoom;
      document.getElementById('chiffrantix-restart-room').hidden = !isRoom || !state.can_restart;
    } else {
      solutionCard.hidden = true;
    }

    const canGuess = !isFinished && (!isRoom || !state.player.is_spectator);
    guessForm.hidden = !canGuess;
    for (const el of guessForm.elements) el.disabled = !canGuess || roomBusy;

    renderHistory(state.player.guesses || []);
    renderScoreboard();
  }

  function updateView() {
    if (!state) return;
    showPlay();
    const isRoom = gameType === 'room';
    const isLobby = isRoom && state.status === 'lobby';

    document.getElementById('chiffrantix-game-mode').textContent = isRoom
      ? (state.player.is_spectator ? `Salon ${state.room_id} · Spectateur` : `Salon ${state.room_id} · Multijoueur`)
      : 'Partie solo';
    document.getElementById('chiffrantix-game-title').textContent =
      state.status === 'finished' || state.player.solved
        ? 'Question dévoilée !'
        : 'Quelle est la question derrière ce chiffre ?';
    document.getElementById('chiffrantix-new-solo').hidden = isRoom;

    document.getElementById('chiffrantix-lobby').hidden = !isLobby;
    document.getElementById('chiffrantix-round').hidden = isLobby;

    if (isLobby) renderLobby();
    else renderRound();

    if (isRoom && (state.status !== 'finished' || state.restart_available)) {
      if (!pollingTimer) startPolling();
    } else {
      stopPolling();
    }
  }

  async function startSolo() {
    const button = document.getElementById('chiffrantix-solo-button');
    hideError(homeError);
    setBusy(button, true, 'Chargement…');
    try {
      gameType = 'solo';
      state = await post('/api/chiffrantix/solo/new', {
        player_id: playerId,
        player_name: playerName,
        difficulty: difficultySelect.value,
        category: categorySelect.value,
      });
      localStorage.setItem('chiffrantix_solo_game_id', state.game_id);
      localStorage.setItem('chiffrantix_active_game_mode', 'solo');
      localStorage.removeItem('chiffrantix_active_room_id');
      document.getElementById('chiffrantix-round-message').textContent =
        'Cliquez sur une case ou proposez vos premiers mots pour débusquer la question !';
      updateView();
      guessInput.focus();
    } catch (error) {
      showError(homeError, error.message);
    } finally {
      setBusy(button, false);
    }
  }

  async function resumeSolo() {
    const gameId = localStorage.getItem('chiffrantix_solo_game_id');
    if (!gameId) return;
    hideError(homeError);
    try {
      gameType = 'solo';
      state = await request(
        `/api/chiffrantix/solo/${encodeURIComponent(gameId)}?player_id=${encodeURIComponent(playerId)}`
      );
      if (difficultySelect && state.difficulty) difficultySelect.value = state.difficulty;
      localStorage.setItem('chiffrantix_active_game_mode', 'solo');
      localStorage.removeItem('chiffrantix_active_room_id');
      updateView();
    } catch (error) {
      localStorage.removeItem('chiffrantix_solo_game_id');
      document.getElementById('chiffrantix-previous-game').hidden = true;
      showError(homeError, error.message);
    }
  }

  async function createRoom() {
    const button = document.getElementById('chiffrantix-create-room');
    hideError(homeError);
    setBusy(button, true, 'Création…');
    try {
      gameType = 'room';
      state = await post('/api/chiffrantix/room/create', {
        player_id: playerId,
        player_name: playerName,
        difficulty: difficultySelect.value,
        category: categorySelect.value,
      });
      localStorage.setItem('chiffrantix_active_game_mode', 'room');
      localStorage.setItem('chiffrantix_active_room_id', state.room_id);
      history.replaceState(null, '', `?room=${encodeURIComponent(state.room_id)}`);
      updateView();
    } catch (error) {
      showError(homeError, error.message);
    } finally {
      setBusy(button, false);
    }
  }

  async function joinRoom(code) {
    const cleanCode = (code || '').trim().toUpperCase();
    if (!cleanCode) {
      showError(homeError, 'Saisissez le code du salon.');
      return;
    }
    const button = document.getElementById('chiffrantix-join-room');
    hideError(homeError);
    setBusy(button, true, 'Connexion…');
    try {
      gameType = 'room';
      state = await post('/api/chiffrantix/room/join', {
        room_id: cleanCode,
        player_id: playerId,
        player_name: playerName,
      });
      localStorage.setItem('chiffrantix_active_game_mode', 'room');
      localStorage.setItem('chiffrantix_active_room_id', state.room_id);
      history.replaceState(null, '', `?room=${encodeURIComponent(state.room_id)}`);
      updateView();
    } catch (error) {
      showHome();
      showError(homeError, error.message);
    } finally {
      setBusy(button, false);
    }
  }

  async function refreshRoom() {
    if (gameType !== 'room' || !state?.room_id || roomRefreshing || roomBusy) return;
    const generation = roomRefreshGeneration;
    roomRefreshing = true;
    try {
      const nextState = await request(
        `/api/chiffrantix/room/${encodeURIComponent(state.room_id)}?player_id=${encodeURIComponent(playerId)}`
      );
      if (generation !== roomRefreshGeneration || roomBusy) return;
      state = nextState;
      updateView();
    } catch (error) {
      if (generation === roomRefreshGeneration) showError(playError, error.message);
    } finally {
      roomRefreshing = false;
    }
  }

  async function startRoom() {
    const button = document.getElementById('chiffrantix-start-game');
    hideError(playError);
    roomBusy = true;
    roomRefreshGeneration += 1;
    setBusy(button, true, 'Démarrage…');
    try {
      state = await post('/api/chiffrantix/room/start', {
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
      setBusy(button, false);
    }
  }

  async function restartRoom() {
    const button = document.getElementById('chiffrantix-restart-room');
    hideError(playError);
    roomBusy = true;
    roomRefreshGeneration += 1;
    setBusy(button, true, 'Relance…');
    try {
      state = await post('/api/chiffrantix/room/restart', {
        room_id: state.room_id,
        player_id: playerId,
        player_name: playerName,
      });
      document.getElementById('chiffrantix-round-message').textContent = '';
      updateView();
      guessInput.focus();
    } catch (error) {
      showError(playError, error.message);
    } finally {
      roomBusy = false;
      setBusy(button, false);
    }
  }

  async function submitGuess(event) {
    event.preventDefault();
    const guess = guessInput.value.trim();
    if (!guess) return;
    hideError(playError);
    const submitButton = guessForm.querySelector('button[type="submit"]');
    roomBusy = gameType === 'room';
    if (roomBusy) roomRefreshGeneration += 1;
    setBusy(submitButton, true, 'Envoi…');
    try {
      if (gameType === 'solo') {
        state = await post('/api/chiffrantix/solo/guess', {
          game_id: state.game_id,
          player_id: playerId,
          player_name: playerName,
          guess,
        });
      } else {
        state = await post('/api/chiffrantix/room/guess', {
          room_id: state.room_id,
          player_id: playerId,
          player_name: playerName,
          guess,
        });
      }

      const res = state.result;
      const msgEl = document.getElementById('chiffrantix-round-message');
      if (res) {
        if (res.solved) {
          msgEl.textContent = '🎉 Vous avez trouvé tous les mots clés de la question !';
        } else if (res.status === 'match') {
          msgEl.textContent = `✅ Le mot « ${res.word} » figure dans la question (${res.matches_count} fois) !`;
        } else if (res.status === 'close') {
          msgEl.textContent = `🔥 « ${res.word} » chauffe une case à ${res.score}/100 !`;
        } else {
          msgEl.textContent = `❄️ « ${res.word} » est froid (${res.score || 0}/100).`;
        }
      }
      guessInput.value = '';
      updateView();
    } catch (error) {
      showError(playError, error.message);
    } finally {
      roomBusy = false;
      setBusy(submitButton, false);
      const canGuess = !!state
        && state.status !== 'finished'
        && !state.player.solved
        && (gameType !== 'room' || !state.player.is_spectator);
      for (const element of guessForm.elements) element.disabled = !canGuess;
      if (canGuess) guessInput.focus();
    }
  }

  async function requestHint() {
    if (gameType !== 'solo' || !state?.game_id) return;
    hideError(playError);
    setBusy(hintButton, true, 'Indice…');
    try {
      state = await post('/api/chiffrantix/solo/hint', {
        game_id: state.game_id,
        player_id: playerId,
        player_name: playerName,
      });
      const word = state.hint?.word;
      if (word) {
        document.getElementById('chiffrantix-round-message').textContent =
          `💡 Indice : le mot « ${word} » a été révélé !`;
      }
      updateView();
      guessInput.focus();
    } catch (error) {
      showError(playError, error.message);
    } finally {
      setBusy(hintButton, false);
    }
  }

  document.getElementById('chiffrantix-solo-button').addEventListener('click', startSolo);
  leaderboardDifficultySelect.addEventListener('change', refreshLeaderboard);
  document.getElementById('chiffrantix-new-solo').addEventListener('click', startSolo);
  document.getElementById('chiffrantix-next-button').addEventListener('click', startSolo);
  document.getElementById('chiffrantix-resume-solo').addEventListener('click', resumeSolo);
  document.getElementById('chiffrantix-create-room').addEventListener('click', createRoom);
  document.getElementById('chiffrantix-join-room').addEventListener('click', () => {
    joinRoom(document.getElementById('chiffrantix-room-code').value);
  });
  document.getElementById('chiffrantix-refresh-rooms').addEventListener('click', refreshRoomDirectory);
  document.getElementById('chiffrantix-start-game').addEventListener('click', startRoom);
  document.getElementById('chiffrantix-restart-room').addEventListener('click', restartRoom);
  document.getElementById('chiffrantix-home-button').addEventListener('click', () => showHome(true));
  hintButton.addEventListener('click', requestHint);
  document.getElementById('chiffrantix-copy-invite').addEventListener('click', async (event) => {
    const url = event.currentTarget.dataset.inviteUrl;
    if (!url) return;
    await navigator.clipboard?.writeText(url).catch(() => {});
    event.currentTarget.textContent = 'Lien copié';
  });
  guessForm.addEventListener('submit', submitGuess);

  showHome(false);
  refreshLeaderboard();
  const requestedRoom = params.get('room');
  const activeMode = localStorage.getItem('chiffrantix_active_game_mode');
  const activeRoom = localStorage.getItem('chiffrantix_active_room_id');
  if (requestedRoom) joinRoom(requestedRoom);
  else if (activeMode === 'room' && activeRoom) joinRoom(activeRoom);
  else if (activeMode === 'solo' && localStorage.getItem('chiffrantix_solo_game_id')) resumeSolo();
})();
