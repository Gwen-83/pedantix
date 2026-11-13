(() => {
  const apiBase = window.PEDANTIX_CONFIG?.BACKEND_URL?.replace(/\/+$/, '') || '';
  const wsBase = apiBase
    ? apiBase.replace(/^http:/, 'ws:').replace(/^https:/, 'wss:')
    : `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}`;
  const EXCUSE = 0;
  const ROOM_STORAGE_KEY = 'tarot_active_room_id';
  const playerName = (
    localStorage.getItem('pedantix_auth_user')
    || localStorage.getItem('pedantix_player_name')
    || 'Joueur'
  ).trim().slice(0, 24) || 'Joueur';
  let playerId = localStorage.getItem('tarot_player_id');
  if (!playerId) {
    playerId = globalThis.crypto?.randomUUID?.()
      || `tarot-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    localStorage.setItem('tarot_player_id', playerId);
  }

  const $ = (id) => document.getElementById(id);
  const home = $('tarot-home');
  const game = $('tarot-game');
  let state = null;
  let socket = null;
  let activeRoomId = '';
  let reconnectTimer = null;
  let reconnectDelay = 500;
  let deliberateClose = false;
  let clockTimer = null;
  let clockBase = 0;
  let clockStartedAt = 0;
  const ui = { turnKey: '', bidDraft: 0, confirming: false, excusePending: false };

  $('tarot-player-name').textContent = playerName;

  const plural = (count, singular, pluralForm = `${singular}s`) => (
    `${count} ${Math.abs(count) > 1 ? pluralForm : singular}`
  );

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
      showError('tarot-game-error', new Error('Connexion au salon interrompue. Reconnexion…'));
      return false;
    }
    socket.send(JSON.stringify(message));
    return true;
  }

  function setRoom(nextState, updateUrl = false) {
    state = nextState;
    activeRoomId = state.room_id;
    localStorage.setItem(ROOM_STORAGE_KEY, activeRoomId);
    if (updateUrl) {
      history.replaceState(null, '', `${window.location.pathname}?room=${encodeURIComponent(activeRoomId)}`);
    }
    clearError('tarot-game-error');
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
    const url = `${wsBase}/ws/tarot-africain/${encodeURIComponent(activeRoomId)}`
      + `?player_id=${encodeURIComponent(playerId)}`;
    const connection = new WebSocket(url);
    socket = connection;
    connection.addEventListener('open', () => {
      reconnectDelay = 500;
      clearError('tarot-game-error');
    });
    connection.addEventListener('message', (event) => {
      let message;
      try {
        message = JSON.parse(event.data);
      } catch (error) {
        console.error('Message Tarot africain illisible :', error);
        return;
      }
      if (message.type === 'state') {
        state = message.state;
        clearError('tarot-game-error');
        render();
      } else if (message.type === 'left') {
        deliberateClose = true;
        connection.close();
        returnHome(false);
      } else if (message.type === 'error') {
        showError('tarot-game-error', new Error(message.message));
      }
    });
    connection.addEventListener('close', (event) => {
      if (socket !== connection) return;
      if (event.code === 4404) {
        returnHome(false);
        showError('tarot-home-error', new Error('Salon introuvable ou participation expirée.'));
        return;
      }
      if (!deliberateClose && activeRoomId) {
        showError('tarot-game-error', new Error('Connexion interrompue. Reconnexion…'));
        reconnectTimer = setTimeout(rejoinAfterDisconnect, reconnectDelay);
        reconnectDelay = Math.min(reconnectDelay * 2, 8000);
      }
    });
  }

  async function rejoinAfterDisconnect() {
    reconnectTimer = null;
    try {
      state = await request('/api/tarot-africain/room/join', {
        room_id: activeRoomId,
        player_id: playerId,
        player_name: playerName,
      });
      render();
    } catch (error) {
      if (/introuvable|commencé/i.test(error.message)) {
        returnHome(false);
        showError('tarot-home-error', error);
        return;
      }
    }
    connectSocket();
  }

  function seat(index) {
    return state?.seats?.[index] || null;
  }

  function seatName(index, { self = true } = {}) {
    const item = seat(index);
    if (!item) return 'Joueur';
    if (self && item.is_self) return 'Vous';
    return item.name;
  }

  function kindLabel(kind) {
    return {
      single_visible: '1 carte · carte visible',
      single_hidden: '1 carte · votre carte est cachée',
    }[kind] || '';
  }

  function excuseValue(mode) {
    return mode === 'max' ? 22 : 0;
  }

  function createCard(card, { hidden = false, mode = null } = {}) {
    const element = document.createElement('span');
    element.className = 'tarot-card';
    if (hidden) {
      element.classList.add('is-back');
      element.setAttribute('role', 'img');
      element.setAttribute('aria-label', 'Carte cachée');
      const back = document.createElement('span');
      back.className = 'tarot-card-center';
      back.setAttribute('aria-hidden', 'true');
      back.textContent = '✦';
      element.append(back);
      return element;
    }
    const corner = document.createElement('span');
    corner.className = 'tarot-card-corner';
    corner.setAttribute('aria-hidden', 'true');
    const center = document.createElement('span');
    center.className = 'tarot-card-center';
    center.setAttribute('aria-hidden', 'true');
    if (card === EXCUSE) {
      element.classList.add('is-excuse');
      corner.textContent = mode ? String(excuseValue(mode)) : '★';
      center.textContent = 'Excuse';
      element.append(corner, center);
      if (mode) {
        const badge = document.createElement('span');
        badge.className = 'tarot-card-mode';
        badge.textContent = mode.toUpperCase();
        element.append(badge);
        element.setAttribute('aria-label', `Excuse jouée en ${mode.toUpperCase()}, valeur ${excuseValue(mode)}`);
      } else {
        element.setAttribute('aria-label', 'Excuse, vaut 0 ou 22 au choix');
      }
    } else {
      corner.textContent = String(card);
      center.textContent = String(card);
      element.append(corner, center);
      element.setAttribute('aria-label', `Atout ${card}`);
    }
    element.setAttribute('role', 'img');
    return element;
  }

  function renderLobby() {
    $('tarot-lobby').hidden = false;
    $('tarot-play').hidden = true;
    $('tarot-phase-label').textContent = 'Salon d’attente';
    $('tarot-room-title').textContent = `Salon ${state.room_id}`;
    $('tarot-invite-code').textContent = state.room_id;
    const count = state.player_count;
    const cardsByPlayers = { 2: 11, 3: 7, 4: 5, 5: 4, 6: 3 };
    const cards = cardsByPlayers[count];
    $('tarot-lobby-message').textContent = cards
      ? `${plural(count, 'joueur')} · ${cards} cartes au maximum, ${plural(22 - cards * count, 'carte mise', 'cartes mises')} de côté, ${count * (cards + 1)} manches au total.`
      : `${plural(count, 'joueur')} · il faut au moins ${state.min_players} joueurs pour démarrer.`;
    $('tarot-lobby-summary').textContent = 'Le premier distributeur sera tiré au sort. L’ordre de jeu suit l’ordre de la liste.';
    $('tarot-lobby-players').replaceChildren(...state.seats.map((item, index) => {
      const row = document.createElement('li');
      const name = document.createElement('span');
      name.textContent = `${index + 1}. ${item.name}${item.is_self ? ' (vous)' : ''}`;
      const detail = document.createElement('small');
      detail.textContent = item.is_host ? 'Hôte' : 'Prêt';
      row.append(name, detail);
      return row;
    }));
    const start = $('tarot-start');
    start.hidden = state.host_player_id !== playerId;
    start.disabled = !state.can_start;
  }

  function syncTurnState() {
    const key = [
      state.match_number, state.round?.number, state.phase, state.current_seat, state.trick_number,
    ].join(':');
    if (key === ui.turnKey) return;
    ui.turnKey = key;
    ui.confirming = false;
    ui.excusePending = false;
    ui.bidDraft = state.forbidden_bid === 0 ? 1 : 0;
  }

  function renderRoundbar() {
    const round = state.round;
    if (!round) {
      $('tarot-round-label').textContent = state.status === 'finished' ? 'Partie terminée' : '';
      $('tarot-round-detail').textContent = '';
      $('tarot-round-badge').hidden = true;
      return;
    }
    $('tarot-round-label').textContent = `Manche ${round.number} / ${round.total}`;
    $('tarot-round-detail').textContent =
      `Distributeur : ${seatName(round.dealer_seat)} (${round.cycle_number}/${round.cycle_count})`
      + ` · ${plural(round.cards_per_player, 'carte')} chacun · ${plural(round.set_aside_count, 'carte mise', 'cartes mises')} de côté`;
    const badge = $('tarot-round-badge');
    badge.hidden = round.kind === 'normal';
    badge.textContent = round.kind === 'single_hidden'
      ? '🙈 Carte cachée'
      : '👁️ Carte visible';
    badge.classList.toggle('is-hidden-round', round.kind === 'single_hidden');
  }

  function setStatus(icon, title, description) {
    $('tarot-status-icon').textContent = icon;
    $('tarot-status-title').textContent = title;
    $('tarot-status-desc').textContent = description;
  }

  function renderStatus() {
    const status = $('tarot-status');
    status.classList.toggle('is-my-turn', Boolean(state.is_my_turn));
    const round = state.round;
    if (state.status === 'finished') {
      setStatus('🏁', 'Partie terminée', 'Tous les joueurs ont distribué : le moins de pénalités l’emporte.');
      return;
    }
    if (state.phase === 'bidding') {
      const hiddenHint = round?.kind === 'single_hidden'
        ? ' Vous voyez les cartes des autres joueurs, mais pas la vôtre.'
        : '';
      if (state.is_my_turn) {
        const dealerHint = round?.dealer_seat === state.my_seat
          ? ' Vous êtes le distributeur : vous annoncez en dernier.'
          : '';
        setStatus('📣', 'À vous d’annoncer', `Combien de plis allez-vous remporter ?${dealerHint}${hiddenHint}`);
      } else {
        const dealer = state.current_seat === round?.dealer_seat ? ' (distributeur)' : '';
        setStatus('⏳', `${seatName(state.current_seat)}${dealer} réfléchit à son annonce…`, hiddenHint.trim());
      }
      return;
    }
    if (state.phase === 'playing') {
      if (state.is_my_turn) {
        setStatus('🃏', 'À vous de jouer', state.trick.length
          ? 'Choisissez n’importe quelle carte de votre main.'
          : 'Vous entamez le pli : choisissez n’importe quelle carte de votre main.');
      } else {
        setStatus('⏳', `${seatName(state.current_seat)} choisit une carte…`, '');
      }
      return;
    }
    if (state.phase === 'trick_end') {
      const winner = seat(state.trick_winner_seat);
      setStatus('🏆', winner?.is_self ? 'Vous remportez le pli !' : `${winner?.name || 'Un joueur'} remporte le pli`, 'Le pli est ramassé dans un instant.');
      return;
    }
    if (state.phase === 'round_end') {
      setStatus('📊', `Fin de la manche ${round?.number || ''}`, 'Les pénalités ont été ajoutées à la feuille de marque.');
    }
  }

  function seatStats(item) {
    const bid = item.bid === null ? '—' : item.bid;
    return `Annonce ${bid} · Plis ${item.tricks} · Pénalités ${item.penalties}`;
  }

  function renderOpponents() {
    const count = state.seats.length;
    const list = $('tarot-opponents');
    const items = [];
    for (let offset = 1; offset < count; offset += 1) {
      const index = (state.my_seat + offset) % count;
      const item = state.seats[index];
      const row = document.createElement('li');
      row.className = 'tarot-opponent';
      if (item.is_current) row.classList.add('is-current');
      if (state.phase === 'trick_end' && state.trick_winner_seat === index) row.classList.add('is-winner');
      const header = document.createElement('div');
      header.className = 'tarot-opponent-header';
      const name = document.createElement('strong');
      name.textContent = item.name;
      header.append(name);
      if (offset === 1) header.append(badge('à votre gauche', 'is-soft'));
      if (item.is_dealer) header.append(badge('Distributeur', 'is-dealer'));
      if (item.is_bot) header.append(badge('🤖 Bot', 'is-bot'));
      const stats = document.createElement('p');
      stats.className = 'tarot-opponent-stats';
      stats.textContent = seatStats(item);
      const cards = document.createElement('div');
      cards.className = 'tarot-opponent-cards';
      if (Array.isArray(item.hand)) {
        cards.classList.add('is-revealed');
        item.hand.forEach((card) => cards.append(createCard(card)));
      } else {
        for (let i = 0; i < item.hand_count; i += 1) cards.append(createCard(null, { hidden: true }));
      }
      if (!item.hand_count) {
        const empty = document.createElement('small');
        empty.textContent = 'Aucune carte en main';
        cards.append(empty);
      }
      row.append(header, stats, cards);
      items.push(row);
    }
    list.replaceChildren(...items);
  }

  function badge(text, modifier) {
    const element = document.createElement('span');
    element.className = `tarot-badge ${modifier}`;
    element.textContent = text;
    return element;
  }

  function renderTrick() {
    const round = state.round;
    const zone = $('tarot-trick');
    $('tarot-trick-title').textContent = round
      ? `Pli ${Math.min(state.trick_number, round.cards_per_player)} / ${round.cards_per_player}`
      : 'Pli en cours';
    $('tarot-bids-total').textContent = round && state.phase !== 'round_end'
      ? `Annonces : ${round.bids_total} pour ${plural(round.cards_per_player, 'pli')}`
      : '';
    if (!state.trick.length) {
      const empty = document.createElement('li');
      empty.className = 'tarot-trick-empty';
      empty.textContent = state.phase === 'bidding'
        ? `Annonces en cours. ${seatName(state.leader_seat)} entamera le premier pli.`
        : state.phase === 'playing'
          ? `${seatName(state.leader_seat)} entame le pli.`
          : '';
      zone.replaceChildren(empty);
      return;
    }
    zone.replaceChildren(...state.trick.map((entry) => {
      const item = document.createElement('li');
      item.className = 'tarot-trick-entry';
      if (state.trick_winner_seat === entry.seat) item.classList.add('is-winner');
      const name = document.createElement('span');
      name.className = 'tarot-trick-name';
      name.textContent = seatName(entry.seat);
      item.append(createCard(entry.card, { mode: entry.excuse_mode }), name);
      if (entry.card === EXCUSE) {
        const note = document.createElement('small');
        note.textContent = `Excuse annoncée ${entry.excuse_mode.toUpperCase()} (${entry.value})`;
        item.append(note);
      }
      return item;
    }));
  }

  function validDraft() {
    const value = ui.bidDraft;
    return Number.isInteger(value) && value >= 0 && value <= state.max_bid;
  }

  function renderBidPanel() {
    const panel = $('tarot-bid-panel');
    const visible = state.is_my_turn && state.phase === 'bidding';
    panel.hidden = !visible;
    if (!visible) return;
    const round = state.round;
    $('tarot-bid-choose').hidden = ui.confirming;
    $('tarot-bid-confirm').hidden = !ui.confirming;
    const input = $('tarot-bid-input');
    input.max = String(state.max_bid);
    if (document.activeElement !== input) input.value = ui.bidDraft ?? '';
    const forbidden = state.forbidden_bid;
    const quick = $('tarot-bid-quick');
    const quickValues = Array.from({ length: round.cards_per_player + 1 }, (_, value) => value);
    quick.replaceChildren(...quickValues.map((value) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'tarot-button tarot-bid-chip';
      button.textContent = String(value);
      button.setAttribute('aria-pressed', String(ui.bidDraft === value));
      if (value === forbidden) {
        button.classList.add('is-forbidden');
        button.title = 'Annonce interdite pour le distributeur';
      }
      button.addEventListener('click', () => {
        ui.bidDraft = value;
        renderBidPanel();
      });
      return button;
    }));
    const rule = $('tarot-bid-rule');
    const isForbidden = forbidden !== null && ui.bidDraft === forbidden;
    if (forbidden !== null) {
      const others = round.bids_total;
      rule.hidden = false;
      rule.classList.toggle('is-error', isForbidden);
      rule.textContent = `${isForbidden ? 'Annonce impossible. ' : ''}En tant que distributeur, vous ne pouvez pas annoncer ${forbidden} : `
        + `les autres joueurs ont annoncé ${plural(others, 'pli')} au total, et ${others} + ${forbidden} = ${round.cards_per_player}, `
        + `le nombre de cartes distribuées. La somme des annonces doit être différente de ${round.cards_per_player}.`;
    } else {
      rule.hidden = true;
      rule.textContent = '';
    }
    const submit = $('tarot-bid-submit');
    submit.disabled = !validDraft() || isForbidden;
    submit.textContent = validDraft() ? `Annoncer ${plural(ui.bidDraft, 'pli')}` : 'Annoncer';
    $('tarot-bid-confirm-text').textContent =
      `Vous annoncez ${plural(ui.bidDraft ?? 0, 'pli')}. Une fois confirmée, votre annonce est définitive et visible par tous les joueurs.`;
  }

  function renderMe() {
    const me = seat(state.my_seat);
    const identity = $('tarot-me-identity');
    identity.replaceChildren();
    const name = document.createElement('strong');
    name.textContent = `${me.name} (vous)`;
    identity.append(name);
    if (me.is_dealer) identity.append(badge('Distributeur', 'is-dealer'));
    if (state.is_my_turn) identity.append(badge('À vous !', 'is-turn'));
    $('tarot-me-stats').textContent = seatStats(me);
    $('tarot-me').classList.toggle('is-current', Boolean(state.is_my_turn));

    renderBidPanel();
    const canPlay = state.is_my_turn && state.phase === 'playing';
    $('tarot-excuse-panel').hidden = !(canPlay && ui.excusePending);

    const hand = $('tarot-hand');
    if (!Array.isArray(me.hand)) {
      const items = [];
      for (let i = 0; i < me.hand_count; i += 1) {
        const item = document.createElement('li');
        item.append(createCard(null, { hidden: true }));
        const note = document.createElement('small');
        note.textContent = 'Votre carte est cachée jusqu’à la fin des annonces';
        item.append(note);
        items.push(item);
      }
      hand.replaceChildren(...items);
      return;
    }
    hand.replaceChildren(...me.hand.map((card) => {
      const item = document.createElement('li');
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'tarot-hand-card';
      button.disabled = !canPlay || ui.excusePending;
      button.append(createCard(card));
      button.setAttribute('aria-label', card === EXCUSE ? 'Jouer l’Excuse' : `Jouer le ${card}`);
      button.addEventListener('click', () => {
        if (card === EXCUSE) {
          ui.excusePending = true;
          renderMe();
          $('tarot-excuse-max').focus();
          return;
        }
        send({ type: 'play', card });
      });
      item.append(button);
      return item;
    }));
    if (!me.hand.length) {
      const empty = document.createElement('li');
      empty.className = 'tarot-hand-empty';
      empty.textContent = 'Vous n’avez plus de carte en main.';
      hand.replaceChildren(empty);
    }
  }

  function renderRoundSummary() {
    const panel = $('tarot-round-summary');
    const last = state.history.at(-1);
    const visible = state.phase === 'round_end' && Boolean(last);
    panel.hidden = !visible;
    $('tarot-trick').closest('.tarot-trick-zone').hidden = visible;
    if (!visible) return;
    $('tarot-round-summary-title').textContent =
      `Fin de la manche ${last.number} · ${plural(last.cards_per_player, 'carte')}`;
    $('tarot-round-summary-body').replaceChildren(...last.results.map((result) => {
      const row = document.createElement('tr');
      if (seat(result.seat)?.is_self) row.classList.add('is-self');
      [seatName(result.seat), result.bid, result.tricks, result.penalty ? `+${result.penalty}` : '0', result.total]
        .forEach((value, column) => {
          const cell = document.createElement(column === 0 ? 'th' : 'td');
          if (column === 0) cell.scope = 'row';
          cell.textContent = String(value);
          if (column === 3) cell.classList.add(result.penalty ? 'is-penalty' : 'is-exact');
          row.append(cell);
        });
      return row;
    }));
  }

  function renderScoreSheet() {
    const head = document.createElement('tr');
    const corner = document.createElement('th');
    corner.scope = 'col';
    corner.textContent = 'Manche';
    head.append(corner);
    state.seats.forEach((item) => {
      const cell = document.createElement('th');
      cell.scope = 'col';
      cell.textContent = item.is_self ? 'Vous' : item.name;
      cell.title = item.name;
      head.append(cell);
    });
    $('tarot-score-head').replaceChildren(head);
    $('tarot-score-tag').textContent = state.round ? `${state.history.length} / ${state.round.total}` : `${state.history.length} manches`;

    $('tarot-score-body').replaceChildren(...state.history.map((entry) => {
      const row = document.createElement('tr');
      const label = document.createElement('th');
      label.scope = 'row';
      const icon = entry.kind === 'single_hidden' ? ' 🙈' : entry.kind === 'single_visible' ? ' 👁️' : '';
      label.textContent = `${entry.number} · ${entry.cards_per_player}c${icon}`;
      label.title = `Distributeur : ${seat(entry.dealer_seat)?.name || ''}`;
      row.append(label);
      entry.results.forEach((result) => {
        const cell = document.createElement('td');
        cell.title = `Annonce ${result.bid} · Plis ${result.tricks}`;
        const penalty = document.createElement('span');
        penalty.className = result.penalty ? 'is-penalty' : 'is-exact';
        penalty.textContent = result.penalty ? `+${result.penalty}` : '✓';
        const detail = document.createElement('small');
        detail.textContent = `${result.bid}/${result.tricks}`;
        cell.append(penalty, detail);
        row.append(cell);
      });
      return row;
    }).reverse());

    const totals = document.createElement('tr');
    const totalLabel = document.createElement('th');
    totalLabel.scope = 'row';
    totalLabel.textContent = 'Total';
    totals.append(totalLabel);
    const lowest = Math.min(...state.seats.map((item) => item.penalties));
    state.seats.forEach((item) => {
      const cell = document.createElement('td');
      cell.textContent = String(item.penalties);
      if (state.history.length && item.penalties === lowest) cell.classList.add('is-leader');
      totals.append(cell);
    });
    $('tarot-score-foot').replaceChildren(totals);
  }

  function renderLog() {
    $('tarot-log').replaceChildren(...state.log.slice().reverse().map((entry) => {
      const item = document.createElement('li');
      item.textContent = entry.text;
      return item;
    }));
  }

  function renderFinished() {
    const overlay = $('tarot-finished');
    if (state.status !== 'finished') {
      overlay.hidden = true;
      return;
    }
    const wasHidden = overlay.hidden;
    overlay.hidden = false;
    const winners = new Set(state.winner_ids);
    const winnerNames = state.seats.filter((item) => winners.has(item.player_id)).map((item) => item.name);
    $('tarot-finished-title').textContent = winners.size === 1
      ? `Victoire de ${winnerNames[0]} !`
      : `Égalité : ${winnerNames.join(', ')} !`;
    const me = seat(state.my_seat);
    $('tarot-finished-subtitle').textContent = winners.has(playerId)
      ? `Bravo, vous terminez avec ${plural(me.penalties, 'point')} de pénalité et gagnez 3 points au classement.`
      : `Vous terminez avec ${plural(me.penalties, 'point')} de pénalité.`;
    const sorted = state.seats
      .map((item, index) => ({ ...item, index }))
      .sort((left, right) => left.penalties - right.penalties || left.name.localeCompare(right.name));
    const medals = ['🥇', '🥈', '🥉'];
    $('tarot-finished-ranks').replaceChildren(...sorted.map((item) => {
      const rank = sorted.filter((other) => other.penalties < item.penalties).length;
      const row = document.createElement('li');
      if (winners.has(item.player_id)) row.classList.add('is-winner');
      if (item.is_self) row.classList.add('is-self');
      const left = document.createElement('span');
      left.textContent = `${medals[rank] || `${rank + 1}.`} ${item.name}${item.is_self ? ' (vous)' : ''}${item.is_bot ? ' · 🤖' : ''}`;
      const right = document.createElement('strong');
      right.textContent = plural(item.penalties, 'pénalité');
      row.append(left, right);
      return row;
    }));
    $('tarot-restart').hidden = state.host_player_id !== playerId;
    if (wasHidden) $('tarot-finished').querySelector('[role="dialog"]').focus?.();
  }

  function render() {
    if (!state) return;
    if (state.status === 'lobby') {
      ui.turnKey = '';
      renderLobby();
      setClock(0);
      return;
    }
    syncTurnState();
    $('tarot-lobby').hidden = true;
    $('tarot-play').hidden = false;
    $('tarot-room-title').textContent = `Salon ${state.room_id}`;
    $('tarot-phase-label').textContent = ({
      bidding: 'Annonces',
      playing: 'Jeu de la carte',
      trick_end: 'Pli remporté',
      round_end: 'Fin de manche',
      finished: 'Partie terminée',
    })[state.phase] || 'En jeu';
    renderRoundbar();
    renderStatus();
    renderOpponents();
    renderTrick();
    renderRoundSummary();
    renderMe();
    renderScoreSheet();
    renderLog();
    renderFinished();
    setClock(state.seconds_remaining);
  }

  function setClock(seconds) {
    clockBase = seconds;
    clockStartedAt = Date.now();
    if (clockTimer) clearInterval(clockTimer);
    const update = () => {
      const display = $('tarot-countdown');
      const remaining = Math.max(0, clockBase - Math.floor((Date.now() - clockStartedAt) / 1000));
      const timed = state?.status === 'playing' && ['bidding', 'playing'].includes(state.phase);
      display.textContent = timed ? `${remaining}s` : state?.status === 'finished' ? 'FIN' : '·';
      display.classList.toggle('is-low', timed && remaining <= 10);
      display.classList.toggle('is-mine', timed && Boolean(state.is_my_turn));
      display.title = timed ? 'Temps restant avant une action automatique' : '';
      if (state?.phase === 'round_end') {
        $('tarot-round-summary-next').textContent = state.round?.number === state.round?.total
          ? `Résultats finaux dans ${remaining} s…`
          : `Manche suivante dans ${remaining} s…`;
      }
    };
    update();
    clockTimer = setInterval(update, 250);
  }

  function renderDirectory(rooms) {
    const directory = $('tarot-room-directory');
    directory.replaceChildren();
    if (!rooms.length) {
      directory.textContent = 'Aucun salon ouvert pour le moment.';
      return;
    }
    rooms.forEach((room) => {
      const card = document.createElement('article');
      card.className = 'tarot-room-card';
      const label = document.createElement('span');
      const title = document.createElement('strong');
      title.textContent = `Salon ${room.room_id} · ${room.host_name}`;
      const detail = document.createElement('small');
      detail.textContent = `${room.player_count}/${room.max_players} joueurs · ${room.status === 'lobby' ? 'en attente' : 'en cours'}`;
      label.append(title, detail);
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'tarot-button';
      button.textContent = room.is_member
        ? 'Reprendre ma place'
        : room.status === 'lobby' ? 'Rejoindre' : 'Partie en cours';
      button.disabled = !room.is_member && room.status !== 'lobby';
      button.addEventListener('click', () => joinRoom(room.room_id));
      card.append(label, button);
      directory.append(card);
    });
  }

  async function refreshDirectory() {
    const directory = $('tarot-room-directory');
    directory.textContent = 'Chargement des salons…';
    try {
      const result = await request(`/api/tarot-africain/rooms?player_id=${encodeURIComponent(playerId)}`);
      renderDirectory(result.rooms || []);
    } catch (error) {
      directory.textContent = `Impossible de charger les salons : ${error.message}`;
    }
  }

  async function createRoom() {
    clearError('tarot-home-error');
    $('tarot-create').disabled = true;
    try {
      const nextState = await request('/api/tarot-africain/room/create', {
        player_id: playerId,
        player_name: playerName,
      });
      deliberateClose = false;
      setRoom(nextState, true);
    } catch (error) {
      showError('tarot-home-error', error);
    } finally {
      $('tarot-create').disabled = false;
    }
  }

  async function joinRoom(rawRoomId, { silent = false } = {}) {
    const roomId = rawRoomId.trim().toUpperCase();
    if (!roomId) {
      showError('tarot-home-error', new Error('Saisissez le code du salon.'));
      return;
    }
    clearError('tarot-home-error');
    try {
      const nextState = await request('/api/tarot-africain/room/join', {
        room_id: roomId,
        player_id: playerId,
        player_name: playerName,
      });
      deliberateClose = false;
      setRoom(nextState, true);
    } catch (error) {
      if (silent) {
        localStorage.removeItem(ROOM_STORAGE_KEY);
      } else {
        showError('tarot-home-error', error);
      }
      refreshDirectory();
    }
  }

  async function returnHome(leave = true) {
    deliberateClose = true;
    if (reconnectTimer) clearTimeout(reconnectTimer);
    reconnectTimer = null;
    if (socket) socket.close();
    if (leave && activeRoomId) {
      try {
        await request('/api/tarot-africain/room/leave', {
          room_id: activeRoomId,
          player_id: playerId,
        });
      } catch (error) {
        showError('tarot-game-error', error);
        deliberateClose = false;
        connectSocket();
        return;
      }
    }
    activeRoomId = '';
    state = null;
    ui.turnKey = '';
    if (clockTimer) clearInterval(clockTimer);
    localStorage.removeItem(ROOM_STORAGE_KEY);
    history.replaceState(null, '', window.location.pathname);
    game.hidden = true;
    home.hidden = false;
    refreshDirectory();
  }

  function leaveTable() {
    if (state?.status === 'playing'
      && !window.confirm('Quitter la table ? Un bot jouera à votre place ; vous pourrez reprendre votre place depuis la liste des salons.')) {
      return;
    }
    returnHome();
  }

  $('tarot-create').addEventListener('click', createRoom);
  $('tarot-join').addEventListener('click', () => joinRoom($('tarot-room-code').value));
  $('tarot-room-code').addEventListener('keydown', (event) => {
    if (event.key === 'Enter') joinRoom(event.currentTarget.value);
  });
  $('tarot-refresh').addEventListener('click', refreshDirectory);
  $('tarot-start').addEventListener('click', () => send({ type: 'start' }));
  $('tarot-leave').addEventListener('click', leaveTable);
  $('tarot-finished-leave').addEventListener('click', () => returnHome());
  $('tarot-restart').addEventListener('click', () => send({ type: 'restart' }));

  $('tarot-bid-input').addEventListener('input', (event) => {
    const raw = event.currentTarget.value.trim();
    ui.bidDraft = /^\d+$/.test(raw) ? Number(raw) : null;
    renderBidPanel();
  });
  $('tarot-bid-input').addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !$('tarot-bid-submit').disabled) $('tarot-bid-submit').click();
  });
  $('tarot-bid-minus').addEventListener('click', () => {
    ui.bidDraft = Math.max(0, (ui.bidDraft ?? 0) - 1);
    renderBidPanel();
  });
  $('tarot-bid-plus').addEventListener('click', () => {
    ui.bidDraft = Math.min(state.max_bid, (ui.bidDraft ?? -1) + 1);
    renderBidPanel();
  });
  $('tarot-bid-submit').addEventListener('click', () => {
    if (!validDraft() || ui.bidDraft === state.forbidden_bid) return;
    ui.confirming = true;
    renderBidPanel();
    $('tarot-bid-confirm-yes').focus();
  });
  $('tarot-bid-confirm-back').addEventListener('click', () => {
    ui.confirming = false;
    renderBidPanel();
    $('tarot-bid-input').focus();
  });
  $('tarot-bid-confirm-yes').addEventListener('click', () => {
    if (!validDraft()) return;
    send({ type: 'bid', bid: ui.bidDraft });
  });
  $('tarot-excuse-min').addEventListener('click', () => send({ type: 'play', card: EXCUSE, excuse_mode: 'min' }));
  $('tarot-excuse-max').addEventListener('click', () => send({ type: 'play', card: EXCUSE, excuse_mode: 'max' }));
  $('tarot-excuse-cancel').addEventListener('click', () => {
    ui.excusePending = false;
    renderMe();
  });
  $('tarot-copy').addEventListener('click', async (event) => {
    const button = event.currentTarget;
    const url = new URL(window.location.href);
    url.search = new URLSearchParams({ room: activeRoomId }).toString();
    try {
      await navigator.clipboard.writeText(url.href);
      button.textContent = 'Lien copié !';
      setTimeout(() => { button.textContent = 'Copier le lien'; }, 1500);
    } catch {
      window.prompt('Copiez ce lien pour inviter vos amis :', url.href);
    }
  });

  const requestedRoom = new URLSearchParams(window.location.search).get('room');
  const savedRoom = localStorage.getItem(ROOM_STORAGE_KEY);
  if (requestedRoom) joinRoom(requestedRoom);
  else if (savedRoom) joinRoom(savedRoom, { silent: true });
  else refreshDirectory();
})();
