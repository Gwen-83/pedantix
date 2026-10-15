(() => {
  const apiBase = window.PEDANTIX_CONFIG?.BACKEND_URL?.replace(/\/+$/, '') || '';
  const playerId = (() => {
    let id = localStorage.getItem('undercover_player_id');
    if (!id) {
      id = globalThis.crypto?.randomUUID?.()
        || `undercover-${Date.now()}-${Math.random().toString(36).slice(2)}`;
      localStorage.setItem('undercover_player_id', id);
    }
    return id;
  })();
  const playerName = (
    localStorage.getItem('pedantix_auth_user')
    || localStorage.getItem('pedantix_player_name')
    || 'Joueur'
  ).trim().slice(0, 24);
  const $ = (id) => document.getElementById(id);
  const home = $('undercover-home');
  const game = $('undercover-game');
  let state = null;
  let roomId = '';
  let pollTimer = null;
  let isRefreshing = false;

  $('undercover-player-name').textContent = playerName;

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

  function playerPayload() {
    return { player_id: playerId, player_name: playerName, room_id: roomId };
  }

  function showError(element, error) {
    element.textContent = error.message || String(error);
    element.hidden = false;
  }

  function clearError(element) {
    element.hidden = true;
    element.textContent = '';
  }

  function setState(nextState) {
    state = nextState;
    roomId = nextState.room_id;
    localStorage.setItem('undercover_active_room_id', roomId);
    history.replaceState(null, '', `${window.location.pathname}?room=${encodeURIComponent(roomId)}`);
    clearError($('undercover-game-error'));
    home.hidden = true;
    game.hidden = false;
    render();
    startPolling();
  }

  function startPolling() {
    if (pollTimer) window.clearInterval(pollTimer);
    pollTimer = window.setInterval(refreshRoom, 1600);
  }

  async function refreshRoom() {
    if (!roomId || isRefreshing) return;
    isRefreshing = true;
    try {
      setState(await request(
        `/api/undercover/room/${encodeURIComponent(roomId)}?player_id=${encodeURIComponent(playerId)}`,
      ));
    } catch (error) {
      showError($('undercover-game-error'), error);
      if (error.message.includes('introuvable')) {
        leaveRoom();
      }
    } finally {
      isRefreshing = false;
    }
  }

  function stopPolling() {
    if (pollTimer) window.clearInterval(pollTimer);
    pollTimer = null;
  }

  function leaveRoom() {
    stopPolling();
    state = null;
    roomId = '';
    localStorage.removeItem('undercover_active_room_id');
    history.replaceState(null, '', window.location.pathname);
    game.hidden = true;
    home.hidden = false;
    refreshDirectory();
  }

  function renderDirectory(rooms) {
    const directory = $('undercover-room-directory');
    directory.replaceChildren();
    if (!rooms.length) {
      directory.textContent = 'Aucun salon ouvert pour le moment.';
      return;
    }
    for (const room of rooms) {
      const card = document.createElement('article');
      card.className = 'undercover-room-card';
      const label = document.createElement('span');
      const title = document.createElement('strong');
      title.textContent = `Salon ${room.room_id}`;
      const details = document.createElement('small');
      details.textContent = `${room.player_count} joueur${room.player_count === 1 ? '' : 's'}`
        + (room.spectator_count ? ` · ${room.spectator_count} spectateur${room.spectator_count === 1 ? '' : 's'}` : '')
        + ` · ${room.status === 'playing' ? 'En cours' : 'En attente'}`;
      label.append(title, details);
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'undercover-secondary';
      button.textContent = room.is_member
        ? 'Reprendre'
        : room.status === 'playing' ? 'Observer' : 'Rejoindre';
      button.addEventListener('click', () => joinRoom(room.room_id));
      card.append(label, button);
      directory.append(card);
    }
  }

  async function refreshDirectory() {
    const directory = $('undercover-room-directory');
    directory.textContent = 'Chargement des salons…';
    try {
      const result = await request(
        `/api/undercover/rooms?player_id=${encodeURIComponent(playerId)}`,
      );
      renderDirectory(result.rooms || []);
    } catch (error) {
      directory.textContent = `Impossible de charger les salons : ${error.message}`;
    }
  }

  async function createRoom() {
    clearError($('undercover-home-error'));
    try {
      setState(await request('/api/undercover/room/create', {
        player_id: playerId,
        player_name: playerName,
      }));
    } catch (error) {
      showError($('undercover-home-error'), error);
    }
  }

  async function joinRoom(code) {
    clearError($('undercover-home-error'));
    try {
      setState(await request('/api/undercover/room/join', {
        ...playerPayload(),
        room_id: code.trim().toUpperCase(),
      }));
    } catch (error) {
      showError($('undercover-home-error'), error);
    }
  }

  async function perform(action, payload = {}) {
    clearError($('undercover-game-error'));
    try {
      setState(await request(`/api/undercover/room/${action}`, {
        ...playerPayload(),
        ...payload,
      }));
    } catch (error) {
      showError($('undercover-game-error'), error);
      await refreshRoom();
    }
  }

  function renderPlayerList(list, players, showRoles = false) {
    list.replaceChildren(...players.map((player) => {
      const item = document.createElement('li');
      const name = document.createElement('span');
      name.textContent = player.name
        + (player.player_id === state.host_player_id ? ' · HÔTE' : '')
        + (player.player_id === playerId ? ' · VOUS' : '');
      const info = document.createElement('small');
      if (player.is_spectator) info.textContent = 'Spectateur';
      else if (!player.alive) info.textContent = showRoles && player.role ? roleLabel(player.role) : 'Éliminé';
      else if (state.status === 'lobby') info.textContent = 'Dans le salon';
      else if (showRoles && player.role) info.textContent = roleLabel(player.role);
      else info.textContent = player.has_voted ? 'A voté' : player.spoken ? 'Indice donné' : 'En jeu';
      item.append(name, info);
      return item;
    }));
  }

  function roleLabel(role) {
    return ({
      civilian: 'Civil',
      undercover: 'Undercover',
      mr_white: 'Mr White',
    })[role] || 'Rôle inconnu';
  }

  function renderLobby() {
    $('undercover-lobby').hidden = false;
    $('undercover-round').hidden = true;
    $('undercover-phase-label').textContent = 'Salon d’attente';
    $('undercover-game-title').textContent = `Salon ${state.room_id}`;
    const invite = new URL(window.location.href);
    invite.search = new URLSearchParams({ room: state.room_id }).toString();
    $('undercover-invite-code').textContent = state.room_id;
    $('undercover-copy-invite').dataset.inviteUrl = invite.href;
    $('undercover-lobby-message').textContent = state.player.is_spectator
      ? 'Vous observez ce salon. Vous pourrez jouer à la prochaine partie.'
      : `${state.player_count} joueur${state.player_count === 1 ? '' : 's'} · il en faut au moins 3 pour démarrer.`;
    $('undercover-role-summary').textContent = state.player_count >= 3
      ? `Rôles prévus : ${state.role_counts.civilian} civils, ${state.role_counts.undercover} undercover${state.role_counts.undercover > 1 ? 's' : ''}`
        + (state.role_counts.mr_white ? ` et ${state.role_counts.mr_white} Mr White.` : '.')
      : '';
    renderPlayerList($('undercover-player-list'), state.players);
    const start = $('undercover-start');
    start.hidden = state.player.player_id !== state.host_player_id;
    start.disabled = !state.can_start;
  }

  function renderRound() {
    $('undercover-lobby').hidden = true;
    $('undercover-round').hidden = false;
    $('undercover-phase-label').textContent = ({
      discussion: 'Manche en cours',
      voting: 'Vote en cours',
      mr_white_guess: 'Dernière chance de Mr White',
      finished: 'Partie terminée',
    })[state.phase] || 'Partie en cours';
    $('undercover-game-title').textContent = `Manche ${state.round_number}`;
    renderPlayerList(
      $('undercover-alive-list'),
      state.players.filter((player) => !player.is_spectator),
      state.status === 'finished',
    );

    const current = state.player;
    const secret = $('undercover-secret');
    if (current.is_spectator) {
      secret.textContent = 'Vous êtes spectateur. Vous pourrez rejoindre la prochaine partie.';
    } else if (current.role === 'mr_white') {
      secret.replaceChildren();
      const title = document.createElement('span');
      title.textContent = current.alive ? 'Votre rôle : Mr White' : 'Vous étiez Mr White';
      const detail = document.createElement('strong');
      detail.textContent = current.alive ? 'Vous n’avez pas de mot.' : 'Aucun mot ne vous avait été donné.';
      secret.append(title, detail);
    } else if (current.word) {
      secret.replaceChildren();
      const title = document.createElement('span');
      title.textContent = `Votre rôle : ${roleLabel(current.role)}`;
      const detail = document.createElement('strong');
      detail.textContent = current.word;
      secret.append(title, detail);
    } else {
      secret.textContent = current.alive ? 'Votre rôle sera distribué au lancement.' : 'Vous avez été éliminé.';
    }

    const discussionActions = $('undercover-discussion-actions');
    const voteActions = $('undercover-vote-actions');
    const whiteForm = $('undercover-white-form');
    discussionActions.hidden = state.phase !== 'discussion';
    voteActions.hidden = state.phase !== 'voting';
    whiteForm.hidden = state.phase !== 'mr_white_guess'
      || current.role !== 'mr_white' || current.alive;
    $('undercover-spoken').disabled = current.is_spectator || !current.alive || current.spoken;
    $('undercover-spoken').textContent = current.spoken
      ? 'Indice validé · en attente'
      : 'J’ai donné mon indice';
    $('undercover-start-vote').hidden = current.player_id !== state.host_player_id;
    if (state.phase === 'discussion') {
      $('undercover-round-message').textContent = current.is_spectator
        ? 'Observez les indices et la discussion.'
        : !current.alive ? 'Vous êtes éliminé et observez la partie.'
          : current.spoken ? 'Vous avez donné votre indice. En attente des autres joueurs.'
            : 'À tour de rôle, donnez un indice lié à votre mot sans le révéler.';
    } else if (state.phase === 'voting') {
      $('undercover-round-message').textContent = current.is_spectator
        ? 'Les joueurs discutent et votent.'
        : !current.alive ? 'Vous êtes éliminé et observez le vote.'
          : current.has_voted ? 'Votre vote est enregistré. En attente des autres joueurs.'
            : 'Votez pour la personne que vous soupçonnez.';
      renderVoteActions(voteActions);
    } else if (state.phase === 'mr_white_guess') {
      $('undercover-round-message').textContent = whiteForm.hidden
        ? 'Mr White a été éliminé et tente de deviner le mot des civils.'
        : 'Vous avez été démasqué. Devinez le mot des civils pour gagner.';
    } else {
      $('undercover-round-message').textContent = 'La partie est terminée.';
    }
    renderLastResult();
    renderFinal();
  }

  function renderVoteActions(container) {
    container.replaceChildren();
    const current = state.player;
    if (current.is_spectator || !current.alive || current.has_voted) return;
    for (const player of state.players) {
      if (player.is_spectator || !player.alive || player.player_id === playerId) continue;
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'undercover-secondary';
      button.textContent = `Voter contre ${player.name}`;
      button.addEventListener('click', () => perform('vote', {
        target_player_id: player.player_id,
      }));
      container.append(button);
    }
  }

  function renderLastResult() {
    const result = $('undercover-result');
    result.hidden = !state.last_result;
    if (!state.last_result) return;
    const last = state.last_result;
    const messages = {
      tie: 'Égalité : personne n’est éliminé. Une nouvelle manche commence.',
      elimination: `${last.player_name} a été éliminé : ${roleLabel(last.role)}.`,
      mr_white_won: `${last.player_name} a deviné le mot des civils et gagne la partie !`,
      mr_white_failed: `${last.player_name} n’a pas trouvé le mot. La partie continue.`,
    };
    result.textContent = messages[last.type] || 'Résultat du vote.';
    if (last.vote_counts) {
      const counts = document.createElement('p');
      counts.textContent = last.vote_counts
        .map((entry) => `${entry.player_name} : ${entry.count}`)
        .join(' · ');
      result.append(counts);
    }
  }

  function renderFinal() {
    const final = $('undercover-final');
    final.hidden = state.status !== 'finished';
    if (final.hidden) return;
    final.replaceChildren();
    const title = document.createElement('h2');
    title.textContent = ({
      civilians: 'Les civils gagnent !',
      undercover: 'Les Undercover gagnent !',
      mr_white: 'Mr White gagne !',
    })[state.winner] || 'Partie terminée';
    const words = document.createElement('p');
    words.textContent = `Mot des civils : ${state.words.civilian} · Mot des Undercover : ${state.words.undercover}`;
    final.append(title, words);
    const results = document.createElement('ul');
    results.className = 'undercover-player-list';
    renderPlayerList(results, state.players, true);
    final.append(results);
    if (state.can_restart) {
      const restart = document.createElement('button');
      restart.type = 'button';
      restart.className = 'undercover-primary';
      restart.textContent = 'Retourner au salon pour rejouer';
      restart.addEventListener('click', () => perform('restart'));
      final.append(restart);
    }
  }

  function render() {
    if (!state) return;
    if (state.status === 'lobby') renderLobby();
    else renderRound();
  }

  $('undercover-create-room').addEventListener('click', createRoom);
  $('undercover-join-room').addEventListener('click', () => joinRoom($('undercover-room-code').value));
  $('undercover-room-code').addEventListener('keydown', (event) => {
    if (event.key === 'Enter') joinRoom($('undercover-room-code').value);
  });
  $('undercover-refresh-rooms').addEventListener('click', refreshDirectory);
  $('undercover-start').addEventListener('click', () => perform('start'));
  $('undercover-spoken').addEventListener('click', () => perform('spoken'));
  $('undercover-start-vote').addEventListener('click', () => perform('voting'));
  $('undercover-leave').addEventListener('click', leaveRoom);
  $('undercover-copy-invite').addEventListener('click', async (event) => {
    try {
      await navigator.clipboard.writeText(event.currentTarget.dataset.inviteUrl);
      event.currentTarget.textContent = 'Lien copié !';
    } catch (error) {
      showError($('undercover-game-error'), new Error(`Impossible de copier le lien : ${error.message}`));
    }
  });
  $('undercover-white-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const input = $('undercover-white-guess');
    if (input.value.trim()) perform('guess', { guess: input.value.trim() });
  });

  async function initialize() {
    const requestedRoom = new URLSearchParams(window.location.search).get('room')
      || localStorage.getItem('undercover_active_room_id');
    if (requestedRoom) {
      try {
        setState(await request('/api/undercover/room/join', {
          player_id: playerId,
          player_name: playerName,
          room_id: requestedRoom,
        }));
        return;
      } catch (error) {
        localStorage.removeItem('undercover_active_room_id');
        history.replaceState(null, '', window.location.pathname);
        showError($('undercover-home-error'), error);
      }
    }
    await refreshDirectory();
  }

  initialize();
  window.addEventListener('beforeunload', stopPolling);
})();
