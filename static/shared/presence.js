(() => {
  const apiBase = window.PEDANTIX_CONFIG?.BACKEND_URL?.replace(/\/+$/, '') || '';
  const gameLabels = {
    pedantix: 'Pédantix',
    motus: 'Motus',
    cemantix: 'Cémantix',
    chiffrantix: 'Chiffrantix',
    sudoku: 'Sudoku',
    battleship: 'Bataille navale',
    geoguessr: 'GeoGuessr',
    undercover: 'Undercover',
    bitoguessr: 'Bitoguessr',
    plongee: 'Plongée',
    memories: 'Memory',
    scribbl: 'Scribbl',
    store: 'La ludothèque',
  };
  const gameId = document.documentElement.dataset.presenceGame
    || window.location.pathname.split('/')[2]
    || 'store';
  let sessionId = sessionStorage.getItem('pedantix_presence_id');
  let invitationModal = null;
  let invitationTimer = null;
  let activeInvitationId = null;
  let invitationPreviousFocus = null;
  let receivedInvitationCheckInFlight = false;
  const chatNotificationCursorKey = 'pedantix_chat_notification_cursor';
  let chatNotificationCursor = Number(localStorage.getItem(chatNotificationCursorKey)) || 0;
  let chatNotificationInitialized = chatNotificationCursor > 0;
  let chatNotificationRequestInFlight = false;
  let chatNotificationTimer = null;
  let chatNotificationStack = null;
  let chatNotificationPermissionButton = null;

  const invitationGames = {
    motus: 'Motus',
    cemantix: 'Cémantix',
    chiffrantix: 'Chiffrantix',
    sudoku: 'Sudoku',
    battleship: 'Bataille navale',
    geoguessr: 'GeoGuessr',
    plongee: 'Plongée',
    memories: 'Memory',
    scribbl: 'Scribbl',
  };
  const gamePlayerStorageKeys = {
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
    const response = await fetch(`${apiBase}${path}`, {
      ...options,
      headers: {
        ...socialHeaders(!!options.body),
        ...options.headers,
      },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(data.detail || 'La demande a échoué.');
      error.status = response.status;
      throw error;
    }
    return data;
  }

  function ensureChatNotificationUi() {
    if (chatNotificationStack) return;
    const styles = document.createElement('style');
    styles.textContent = `
      .shared-chat-notification-stack {
        position: fixed; z-index: 15000; right: 16px; bottom: 16px;
        display: grid; width: min(390px, calc(100vw - 32px)); gap: 9px;
        font: 500 .9rem/1.45 system-ui,sans-serif;
      }
      .shared-chat-notification {
        display: flex; align-items: flex-start; gap: 10px; padding: 13px 14px;
        border: 1px solid rgba(148,163,184,.42); border-radius: 13px;
        background: #17212b; color: #f8fafc; box-shadow: 0 10px 32px rgba(0,0,0,.32);
      }
      .shared-chat-notification a { flex: 1; color: inherit; text-decoration: none; }
      .shared-chat-notification a:hover { text-decoration: underline; }
      .shared-chat-notification strong, .shared-chat-notification span { display: block; }
      .shared-chat-notification span { margin-top: 3px; color: #d1d5db; overflow-wrap: anywhere; }
      .shared-chat-notification button, .shared-chat-notification-permission {
        border: 1px solid rgba(255,255,255,.25); border-radius: 9px;
        background: rgba(255,255,255,.1); color: #fff; font: inherit; cursor: pointer;
      }
      .shared-chat-notification button { padding: 2px 8px; }
      .shared-chat-notification-permission {
        position: fixed; z-index: 14999; left: 16px; bottom: 16px;
        padding: 9px 12px; background: #17212b; box-shadow: 0 6px 22px rgba(0,0,0,.25);
      }
      .shared-chat-notification-permission[hidden] { display: none; }
      @media (max-width: 520px) {
        .shared-chat-notification-stack { right: 10px; bottom: 10px; width: calc(100vw - 20px); }
        .shared-chat-notification-permission { left: 10px; bottom: 10px; }
      }`;
    document.head.append(styles);
    chatNotificationStack = document.createElement('div');
    chatNotificationStack.className = 'shared-chat-notification-stack';
    chatNotificationStack.setAttribute('role', 'region');
    chatNotificationStack.setAttribute('aria-label', 'Nouveaux messages du chat général');
    chatNotificationStack.setAttribute('aria-live', 'polite');
    chatNotificationStack.setAttribute('aria-relevant', 'additions');
    document.body.append(chatNotificationStack);

    if ('Notification' in window) {
      chatNotificationPermissionButton = document.createElement('button');
      chatNotificationPermissionButton.type = 'button';
      chatNotificationPermissionButton.className = 'shared-chat-notification-permission';
      chatNotificationPermissionButton.textContent = 'Activer les notifications du chat';
      chatNotificationPermissionButton.addEventListener('click', async () => {
        chatNotificationPermissionButton.disabled = true;
        try {
          await window.Notification.requestPermission();
        } catch (error) {
          console.warn('Impossible d’activer les notifications du chat.', error);
        } finally {
          updateChatNotificationPermissionButton();
        }
      });
      document.body.append(chatNotificationPermissionButton);
      updateChatNotificationPermissionButton();
    }
  }

  function updateChatNotificationPermissionButton() {
    if (!chatNotificationPermissionButton || !('Notification' in window)) return;
    const permission = window.Notification.permission;
    chatNotificationPermissionButton.hidden = permission !== 'default';
    chatNotificationPermissionButton.disabled = false;
    chatNotificationPermissionButton.title = permission === 'denied'
      ? 'Les notifications sont bloquées dans les paramètres du navigateur.'
      : '';
  }

  function showGeneralChatNotification(message) {
    ensureChatNotificationUi();
    const toast = document.createElement('div');
    toast.className = 'shared-chat-notification';
    toast.setAttribute('role', 'status');
    const link = document.createElement('a');
    link.href = '/#store-chat-title';
    const sender = document.createElement('strong');
    sender.textContent = `${message.username} · Chat général`;
    const text = document.createElement('span');
    text.textContent = message.message;
    link.append(sender, text);
    const close = document.createElement('button');
    close.type = 'button';
    close.setAttribute('aria-label', 'Fermer la notification');
    close.textContent = '×';
    close.addEventListener('click', () => toast.remove());
    toast.append(link, close);
    chatNotificationStack.append(toast);
    while (chatNotificationStack.children.length > 3) {
      chatNotificationStack.firstElementChild.remove();
    }
    window.setTimeout(() => toast.remove(), 10_000);

    if (
      'Notification' in window
      && window.Notification.permission === 'granted'
      && (document.visibilityState !== 'visible' || !document.hasFocus())
    ) {
      try {
        const notification = new window.Notification(
          `${message.username} · Chat général`,
          { body: message.message, tag: `pedantix-chat-${message.id}` },
        );
        notification.onclick = () => window.focus();
      } catch (error) {
        console.warn('Impossible d’afficher la notification système du chat.', error);
      }
    }
  }

  async function refreshGeneralChatNotifications() {
    if (chatNotificationRequestInFlight) return;
    chatNotificationRequestInFlight = true;
    try {
      const storedCursor = Number(localStorage.getItem(chatNotificationCursorKey)) || 0;
      chatNotificationCursor = Math.max(chatNotificationCursor, storedCursor);
      const query = chatNotificationInitialized
        ? `?after_id=${chatNotificationCursor}`
        : '';
      const data = await socialRequest(`/api/social/chat${query}`);
      const messages = data.messages || [];
      if (!chatNotificationInitialized) {
        const latestId = messages.reduce(
          (latest, message) => Math.max(latest, Number(message.id) || 0),
          0,
        );
        chatNotificationCursor = latestId;
        chatNotificationInitialized = true;
        if (latestId) localStorage.setItem(chatNotificationCursorKey, String(latestId));
        return;
      }

      const currentUsername = (localStorage.getItem('pedantix_auth_user') || '')
        .trim()
        .toLocaleLowerCase();
      for (const message of messages) {
        const messageId = Number(message.id);
        if (!Number.isInteger(messageId) || messageId <= chatNotificationCursor) continue;
        chatNotificationCursor = messageId;
        localStorage.setItem(chatNotificationCursorKey, String(messageId));
        if (String(message.username || '').trim().toLocaleLowerCase() !== currentUsername) {
          showGeneralChatNotification(message);
        }
      }
    } catch (error) {
      console.warn('Impossible de vérifier les nouveaux messages du chat général.', error);
    } finally {
      chatNotificationRequestInFlight = false;
      updateChatNotificationPermissionButton();
    }
  }

  function ensureInvitationModal() {
    if (invitationModal) return invitationModal;
    invitationModal = document.createElement('div');
    invitationModal.className = 'shared-invitation-overlay';
    invitationModal.hidden = true;
    invitationModal.innerHTML = `
      <section class="shared-invitation-dialog" role="dialog" aria-modal="true" aria-labelledby="shared-invitation-title">
        <span class="shared-invitation-icon" aria-hidden="true">⚓</span>
        <p class="shared-invitation-eyebrow">Invitation à jouer</p>
        <h2 id="shared-invitation-title"></h2>
        <p class="shared-invitation-copy"></p>
        <p class="shared-invitation-countdown" role="timer"></p>
        <p class="shared-invitation-error" role="alert" hidden></p>
        <div class="shared-invitation-actions">
          <button type="button" class="shared-invitation-accept">Accepter et rejoindre</button>
          <button type="button" class="shared-invitation-decline">Refuser</button>
        </div>
      </section>`;
    document.body.append(invitationModal);
    return invitationModal;
  }

  function navigateToInvitation(invitation, playerId) {
    const storageKey = gamePlayerStorageKeys[invitation.game_id];
    if (!storageKey || !invitation.room_id || !playerId) {
      throw new Error('Le salon créé ne peut pas être ouvert.');
    }
    localStorage.setItem(storageKey, playerId);
    window.location.href =
      `/games/${encodeURIComponent(invitation.game_id)}/?room=${encodeURIComponent(invitation.room_id)}`;
  }

  function hideInvitationModal() {
    if (invitationTimer) window.clearInterval(invitationTimer);
    invitationTimer = null;
    activeInvitationId = null;
    if (invitationModal) invitationModal.hidden = true;
    if (invitationPreviousFocus?.isConnected) invitationPreviousFocus.focus();
    invitationPreviousFocus = null;
  }

  function renderInvitation(invitation) {
    const modal = ensureInvitationModal();
    invitationPreviousFocus = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    activeInvitationId = Number(invitation.id);
    modal.querySelector('#shared-invitation-title').textContent =
      `${invitation.sender_username} vous invite à jouer à ${invitationGames[invitation.game_id] || invitation.game_id}`;
    modal.querySelector('.shared-invitation-copy').textContent =
      'En acceptant, un nouveau salon sera créé pour vous deux. Votre partie actuelle restera inchangée si vous refusez.';
    modal.querySelector('.shared-invitation-error').hidden = true;
    const accept = modal.querySelector('.shared-invitation-accept');
    const decline = modal.querySelector('.shared-invitation-decline');
    accept.disabled = false;
    decline.disabled = false;
    modal.hidden = false;
    accept.focus();

    const updateCountdown = () => {
      const seconds = Math.max(0, Math.ceil(Number(invitation.expires_at) - Date.now() / 1000));
      const minutes = Math.floor(seconds / 60);
      const remainder = String(seconds % 60).padStart(2, '0');
      modal.querySelector('.shared-invitation-countdown').textContent =
        `Réponse possible pendant ${minutes}:${remainder}`;
      if (!seconds) {
        hideInvitationModal();
        refreshInvitations();
      }
    };
    updateCountdown();
    invitationTimer = window.setInterval(updateCountdown, 1000);

    accept.onclick = async () => {
      accept.disabled = true;
      decline.disabled = true;
      try {
        const result = await socialRequest(`/api/social/invitations/${invitation.id}`, {
          method: 'POST',
          body: JSON.stringify({ action: 'accepted' }),
        });
        navigateToInvitation(result, result.player_id);
      } catch (error) {
        const errorMessage = modal.querySelector('.shared-invitation-error');
        errorMessage.textContent = error.message;
        errorMessage.hidden = false;
        if (error.status === 404 || error.status === 410) {
          hideInvitationModal();
          refreshInvitations();
        } else {
          accept.disabled = false;
          decline.disabled = false;
        }
      }
    };
    decline.onclick = async () => {
      accept.disabled = true;
      decline.disabled = true;
      try {
        await socialRequest(`/api/social/invitations/${invitation.id}`, {
          method: 'POST',
          body: JSON.stringify({ action: 'declined' }),
        });
        hideInvitationModal();
        refreshInvitations();
      } catch (error) {
        const errorMessage = modal.querySelector('.shared-invitation-error');
        errorMessage.textContent = error.message;
        errorMessage.hidden = false;
        if (error.status === 404 || error.status === 410) {
          hideInvitationModal();
          refreshInvitations();
        } else {
          accept.disabled = false;
          decline.disabled = false;
        }
      }
    };
  }

  async function refreshInvitations() {
    if (receivedInvitationCheckInFlight) return;
    const username = localStorage.getItem('pedantix_auth_user');
    if (!username || !localStorage.getItem('pedantix_auth_token')) {
      hideInvitationModal();
      return;
    }
    receivedInvitationCheckInFlight = true;
    try {
      const data = await socialRequest('/api/social/invitations');
      const invitations = data.invitations || [];
      const active = invitations.find((invitation) => Number(invitation.id) === activeInvitationId);
      if (active && invitationModal && !invitationModal.hidden) return;
      if (activeInvitationId !== null) hideInvitationModal();
      if (invitations.length) renderInvitation(invitations[0]);
    } catch (error) {
      console.warn('Impossible de vérifier les invitations reçues.', error);
    } finally {
      receivedInvitationCheckInFlight = false;
    }
  }

  async function sendHeartbeat() {
    const username = (localStorage.getItem('pedantix_auth_user') || '').trim().slice(0, 24);
    if (!username) return;
    if (!sessionId) {
      sessionId = globalThis.crypto?.randomUUID?.()
        || `presence-${Date.now()}-${Math.random().toString(36).slice(2)}`;
      sessionStorage.setItem('pedantix_presence_id', sessionId);
    }
    try {
      const response = await fetch(`${apiBase}/api/presence`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, username, game_id: gameId }),
        keepalive: true,
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
    } catch (error) {
      console.warn('Impossible de signaler la présence au serveur.', error);
    }
  }

  function renderOnlinePlayers(players) {
    const list = document.getElementById('store-online-list');
    const count = document.getElementById('store-online-count');
    const plural = document.getElementById('store-online-count-plural');
    if (!list || !count || !plural) return;

    list.replaceChildren();
    count.textContent = String(players.length);
    plural.textContent = players.length === 1 ? '' : 's';
    if (players.length === 0) {
      const empty = document.createElement('li');
      empty.className = 'store-online-empty';
      empty.textContent = 'Aucun joueur connecté pour le moment.';
      list.append(empty);
      return;
    }

    const currentUsername = (localStorage.getItem('pedantix_auth_user') || '').trim();
    for (const player of players) {
      const item = document.createElement('li');
      const name = document.createElement('span');
      name.className = 'store-online-name';
      name.textContent = player.username;
      const game = document.createElement('small');
      game.textContent = gameLabels[player.game_id] || 'En ligne';
      item.append(name, game);
      if (currentUsername && player.username.toLocaleLowerCase() !== currentUsername.toLocaleLowerCase()) {
        const invite = document.createElement('button');
        invite.type = 'button';
        invite.className = 'store-invite-player';
        invite.textContent = 'Inviter';
        invite.setAttribute('aria-label', `Inviter ${player.username} à jouer`);
        invite.addEventListener('click', () => {
          document.dispatchEvent(new CustomEvent('store:invite-player', {
            detail: { username: player.username },
          }));
        });
        item.append(invite);
      }
      list.append(item);
    }
  }

  async function refreshOnlinePlayers() {
    const list = document.getElementById('store-online-list');
    if (!list) return;
    try {
      const response = await fetch(`${apiBase}/api/presence`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
      renderOnlinePlayers(data.players || []);
    } catch (error) {
      list.replaceChildren();
      const message = document.createElement('li');
      message.className = 'store-online-empty store-online-error';
      message.textContent = `Impossible de charger les joueurs : ${error.message}`;
      list.append(message);
    }
  }

  function initializeGamePauseControl() {
    const pauseStyles = document.createElement('style');
    pauseStyles.textContent = `
      .shared-game-pause-notice {
        position: fixed; z-index: 10000; top: 12px; left: 50%; display: flex;
        width: min(720px, calc(100vw - 24px)); align-items: center;
        justify-content: space-between; gap: 12px; transform: translateX(-50%);
        padding: 10px 14px; border: 1px solid rgba(255,255,255,.2);
        border-radius: 12px; background: #1e293b; color: #f8fafc;
        box-shadow: 0 8px 28px rgba(0,0,0,.28); font: 600 .82rem/1.4 system-ui,sans-serif;
      }
      .shared-game-pause-notice[hidden] { display: none; }
      .shared-game-pause-notice.is-paused { background: #7f1d1d; }
      .shared-game-pause-notice button {
        flex: 0 0 auto; padding: 7px 10px; border: 1px solid rgba(255,255,255,.3);
        border-radius: 8px; background: rgba(255,255,255,.12); color: inherit; font: inherit;
      }
      .shared-game-pause-notice button:disabled { cursor: wait; opacity: .65; }
      @media (max-width: 560px) {
        .shared-game-pause-notice { align-items: stretch; flex-direction: column; gap: 8px; }
      }`;
    document.head.append(pauseStyles);
    const notice = document.createElement('aside');
    notice.className = 'shared-game-pause-notice';
    notice.hidden = true;
    notice.setAttribute('role', 'status');
    notice.setAttribute('aria-live', 'polite');
    const message = document.createElement('span');
    const control = document.createElement('button');
    control.type = 'button';
    control.hidden = true;
    notice.append(message, control);
    document.body.append(notice);

    const username = localStorage.getItem('pedantix_auth_user') || '';
    const token = localStorage.getItem('pedantix_auth_token') || '';
    let canControl = false;
    let requestInFlight = false;
    let refreshTimer = null;
    let adminPassword = '';

    async function refresh() {
      if (requestInFlight) return;
      requestInFlight = true;
      try {
        const response = await fetch(`${apiBase}/api/games/pause`, {
          headers: {
            'X-Auth-User': username,
            'X-Auth-Token': token,
          },
          cache: 'no-store',
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
        canControl = data.can_control === true;
        control.hidden = !canControl;
        notice.hidden = !data.paused && !canControl;
        notice.classList.toggle('is-paused', data.paused === true);
        message.textContent = data.paused
          ? 'Les parties sont en pause pour cause de maintenance. Les parties en cours restent accessibles, mais aucun nouveau lancement n’est accepté.'
          : canControl ? 'Toutes les parties sont disponibles.' : '';
        if (canControl) {
          control.textContent = data.paused ? 'Reprendre les parties' : 'Mettre les parties en pause';
          control.setAttribute('aria-pressed', String(data.paused === true));
        }
      } catch (error) {
        console.error('Impossible de récupérer la pause globale des parties.', error);
        if (canControl) {
          notice.hidden = false;
          message.textContent = `État de la pause indisponible : ${error.message}`;
          control.hidden = false;
          control.disabled = true;
        }
      } finally {
        requestInFlight = false;
      }
    }

    control.addEventListener('click', async () => {
      if (!canControl || requestInFlight) return;
      if (!adminPassword) {
        adminPassword = window.prompt('Confirmez le mot de passe du compte Gwen pour modifier la pause :') || '';
        if (!adminPassword) return;
      }
      requestInFlight = true;
      control.disabled = true;
      try {
        const response = await fetch(`${apiBase}/api/admin/game-pause`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Auth-User': username,
            'X-Auth-Token': token,
          },
          body: JSON.stringify({
            paused: control.getAttribute('aria-pressed') !== 'true',
            admin_password: adminPassword,
          }),
          cache: 'no-store',
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
        notice.classList.toggle('is-paused', data.paused === true);
        notice.hidden = !data.paused && !canControl;
        message.textContent = data.paused
          ? 'Les parties sont en pause pour cause de maintenance. Les parties en cours restent accessibles, mais aucun nouveau lancement n’est accepté.'
          : 'Toutes les parties sont disponibles.';
        control.textContent = data.paused ? 'Reprendre les parties' : 'Mettre les parties en pause';
        control.setAttribute('aria-pressed', String(data.paused === true));
      } catch (error) {
        console.error('Impossible de modifier la pause globale des parties.', error);
        message.textContent = `La modification n’a pas été confirmée : ${error.message}`;
        notice.hidden = false;
        if (error.message.includes('compte administrateur Gwen')) adminPassword = '';
      } finally {
        requestInFlight = false;
        control.disabled = false;
        refresh();
      }
    });

    refresh();
    refreshTimer = window.setInterval(refresh, 3000);
    window.addEventListener('pagehide', () => {
      if (refreshTimer) window.clearInterval(refreshTimer);
    }, { once: true });
  }

  initializeGamePauseControl();
  ensureChatNotificationUi();
  refreshGeneralChatNotifications();
  chatNotificationTimer = window.setInterval(refreshGeneralChatNotifications, 3_000);
  sendHeartbeat();
  window.setInterval(sendHeartbeat, 30_000);
  refreshInvitations();
  window.setInterval(refreshInvitations, 3_000);
  function refreshVisibleSocialState() {
    if (document.visibilityState !== 'visible') return;
    sendHeartbeat();
    refreshInvitations();
    refreshGeneralChatNotifications();
  }
  document.addEventListener('visibilitychange', refreshVisibleSocialState);
  window.addEventListener('focus', refreshVisibleSocialState);
  window.addEventListener('pageshow', refreshVisibleSocialState);
  window.addEventListener('pagehide', () => {
    if (chatNotificationTimer) window.clearInterval(chatNotificationTimer);
  }, { once: true });
  if (document.getElementById('store-online-list')) {
    refreshOnlinePlayers();
    window.setInterval(refreshOnlinePlayers, 15_000);
  }
})();
