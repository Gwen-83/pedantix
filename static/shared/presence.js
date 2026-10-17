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
    store: 'La ludothèque',
  };
  const gameId = document.documentElement.dataset.presenceGame
    || window.location.pathname.split('/')[2]
    || 'store';
  let sessionId = sessionStorage.getItem('pedantix_presence_id');

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

    for (const player of players) {
      const item = document.createElement('li');
      const name = document.createElement('span');
      name.className = 'store-online-name';
      name.textContent = player.username;
      const game = document.createElement('small');
      game.textContent = gameLabels[player.game_id] || 'En ligne';
      item.append(name, game);
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

  sendHeartbeat();
  window.setInterval(sendHeartbeat, 30_000);
  if (document.getElementById('store-online-list')) {
    refreshOnlinePlayers();
    window.setInterval(refreshOnlinePlayers, 15_000);
  }
})();
