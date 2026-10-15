(() => {
  'use strict';

  const canvas = document.getElementById('arena');
  const ctx = canvas.getContext('2d');
  const mini = document.getElementById('minimap');
  const miniCtx = mini.getContext('2d');
  const apiBase = window.PEDANTIX_CONFIG?.BACKEND_URL?.replace(/\/+$/, '') || '';
  const backendUrl = new URL(apiBase || window.location.origin);
  const overlay = document.getElementById('start-overlay');
  const startButton = document.getElementById('start-button');
  const message = document.getElementById('connection-message');
  const playerName = (localStorage.getItem('pedantix_auth_user') || '').trim().slice(0, 24);
  const authToken = localStorage.getItem('pedantix_auth_token') || '';
  if (!playerName || !authToken) {
    const next = `${window.location.pathname}${window.location.search}${window.location.hash}`;
    window.location.replace(`/?login=1&next=${encodeURIComponent(next)}`);
    return;
  }
  const keys = { forward: false, back: false, left: false, right: false, fire: false };
  const camera = { x: 1.5, z: 1.5, yaw: 0 };
  const targetCamera = { x: 1.5, z: 1.5 };
  let arena = [];
  let players = [];
  let selfId = '';
  let team = 'blue';
  let socket = null;
  let active = false;
  let lastFrame = 0;
  let lastInput = 0;
  let touchLookX = null;
  let movePointer = null;
  let moveOrigin = null;
  let moveAxis = { x: 0, y: 0 };
  let scores = { blue: 0, red: 0 };
  let winner = null;
  let hasCameraPosition = false;
  let roomStatus = 'lobby';
  let hostId = '';
  let canStart = false;
  let isSpectator = false;

  const $ = (id) => document.getElementById(id);
  const statusLabel = $('server-count');
  const playerLabel = $('player-name');
  playerLabel.textContent = playerName;
  const spectatorBadge = document.createElement('div');
  spectatorBadge.textContent = 'OBSERVATEUR · Vous jouerez au prochain match';
  spectatorBadge.style.cssText = 'position:absolute;z-index:8;top:58px;left:50%;transform:translateX(-50%);padding:9px 14px;border:1px solid #d7ff55aa;border-radius:4px;background:#101827e8;color:#d7ff55;font:700 .68rem "DM Mono",monospace;letter-spacing:.08em;text-align:center;pointer-events:none;white-space:nowrap';
  spectatorBadge.hidden = true;
  $('arena').parentElement.append(spectatorBadge);

  function updateSpectatorUI() {
    spectatorBadge.hidden = !isSpectator;
    $('team-label').textContent = isSpectator ? 'OBSERVATEUR' : (team === 'blue' ? 'BLEU' : 'ROUGE');
    $('team-label').classList.toggle('red', !isSpectator && team === 'red');
    ['control-hint', 'touch-controls'].forEach((id) => {
      $(id).style.display = isSpectator ? 'none' : '';
    });
    ['.crosshair', '.weapon-card', '.health-card'].forEach((selector) => {
      document.querySelector(selector).style.display = isSpectator ? 'none' : '';
    });
    if (isSpectator) {
      Object.keys(keys).forEach((key) => { keys[key] = false; });
      moveAxis = { x: 0, y: 0 };
    }
  }

  function resize() {
    const rect = canvas.getBoundingClientRect();
    const ratio = Math.min(window.devicePixelRatio || 1, 1.25);
    canvas.width = Math.max(1, Math.floor(rect.width * ratio));
    canvas.height = Math.max(1, Math.floor(rect.height * ratio));
  }
  window.addEventListener('resize', resize);
  resize();

  fetch(`${apiBase}/api/voxelstrike/status`).then((response) => response.json()).then((status) => {
    statusLabel.textContent = `${status.players}/${status.capacity} en ligne`;
  }).catch(() => {
    statusLabel.textContent = 'Serveur prêt';
  });

  function showOverlay(title, copy, buttonText) {
    overlay.hidden = false;
    overlay.querySelector('h1').innerHTML = title;
    overlay.querySelector('.intro-copy').textContent = copy;
    startButton.innerHTML = `${buttonText} <span>↗</span>`;
    startButton.disabled = false;
  }

  function joinGame() {
    if (socket?.readyState === WebSocket.OPEN || socket?.readyState === WebSocket.CONNECTING) return;
    startButton.disabled = true;
    startButton.innerHTML = 'CONNEXION AU SERVEUR… <span>↗</span>';
    message.textContent = 'Connexion au salon de jeu…';
    const scheme = backendUrl.protocol === 'https:' ? 'wss:' : 'ws:';
    const query = new URLSearchParams({ name: playerName, token: authToken });
    socket = new WebSocket(`${scheme}//${backendUrl.host}/ws/voxelstrike?${query}`);
    socket.addEventListener('open', () => {
      statusLabel.textContent = 'Serveur connecté';
      active = true;
    });
    socket.addEventListener('message', (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'welcome') {
        selfId = data.id;
        team = data.team;
        isSpectator = Boolean(data.spectator);
        arena = data.arena;
        roomStatus = data.status;
        hostId = data.host_id;
        $('room-code').textContent = `· SALON ${data.room}`;
        $('lobby-room').textContent = data.room;
        $('match-label').textContent = 'SALON D’ATTENTE';
        $('lobby-panel').hidden = false;
        $('feature-row')?.setAttribute('hidden', '');
        updateSpectatorUI();
        if (isSpectator) overlay.hidden = true;
        updateLobby();
        updatePresenceCount();
      } else if (data.type === 'state') {
        const wasInLobby = roomStatus === 'lobby';
        players = data.players;
        const me = players.find((player) => player.id === selfId);
        if (me) {
          isSpectator = Boolean(me.spectator);
          team = me.team;
          updateSpectatorUI();
        }
        scores = data.scores;
        winner = data.winner;
        roomStatus = data.status;
        hostId = data.host_id;
        canStart = data.can_start;
        if (roomStatus === 'lobby') {
          overlay.hidden = false;
          updateLobby();
        } else if (wasInLobby) {
          overlay.hidden = true;
        }
        updateHud();
        updatePresenceCount();
      } else if (data.type === 'full') {
        active = false;
        statusLabel.textContent = 'Serveur complet';
        showOverlay('SERVEUR<br><span>COMPLET</span>', data.message, 'RÉESSAYER');
        $('lobby-panel').hidden = true;
      }
    });
    socket.addEventListener('close', () => {
      active = false;
      Object.keys(keys).forEach((key) => { keys[key] = false; });
      if (statusLabel.textContent === 'Serveur complet') return;
      showOverlay('CONNEXION<br><span>PERDUE</span>', 'La partie a été interrompue. Reconnectez-vous pour rejouer.', 'RECONNECTER');
      $('lobby-panel').hidden = true;
      statusLabel.textContent = 'Déconnecté';
    });
    socket.addEventListener('error', () => {
      message.textContent = 'Impossible de joindre le serveur. Réessayez dans un instant.';
      startButton.innerHTML = 'RÉESSAYER <span>↗</span>';
      startButton.disabled = false;
      statusLabel.textContent = 'Connexion impossible';
    });
  }

  function updateLobby() {
    const isHost = selfId === hostId;
    const lobbyPlayers = $('lobby-players');
    const count = players.length;
    overlay.querySelector('h1').innerHTML = 'SALON<br><span>D’ATTENTE</span>';
    overlay.querySelector('.intro-copy').textContent = 'Retrouvez votre équipe avant le début de la partie.';
    $('lobby-count').textContent = `${count}/${10} JOUEURS`;
    lobbyPlayers.replaceChildren();
    players.forEach((player) => {
      const item = document.createElement('li');
      const name = document.createElement('span');
      const teamName = document.createElement('small');
      name.textContent = `${player.name}${player.id === hostId ? ' · HÔTE' : ''}${player.id === selfId ? ' (vous)' : ''}`;
      teamName.textContent = player.team === 'blue' ? 'BLEU' : 'ROUGE';
      teamName.className = player.team === 'blue' ? 'lobby-team-blue' : 'lobby-team-red';
      item.append(name, teamName);
      lobbyPlayers.append(item);
    });
    if (isHost) {
      $('lobby-message').textContent = count < 2
        ? 'Invitez un autre joueur. La partie démarre à partir de deux joueurs.'
        : 'Tout le monde est prêt ? Lancez la partie.';
      startButton.innerHTML = 'LANCER LA PARTIE <span>↗</span>';
    } else {
      $('lobby-message').textContent = 'En attente du lancement par l’hôte du salon.';
      startButton.innerHTML = 'EN ATTENTE DE L’HÔTE <span>…</span>';
    }
    startButton.disabled = !isHost || !canStart;
  }

  function handlePrimaryAction() {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      joinGame();
      return;
    }
    if (roomStatus === 'lobby') {
      if (selfId === hostId && canStart) {
        canvas.requestPointerLock?.();
        socket.send(JSON.stringify({ type: 'start' }));
        startButton.disabled = true;
        $('lobby-message').textContent = 'Démarrage de la partie…';
      }
      return;
    }
    if (isSpectator) {
      overlay.hidden = true;
      return;
    }
    canvas.requestPointerLock?.();
    overlay.hidden = true;
  }

  function updatePresenceCount() {
    const alive = players.filter((player) => player.alive && !player.spectator).length;
    const spectators = players.filter((player) => player.spectator).length;
    $('alive-count').textContent = `${alive} joueur${alive !== 1 ? 's' : ''} en vie · ${spectators} observateur${spectators !== 1 ? 's' : ''}`;
    $('blue-score').textContent = scores.blue;
    $('red-score').textContent = scores.red;
    const me = players.find((player) => player.id === selfId);
    if (me) {
      targetCamera.x = me.x;
      targetCamera.z = me.z;
      if (!hasCameraPosition) {
        camera.x = me.x;
        camera.z = me.z;
        hasCameraPosition = true;
      }
      $('health-value').textContent = me.hp;
      $('health-bar').style.width = `${me.hp}%`;
      $('health-bar').style.background = me.hp < 35 ? '#ff526e' : 'linear-gradient(90deg,#a6e84e,#d7ff55)';
      $('hit-marker').hidden = !me.hit;
      $('death-overlay').hidden = isSpectator || me.alive;
    }
    if (isSpectator) {
      $('match-label').textContent = 'OBSERVATEUR';
    } else if (roomStatus === 'lobby') {
      $('match-label').textContent = 'SALON D’ATTENTE';
    } else if (winner) {
      $('match-label').textContent = winner === team ? 'VICTOIRE' : 'DÉFAITE';
    } else {
      $('match-label').textContent = 'PARTIE EN COURS';
    }
  }

  function updateHud() {
    updatePresenceCount();
    drawMinimap();
  }

  function isWall(x, z) {
    const row = Math.floor(z);
    const col = Math.floor(x);
    return row < 0 || row >= arena.length || col < 0 || col >= (arena[row] || '').length || arena[row][col] === '#';
  }

  function castRay(angle, width, height) {
    const rayX = Math.sin(angle);
    const rayZ = Math.cos(angle);
    let mapX = Math.floor(camera.x);
    let mapZ = Math.floor(camera.z);
    const deltaX = Math.abs(1 / (rayX || 0.000001));
    const deltaZ = Math.abs(1 / (rayZ || 0.000001));
    const stepX = rayX < 0 ? -1 : 1;
    const stepZ = rayZ < 0 ? -1 : 1;
    let sideX = rayX < 0 ? (camera.x - mapX) * deltaX : (mapX + 1 - camera.x) * deltaX;
    let sideZ = rayZ < 0 ? (camera.z - mapZ) * deltaZ : (mapZ + 1 - camera.z) * deltaZ;
    let side = 0;
    let distance = 0.1;
    for (let step = 0; step < 48; step += 1) {
      if (sideX < sideZ) {
        distance = sideX;
        sideX += deltaX;
        mapX += stepX;
        side = 0;
      } else {
        distance = sideZ;
        sideZ += deltaZ;
        mapZ += stepZ;
        side = 1;
      }
      if (isWall(mapX + 0.01, mapZ + 0.01)) break;
    }
    const correction = Math.max(0.12, distance * Math.cos(angle - camera.yaw));
    const wallHeight = Math.min(height * 1.8, height / correction * 0.78);
    const top = Math.floor(height * 0.51 - wallHeight / 2);
    const texture = side ? 0.77 : 1;
    const shade = Math.max(0.25, 1 - correction / 19) * texture;
    const tile = (mapX * 7 + mapZ * 13 + (side ? 3 : 0)) % 4;
    const base = [[61, 78, 94], [67, 80, 92], [55, 73, 91], [72, 81, 91]][tile];
    const r = Math.round(base[0] * shade);
    const g = Math.round(base[1] * shade);
    const b = Math.round(base[2] * shade);
    ctx.fillStyle = `rgb(${r},${g},${b})`;
    ctx.fillRect(width, top, 3, wallHeight);
    const face = (Math.floor((rayX + rayZ) * 10) % 3 === 0);
    if (face) {
      ctx.fillStyle = `rgba(170,205,224,${0.05 * shade})`;
      ctx.fillRect(width, top, 2, wallHeight);
    }
    ctx.fillStyle = `rgba(2,7,15,${Math.min(0.55, correction / 36)})`;
    ctx.fillRect(width, top + wallHeight - 2, 3, 2);
    return correction;
  }

  function drawPlayerSprites(width, height, wallDepths) {
    const fov = Math.PI / 2.8;
    const visible = players
      .filter((player) => player.id !== selfId && player.alive)
      .map((player) => {
        const dx = player.x - camera.x;
        const dz = player.z - camera.z;
        const distance = Math.hypot(dx, dz);
        return { player, distance, angle: Math.atan2(dx, dz) - camera.yaw };
      })
      .map((item) => ({ ...item, angle: Math.atan2(Math.sin(item.angle), Math.cos(item.angle)) }))
      .filter((item) => Math.abs(item.angle) < fov * 0.6 && item.distance > 0.2)
      .sort((a, b) => b.distance - a.distance);

    for (const item of visible) {
      const depth = item.distance * Math.cos(item.angle);
      if (depth < 0.25) continue;
      const screenX = (0.5 + item.angle / fov) * width;
      if (depth > wallDepths[Math.min(wallDepths.length - 1, Math.floor(screenX / 3))]) continue;
      const scale = Math.min(height * 0.85, height / depth * 0.36);
      const bodyWidth = scale * 0.48;
      const bodyHeight = scale * 1.05;
      const footY = height * 0.53 + bodyHeight * 0.44;
      const color = item.player.team === 'blue' ? '#42bfff' : '#ff4f69';
      const x = screenX - bodyWidth / 2;
      const y = footY - bodyHeight;
      ctx.fillStyle = 'rgba(0,0,0,.36)';
      ctx.fillRect(x - bodyWidth * 0.15, footY - 2, bodyWidth * 1.3, Math.max(2, scale * .08));
      ctx.fillStyle = color;
      ctx.fillRect(x, y + bodyHeight * .26, bodyWidth, bodyHeight * .74);
      ctx.fillStyle = '#d4dae0';
      ctx.fillRect(x + bodyWidth * .18, y, bodyWidth * .64, bodyHeight * .34);
      ctx.fillStyle = '#202b35';
      ctx.fillRect(x + bodyWidth * .18, y + bodyHeight * .16, bodyWidth * .64, bodyHeight * .08);
      ctx.fillStyle = '#141b26';
      ctx.fillRect(x + bodyWidth * .13, footY - bodyHeight * .22, bodyWidth * .25, bodyHeight * .22);
      ctx.fillRect(x + bodyWidth * .62, footY - bodyHeight * .22, bodyWidth * .25, bodyHeight * .22);
      ctx.fillStyle = '#06101c';
      ctx.fillRect(x, y - 8, bodyWidth, 3);
      ctx.fillStyle = color;
      ctx.fillRect(x, y - 8, bodyWidth * (item.player.hp / 100), 3);
      if (item.distance < 9 && bodyWidth > 20) {
        ctx.font = `600 ${Math.max(9, Math.min(13, bodyWidth * .24))}px Manrope, sans-serif`;
        ctx.textAlign = 'center';
        ctx.fillStyle = '#f4f6fa';
        ctx.fillText(item.player.name, screenX, y - 13);
      }
    }
  }

  function drawWeapon(width, height) {
    const scale = Math.min(width, height);
    const baseX = width * 0.52;
    const bottom = height * 1.02;
    ctx.save();
    ctx.translate(baseX, bottom);
    ctx.rotate(-0.04);
    ctx.fillStyle = '#141b23';
    ctx.fillRect(-scale * .045, -scale * .25, scale * .11, scale * .31);
    ctx.fillStyle = '#33414b';
    ctx.fillRect(-scale * .032, -scale * .34, scale * .064, scale * .28);
    ctx.fillStyle = '#60707a';
    ctx.fillRect(-scale * .013, -scale * .36, scale * .026, scale * .08);
    ctx.fillStyle = '#262f38';
    ctx.fillRect(-scale * .07, -scale * .18, scale * .14, scale * .12);
    ctx.fillStyle = '#d7ff55';
    ctx.fillRect(-scale * .008, -scale * .31, scale * .016, scale * .04);
    ctx.restore();
  }

  function render(now) {
    requestAnimationFrame(render);
    if (now - lastFrame < 30) return;
    lastFrame = now;
    const width = canvas.width;
    const height = canvas.height;
    if (!width || !height) return;
    camera.x += (targetCamera.x - camera.x) * 0.32;
    camera.z += (targetCamera.z - camera.z) * 0.32;

    const horizon = height * 0.51;
    const sky = ctx.createLinearGradient(0, 0, 0, horizon);
    sky.addColorStop(0, '#17243a');
    sky.addColorStop(1, '#677588');
    ctx.fillStyle = sky;
    ctx.fillRect(0, 0, width, horizon);
    const ground = ctx.createLinearGradient(0, horizon, 0, height);
    ground.addColorStop(0, '#313a43');
    ground.addColorStop(1, '#111923');
    ctx.fillStyle = ground;
    ctx.fillRect(0, horizon, width, height - horizon);
    ctx.fillStyle = 'rgba(199,214,222,.07)';
    for (let i = 1; i < 8; i += 1) {
      const y = horizon + (height - horizon) * (i / 8) ** 1.8;
      ctx.fillRect(0, y, width, 1);
    }

    const fov = Math.PI / 2.8;
    const wallDepths = new Float32Array(Math.ceil(width / 3));
    for (let x = 0; x < width; x += 3) {
      const rayAngle = camera.yaw + (x / width - .5) * fov;
      wallDepths[Math.floor(x / 3)] = castRay(rayAngle, x, height);
    }
    drawPlayerSprites(width, height, wallDepths);
    drawWeapon(width, height);
  }

  function drawMinimap() {
    if (!arena.length) return;
    const size = mini.width;
    const cell = size / Math.max(arena.length, arena[0].length);
    const offsetX = (size - arena[0].length * cell) / 2;
    const offsetY = (size - arena.length * cell) / 2;
    miniCtx.clearRect(0, 0, size, size);
    miniCtx.fillStyle = '#111a27';
    miniCtx.fillRect(0, 0, size, size);
    arena.forEach((row, z) => [...row].forEach((tile, x) => {
      if (tile === '#') {
        miniCtx.fillStyle = '#536274';
        miniCtx.fillRect(offsetX + x * cell + 1, offsetY + z * cell + 1, cell - 2, cell - 2);
      }
    }));
    players.forEach((player) => {
      if (!player.alive && !player.spectator) return;
      miniCtx.beginPath();
      miniCtx.fillStyle = player.spectator ? '#d7ff55' : (player.team === 'blue' ? '#54c8ff' : '#ff526e');
      miniCtx.arc(offsetX + player.x * cell, offsetY + player.z * cell, player.id === selfId ? 4 : 2.4, 0, Math.PI * 2);
      if (player.spectator) {
        miniCtx.strokeStyle = '#d7ff55';
        miniCtx.lineWidth = 1.5;
        miniCtx.stroke();
      }
      miniCtx.fill();
    });
  }

  function sendInput(now) {
    if (isSpectator || !active || roomStatus !== 'playing' || !socket || socket.readyState !== WebSocket.OPEN || now - lastInput < 50) return;
    lastInput = now;
    const inputKeys = { ...keys };
    if (moveAxis.y < -.25) inputKeys.forward = true;
    if (moveAxis.y > .25) inputKeys.back = true;
    if (moveAxis.x < -.25) inputKeys.left = true;
    if (moveAxis.x > .25) inputKeys.right = true;
    socket.send(JSON.stringify({ type: 'input', yaw: camera.yaw, keys: inputKeys }));
  }

  function animation(now) {
    sendInput(now);
    requestAnimationFrame(animation);
  }
  requestAnimationFrame(render);
  requestAnimationFrame(animation);

  startButton.addEventListener('click', handlePrimaryAction);
  document.addEventListener('pointerlockchange', () => {
    if (document.pointerLockElement === canvas) {
      overlay.hidden = true;
    } else if (active && socket?.readyState === WebSocket.OPEN) {
      showOverlay('EN<br><span>PAUSE</span>', 'La partie continue. Reprenez quand vous êtes prêt.', 'REPRENDRE');
    }
  });
  document.addEventListener('mousemove', (event) => {
    if (document.pointerLockElement === canvas) camera.yaw += event.movementX * .0025;
  });
  document.addEventListener('keydown', (event) => {
    const key = event.key.toLowerCase();
    const map = { z: 'forward', w: 'forward', arrowup: 'forward', s: 'back', arrowdown: 'back', q: 'left', a: 'left', arrowleft: 'left', d: 'right', arrowright: 'right' };
    if (map[key]) {
      keys[map[key]] = true;
      event.preventDefault();
    }
  });
  document.addEventListener('keyup', (event) => {
    const key = event.key.toLowerCase();
    const map = { z: 'forward', w: 'forward', arrowup: 'forward', s: 'back', arrowdown: 'back', q: 'left', a: 'left', arrowleft: 'left', d: 'right', arrowright: 'right' };
    if (map[key]) keys[map[key]] = false;
  });
  canvas.addEventListener('mousedown', (event) => {
    if (event.button === 0 && document.pointerLockElement === canvas) keys.fire = true;
  });
  document.addEventListener('mouseup', () => { keys.fire = false; });
  canvas.addEventListener('click', () => {
    if (!isSpectator && active && roomStatus === 'playing' && document.pointerLockElement !== canvas) canvas.requestPointerLock?.();
  });
  canvas.addEventListener('touchstart', (event) => {
    if (event.touches[0] && event.touches[0].clientX > window.innerWidth * .42) touchLookX = event.touches[0].clientX;
  }, { passive: true });
  canvas.addEventListener('touchmove', (event) => {
    const touch = [...event.touches].find((item) => item.clientX > window.innerWidth * .42);
    if (touch && touchLookX !== null) {
      camera.yaw += (touch.clientX - touchLookX) * .009;
      touchLookX = touch.clientX;
    }
  }, { passive: true });
  canvas.addEventListener('touchend', (event) => {
    if (![...event.touches].some((item) => item.clientX > window.innerWidth * .42)) touchLookX = null;
  });

  const movePad = $('move-pad');
  movePad.addEventListener('pointerdown', (event) => {
    movePointer = event.pointerId;
    moveOrigin = { x: event.clientX, y: event.clientY };
    movePad.setPointerCapture(event.pointerId);
  });
  movePad.addEventListener('pointermove', (event) => {
    if (event.pointerId !== movePointer || !moveOrigin) return;
    moveAxis = {
      x: Math.max(-1, Math.min(1, (event.clientX - moveOrigin.x) / 33)),
      y: Math.max(-1, Math.min(1, (event.clientY - moveOrigin.y) / 33)),
    };
  });
  function releaseMove(event) {
    if (event.pointerId !== movePointer) return;
    movePointer = null;
    moveOrigin = null;
    moveAxis = { x: 0, y: 0 };
  }
  movePad.addEventListener('pointerup', releaseMove);
  movePad.addEventListener('pointercancel', releaseMove);
  const fireButton = $('touch-fire');
  fireButton.addEventListener('pointerdown', (event) => {
    keys.fire = true;
    fireButton.setPointerCapture(event.pointerId);
  });
  fireButton.addEventListener('pointerup', () => { keys.fire = false; });
  fireButton.addEventListener('pointercancel', () => { keys.fire = false; });

  joinGame();

  window.addEventListener('beforeunload', () => socket?.close());
})();
