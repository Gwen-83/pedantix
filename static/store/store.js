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
  const gameLinks = [...document.querySelectorAll('.store-game-card-available')];
  const gameSearch = document.getElementById('store-game-search');
  const gameCount = document.getElementById('store-game-count');
  const noGamesMessage = document.getElementById('store-no-games');
  const storeFilters = [...document.querySelectorAll('[data-store-filter]')];
  const chatList = document.getElementById('store-chat-list');
  const chatForm = document.getElementById('store-chat-form');
  const chatInput = document.getElementById('store-chat-input');
  const chatStatus = document.getElementById('store-chat-status');
  const invitationList = document.getElementById('store-invitation-list');
  const inviteOverlay = document.getElementById('store-invite-overlay');
  const inviteForm = document.getElementById('store-invite-form');
  const inviteRoomSelect = document.getElementById('store-invite-room');
  let lastChatId = 0;
  let pendingInviteUsername = null;
  let inviteRooms = [];
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
      undercover: '/games/undercover/',
      bitoguessr: '/games/bitoguessr/',
    }[launchTarget.searchParams.get('game')] || '/games/pedantix/';
    launchTarget.searchParams.delete('game');
  }
  const safeLaunchTarget = launchTarget
    && launchTarget.origin === window.location.origin
    && ['/games/pedantix/', '/games/motus/', '/games/cemantix/', '/games/chiffrantix/', '/games/battleship/', '/games/sudoku/', '/games/geoguessr/', '/games/undercover/', '/games/bitoguessr/', '/games/plongee/'].includes(launchTarget.pathname)
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
    accountButton.hidden = !!username;
    logoutButton.hidden = !username;
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

    gameLinks.forEach(link => {
      const searchableText = normalizeSearchText(link.textContent);
      const categories = (link.dataset.categories || '').split(/\s+/);
      const matchesSearch = !search || searchableText.includes(search);
      const matchesCategory = activeFilter === 'all' || categories.includes(activeFilter);
      const visible = matchesSearch && matchesCategory;
      link.hidden = !visible;
      if (visible) visibleCount += 1;
    });

    gameCount.textContent = visibleCount === gameLinks.length
      ? `${visibleCount} jeu${visibleCount === 1 ? '' : 'x'}`
      : `${visibleCount} / ${gameLinks.length} jeux`;
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
        activity.textContent = `${Number(stats.finished_games || 0).toLocaleString('fr-FR')} partie${stats.finished_games === 1 ? '' : 's'} terminée${stats.finished_games === 1 ? '' : 's'}`;
        link.querySelector('.store-game-info').append(activity);
      });
      status.textContent = 'Statistiques actualisées à partir des parties enregistrées.';
    } catch (error) {
      status.textContent = 'Les statistiques sont momentanément indisponibles.';
      console.error('Chargement des statistiques de la ludothèque impossible :', error);
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
      empty.textContent = 'Aucune invitation reçue.';
      invitationList.append(empty);
      return;
    }
    const gameNames = {
      pedantix: 'Pédantix', motus: 'Motus', cemantix: 'Cémantix',
      chiffrantix: 'Chiffrantix', sudoku: 'Sudoku', battleship: 'Bataille navale',
      geoguessr: 'GeoGuessr', undercover: 'Undercover',
      bitoguessr: 'Bitoguessr', plongee: 'Plongée',
    };
    invitations.forEach((invitation) => {
      const item = document.createElement('li');
      const text = document.createElement('span');
      text.textContent = `${invitation.sender_username} vous invite dans ${gameNames[invitation.game_id] || invitation.game_id} · salon ${invitation.room_id}`;
      const actions = document.createElement('div');
      actions.className = 'store-invitation-actions';
      const accept = document.createElement('button');
      accept.type = 'button';
      accept.className = 'store-invitation-accept';
      accept.textContent = 'Rejoindre';
      accept.addEventListener('click', () => handleInvitation(invitation, 'accepted'));
      const dismiss = document.createElement('button');
      dismiss.type = 'button';
      dismiss.textContent = 'Ignorer';
      dismiss.addEventListener('click', () => handleInvitation(invitation, 'dismissed'));
      actions.append(accept, dismiss);
      item.append(text, actions);
      invitationList.append(item);
    });
  }

  async function refreshInvitations() {
    if (!localStorage.getItem('pedantix_auth_token')) return;
    try {
      const data = await socialRequest('/api/social/invitations');
      renderInvitations(data.invitations || []);
    } catch (error) {
      invitationList.replaceChildren();
      const message = document.createElement('li');
      message.className = 'store-social-empty';
      message.textContent = `Impossible de charger les invitations : ${error.message}`;
      invitationList.append(message);
    }
  }

  function gameUrl(gameId, roomId) {
    return `/games/${encodeURIComponent(gameId)}/?room=${encodeURIComponent(roomId)}`;
  }

  async function handleInvitation(invitation, action) {
    try {
      await socialRequest(`/api/social/invitations/${invitation.id}`, {
        method: 'POST',
        body: JSON.stringify({ action }),
      });
      if (action === 'accepted') {
        window.location.href = gameUrl(invitation.game_id, invitation.room_id);
        return;
      }
      await refreshInvitations();
    } catch (error) {
      chatStatus.textContent = `Impossible de traiter l’invitation : ${error.message}`;
    }
  }

  async function openInviteDialog(username) {
    if (!localStorage.getItem('pedantix_auth_token')) {
      pendingInviteUsername = username;
      openDialog(false);
      return;
    }
    document.getElementById('store-invite-description').textContent =
      `Choisissez le salon à partager avec ${username}.`;
    document.getElementById('store-invite-status').textContent = 'Chargement de vos salons…';
    inviteRoomSelect.replaceChildren();
    document.getElementById('store-invite-submit').disabled = true;
    inviteOverlay.hidden = false;
    try {
      const data = await socialRequest('/api/social/rooms');
      inviteRooms = data.rooms || [];
      inviteRoomSelect.replaceChildren(...inviteRooms.map((room) => {
        const option = document.createElement('option');
        option.value = `${room.game_id}:${room.room_id}`;
        option.textContent = `${room.game_name} · Salon ${room.room_id}${room.status === 'playing' ? ' · en cours' : ' · en attente'}`;
        return option;
      }));
      document.getElementById('store-invite-status').textContent = inviteRooms.length
        ? ''
        : 'Vous ne participez à aucun salon actif. Créez ou rejoignez un salon dans un jeu, puis revenez inviter ce joueur.';
      document.getElementById('store-invite-submit').disabled = !inviteRooms.length;
      inviteForm.dataset.recipient = username;
      document.getElementById('store-invite-close').focus();
    } catch (error) {
      document.getElementById('store-invite-status').textContent =
        `Impossible de charger vos salons : ${error.message}`;
    }
  }

  async function sendInvitation(event) {
    event.preventDefault();
    const [gameId, ...roomParts] = inviteRoomSelect.value.split(':');
    const roomId = roomParts.join(':');
    if (!gameId || !roomId) return;
    const submit = document.getElementById('store-invite-submit');
    submit.disabled = true;
    document.getElementById('store-invite-status').textContent = 'Envoi…';
    try {
      await socialRequest('/api/social/invitations', {
        method: 'POST',
        body: JSON.stringify({
          recipient_username: inviteForm.dataset.recipient,
          game_id: gameId,
          room_id: roomId,
        }),
      });
      document.getElementById('store-invite-status').textContent = 'Invitation envoyée.';
      window.setTimeout(() => { inviteOverlay.hidden = true; }, 900);
    } catch (error) {
      document.getElementById('store-invite-status').textContent =
        `Impossible d’envoyer l’invitation : ${error.message}`;
      submit.disabled = !inviteRooms.length;
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
  document.addEventListener('store:invite-player', (event) => {
    openInviteDialog(event.detail.username);
  });
  document.getElementById('store-invite-close').addEventListener('click', () => {
    inviteOverlay.hidden = true;
  });
  inviteOverlay.addEventListener('click', (event) => {
    if (event.target === inviteOverlay) inviteOverlay.hidden = true;
  });
  inviteForm.addEventListener('submit', sendInvitation);
  refreshChat(true);
  window.setInterval(() => refreshChat(), 3000);
  window.setInterval(refreshInvitations, 5000);

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
  if (params.get('login') === '1') openDialog(!!safeLaunchTarget);
})();
