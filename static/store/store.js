(() => {
  if (!document.documentElement.classList.contains('store-mode')) return;

  const overlay = document.getElementById('store-auth-overlay');
  const usernameForm = document.getElementById('store-username-form');
  const passwordForm = document.getElementById('store-password-form');
  const usernameInput = document.getElementById('store-username');
  const passwordInput = document.getElementById('store-password');
  const passwordLabel = document.getElementById('store-password-label');
  const passwordSubmit = document.getElementById('store-password-submit');
  const authError = document.getElementById('store-auth-error');
  const accountName = document.getElementById('store-account-name');
  const accountButton = document.getElementById('store-account-button');
  const logoutButton = document.getElementById('store-logout-button');
  const adminUsageLink = document.getElementById('store-admin-usage-link');
  const gameLinks = [...document.querySelectorAll('.store-game-card-available')];
  const gameCards = [...document.querySelectorAll('.store-game-card-available, .store-game-card-soon')];
  const gameSearch = document.getElementById('store-game-search');
  const gameCount = document.getElementById('store-game-count');
  const noGamesMessage = document.getElementById('store-no-games');
  const storeFilters = [...document.querySelectorAll('[data-store-filter]')];
  const chatList = document.getElementById('store-chat-list');
  const chatForm = document.getElementById('store-chat-form');
  const chatInput = document.getElementById('store-chat-input');
  const chatStatus = document.getElementById('store-chat-status');
  const invitationList = document.getElementById('store-invitation-list');
  const activeRoomList = document.getElementById('store-active-rooms');
  const inviteOverlay = document.getElementById('store-invite-overlay');
  const inviteForm = document.getElementById('store-invite-form');
  const inviteGameSelect = document.getElementById('store-invite-game');
  let lastChatId = 0;
  let pendingInviteUsername = null;
  let pendingOutgoingInvitationId = null;
  let outgoingInvitationTimer = null;
  let outgoingInvitationCheckInFlight = false;
  let invitationRequestInFlight = false;
  let roomsRequestInFlight = false;
  const params = new URLSearchParams(window.location.search);
  const requestedNext = params.get('next');
  const launchTarget = requestedNext ? new URL(requestedNext, window.location.origin) : null;
  const legacyLaunchTarget = launchTarget
    && launchTarget.origin === window.location.origin
    && launchTarget.pathname === '/'
    && (launchTarget.searchParams.get('game') === 'pedantix'
      || launchTarget.searchParams.get('game') === 'motus'
      || launchTarget.searchParams.get('game') === 'cemantix'
      || launchTarget.searchParams.get('game') === 'chiffrantix'
      || launchTarget.searchParams.get('game') === 'battleship'
      || launchTarget.searchParams.get('game') === 'sudoku'
      || launchTarget.searchParams.get('game') === 'geoguessr'
      || launchTarget.searchParams.get('game') === 'plongee'
      || launchTarget.searchParams.get('game') === 'memories'
      || launchTarget.searchParams.get('game') === 'scribbl'
      || launchTarget.searchParams.get('game') === 'undercover'
      || launchTarget.searchParams.has('assist')
      || launchTarget.searchParams.has('room')
      || launchTarget.searchParams.get('mode') === 'solo'
      || launchTarget.searchParams.get('mode') === 'multi');
  if (legacyLaunchTarget) {
    launchTarget.pathname = {
      pedantix: '/games/pedantix/',
      motus: '/games/motus/',
      cemantix: '/games/cemantix/',
      chiffrantix: '/games/chiffrantix/',
      battleship: '/games/battleship/',
      sudoku: '/games/sudoku/',
      geoguessr: '/games/geoguessr/',
      plongee: '/games/plongee/',
      memories: '/games/memories/',
      scribbl: '/games/scribbl/',
      undercover: '/games/undercover/',
      bitoguessr: '/games/bitoguessr/',
    }[launchTarget.searchParams.get('game')] || '/games/pedantix/';
    launchTarget.searchParams.delete('game');
  }
  const safeLaunchTarget = launchTarget
    && launchTarget.origin === window.location.origin
    && ['/games/pedantix/', '/games/motus/', '/games/cemantix/', '/games/chiffrantix/', '/games/battleship/', '/games/sudoku/', '/games/geoguessr/', '/games/undercover/', '/games/bitoguessr/', '/games/plongee/', '/games/memories/', '/games/scribbl/'].includes(launchTarget.pathname)
    ? launchTarget
    : null;
  let pendingLaunch = params.get('login') === '1' && !!safeLaunchTarget;
  let pendingUsername = '';
  let authAction = 'login';

  function apiUrl(endpoint) {
    const base = window.PEDANTIX_CONFIG?.BACKEND_URL?.replace(/\/+$/, '') || '';
    return `${base}${endpoint}`;
  }

  function showError(message) {
    authError.textContent = message;
    authError.hidden = false;
  }

  function resetAuthForm() {
    pendingUsername = '';
    authAction = 'login';
    usernameForm.hidden = false;
    passwordForm.hidden = true;
    authError.hidden = true;
    authError.textContent = '';
    document.getElementById('store-auth-subtitle').textContent = 'Connectez-vous ou créez un compte pour jouer.';
    usernameInput.value = '';
    passwordInput.value = '';
  }

  function closeDialog() {
    overlay.hidden = true;
    pendingLaunch = false;
    resetAuthForm();
  }

  function openDialog(launchAfterAuth = false) {
    pendingLaunch = launchAfterAuth;
    resetAuthForm();
    overlay.hidden = false;
    usernameInput.focus();
  }

  function syncAccount() {
    const username = localStorage.getItem('pedantix_auth_user');
    const authenticated = !!username && !!localStorage.getItem('pedantix_auth_token');
    accountName.hidden = !username;
    accountName.textContent = username ? `Bonjour, ${username}` : '';
    accountButton.hidden = authenticated;
    logoutButton.hidden = !authenticated;
    adminUsageLink.hidden = !authenticated || username.trim().toLocaleLowerCase() !== 'gwen';
    chatForm.hidden = !authenticated;
    document.getElementById('store-chat-login').hidden = authenticated;
    if (authenticated) {
      refreshInvitations();
      if (pendingInviteUsername) {
        const target = pendingInviteUsername;
        pendingInviteUsername = null;
        openInviteDialog(target);
      }
    } else {
      invitationList.replaceChildren();
      const empty = document.createElement('li');
      empty.className = 'store-social-empty';
      empty.textContent = 'Connectez-vous pour voir vos invitations.';
      invitationList.append(empty);
    }
  }

  function normalizeSearchText(value) {
    return value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('fr');
  }

  function filterGames() {
    const search = normalizeSearchText(gameSearch.value.trim());
    const activeFilter = storeFilters.find(button => button.getAttribute('aria-pressed') === 'true')
      ?.dataset.storeFilter || 'all';
    let visibleCount = 0;

    gameCards.forEach(card => {
      const searchableText = normalizeSearchText(card.textContent);
      const categories = (card.dataset.categories || '').split(/\s+/);
      const matchesSearch = !search || searchableText.includes(search);
      const matchesCategory = activeFilter === 'all' || categories.includes(activeFilter);
      const visible = matchesSearch && matchesCategory;
      card.hidden = !visible;
      if (visible) visibleCount += 1;
    });

    gameCount.textContent = visibleCount === gameCards.length
      ? `${visibleCount} jeu${visibleCount === 1 ? '' : 'x'}`
      : `${visibleCount} / ${gameCards.length} jeux`;
    noGamesMessage.hidden = visibleCount > 0;
  }

  async function loadStoreStats() {
    const status = document.getElementById('store-stats-status');
    try {
      const response = await fetch(apiUrl('/api/stats/overview'));
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Statistiques indisponibles.');

      document.getElementById('store-stat-games').textContent = String(gameLinks.length);
      document.getElementById('store-stat-started').textContent = Number(data.started_games || 0).toLocaleString('fr-FR');
      document.getElementById('store-stat-finished').textContent = Number(data.finished_games || 0).toLocaleString('fr-FR');
      const gamesById = new Map((data.games || []).map(game => [game.game_id, game]));
      gameLinks.forEach(link => {
        const gameId = new URL(link.href).pathname.split('/').filter(Boolean).at(-1);
        const stats = gamesById.get(gameId);
        if (!stats) return;

        const activity = document.createElement('span');
        activity.className = 'store-game-activity';
        const finished = Number(stats.finished_games || 0);
        const started = Number(stats.started_games || 0);
        const playerHours = Number(stats.player_hours || 0).toLocaleString('fr-FR', { maximumFractionDigits: 2 });
        activity.textContent = `${finished.toLocaleString('fr-FR')} / ${started.toLocaleString('fr-FR')} sessions terminées · ${playerHours} h joueur`;
        link.querySelector('.store-game-info').append(activity);
      });
      status.textContent = `${Number(data.unfinished_games || 0).toLocaleString('fr-FR')} sessions lancées sans fin enregistrée. Le temps cumulé additionne les durées de jeu de chaque joueur.`;
    } catch (error) {
      status.textContent = 'Les statistiques sont momentanément indisponibles.';
      console.error('Chargement des statistiques de la ludothèque impossible :', error);
    }
  }

  async function loadFeaturedLeaderboards() {
    const container = document.getElementById('store-featured-leaderboards');
    try {
      const response = await fetch(apiUrl('/api/leaderboards/featured'));
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Classements indisponibles.');
      container.replaceChildren();
      data.games.forEach((game) => {
        const section = document.createElement('section');
        section.className = 'store-featured-game';
        const title = document.createElement('a');
        title.className = 'store-featured-game-title';
        title.href = game.href;
        title.textContent = game.title;
        section.append(title);
        game.leaders.forEach(({ difficulty, leader }) => {
          const row = document.createElement('div');
          row.className = 'store-featured-leader';
          const label = document.createElement('span');
          const difficultyLabels = {
            classique: 'Top 1',
            '4x4': 'Grille 4 × 4',
            '6x6': 'Grille 6 × 6',
            facile: 'Facile',
            moyen: 'Moyen',
            difficile: 'Difficile',
          };
          label.textContent = difficultyLabels[difficulty] || 'Tous niveaux';
          row.append(label);
          const result = document.createElement('span');
          result.className = 'store-featured-leader-result';
          if (leader) {
            const name = document.createElement('strong');
            name.textContent = leader.player_name;
            result.append(name);
            const detail = document.createElement('span');
            detail.className = 'store-featured-leader-detail';
            detail.textContent = leader.detail;
            result.append(detail);
          } else {
            const empty = document.createElement('span');
            empty.className = 'store-featured-leader-empty';
            empty.textContent = 'Aucun score';
            result.append(empty);
          }
          row.append(result);
          section.append(row);
        });
        container.append(section);
      });
    } catch (error) {
      container.replaceChildren();
      const failure = document.createElement('p');
      failure.className = 'store-social-empty';
      failure.textContent = 'Les meilleurs scores sont momentanément indisponibles.';
      container.append(failure);
      console.error('Chargement des meilleurs scores impossible :', error);
    }
  }

  function socialHeaders(json = false) {
    const headers = {};
    if (json) headers['Content-Type'] = 'application/json';
    const username = localStorage.getItem('pedantix_auth_user');
    const token = localStorage.getItem('pedantix_auth_token');
    if (username && token) {
      headers['X-Auth-User'] = username;
      headers['X-Auth-Token'] = token;
    }
    return headers;
  }

  async function socialRequest(path, options = {}) {
    const response = await fetch(apiUrl(path), {
      ...options,
      headers: {
        ...socialHeaders(!!options.body),
        ...options.headers,
      },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || 'La demande a échoué.');
    return data;
  }

  function addChatMessage(message) {
    if (!message || Number(message.id) <= lastChatId) return;
    chatList.querySelector('.store-social-empty')?.remove();
    const shouldScroll = chatList.scrollHeight - chatList.scrollTop - chatList.clientHeight < 40;
    const item = document.createElement('li');
    const heading = document.createElement('div');
    heading.className = 'store-chat-message-heading';
    const username = document.createElement('strong');
    username.textContent = message.username;
    const time = document.createElement('time');
    const createdAt = new Date(message.created_at);
    time.dateTime = Number.isNaN(createdAt.getTime()) ? '' : createdAt.toISOString();
    time.textContent = Number.isNaN(createdAt.getTime())
      ? ''
      : createdAt.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
    const text = document.createElement('span');
    text.className = 'store-chat-message-text';
    text.textContent = message.message;
    heading.append(username, time);
    item.append(heading, text);
    chatList.append(item);
    lastChatId = Number(message.id);
    while (chatList.children.length > 100) chatList.firstElementChild.remove();
    if (shouldScroll) chatList.scrollTop = chatList.scrollHeight;
  }

  async function refreshChat(initial = false) {
    try {
      const query = initial || lastChatId === 0 ? '' : `?after_id=${lastChatId}`;
      const data = await socialRequest(`/api/social/chat${query}`);
      if (initial || lastChatId === 0) chatList.replaceChildren();
      (data.messages || []).forEach(addChatMessage);
      if (!chatList.children.length) {
        const empty = document.createElement('li');
        empty.className = 'store-social-empty';
        empty.textContent = 'Aucun message pour le moment. Lancez la conversation !';
        chatList.append(empty);
      }
      chatStatus.textContent = '';
    } catch (error) {
      chatStatus.textContent = `Chat indisponible : ${error.message}`;
    }
  }

  function renderInvitations(invitations) {
    invitationList.replaceChildren();
    if (!invitations.length) {
      const empty = document.createElement('li');
      empty.className = 'store-social-empty';
      empty.textContent = 'Aucune invitation envoyée.';
      invitationList.append(empty);
      return;
    }
    const gameNames = {
      pedantix: 'Pédantix', motus: 'Motus', cemantix: 'Cémantix',
      chiffrantix: 'Chiffrantix', sudoku: 'Sudoku', battleship: 'Bataille navale',
      geoguessr: 'GeoGuessr', undercover: 'Undercover',
      bitoguessr: 'Bitoguessr', plongee: 'Plongée', memories: 'Memory',
      scribbl: 'Scribbl',
    };
    invitations.forEach((invitation) => {
      const item = document.createElement('li');
      const text = document.createElement('span');
      const statuses = {
        pending: 'En attente de réponse · valable 5 minutes',
        accepted: `Acceptée · salon ${invitation.room_id}`,
        declined: 'Refusée',
        expired: 'Expirée',
        cancelled: 'Annulée',
      };
      text.textContent = `Invitation à ${invitation.recipient_username} · ${gameNames[invitation.game_id] || invitation.game_id} · ${statuses[invitation.status] || invitation.status}`;
      item.append(text);
      invitationList.append(item);
    });
  }

  async function refreshInvitations() {
    if (!localStorage.getItem('pedantix_auth_token')) return;
    try {
      const data = await socialRequest('/api/social/invitations/sent');
      renderInvitations(data.invitations || []);
    } catch (error) {
      invitationList.replaceChildren();
      const message = document.createElement('li');
      message.className = 'store-social-empty';
      message.textContent = `Impossible de charger les invitations : ${error.message}`;
      invitationList.append(message);
    }
  }

  async function refreshActiveRooms() {
    if (roomsRequestInFlight) return;
    roomsRequestInFlight = true;
    try {
      const data = await socialRequest('/api/social/rooms');
      const rooms = data.rooms || [];
      activeRoomList.replaceChildren();
      if (!rooms.length) {
        const empty = document.createElement('li');
        empty.className = 'store-social-empty';
        empty.textContent = 'Aucun salon public disponible pour le moment.';
        activeRoomList.append(empty);
        return;
      }

      rooms.forEach((room) => {
        const item = document.createElement('li');
        item.className = 'store-active-room';
        const details = document.createElement('div');
        details.className = 'store-active-room-details';
        const title = document.createElement('strong');
        title.textContent = `${room.game_name} · ${room.room_id}`;
        const metadata = document.createElement('small');
        const roomState = room.status === 'playing' ? 'Partie en cours' : 'En attente';
        const headcount = `${room.player_count} joueur${room.player_count === 1 ? '' : 's'}`;
        const mode = room.game_mode ? ` · ${room.game_mode}` : '';
        metadata.textContent = `${roomState}${mode} · ${headcount}${room.host_name ? ` · hôte : ${room.host_name}` : ''}`;
        details.append(title, metadata);

        const join = document.createElement('button');
        join.type = 'button';
        join.className = 'store-active-room-join';
        join.textContent = 'Rejoindre';
        join.setAttribute(
          'aria-label',
          `Rejoindre le salon ${room.room_id} de ${room.game_name}`,
        );
        join.addEventListener('click', () => {
          join.disabled = true;
          join.textContent = 'Ouverture…';
          window.location.href =
            `/games/${encodeURIComponent(room.game_id)}/?room=${encodeURIComponent(room.room_id)}`;
        });
        item.append(details, join);
        activeRoomList.append(item);
      });
    } catch (error) {
      activeRoomList.replaceChildren();
      const message = document.createElement('li');
      message.className = 'store-social-empty';
      message.textContent = `Impossible de charger les salons : ${error.message}`;
      activeRoomList.append(message);
    } finally {
      roomsRequestInFlight = false;
    }
  }

  async function openInviteDialog(username) {
    if (!localStorage.getItem('pedantix_auth_token')) {
      pendingInviteUsername = username;
      openDialog(false);
      return;
    }
    document.getElementById('store-invite-description').textContent =
      `Choisissez un jeu. Un salon privé avec vous deux sera créé si ${username} accepte. L’invitation expire dans 5 minutes.`;
    document.getElementById('store-invite-status').textContent = '';
    document.getElementById('store-invite-submit').disabled = false;
    inviteForm.hidden = false;
    inviteOverlay.hidden = false;
    inviteForm.dataset.recipient = username;
    document.getElementById('store-invite-close').focus();
  }

  function stopOutgoingInvitationPolling() {
    if (outgoingInvitationTimer) window.clearInterval(outgoingInvitationTimer);
    outgoingInvitationTimer = null;
  }

  function navigateToAcceptedInvitation(invitation) {
    const playerStorageKeys = {
      motus: 'motus_player_id',
      cemantix: 'cemantix_player_id',
      chiffrantix: 'chiffrantix_player_id',
      sudoku: 'sudoku_player_id',
      battleship: 'battleship_player_id',
      geoguessr: 'geoguessr_player_id',
      plongee: 'plongee_player_id',
      memories: 'memories_player_id',
      scribbl: 'scribbl_player_id',
    };
    const storageKey = playerStorageKeys[invitation.game_id];
    if (!storageKey || !invitation.room_id || !invitation.sender_player_id) {
      document.getElementById('store-invite-status').textContent =
        'L’invitation a été acceptée, mais le salon ne peut pas être ouvert.';
      return;
    }
    localStorage.setItem(storageKey, invitation.sender_player_id);
    window.location.href =
      `/games/${encodeURIComponent(invitation.game_id)}/?room=${encodeURIComponent(invitation.room_id)}`;
  }

  async function refreshOutgoingInvitation() {
    if (pendingOutgoingInvitationId === null || outgoingInvitationCheckInFlight) return null;
    outgoingInvitationCheckInFlight = true;
    try {
      const data = await socialRequest('/api/social/invitations/sent');
      const invitation = (data.invitations || []).find(
        (item) => Number(item.id) === pendingOutgoingInvitationId,
      );
      if (!invitation) return null;
      if (invitation.status === 'accepted') {
        stopOutgoingInvitationPolling();
        pendingOutgoingInvitationId = null;
        navigateToAcceptedInvitation(invitation);
        return 'accepted';
      }
      if (['declined', 'expired', 'cancelled'].includes(invitation.status)) {
        stopOutgoingInvitationPolling();
        pendingOutgoingInvitationId = null;
        const messages = {
          declined: 'Invitation refusée.',
          expired: 'Invitation expirée sans réponse.',
          cancelled: 'Invitation annulée.',
        };
        document.getElementById('store-invite-status').textContent =
          messages[invitation.status];
        document.getElementById('store-invite-close').focus();
        return invitation.status;
      }
      return invitation.status;
    } catch (error) {
      document.getElementById('store-invite-status').textContent =
        `Impossible de vérifier la réponse : ${error.message}`;
      return null;
    } finally {
      outgoingInvitationCheckInFlight = false;
    }
  }

  async function closeInviteDialog() {
    if (invitationRequestInFlight) return;
    if (pendingOutgoingInvitationId !== null) {
      const invitationId = pendingOutgoingInvitationId;
      const close = document.getElementById('store-invite-close');
      close.disabled = true;
      document.getElementById('store-invite-status').textContent =
        'Annulation de l’invitation…';
      try {
        await socialRequest(`/api/social/invitations/${invitationId}`, {
          method: 'POST',
          body: JSON.stringify({ action: 'cancelled' }),
        });
        stopOutgoingInvitationPolling();
        pendingOutgoingInvitationId = null;
        refreshInvitations();
        inviteOverlay.hidden = true;
      } catch (error) {
        document.getElementById('store-invite-status').textContent =
          `Impossible d’annuler l’invitation : ${error.message}`;
        const status = await refreshOutgoingInvitation();
        if (['declined', 'expired', 'cancelled'].includes(status)) {
          inviteOverlay.hidden = true;
        }
      } finally {
        close.disabled = false;
      }
      return;
    }
    inviteOverlay.hidden = true;
  }

  async function sendInvitation(event) {
    event.preventDefault();
    const gameId = inviteGameSelect.value;
    const submit = document.getElementById('store-invite-submit');
    const close = document.getElementById('store-invite-close');
    submit.disabled = true;
    close.disabled = true;
    invitationRequestInFlight = true;
    document.getElementById('store-invite-status').textContent = 'Envoi…';
    try {
      const invitation = await socialRequest('/api/social/invitations', {
        method: 'POST',
        body: JSON.stringify({
          recipient_username: inviteForm.dataset.recipient,
          game_id: gameId,
        }),
      });
      pendingOutgoingInvitationId = Number(invitation.id);
      inviteForm.hidden = true;
      document.getElementById('store-invite-description').textContent =
        `Invitation envoyée à ${invitation.recipient_username} pour jouer à ${inviteGameSelect.selectedOptions[0].textContent}.`;
      document.getElementById('store-invite-status').textContent =
        'En attente de son acceptation… Fermer cette fenêtre annulera l’invitation.';
      refreshInvitations();
      stopOutgoingInvitationPolling();
      outgoingInvitationTimer = window.setInterval(refreshOutgoingInvitation, 2000);
      refreshOutgoingInvitation();
    } catch (error) {
      document.getElementById('store-invite-status').textContent =
        `Impossible d’envoyer l’invitation : ${error.message}`;
      submit.disabled = false;
    } finally {
      invitationRequestInFlight = false;
      close.disabled = false;
    }
  }

  gameSearch.addEventListener('input', filterGames);
  chatForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const message = chatInput.value.trim();
    if (!message) return;
    const submit = chatForm.querySelector('button[type="submit"]');
    submit.disabled = true;
    chatStatus.textContent = '';
    try {
      const created = await socialRequest('/api/social/chat', {
        method: 'POST',
        body: JSON.stringify({ message }),
      });
      addChatMessage(created);
      chatInput.value = '';
    } catch (error) {
      chatStatus.textContent = `Message non envoyé : ${error.message}`;
    } finally {
      submit.disabled = false;
      chatInput.focus();
    }
  });
  document.getElementById('store-chat-login').addEventListener('click', () => openDialog(false));
  document.getElementById('store-rooms-refresh').addEventListener('click', refreshActiveRooms);
  document.addEventListener('store:invite-player', (event) => {
    openInviteDialog(event.detail.username);
  });
  document.getElementById('store-invite-close').addEventListener('click', closeInviteDialog);
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !inviteOverlay.hidden) closeInviteDialog();
  });
  inviteOverlay.addEventListener('click', (event) => {
    if (event.target === inviteOverlay) closeInviteDialog();
  });
  inviteForm.addEventListener('submit', sendInvitation);
  refreshChat(true);
  refreshActiveRooms();
  window.setInterval(() => refreshChat(), 3000);
  window.setInterval(refreshInvitations, 5000);
  window.setInterval(refreshActiveRooms, 10000);

  storeFilters.forEach(button => {
    button.addEventListener('click', () => {
      storeFilters.forEach(filter => {
        const active = filter === button;
        filter.classList.toggle('is-active', active);
        filter.setAttribute('aria-pressed', String(active));
      });
      filterGames();
    });
  });

  async function submitUsername(event) {
    event.preventDefault();
    const username = usernameInput.value.trim();
    if (username.length < 2) {
      showError("Le nom d'utilisateur doit contenir au moins 2 caractères.");
      return;
    }

    const submit = usernameForm.querySelector('button[type="submit"]');
    submit.disabled = true;
    submit.textContent = 'Vérification…';
    authError.hidden = true;
    try {
      const response = await fetch(apiUrl('/api/auth/check-username'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Impossible de vérifier ce nom d’utilisateur.");

      pendingUsername = data.username || username;
      authAction = data.exists ? 'login' : 'register';
      usernameForm.hidden = true;
      passwordForm.hidden = false;
      passwordLabel.textContent = data.exists ? 'Mot de passe' : 'Choisissez un mot de passe';
      passwordInput.autocomplete = data.exists ? 'current-password' : 'new-password';
      passwordSubmit.textContent = data.exists ? 'Se connecter' : 'Créer mon compte';
      document.getElementById('store-auth-subtitle').textContent = data.exists
        ? `Bon retour, ${pendingUsername}. Saisissez votre mot de passe.`
        : `Le nom ${pendingUsername} est disponible. Créez votre compte.`;
      passwordInput.focus();
    } catch (error) {
      showError(error.message || 'Impossible de joindre le serveur. Vérifiez votre connexion.');
    } finally {
      submit.disabled = false;
      submit.textContent = 'Continuer';
    }
  }

  async function submitPassword(event) {
    event.preventDefault();
    const password = passwordInput.value;
    if (password.length < 3) {
      showError('Le mot de passe doit contenir au moins 3 caractères.');
      return;
    }

    passwordSubmit.disabled = true;
    passwordSubmit.textContent = authAction === 'login' ? 'Connexion…' : 'Création…';
    authError.hidden = true;
    try {
      const endpoint = authAction === 'login' ? '/api/auth/login' : '/api/auth/register';
      const response = await fetch(apiUrl(endpoint), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: pendingUsername, password })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || data.error || 'La connexion a échoué.');

      localStorage.setItem('pedantix_auth_user', data.username);
      localStorage.setItem('pedantix_auth_token', data.token);
      localStorage.setItem('pedantix_player_name', data.username);
      syncAccount();
      const shouldLaunch = pendingLaunch;
      closeDialog();
      if (shouldLaunch) window.location.href = safeLaunchTarget?.href || gameLinks[0].href;
    } catch (error) {
      showError(error.message || 'Erreur de communication avec le serveur.');
    } finally {
      passwordSubmit.disabled = false;
      passwordSubmit.textContent = authAction === 'login' ? 'Se connecter' : 'Créer mon compte';
    }
  }

  accountButton.addEventListener('click', () => openDialog(false));
  logoutButton.addEventListener('click', () => {
    localStorage.removeItem('pedantix_auth_user');
    localStorage.removeItem('pedantix_auth_token');
    localStorage.removeItem('pedantix_player_name');
    syncAccount();
  });
  document.getElementById('store-auth-close').addEventListener('click', closeDialog);
  document.getElementById('store-auth-back').addEventListener('click', () => {
    resetAuthForm();
    usernameInput.focus();
  });
  overlay.addEventListener('click', event => {
    if (event.target === overlay) closeDialog();
  });
  usernameForm.addEventListener('submit', submitUsername);
  passwordForm.addEventListener('submit', submitPassword);
  gameLinks.forEach(link => {
    link.addEventListener('click', event => {
      if (localStorage.getItem('pedantix_auth_user')) return;
      event.preventDefault();
      openDialog(true);
    });
  });

  syncAccount();
  filterGames();
  loadStoreStats();
  loadFeaturedLeaderboards();
  if (params.get('login') === '1') openDialog(!!safeLaunchTarget);
})();
