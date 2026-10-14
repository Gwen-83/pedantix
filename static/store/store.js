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
  const params = new URLSearchParams(window.location.search);
  const requestedNext = params.get('next');
  const launchTarget = requestedNext ? new URL(requestedNext, window.location.origin) : null;
  const legacyLaunchTarget = launchTarget
    && launchTarget.origin === window.location.origin
    && launchTarget.pathname === '/'
    && (launchTarget.searchParams.get('game') === 'pedantix'
      || launchTarget.searchParams.get('game') === 'motus'
      || launchTarget.searchParams.get('game') === 'cemantix'
      || launchTarget.searchParams.get('game') === 'battleship'
      || launchTarget.searchParams.get('game') === 'sudoku'
      || launchTarget.searchParams.has('assist')
      || launchTarget.searchParams.has('room')
      || launchTarget.searchParams.get('mode') === 'solo'
      || launchTarget.searchParams.get('mode') === 'multi');
  if (legacyLaunchTarget) {
    launchTarget.pathname = {
      pedantix: '/games/pedantix/',
      motus: '/games/motus/',
      cemantix: '/games/cemantix/',
      battleship: '/games/battleship/',
      sudoku: '/games/sudoku/',
    }[launchTarget.searchParams.get('game')] || '/games/pedantix/';
    launchTarget.searchParams.delete('game');
  }
  const safeLaunchTarget = launchTarget
    && launchTarget.origin === window.location.origin
    && ['/games/pedantix/', '/games/motus/', '/games/cemantix/', '/games/battleship/', '/games/sudoku/'].includes(launchTarget.pathname)
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
    accountName.hidden = !username;
    accountName.textContent = username ? `Bonjour, ${username}` : '';
    accountButton.hidden = !!username;
    logoutButton.hidden = !username;
  }

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
  if (params.get('login') === '1') openDialog(!!safeLaunchTarget);
})();
