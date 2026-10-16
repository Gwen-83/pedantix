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
  let map = null;
  let countryLayer = null;
  const smallCountryMarkers = new Map();
  let mapCountries = new Set();
  let selectedCountry = null;

  document.getElementById('bito-player-name').textContent = playerName;

  async function request(path, options = {}) {
    const gateToken = localStorage.getItem('bitoguessr_gate_token') || '';
    const authUser = (localStorage.getItem('pedantix_auth_user') || '').trim();
    const response = await fetch(`${apiBase}${path}`, {
      ...options,
      headers: {
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        'x-player-id': playerId,
        ...(gateToken ? { 'x-gate-token': gateToken } : {}),
        ...(authUser ? { 'x-auth-user': authUser } : {}),
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

  function countryName(code) {
    const smallCountryNames = {
      AND: 'Andorre',
      ATG: 'Antigua-et-Barbuda',
      BHR: 'Bahreïn',
      BRB: 'Barbade',
      COK: 'Îles Cook',
      COM: 'Comores',
      CPV: 'Cap-Vert',
      DMA: 'Dominique',
      FSM: 'Micronésie',
      GRD: 'Grenade',
      HKG: 'Hong Kong',
      KIR: 'Kiribati',
      KNA: 'Saint-Kitts-et-Nevis',
      LCA: 'Sainte-Lucie',
      LIE: 'Liechtenstein',
      MCO: 'Monaco',
      MDV: 'Maldives',
      MHL: 'Îles Marshall',
      MLT: 'Malte',
      MUS: 'Maurice',
      NIU: 'Nioué',
      NRU: 'Nauru',
      PLW: 'Palaos',
      SGP: 'Singapour',
      SMR: 'Saint-Marin',
      STP: 'Sao Tomé-et-Principe',
      SYC: 'Seychelles',
      TON: 'Tonga',
      TUV: 'Tuvalu',
      VAT: 'Vatican',
      VCT: 'Saint-Vincent-et-les Grenadines',
      WSM: 'Samoa',
    };
    if (smallCountryNames[code]) return smallCountryNames[code];
    const feature = countryLayer?.getLayers().find(
      (layer) => layer.feature.properties.ADM0_A3 === code,
    );
    return feature?.feature.properties.NAME_FR
      || feature?.feature.properties.ADMIN
      || code;
  }

  function roundResult() {
    return gameType === 'solo' ? state?.result : state?.last_round;
  }

  function updateMap() {
    if (!countryLayer || !state) return;
    const result = roundResult();
    const correctCountries = new Set(result?.correct_countries || []);
    const ownGuess = gameType === 'room'
      ? result?.guesses?.find((guess) => guess.player_id === playerId)?.guess
        || state.player?.guess
      : result?.guess;
    countryLayer.setStyle((feature) => {
      const code = feature.properties.ADM0_A3;
      const playable = mapCountries.has(code);
      const correct = correctCountries.has(code);
      const incorrectGuess = code === ownGuess && result && !correct;
      const selected = code === (ownGuess || selectedCountry);
      return {
        color: correct ? '#62d3a0' : incorrectGuess ? '#ff7373' : selected ? '#7cc9ee' : '#9eabb1',
        weight: correct || incorrectGuess || selected ? 2 : 0.7,
        fillColor: correct ? '#16845a' : incorrectGuess ? '#a33d4a' : selected ? '#287da7' : playable ? '#65777c' : '#344147',
        fillOpacity: correct || incorrectGuess || selected ? 0.78 : playable ? 0.55 : 0.36,
        opacity: playable || correct || selected ? 0.9 : 0.55,
      };
    });
    smallCountryMarkers.forEach((marker, code) => {
      const correct = correctCountries.has(code);
      const incorrectGuess = code === ownGuess && result && !correct;
      const selected = code === (ownGuess || selectedCountry);
      marker.setStyle({
        color: correct ? '#62d3a0' : incorrectGuess ? '#ff7373' : selected ? '#7cc9ee' : '#fff',
        fillColor: correct ? '#16845a' : incorrectGuess ? '#a33d4a' : selected ? '#287da7' : '#8d6263',
        fillOpacity: 1,
        weight: 2,
      });
    });
  }

  function selectCountry(code) {
    if (!state || !mapCountries.has(code)) {
      document.getElementById('bito-map-status').textContent =
        'Aucune estimation disponible pour ce pays dans cette compilation.';
      return;
    }
    if (busy || state.player?.submitted || roundResult()) return;
    selectedCountry = code;
    document.getElementById('bito-map-status').textContent =
      `Pays sélectionné : ${countryName(code)}.`;
    updateMap();
    submitGuess(code);
  }

  function onCountryFeature(feature, layer) {
    const code = feature.properties.ADM0_A3;
    layer.bindTooltip(feature.properties.NAME_FR || feature.properties.ADMIN);
    layer.on({
      click: () => selectCountry(code),
      mouseover: (event) => {
        if (mapCountries.has(code) && !roundResult()) {
          event.target.setStyle({ weight: 1.8, fillOpacity: 0.76 });
          event.target.bringToFront();
        }
      },
      mouseout: () => updateMap(),
    });
  }

  async function initializeMap() {
    const status = document.getElementById('bito-map-status');
    if (!window.L) {
      status.textContent = 'La carte est indisponible. Rechargez la page pour réessayer.';
      return;
    }
    map = L.map('bito-map', {
      worldCopyJump: true,
      minZoom: 1,
      maxZoom: 6,
      zoomSnap: 0.5,
    }).setView([18, 0], 1.5);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 6,
      attribution: '&copy; OpenStreetMap',
    }).addTo(map);
    try {
      const response = await fetch('/static/games/geoguessr/data/countries.geojson');
      if (!response.ok) throw new Error(`Erreur ${response.status}`);
      const countries = await response.json();
      countryLayer = L.geoJSON(countries, {
        style: () => ({
          color: '#9eabb1',
          weight: 0.7,
          fillColor: '#344147',
          fillOpacity: 0.36,
        }),
        onEachFeature: onCountryFeature,
      }).addTo(map);
      [
        ['AND', [42.50, 1.52]],
        ['ATG', [17.06, -61.79]],
        ['BHR', [26.06, 50.55]],
        ['BRB', [13.19, -59.54]],
        ['COK', [-21.23, -159.77]],
        ['COM', [-11.64, 43.33]],
        ['CPV', [15.12, -23.62]],
        ['DMA', [15.41, -61.37]],
        ['FSM', [6.92, 158.16]],
        ['GRD', [12.11, -61.67]],
        ['HKG', [22.32, 114.17]],
        ['KIR', [1.87, -157.36]],
        ['KNA', [17.35, -62.78]],
        ['LCA', [13.90, -60.97]],
        ['LIE', [47.16, 9.55]],
        ['MCO', [43.73, 7.42]],
        ['MDV', [3.20, 73.22]],
        ['MHL', [7.13, 171.18]],
        ['MLT', [35.93, 14.37]],
        ['MUS', [-20.34, 57.55]],
        ['NIU', [-19.05, -169.86]],
        ['NRU', [-0.52, 166.93]],
        ['PLW', [7.51, 134.58]],
        ['SGP', [1.35, 103.82]],
        ['SMR', [43.94, 12.45]],
        ['STP', [0.18, 6.61]],
        ['SYC', [-4.67, 55.49]],
        ['TON', [-21.17, -175.19]],
        ['TUV', [-7.10, 177.64]],
        ['VAT', [41.90, 12.45]],
        ['VCT', [13.25, -61.19]],
        ['WSM', [-13.75, -172.10]],
      ].forEach(([code, coordinates]) => {
        const marker = L.circleMarker(coordinates, {
          radius: 5,
          color: '#fff',
          weight: 2,
          fillColor: '#8d6263',
          fillOpacity: 1,
        }).addTo(map);
        marker.bindTooltip(countryName(code));
        marker.on('click', () => selectCountry(code));
        smallCountryMarkers.set(code, marker);
      });
      status.textContent = 'Cliquez sur un pays ou une île pour valider votre réponse.';
      updateMap();
    } catch (error) {
      status.textContent = `Impossible de charger la carte : ${error.message}`;
    }
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
    const correctNames = (result.correct_countries || []).map(countryName);
    detail.textContent = `Réponse${correctNames.length > 1 ? 's' : ''} valable${correctNames.length > 1 ? 's' : ''} : ${correctNames.join(', ')} · ${formatPrompt(result.prompt_cm)} · +${earned} point${earned === 1 ? '' : 's'}.`;
    section.append(heading, detail);

    if (gameType === 'room' && Array.isArray(result.guesses)) {
      const ranking = document.createElement('ol');
      [...result.guesses]
        .sort((left, right) => right.score - left.score || left.name.localeCompare(right.name, 'fr'))
        .forEach((guess) => {
          const item = document.createElement('li');
          item.textContent = `${guess.name} · ${guess.guess ? countryName(guess.guess) : 'sans réponse'} · ${guess.correct ? 'juste' : 'faux'} · +${guess.score}`;
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
    const waiting = document.getElementById('bito-waiting');
    const prompt = document.getElementById('bito-prompt');
    const result = roundResult();
    const isLobby = state.status === 'lobby';
    const isComplete = Boolean(result);
    const submitted = gameType === 'room' && state.player?.submitted;

    question.hidden = isLobby;
    waiting.hidden = true;

    if (!question.hidden) {
      prompt.textContent = formatPrompt(result?.prompt_cm ?? state.prompt_cm);
      mapCountries = new Set(state.countries || []);
      if (map) window.setTimeout(() => map.invalidateSize(), 0);
      if (submitted && !isComplete) {
        waiting.textContent = 'Réponse enregistrée. En attente des autres joueurs…';
        waiting.hidden = false;
        document.getElementById('bito-map-status').textContent =
          `Votre réponse : ${countryName(state.player.guess)}.`;
      } else if (isComplete) {
        document.getElementById('bito-map-status').textContent =
          'Les pays en vert correspondent à cette valeur ; votre réponse apparaît en rouge si elle est incorrecte.';
      } else if (!selectedCountry) {
        document.getElementById('bito-map-status').textContent =
          'Cliquez sur un pays coloré. Les pays grisés ne disposent pas de données.';
      }
    }
    updateMap();
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
    selectedCountry = null;
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
    selectedCountry = null;
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
    selectedCountry = null;
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
  initializeMap();
  if (params.has('room')) {
    resumeRoom(params.get('room'));
  } else if (params.get('mode') === 'solo' && params.has('game_id')) {
    resumeSolo(params.get('game_id'));
  }
})();
