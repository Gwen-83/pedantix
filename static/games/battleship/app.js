(() => {
  const apiBase = window.PEDANTIX_CONFIG?.BACKEND_URL?.replace(/\/+$/, '') || '';
  const home = document.getElementById('naval-home');
  const play = document.getElementById('naval-play');
  const homeError = document.getElementById('naval-home-error');
  const playError = document.getElementById('naval-play-error');
  const roomInput = document.getElementById('naval-room-code');
  const params = new URLSearchParams(window.location.search);
  const shipNames = {
    carrier: 'Porte-avions',
    battleship: 'Cuirassé',
    cruiser: 'Croiseur',
    submarine: 'Sous-marin',
    destroyer: 'Torpilleur',
    frigate: 'Frégate',
  };
  const difficultySelect = document.getElementById('naval-difficulty');
  const roomDirectory = document.getElementById('naval-room-directory');
  const rows = 'ABCDEFGHIJ';
  let playerId = localStorage.getItem('battleship_player_id');
  if (!playerId) {
    playerId = globalThis.crypto?.randomUUID?.()
      || `battleship-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    localStorage.setItem('battleship_player_id', playerId);
  }
  const playerName = (localStorage.getItem('pedantix_player_name')
    || localStorage.getItem('pedantix_auth_user')
    || 'Joueur').trim().slice(0, 24);

  let state = null;
  let pollingTimer = null;
  let roomBusy = false;
  let selectedShip = 'carrier';
  let vertical = false;
  let draftFleet = {};
  let lastShotResult = null;

  document.getElementById('naval-player-name').textContent = playerName;

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

  function roomPayload() {
    return { room_id: state.room_id, player_id: playerId, player_name: playerName };
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
    pollingTimer = window.setInterval(refreshRoom, 1500);
  }

  function showHome() {
    stopPolling();
    state = null;
    home.hidden = false;
    play.hidden = true;
    history.replaceState(null, '', window.location.pathname);
    refreshRoomDirectory();
  }

  function renderRoomDirectory(rooms) {
    roomDirectory.replaceChildren();
    if (!rooms.length) {
      const empty = document.createElement('p');
      empty.className = 'naval-room-empty';
      empty.textContent = 'Aucun salon ouvert pour le moment.';
      roomDirectory.append(empty);
      return;
    }
    for (const room of rooms) {
      const card = document.createElement('div');
      card.className = 'naval-room-card';
      const copy = document.createElement('span');
      copy.className = 'naval-room-card-copy';
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
      button.className = 'naval-secondary-button';
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
      const data = await request(`/api/battleship/rooms?player_id=${encodeURIComponent(playerId)}`);
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

  function coordinate(row, column) {
    return `${rows[row]}${column + 1}`;
  }

  function coordinateParts(value) {
    const match = /^([A-J])(\d{1,2})$/.exec(value);
    return match ? [rows.indexOf(match[1]), Number(match[2]) - 1] : null;
  }

  function renderGrid(container, { ships = [], shots = [], interactive = false, shotMode = false } = {}) {
    const shipByCell = new Map();
    for (const ship of ships) {
      for (const cell of ship.cells) shipByCell.set(cell, ship);
    }
    const shotByCell = new Map(shots.map((shot) => [shot.coordinate, shot]));
    const grid = document.createElement('div');
    grid.className = 'naval-grid';
    grid.setAttribute('role', 'grid');
    const corner = document.createElement('span');
    corner.className = 'naval-axis';
    corner.setAttribute('aria-hidden', 'true');
    grid.append(corner);
    for (let column = 0; column < 10; column += 1) {
      const heading = document.createElement('span');
      heading.className = 'naval-axis';
      heading.textContent = String(column + 1);
      heading.setAttribute('role', 'columnheader');
      grid.append(heading);
    }

    for (let row = 0; row < 10; row += 1) {
      const rowHeading = document.createElement('span');
      rowHeading.className = 'naval-axis';
      rowHeading.textContent = rows[row];
      rowHeading.setAttribute('role', 'rowheader');
      grid.append(rowHeading);
      for (let column = 0; column < 10; column += 1) {
        const cell = coordinate(row, column);
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'naval-cell';
        button.setAttribute('role', 'gridcell');
        button.setAttribute('aria-label', cell);
        button.title = cell;
        const ship = shipByCell.get(cell);
        const shot = shotByCell.get(cell);
        if (ship) {
          button.classList.add('naval-ship', `naval-${ship.ship_id}`);
          button.setAttribute('aria-label', `${cell}, ${ship.name}${ship.sunk ? ', coulé' : ''}`);
          if (ship.sunk) button.classList.add('naval-sunk');
        }
        if (shot) {
          button.classList.add(shot.hit ? 'naval-hit' : 'naval-miss');
          button.textContent = shot.hit ? '×' : '•';
          button.setAttribute('aria-label', `${cell}, ${shot.hit ? 'touché' : 'dans l’eau'}`);
        } else if (ship && !shotMode) {
          button.textContent = '■';
        }
        if (interactive) {
          button.classList.add('naval-setup-cell');
          button.addEventListener('click', () => placeSelectedShip(cell));
        } else if (shotMode) {
          button.classList.add('naval-shot-cell');
          button.disabled = !isMyTurn() || !!shot;
          button.addEventListener('click', () => fire(cell));
        } else {
          button.disabled = true;
        }
        grid.append(button);
      }
    }
    container.replaceChildren(grid);
  }

  function fleetForRender() {
    if (!state) return [];
    const currentFleet = state.own_fleet.map((ship) => ({ ...ship }));
    return currentFleet.map((ship) => ({
      ...ship,
      cells: draftFleet[ship.ship_id] || ship.cells,
    }));
  }

  function isMyTurn() {
    return state?.status === 'playing'
      && !myPlayer()?.is_spectator
      && state.current_player_id === playerId;
  }

  function myPlayer() {
    return state?.players.find((player) => player.player_id === playerId);
  }

  function renderShipPicker() {
    const picker = document.getElementById('naval-ship-picker');
    picker.replaceChildren();
    const ready = myPlayer()?.ready;
    for (const [shipId, length] of Object.entries(state.ship_lengths)) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'naval-ship-button';
      button.textContent = `${shipNames[shipId]} · ${length}`;
      button.setAttribute('aria-pressed', String(selectedShip === shipId));
      button.disabled = ready;
      button.addEventListener('click', () => {
        selectedShip = shipId;
        renderShipPicker();
      });
      picker.append(button);
    }
  }

  function renderLobby() {
    const players = state.players;
    const ownPlayer = myPlayer();
    document.getElementById('naval-status-label').textContent = 'Salon de préparation';
    document.getElementById('naval-title').textContent = `Salon ${state.room_id}`;
    document.getElementById('naval-lobby').hidden = false;
    document.getElementById('naval-battle').hidden = true;
    const activeCount = players.filter((player) => !player.is_spectator).length;
    const spectatorCount = players.length - activeCount;
    document.getElementById('naval-lobby-status').textContent =
      `${activeCount} joueur${activeCount === 1 ? '' : 's'}${spectatorCount ? ` · ${spectatorCount} observateur${spectatorCount === 1 ? '' : 's'}` : ''} dans le salon. Au moins deux joueurs sont nécessaires.`;
    document.getElementById('naval-invite-code').textContent = `Code : ${state.room_id}`;
    const inviteUrl = new URL(window.location.href);
    inviteUrl.search = new URLSearchParams({ room: state.room_id }).toString();
    document.getElementById('naval-copy-invite').dataset.inviteUrl = inviteUrl.href;
    const list = document.getElementById('naval-player-list');
    list.replaceChildren(...players.map((player) => {
      const item = document.createElement('li');
      const name = document.createElement('span');
      name.textContent = player.name + (player.player_id === state.host_player_id ? ' (hôte)' : '');
      const ready = document.createElement('small');
      ready.textContent = player.is_spectator
        ? 'Observateur · en attente de la prochaine partie'
        : player.ready ? 'Flotte confirmée' : 'Préparation…';
      if (player.is_spectator) item.classList.add('naval-spectator');
      item.append(name, ready);
      return item;
    }));

    const readyButton = document.getElementById('naval-ready-button');
    readyButton.textContent = ownPlayer?.ready ? 'Modifier ma flotte' : 'Confirmer ma flotte';
    readyButton.disabled = roomBusy;
    document.getElementById('naval-start-button').hidden = playerId !== state.host_player_id;
    document.getElementById('naval-start-button').disabled = !state.can_start || roomBusy;
    document.getElementById('naval-orientation').textContent =
      `Orientation : ${vertical ? 'verticale' : 'horizontale'}`;
    document.getElementById('naval-orientation').disabled = !!ownPlayer?.ready;
    document.getElementById('naval-randomize').disabled = roomBusy || !!ownPlayer?.ready;
    renderShipPicker();
    renderGrid(document.getElementById('naval-setup-grid'), {
      ships: fleetForRender(),
      interactive: !ownPlayer?.ready,
    });
    document.getElementById('naval-setup-help').textContent = ownPlayer?.ready
      ? 'Votre flotte est confirmée. Vous pourrez la modifier en sélectionnant « Modifier ma flotte ».'
      : 'Sélectionnez un navire, puis une case de départ. Les navires ne peuvent pas se toucher.';
  }

  function renderBattle() {
    document.getElementById('naval-status-label').textContent =
      state.status === 'finished' ? 'Bataille terminée' : `Tour ${state.turn_number}`;
    const ownPlayer = state.players.find((player) => player.player_id === playerId);
    document.getElementById('naval-title').textContent = state.status === 'finished'
      ? 'Partie terminée'
      : 'À l’abordage !';
    document.getElementById('naval-lobby').hidden = true;
    document.getElementById('naval-battle').hidden = false;
    const target = state.players.find((player) => player.player_id === state.target_player_id);
    const current = state.players.find((player) => player.player_id === state.current_player_id);
    const turnMessage = document.getElementById('naval-turn-message');
    const shotMessage = document.getElementById('naval-shot-result');
    shotMessage.className = 'naval-shot-result';
    if (lastShotResult) {
      const targetName = state.players.find(
        (player) => player.player_id === lastShotResult.target_id,
      )?.name || 'l’adversaire';
      if (lastShotResult.hit) {
        const sunk = lastShotResult.sunk_ship
          ? ` Vous avez coulé le ${shipNames[lastShotResult.sunk_ship]}.`
          : '';
        const eliminated = lastShotResult.eliminated ? ` ${targetName} est éliminé.` : '';
        const extraShot = state.status === 'playing' && isMyTurn()
          ? ' Vous gardez la main.'
          : '';
        shotMessage.textContent =
          `Touché sur ${targetName} en ${lastShotResult.coordinate}.${sunk}${eliminated}${extraShot}`;
        shotMessage.classList.add('naval-shot-hit');
      } else {
        shotMessage.textContent =
          `Dans l’eau en ${lastShotResult.coordinate}. Le tour passe à ${current?.name || 'l’adversaire'}.`;
        shotMessage.classList.add('naval-shot-miss');
      }
    } else {
      shotMessage.textContent = '';
    }
    if (ownPlayer?.is_spectator) {
      turnMessage.textContent = state.status === 'finished'
        ? 'Vous observez la partie terminée. Vous rejoindrez la prochaine partie au redémarrage.'
        : `Vous observez la partie en direct${current ? ` · tour de ${current.name}` : ''}.`;
    } else if (state.status === 'finished') {
      const winner = state.players.find((player) => player.player_id === state.winner_player_id);
      turnMessage.textContent = winner ? `${winner.name} remporte la bataille !` : 'La bataille est terminée.';
    } else if (isMyTurn()) {
      turnMessage.textContent = target
        ? `C’est votre tour. Choisissez une case sur le plateau de ${target.name}.`
        : 'C’est votre tour.';
    } else {
      turnMessage.textContent = current ? `Au tour de ${current.name} de tirer.` : 'En attente du prochain tir…';
    }

    const viewedPlayer = state.players.find(
      (player) => player.player_id === (ownPlayer?.is_spectator
        ? state.observed_player_id
        : playerId),
    );
    document.getElementById('naval-own-ships-count').textContent = ownPlayer?.is_spectator
      ? `${viewedPlayer?.ships_remaining ?? 0} navire${viewedPlayer?.ships_remaining === 1 ? '' : 's'} à flot`
      : `${ownPlayer?.ships_remaining ?? 0} navire${ownPlayer?.ships_remaining === 1 ? '' : 's'} à flot`;
    document.getElementById('naval-own-board-title').textContent = ownPlayer?.is_spectator
      ? `Impacts subis par ${viewedPlayer?.name || 'le joueur actif'}`
      : 'Votre flotte';
    document.getElementById('naval-target-title').textContent =
      target ? `Plateau de ${target.name}` : 'Plateau adverse';
    document.getElementById('naval-turn-badge').textContent =
      state.status === 'finished' ? 'Terminé' : isMyTurn() ? 'À vous' : 'En attente';
    const ownShips = state.own_fleet.map((ship) => ({ ...ship }));
    const incoming = state.incoming_shots.map((shot) => ({ ...shot }));
    renderGrid(document.getElementById('naval-own-grid'), { ships: ownShips, shots: incoming });
    renderGrid(document.getElementById('naval-target-grid'), {
      shots: state.target_shots,
      shotMode: state.status === 'playing',
    });
    const battleList = document.getElementById('naval-battle-player-list');
    battleList.replaceChildren(...state.players.map((player) => {
      const item = document.createElement('li');
      const name = document.createElement('span');
      name.textContent = player.name + (player.player_id === playerId ? ' (vous)' : '');
      const status = document.createElement('small');
      status.textContent = player.is_spectator
        ? 'Observateur · en attente de la prochaine partie'
        : player.eliminated
        ? 'Éliminé'
        : `${player.ships_remaining} navire${player.ships_remaining === 1 ? '' : 's'} à flot`;
      if (player.is_spectator) item.classList.add('naval-spectator');
      item.append(name, status);
      return item;
    }));
    const scoreboard = document.getElementById('naval-scoreboard');
    scoreboard.hidden = state.status !== 'finished';
    if (!scoreboard.hidden) {
      scoreboard.replaceChildren();
      const heading = document.createElement('h2');
      heading.textContent = turnMessage.textContent;
      scoreboard.append(heading);
    }
    const restartButton = document.getElementById('naval-restart-button');
    restartButton.hidden = state.status !== 'finished' || playerId !== state.host_player_id;
    restartButton.disabled = roomBusy;
  }

  function updateView() {
    if (!state) return;
    showPlay();
    if (state.status === 'lobby') renderLobby();
    else renderBattle();
  }

  async function createRoom() {
    const button = document.getElementById('naval-create-room');
    setBusy(button, true, 'Création…');
    hideError(homeError);
    try {
      state = await post('/api/battleship/room/create', {
        player_id: playerId,
        player_name: playerName,
        difficulty: difficultySelect.value,
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
      state = await post('/api/battleship/room/join', {
        room_id: cleanRoomId,
        player_id: playerId,
        player_name: playerName,
      });
      difficultySelect.value = state.difficulty || 'moyen';
      enterRoom();
    } catch (error) {
      showError(homeError, error.message);
    }
  }

  function enterRoom() {
    localStorage.setItem('battleship_active_room_id', state.room_id);
    history.replaceState(null, '', `${window.location.pathname}?room=${encodeURIComponent(state.room_id)}`);
    draftFleet = {};
    updateView();
    startPolling();
  }

  async function placeSelectedShip(startCell) {
    if (!state || myPlayer()?.ready || roomBusy) return;
    const parts = coordinateParts(startCell);
    if (!parts) return;
    const [row, column] = parts;
    const length = state.ship_lengths[selectedShip];
    const cells = [];
    for (let offset = 0; offset < length; offset += 1) {
      const nextRow = row + (vertical ? offset : 0);
      const nextColumn = column + (vertical ? 0 : offset);
      if (nextRow > 9 || nextColumn > 9) {
        document.getElementById('naval-setup-help').textContent = 'Ce navire ne tient pas dans cette direction à partir de cette case.';
        return;
      }
      cells.push(coordinate(nextRow, nextColumn));
    }
    const current = Object.fromEntries(state.own_fleet.map((ship) => [
      ship.ship_id,
      draftFleet[ship.ship_id] || ship.cells,
    ]));
    draftFleet = { ...draftFleet, [selectedShip]: cells };
    const fleet = { ...current, ...draftFleet };
    roomBusy = true;
    try {
      state = await post('/api/battleship/room/fleet', { ...roomPayload(), fleet });
      draftFleet = {};
      updateView();
    } catch (error) {
      draftFleet = { ...draftFleet, [selectedShip]: cells };
      document.getElementById('naval-setup-help').textContent = error.message;
      renderGrid(document.getElementById('naval-setup-grid'), {
        ships: fleetForRender(),
        interactive: true,
      });
    } finally {
      roomBusy = false;
      if (state?.status === 'lobby') renderLobby();
    }
  }

  async function randomizeFleet() {
    if (!state || roomBusy) return;
    roomBusy = true;
    try {
      state = await post('/api/battleship/room/randomize', roomPayload());
      draftFleet = {};
      updateView();
    } catch (error) {
      showError(playError, error.message);
    } finally {
      roomBusy = false;
      if (state?.status === 'lobby') renderLobby();
    }
  }

  async function setReady(ready) {
    if (!state || roomBusy) return;
    roomBusy = true;
    try {
      state = await post('/api/battleship/room/ready', { ...roomPayload(), ready });
      updateView();
    } catch (error) {
      showError(playError, error.message);
    } finally {
      roomBusy = false;
      if (state?.status === 'lobby') renderLobby();
    }
  }

  async function startGame() {
    if (!state || roomBusy) return;
    roomBusy = true;
    try {
      state = await post('/api/battleship/room/start', roomPayload());
      updateView();
    } catch (error) {
      showError(playError, error.message);
    } finally {
      roomBusy = false;
    }
  }

  async function restartGame() {
    if (!state || state.status !== 'finished' || roomBusy) return;
    roomBusy = true;
    const button = document.getElementById('naval-restart-button');
    button.disabled = true;
    try {
      state = await post('/api/battleship/room/restart', roomPayload());
      lastShotResult = null;
      draftFleet = {};
      updateView();
    } catch (error) {
      showError(playError, error.message);
    } finally {
      roomBusy = false;
      if (state?.status === 'finished') renderBattle();
      else if (state?.status === 'lobby') renderLobby();
    }
  }

  async function fire(coordinateValue) {
    if (!state || !isMyTurn() || roomBusy) return;
    roomBusy = true;
    hideError(playError);
    try {
      const response = await post('/api/battleship/room/fire', {
        ...roomPayload(),
        coordinate: coordinateValue,
      });
      lastShotResult = response.result;
      state = response;
      updateView();
    } catch (error) {
      showError(playError, error.message);
    } finally {
      roomBusy = false;
    }
  }

  async function refreshRoom() {
    if (!state || roomBusy) return;
    try {
      state = await request(
        `/api/battleship/room/${encodeURIComponent(state.room_id)}?player_id=${encodeURIComponent(playerId)}`,
      );
      updateView();
    } catch (error) {
      stopPolling();
      showError(playError, error.message);
    }
  }

  document.getElementById('naval-create-room').addEventListener('click', createRoom);
  document.getElementById('naval-refresh-rooms').addEventListener('click', refreshRoomDirectory);
  document.getElementById('naval-join-room').addEventListener('click', () => joinRoom(roomInput.value));
  roomInput.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      joinRoom(roomInput.value);
    }
  });
  document.getElementById('naval-copy-invite').addEventListener('click', async (event) => {
    const url = event.currentTarget.dataset.inviteUrl;
    try {
      await navigator.clipboard.writeText(url);
      event.currentTarget.textContent = 'Lien copié !';
      window.setTimeout(() => { event.currentTarget.textContent = 'Copier le lien'; }, 1800);
    } catch {
      window.prompt('Copiez ce lien pour inviter vos amis :', url);
    }
  });
  document.getElementById('naval-home-button').addEventListener('click', () => {
    localStorage.removeItem('battleship_active_room_id');
    window.location.assign('/');
  });
  document.getElementById('naval-orientation').addEventListener('click', () => {
    vertical = !vertical;
    renderLobby();
  });
  document.getElementById('naval-randomize').addEventListener('click', randomizeFleet);
  document.getElementById('naval-ready-button').addEventListener('click', () => {
    if (myPlayer()?.ready) setReady(false);
    else setReady(true);
  });
  document.getElementById('naval-start-button').addEventListener('click', startGame);
  document.getElementById('naval-restart-button').addEventListener('click', restartGame);

  const roomId = params.get('room');
  if (roomId) {
    roomInput.value = roomId;
    joinRoom(roomId);
  } else if (localStorage.getItem('battleship_active_room_id')) {
    joinRoom(localStorage.getItem('battleship_active_room_id'));
  }
})();
