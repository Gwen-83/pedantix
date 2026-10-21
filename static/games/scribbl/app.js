(() => {
  const apiBase = window.PEDANTIX_CONFIG?.BACKEND_URL?.replace(/\/+$/, '') || '';
  const wsBase = apiBase
    ? apiBase.replace(/^http:/, 'ws:').replace(/^https:/, 'wss:')
    : `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}`;
  const palette = [
    '#172033', '#ffffff', '#f43f5e', '#f97316', '#facc15', '#22c55e',
    '#14b8a6', '#0ea5e9', '#6366f1', '#a855f7', '#ec4899', '#92400e',
  ];
  const playerName = (
    localStorage.getItem('pedantix_auth_user')
    || localStorage.getItem('pedantix_player_name')
    || 'Joueur'
  ).trim().slice(0, 24) || 'Joueur';
  let playerId = localStorage.getItem('scribbl_player_id');
  if (!playerId) {
    playerId = globalThis.crypto?.randomUUID?.()
      || `scribbl-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    localStorage.setItem('scribbl_player_id', playerId);
  }

  const $ = (id) => document.getElementById(id);
  const home = $('scribbl-home');
  const game = $('scribbl-game');
  const canvas = $('scribbl-canvas');
  const ctx = canvas.getContext('2d');
  let state = null;
  let socket = null;
  let activeRoomId = '';
  let reconnectTimer = null;
  let reconnectDelay = 500;
  let deliberateClose = false;
  let clockTimer = null;
  let clockStartedAt = 0;
  let clockBase = 0;
  let selectedColor = palette[0];
  let erasing = false;
  let brushWidth = 7;
  let pointerDown = false;
  let pendingPoints = [];
  let flushFrame = 0;

  $('scribbl-player-name').textContent = playerName;
  $('scribbl-brush').addEventListener('input', (event) => {
    brushWidth = Number(event.currentTarget.value);
  });

  async function request(path, body) {
    const response = await fetch(`${apiBase}${path}`, {
      method: body ? 'POST' : 'GET',
      headers: body ? { 'Content-Type': 'application/json' } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || 'Une erreur est survenue.');
    return data;
  }

  function showError(id, error) {
    const target = $(id);
    target.textContent = error.message || String(error);
    target.hidden = false;
  }

  function clearError(id) {
    $(id).textContent = '';
    $(id).hidden = true;
  }

  function send(message) {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      showError('scribbl-game-error', new Error('Connexion au salon interrompue. Reconnexion…'));
      return false;
    }
    socket.send(JSON.stringify(message));
    return true;
  }

  function setRoom(nextState, updateUrl = false) {
    state = nextState;
    activeRoomId = state.room_id;
    localStorage.setItem('scribbl_active_room_id', activeRoomId);
    if (updateUrl) {
      history.replaceState(
        null,
        '',
        `${window.location.pathname}?room=${encodeURIComponent(activeRoomId)}`,
      );
    }
    clearError('scribbl-game-error');
    home.hidden = true;
    game.hidden = false;
    render();
    connectSocket();
  }

  function connectSocket() {
    if (!activeRoomId || deliberateClose) return;
    if (reconnectTimer) clearTimeout(reconnectTimer);
    reconnectTimer = null;
    if (socket) socket.close();
    const url = `${wsBase}/ws/scribbl/${encodeURIComponent(activeRoomId)}`
      + `?player_id=${encodeURIComponent(playerId)}`;
    const connection = new WebSocket(url);
    socket = connection;
    connection.addEventListener('open', () => {
      reconnectDelay = 500;
      clearError('scribbl-game-error');
      $('scribbl-chat-input').disabled = false;
    });
    connection.addEventListener('message', (event) => {
      let message;
      try {
        message = JSON.parse(event.data);
      } catch (error) {
        console.error('Message Scribbl illisible :', error);
        return;
      }
      if (message.type === 'state') {
        state = message.state;
        render();
      } else if (message.type === 'draw') {
        let previousPoint = null;
        if (message.start || !state.strokes.length) {
          state.strokes.push({
            color: message.color,
            width: message.width,
            points: [],
          });
        } else {
          previousPoint = state.strokes.at(-1).points.at(-1) || null;
        }
        state.strokes.at(-1).points.push(...message.points);
        paintSegment(
          message.points,
          message.color,
          message.width,
          message.start,
          previousPoint,
        );
      } else if (message.type === 'clear') {
        state.strokes = [];
        paintCanvas();
      } else if (message.type === 'left') {
        deliberateClose = true;
        socket.close();
        returnHome(false);
      } else if (message.type === 'guess_result' && message.correct) {
        $('scribbl-chat-input').value = '';
      } else if (message.type === 'error') {
        showError('scribbl-game-error', new Error(message.message));
      }
    });
    connection.addEventListener('close', (event) => {
      if (socket !== connection) return;
      $('scribbl-chat-input').disabled = true;
      if (event.code === 4404) {
        showError('scribbl-game-error', new Error('Salon introuvable ou participation expirée.'));
        returnHome(false);
        return;
      }
      if (!deliberateClose && activeRoomId) {
        showError('scribbl-game-error', new Error('Connexion interrompue. Reconnexion…'));
        if (reconnectTimer) clearTimeout(reconnectTimer);
        reconnectTimer = setTimeout(connectSocket, reconnectDelay);
        reconnectDelay = Math.min(reconnectDelay * 2, 8000);
      }
    });
    connection.addEventListener('error', () => {
      showError('scribbl-game-error', new Error('Connexion au salon indisponible.'));
    });
  }

  function renderLobby() {
    $('scribbl-lobby').hidden = false;
    $('scribbl-play').hidden = true;
    $('scribbl-phase-label').textContent = 'Salon d’attente';
    $('scribbl-room-title').textContent = `Salon ${state.room_id}`;
    $('scribbl-invite-code').textContent = state.room_id;
    $('scribbl-lobby-message').textContent =
      `${state.player_count} joueur${state.player_count === 1 ? '' : 's'} · 2 à 8 joueurs pour jouer.`;
    $('scribbl-round-summary').textContent =
      `${state.rounds_per_player} manche${state.rounds_per_player === 1 ? '' : 's'} par joueur`;
    $('scribbl-lobby-players').replaceChildren(...state.players.map((player) => {
      const item = document.createElement('li');
      const name = document.createElement('span');
      name.textContent = `${player.name}${player.player_id === state.host_player_id ? ' · hôte' : ''}`;
      const detail = document.createElement('small');
      detail.textContent = 'Prêt';
      item.append(name, detail);
      return item;
    }));
    const start = $('scribbl-start');
    start.hidden = state.host_player_id !== playerId;
    start.disabled = !state.can_start;
  }

  function renderScoreboard() {
    const scores = $('scribbl-score-list');
    scores.replaceChildren(...state.players
      .slice()
      .sort((left, right) => right.score - left.score || left.name.localeCompare(right.name))
      .map((player) => {
        const item = document.createElement('li');
        const name = document.createElement('span');
        name.textContent = `${player.name}${player.is_artist ? ' · dessine' : ''}`;
        const score = document.createElement('strong');
        score.textContent = `${player.score} pts`;
        if (player.is_artist) item.classList.add('is-artist');
        if (player.guessed) item.classList.add('is-found');
        item.append(name, score);
        return item;
      }));
  }

  function renderChat() {
    const list = $('scribbl-chat-list');
    const wasAtBottom = list.scrollHeight - list.scrollTop - list.clientHeight < 35;
    list.replaceChildren(...state.chat.map((message) => {
      const item = document.createElement('li');
      item.textContent = message.kind === 'system'
        ? message.text
        : `${message.player_name}: ${message.text}`;
      if (message.kind === 'correct') item.classList.add('is-correct');
      if (message.kind === 'system') item.classList.add('is-system');
      return item;
    }));
    if (wasAtBottom) list.scrollTop = list.scrollHeight;
  }

  function renderWordChoices() {
    const choice = $('scribbl-choice');
    const isChoosing = state.phase === 'choosing' && state.is_artist;
    choice.hidden = !isChoosing;
    const choices = $('scribbl-word-choices');
    choices.replaceChildren(...(isChoosing ? state.word_choices : []).map((word, index) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'scribbl-button scribbl-button-primary';
      button.textContent = word;
      button.addEventListener('click', () => send({ type: 'choose', index }));
      return button;
    }));
  }

  function renderPalette() {
    $('scribbl-palette').replaceChildren(...palette.map((color) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'scribbl-color';
      button.style.backgroundColor = color;
      button.setAttribute('aria-label', `Couleur ${color}`);
      button.setAttribute('aria-pressed', String(!erasing && selectedColor === color));
      button.addEventListener('click', () => {
        selectedColor = color;
        erasing = false;
        $('scribbl-eraser').setAttribute('aria-pressed', 'false');
        renderPalette();
      });
      return button;
    }));
  }

  function render() {
    if (!state) return;
    if (state.status === 'lobby') {
      renderLobby();
      return;
    }

    $('scribbl-lobby').hidden = true;
    $('scribbl-play').hidden = false;
    $('scribbl-room-title').textContent = `Salon ${state.room_id}`;
    $('scribbl-phase-label').textContent = ({
      choosing: 'Choix du mot',
      drawing: 'À vos crayons !',
      reveal: 'Mot dévoilé',
      finished: 'Partie terminée',
    })[state.phase] || 'En jeu';
    $('scribbl-round-label').textContent =
      `Manche ${Math.min(state.round_number, state.rounds_per_player)} / ${state.rounds_per_player}`;
    const artist = state.players.find((player) => player.player_id === state.artist_player_id);
    $('scribbl-turn-label').textContent = artist
      ? state.is_artist ? 'C’est votre tour de dessiner' : `${artist.name} dessine`
      : '';
    $('scribbl-reveal').hidden = state.phase !== 'reveal';
    $('scribbl-reveal').textContent = state.phase === 'reveal'
      ? `Le mot était : ${state.word || ''}`
      : '';
    $('scribbl-canvas-placeholder').hidden = state.phase === 'drawing' || state.phase === 'reveal';
    const canDraw = state.status === 'playing' && state.phase === 'drawing' && state.is_artist;
    $('scribbl-toolbar').hidden = !canDraw;
    $('scribbl-canvas').classList.toggle('is-drawable', canDraw);
    $('scribbl-chat-input').placeholder = state.phase === 'drawing' && !state.is_artist
      ? 'Devinez le mot…'
      : 'Écrire dans le chat…';
    renderWordChoices();
    renderScoreboard();
    renderChat();
    renderPalette();
    $('scribbl-finished').hidden = state.status !== 'finished';
    if (state.status === 'finished') {
      const winners = new Set(state.winner_ids);
      const winnerNames = state.players
        .filter((player) => winners.has(player.player_id))
        .map((player) => player.name)
        .join(', ');
      $('scribbl-finished-title').textContent =
        winners.size === 1 ? `Victoire de ${winnerNames} !` : 'Égalité !';
      $('scribbl-finished-summary').textContent =
        `Bravo ${winnerNames} ! Les points ont été ajoutés à vos statistiques de jeu.`;
      $('scribbl-restart').hidden = state.host_player_id !== playerId;
    }
    setClock(state.seconds_remaining);
    paintCanvas();
  }

  function setClock(seconds) {
    clockBase = seconds;
    clockStartedAt = Date.now();
    if (clockTimer) clearInterval(clockTimer);
    const update = () => {
      const remaining = state?.status === 'playing'
        ? Math.max(0, clockBase - Math.floor((Date.now() - clockStartedAt) / 1000))
        : 0;
      const display = $('scribbl-countdown');
      display.textContent = String(remaining);
      display.classList.toggle('is-low', remaining <= 10);
    };
    update();
    clockTimer = setInterval(update, 200);
  }

  function resizeCanvas() {
    const bounds = canvas.getBoundingClientRect();
    if (!bounds.width || !bounds.height) return;
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    const width = Math.round(bounds.width * ratio);
    const height = Math.round(bounds.height * ratio);
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    }
  }

  function paintCanvas() {
    if (!canvas || !ctx) return;
    resizeCanvas();
    const bounds = canvas.getBoundingClientRect();
    ctx.clearRect(0, 0, bounds.width, bounds.height);
    if (!state) return;
    state.strokes.forEach((stroke) => {
      paintSegment(stroke.points, stroke.color, stroke.width, true);
    });
  }

  function paintSegment(points, color, width, start, previousPoint = null) {
    if (!points?.length) return;
    const bounds = canvas.getBoundingClientRect();
    const converted = points.map(([x, y]) => [x * bounds.width, y * bounds.height]);
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.lineWidth = width;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    if (start && converted.length === 1) {
      ctx.beginPath();
      ctx.arc(converted[0][0], converted[0][1], width / 2, 0, Math.PI * 2);
      ctx.fill();
      return;
    }
    ctx.beginPath();
    if (start && converted.length) ctx.moveTo(...converted[0]);
    else if (converted.length) {
      const prior = previousPoint || state?.strokes.at(-1)?.points.at(-1);
      if (prior) ctx.moveTo(prior[0] * bounds.width, prior[1] * bounds.height);
      else ctx.moveTo(...converted[0]);
    }
    const linePoints = start ? converted.slice(1) : converted;
    linePoints.forEach(([x, y]) => ctx.lineTo(x, y));
    if (linePoints.length) ctx.stroke();
  }

  function pointFromEvent(event) {
    const bounds = canvas.getBoundingClientRect();
    return [
      Math.min(1, Math.max(0, (event.clientX - bounds.left) / bounds.width)),
      Math.min(1, Math.max(0, (event.clientY - bounds.top) / bounds.height)),
    ];
  }

  function flushStroke(start = false) {
    if (!pendingPoints.length) return;
    const points = pendingPoints.splice(0, 32);
    const color = erasing ? '#ffffff' : selectedColor;
    const width = erasing ? 24 : brushWidth;
    if (!send({ type: 'stroke', start, points, color, width })) {
      pointerDown = false;
      pendingPoints = [];
    }
  }

  canvas.addEventListener('pointerdown', (event) => {
    if (!state?.is_artist || state.phase !== 'drawing' || state.status !== 'playing') return;
    event.preventDefault();
    pointerDown = true;
    canvas.setPointerCapture(event.pointerId);
    pendingPoints = [pointFromEvent(event)];
    paintSegment(pendingPoints, erasing ? '#ffffff' : selectedColor, erasing ? 24 : brushWidth, true);
    flushStroke(true);
  });
  canvas.addEventListener('pointermove', (event) => {
    if (!pointerDown) return;
    pendingPoints.push(pointFromEvent(event));
    const latest = pendingPoints.slice(-2);
    paintSegment(latest, erasing ? '#ffffff' : selectedColor, erasing ? 24 : brushWidth, true);
    if (!flushFrame) {
      flushFrame = requestAnimationFrame(() => {
        flushFrame = 0;
        flushStroke(false);
      });
    }
  });
  function finishStroke() {
    pointerDown = false;
    if (flushFrame) cancelAnimationFrame(flushFrame);
    flushFrame = 0;
    while (pendingPoints.length) flushStroke(false);
  }
  canvas.addEventListener('pointerup', finishStroke);
  canvas.addEventListener('pointercancel', finishStroke);
  canvas.addEventListener('lostpointercapture', finishStroke);
  new ResizeObserver(() => {
    resizeCanvas();
    paintCanvas();
  }).observe(canvas);

  function renderDirectory(rooms) {
    const directory = $('scribbl-room-directory');
    directory.replaceChildren();
    if (!rooms.length) {
      directory.textContent = 'Aucun salon ouvert pour le moment.';
      return;
    }
    rooms.forEach((room) => {
      const card = document.createElement('article');
      card.className = 'scribbl-room-card';
      const label = document.createElement('span');
      const title = document.createElement('strong');
      title.textContent = `Salon ${room.room_id} · ${room.host_name}`;
      const detail = document.createElement('small');
      detail.textContent = `${room.player_count}/${room.max_players} joueurs · ${room.status === 'lobby' ? 'en attente' : 'en cours'}`;
      label.append(title, detail);
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'scribbl-button';
      button.textContent = room.is_member
        ? 'Reprendre'
        : room.status === 'playing' ? 'Partie en cours' : 'Rejoindre';
      button.disabled = !room.is_member && room.status !== 'lobby';
      button.addEventListener('click', () => joinRoom(room.room_id));
      card.append(label, button);
      directory.append(card);
    });
  }

  async function refreshDirectory() {
    const directory = $('scribbl-room-directory');
    directory.textContent = 'Chargement des salons…';
    try {
      const result = await request(`/api/scribbl/rooms?player_id=${encodeURIComponent(playerId)}`);
      renderDirectory(result.rooms || []);
    } catch (error) {
      directory.textContent = `Impossible de charger les salons : ${error.message}`;
    }
  }

  async function createRoom() {
    clearError('scribbl-home-error');
    $('scribbl-create').disabled = true;
    try {
      const nextState = await request('/api/scribbl/room/create', {
        player_id: playerId,
        player_name: playerName,
        rounds_per_player: Number($('scribbl-rounds').value),
      });
      deliberateClose = false;
      setRoom(nextState, true);
    } catch (error) {
      showError('scribbl-home-error', error);
    } finally {
      $('scribbl-create').disabled = false;
    }
  }

  async function joinRoom(rawRoomId) {
    const roomId = rawRoomId.trim().toUpperCase();
    if (!roomId) {
      showError('scribbl-home-error', new Error('Saisissez le code du salon.'));
      return;
    }
    clearError('scribbl-home-error');
    try {
      const nextState = await request('/api/scribbl/room/join', {
        room_id: roomId,
        player_id: playerId,
        player_name: playerName,
      });
      deliberateClose = false;
      setRoom(nextState, true);
    } catch (error) {
      showError('scribbl-home-error', error);
    }
  }

  async function returnHome(leave = true) {
    deliberateClose = true;
    if (reconnectTimer) clearTimeout(reconnectTimer);
    reconnectTimer = null;
    if (socket) socket.close();
    if (leave && activeRoomId) {
      try {
        await request('/api/scribbl/room/leave', {
          room_id: activeRoomId,
          player_id: playerId,
        });
      } catch (error) {
        showError('scribbl-game-error', error);
        deliberateClose = false;
        connectSocket();
        return;
      }
    }
    activeRoomId = '';
    state = null;
    localStorage.removeItem('scribbl_active_room_id');
    history.replaceState(null, '', window.location.pathname);
    game.hidden = true;
    home.hidden = false;
    refreshDirectory();
  }

  $('scribbl-create').addEventListener('click', createRoom);
  $('scribbl-join').addEventListener('click', () => joinRoom($('scribbl-room-code').value));
  $('scribbl-room-code').addEventListener('keydown', (event) => {
    if (event.key === 'Enter') joinRoom(event.currentTarget.value);
  });
  $('scribbl-refresh').addEventListener('click', refreshDirectory);
  $('scribbl-start').addEventListener('click', () => send({ type: 'start' }));
  $('scribbl-leave').addEventListener('click', () => returnHome());
  $('scribbl-restart').addEventListener('click', () => send({ type: 'restart' }));
  $('scribbl-clear').addEventListener('click', () => send({ type: 'clear' }));
  $('scribbl-eraser').addEventListener('click', (event) => {
    erasing = !erasing;
    event.currentTarget.setAttribute('aria-pressed', String(erasing));
    renderPalette();
  });
  $('scribbl-chat-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const text = $('scribbl-chat-input').value.trim();
    if (!text) return;
    const isGuess = state?.status === 'playing'
      && state.phase === 'drawing'
      && !state.is_artist;
    if (send({ type: isGuess ? 'guess' : 'message', text })) {
      $('scribbl-chat-input').value = '';
    }
  });
  $('scribbl-copy').addEventListener('click', async (event) => {
    const url = new URL(window.location.href);
    url.search = new URLSearchParams({ room: activeRoomId }).toString();
    try {
      await navigator.clipboard.writeText(url.href);
      event.currentTarget.textContent = 'Lien copié !';
      setTimeout(() => { event.currentTarget.textContent = 'Copier le lien'; }, 1500);
    } catch {
      window.prompt('Copiez ce lien pour inviter vos amis :', url.href);
    }
  });

  const requestedRoom = new URLSearchParams(window.location.search).get('room');
  if (requestedRoom) joinRoom(requestedRoom);
  else refreshDirectory();
})();
