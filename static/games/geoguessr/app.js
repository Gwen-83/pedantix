(() => {
  const apiBase = window.PEDANTIX_CONFIG?.BACKEND_URL?.replace(/\/+$/, '') || '';
  const home = document.getElementById('geo-home');
  const play = document.getElementById('geo-play');
  const homeError = document.getElementById('geo-home-error');
  const playError = document.getElementById('geo-play-error');
  const variantSelect = document.getElementById('geo-variant');
  const regionSelect = document.getElementById('geo-region');
  const roomVariantSelect = document.getElementById('geo-room-variant');
  const roomRegionSelect = document.getElementById('geo-room-region');
  const roomInput = document.getElementById('geo-room-code');
  const roomDirectory = document.getElementById('geo-room-directory');
  const mapStage = document.getElementById('geo-map-stage');
  const roundResult = document.getElementById('geo-round-result');
  const scoreboard = document.getElementById('geo-scoreboard');
  const params = new URLSearchParams(window.location.search);
  let playerId = localStorage.getItem('geoguessr_player_id');
  if (!playerId) {
    playerId = globalThis.crypto?.randomUUID?.()
      || `geoguessr-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    localStorage.setItem('geoguessr_player_id', playerId);
  }
  const playerName = (localStorage.getItem('pedantix_player_name')
    || localStorage.getItem('pedantix_auth_user')
    || 'Joueur').trim().slice(0, 24);

  let state = null;
  let gameType = null;
  let map = null;
  let guessMarker = null;
  let targetMarker = null;
  let answerLine = null;
  let countryBoundaryLayer = null;
  let countryBoundaryLoading = null;
  let mapLabelsLayer = null;
  let selectedPosition = null;
  let pollingTimer = null;
  let roomRefreshing = false;
  let roomBusy = false;
  let renderedRound = null;
  let renderedResultRound = null;
  let lastResultSignature = '';
  let mapillaryToken = '';
  let googleMapsApiKey = '';
  let googleMapsLoading = null;
  let panoramaViewer = null;
  let googlePanoramaViewer = null;
  let googleLastPanoramaId = '';
  let googlePanoramaRoundKey = '';
  let googleNavigationPending = false;
  let googleNavigationRollback = false;
  let activePanoramaId = '';
  let activePanoramaProvider = '';

  document.getElementById('geo-player-name').textContent = playerName;

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

  function regionLabel(region) {
    return ({ france: 'France', europe: 'Europe', world: 'Monde' })[region] || 'Monde';
  }

  function variantLabel(variant) {
    return variant === 'panorama' ? 'Photo immersive' : 'Villes sur carte';
  }

  function currentRoundResult() {
    if (gameType === 'solo') return state?.last_result || null;
    return state?.last_round || null;
  }

  function roundResultSignature(round) {
    const target = round?.target || round;
    if (!round || !target?.city) return '';
    return `${round.round_number}:${target.city}:${target.country || ''}`;
  }

  function roundResultStorageKey() {
    const gameId = gameType === 'solo' ? state?.game_id : state?.room_id;
    return `geoguessr_seen_result_${gameType}_${gameId}`;
  }

  function isWaitingForNextRound() {
    const round = currentRoundResult();
    const signature = roundResultSignature(round);
    return state?.status === 'playing'
      && !!signature
      && round.round_number === state.round_number - 1
      && localStorage.getItem(roundResultStorageKey()) !== signature;
  }

  async function loadPanoramaConfig() {
    const setup = document.getElementById('geo-panorama-setup');
    try {
      const config = await request('/api/geoguessr/config');
      mapillaryToken = config.mapillary_access_token || '';
      googleMapsApiKey = config.google_maps_browser_api_key || '';
      const panoramaUnavailable = !config.panorama_available;
      variantSelect.querySelector('option[value="panorama"]').disabled = panoramaUnavailable;
      roomVariantSelect.querySelector('option[value="panorama"]').disabled = panoramaUnavailable;
      if (panoramaUnavailable) {
        setup.replaceChildren(document.createTextNode(
          'Le mode photo nécessite GOOGLE_MAPS_BROWSER_API_KEY et GOOGLE_MAPS_SERVER_API_KEY, ou MAPILLARY_ACCESS_TOKEN configuré sur le serveur. '
        ));
        const link = document.createElement('a');
        link.href = config.google_streetview_configured
          ? 'https://www.mapillary.com/dashboard/developers'
          : 'https://console.cloud.google.com/google/maps-apis/credentials';
        link.target = '_blank';
        link.rel = 'noopener';
        link.textContent = config.google_streetview_configured
          ? 'Créer un jeton Mapillary de secours'
          : 'Configurer les clés Google Maps';
        setup.append(link);
        setup.hidden = false;
      } else if (config.google_streetview_configured
        && !config.google_streetview_available && mapillaryToken) {
        setup.textContent =
          `Seuil Google atteint (${config.google_monthly_events_reserved}/${config.google_monthly_event_limit}) : les nouvelles parties photo utiliseront Mapillary.`;
        setup.hidden = false;
      } else {
        setup.hidden = true;
      }
      if (state?.variant === 'panorama') renderView();
    } catch (error) {
      setup.textContent = `Configuration des photos impossible à charger : ${error.message}`;
      setup.hidden = false;
      variantSelect.querySelector('option[value="panorama"]').disabled = true;
      roomVariantSelect.querySelector('option[value="panorama"]').disabled = true;
    }
  }

  function loadGoogleMaps() {
    if (window.google?.maps?.StreetViewPanorama) return Promise.resolve();
    if (googleMapsLoading) return googleMapsLoading;
    googleMapsLoading = new Promise((resolve, reject) => {
      if (!googleMapsApiKey) {
        reject(new Error('La clé Google Maps n’est pas disponible.'));
        return;
      }
      const script = document.createElement('script');
      script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(googleMapsApiKey)}&v=weekly&language=fr&region=FR`;
      script.async = true;
      script.onload = () => resolve();
      script.onerror = () => {
        googleMapsLoading = null;
        reject(new Error('Google Maps JavaScript API ne s’est pas chargée.'));
      };
      document.head.append(script);
    });
    return googleMapsLoading;
  }

  function googleGameRoundKey() {
    return `${gameType}:${state?.game_id || state?.room_id}:${state?.round_number}`;
  }

  async function handleGooglePanoramaChange() {
    if (!googlePanoramaViewer) return;
    const currentPano = googlePanoramaViewer.getPano();
    if (!currentPano) return;
    if (googleNavigationRollback) {
      googleLastPanoramaId = currentPano;
      googleNavigationRollback = false;
      return;
    }
    const roundKey = googleGameRoundKey();
    if (googlePanoramaRoundKey !== roundKey || !googleLastPanoramaId) {
      googlePanoramaRoundKey = roundKey;
      googleLastPanoramaId = currentPano;
      return;
    }
    if (currentPano === googleLastPanoramaId || googleNavigationPending) return;

    const previousPano = googleLastPanoramaId;
    googleLastPanoramaId = currentPano;
    googleNavigationPending = true;
    googlePanoramaViewer.setOptions({ linksControl: false, clickToGo: false });
    try {
      const data = await post('/api/geoguessr/panorama/authorize', {
        player_id: playerId,
        ...(gameType === 'solo' ? { game_id: state.game_id } : { room_id: state.room_id }),
        navigation: true,
      });
      if (!data.allowed) {
        googleLastPanoramaId = previousPano;
        googleNavigationRollback = true;
        googlePanoramaViewer.setPano(previousPano);
        showError(playError, 'La limite mensuelle de navigation Google est atteinte. Cette photo ne peut plus avancer.');
      }
    } catch (error) {
      googleLastPanoramaId = previousPano;
      googleNavigationRollback = true;
      googlePanoramaViewer.setPano(previousPano);
      showError(playError, `Impossible de vérifier le quota de navigation : ${error.message}`);
    } finally {
      googleNavigationPending = false;
      googlePanoramaViewer?.setOptions({ linksControl: true, clickToGo: true });
    }
  }

  async function showPanorama(imageId) {
    const provider = state?.panorama_provider || 'mapillary';
    if (!imageId || (provider === 'mapillary' && (!mapillaryToken || !window.mapillary?.Viewer))) {
      showError(playError, 'Le lecteur de photos ne peut pas être chargé. Vérifiez la configuration et votre connexion.');
      return;
    }
    if (activePanoramaProvider === provider && activePanoramaId === imageId) return;
    activePanoramaId = imageId;
    activePanoramaProvider = provider;
    try {
      const container = document.getElementById('geo-panorama-viewer');
      document.querySelector('#geo-panorama-panel > small').textContent =
        provider === 'google' ? 'Google Street View' : 'Images © Mapillary contributors';
      if (provider === 'google') {
        googlePanoramaRoundKey = googleGameRoundKey();
        googleLastPanoramaId = imageId;
        await loadGoogleMaps();
        const authorization = await post('/api/geoguessr/panorama/authorize', {
          player_id: playerId,
          ...(gameType === 'solo' ? { game_id: state.game_id } : { room_id: state.room_id }),
        });
        if (!authorization.allowed) {
          throw new Error('Le quota Google Street View est atteint. Les prochaines parties photo passeront sur Mapillary.');
        }
        if (panoramaViewer) {
          panoramaViewer.remove();
          panoramaViewer = null;
        }
        if (!googlePanoramaViewer) {
          googlePanoramaViewer = new window.google.maps.StreetViewPanorama(container, {
            pano: imageId,
            linksControl: true,
            clickToGo: true,
            addressControl: false,
            enableCloseButton: false,
            fullscreenControl: true,
            panControl: true,
            zoomControl: true,
            motionTracking: false,
            keyboardShortcuts: true,
          });
          googlePanoramaViewer.addListener('pano_changed', handleGooglePanoramaChange);
        } else {
          googlePanoramaViewer.setPano(imageId);
        }
        document.querySelector('#geo-panorama-panel > small').textContent =
          'Google Street View · Cliquez sur les flèches dans la photo pour avancer.';
      } else {
        if (googlePanoramaViewer) {
          window.google?.maps?.event?.clearInstanceListeners(googlePanoramaViewer);
          googlePanoramaViewer.setVisible(false);
          googlePanoramaViewer = null;
          document.getElementById('geo-panorama-viewer').replaceChildren();
        }
        if (!panoramaViewer) {
          panoramaViewer = new window.mapillary.Viewer({
            accessToken: mapillaryToken,
            container: 'geo-panorama-viewer',
            imageId,
          });
        } else {
          await panoramaViewer.moveTo(imageId);
        }
      }
      requestAnimationFrame(() => panoramaViewer?.resize());
    } catch (error) {
      activePanoramaId = '';
      activePanoramaProvider = '';
      googleLastPanoramaId = '';
      googlePanoramaRoundKey = '';
      showError(playError, `Impossible d’ouvrir cette photo : ${error.message || 'erreur du lecteur'}`);
    }
  }

  function mapView(region) {
    if (region === 'france') return { center: [46.6, 2.4], zoom: 5 };
    if (region === 'europe') return { center: [51.5, 12], zoom: 4 };
    return { center: [20, 0], zoom: 2 };
  }

  function ensureMap() {
    if (map) {
      if (!countryBoundaryLayer && !countryBoundaryLoading) loadCountryBoundaries();
      return true;
    }
    if (!window.L) {
      showError(playError, 'La carte ne s’est pas chargée. Vérifiez votre connexion puis rechargez la page.');
      return false;
    }
    map = L.map('geo-map', { worldCopyJump: true, minZoom: 2, maxZoom: 18 })
      .setView([20, 0], 2);
    loadCountryBoundaries();
    map.on('click', (event) => {
      if (!state || state.status !== 'playing' || guessLocked()) return;
      selectedPosition = { latitude: event.latlng.lat, longitude: event.latlng.lng };
      setGuessMarker(selectedPosition.latitude, selectedPosition.longitude);
      document.getElementById('geo-submit-guess').disabled = false;
      document.getElementById('geo-round-message').textContent =
        `Estimation sélectionnée : ${event.latlng.lat.toFixed(2)}, ${event.latlng.lng.toFixed(2)}. Vous pouvez encore la déplacer.`;
    });
    return true;
  }

  function setMapStyle(isPanorama) {
    if (!map) return;
    if (isPanorama && !mapLabelsLayer) {
      mapLabelsLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>',
      }).addTo(map);
    } else if (!isPanorama && mapLabelsLayer) {
      map.removeLayer(mapLabelsLayer);
      mapLabelsLayer = null;
    }

    countryBoundaryLayer?.setStyle({
      fillOpacity: isPanorama ? 0 : 1,
    });
    const attribution = document.querySelector('.geo-map-actions > span');
    attribution.textContent = isPanorama
      ? 'Carte © OpenStreetMap · frontières © Natural Earth'
      : 'Frontières © Natural Earth (domaine public) · sans noms de villes';
  }

  function loadCountryBoundaries() {
    if (countryBoundaryLayer || countryBoundaryLoading) return;
    countryBoundaryLoading = fetch('/static/games/geoguessr/data/countries.geojson')
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
      })
      .then((countries) => {
        const isPanorama = state?.variant === 'panorama';
        countryBoundaryLayer = L.geoJSON(countries, {
          interactive: false,
          style: {
            color: '#63716f',
            weight: 1,
            opacity: 0.9,
            fillColor: '#e8e9df',
            fillOpacity: isPanorama ? 0 : 1,
          },
        }).addTo(map);
        countryBoundaryLayer.bringToBack();
      })
      .catch((error) => {
        countryBoundaryLoading = null;
        showError(playError, `Impossible de charger les frontières de la carte : ${error.message}`);
      });
  }

  function clearMapMarkers() {
    for (const layer of [guessMarker, targetMarker, answerLine]) {
      if (layer && map) map.removeLayer(layer);
    }
    guessMarker = null;
    targetMarker = null;
    answerLine = null;
    selectedPosition = null;
  }

  function setGuessMarker(latitude, longitude) {
    if (guessMarker) map.removeLayer(guessMarker);
    guessMarker = L.circleMarker([latitude, longitude], {
      radius: 8,
      color: '#ffffff',
      weight: 3,
      fillColor: '#16a34a',
      fillOpacity: 1,
    }).addTo(map);
  }

  function showAnswerOnMap(target, guess) {
    clearMapMarkers();
    if (guess) setGuessMarker(guess.latitude, guess.longitude);
    targetMarker = L.circleMarker([target.latitude, target.longitude], {
      radius: 9,
      color: '#ffffff',
      weight: 3,
      fillColor: '#ef4444',
      fillOpacity: 1,
    }).addTo(map).bindTooltip(`${target.city}, ${target.country}`);
    if (guess) {
      answerLine = L.polyline([
        [guess.latitude, guess.longitude],
        [target.latitude, target.longitude],
      ], { color: '#fbbf24', weight: 3, dashArray: '7 7' }).addTo(map);
      map.fitBounds(answerLine.getBounds().pad(0.22), { maxZoom: 7 });
    } else {
      map.setView([target.latitude, target.longitude], 5);
    }
  }

  function soloGuessMarker(result) {
    return {
      latitude: result.guess_latitude,
      longitude: result.guess_longitude,
    };
  }

  function guessLocked() {
    if (!state || state.status !== 'playing') return true;
    return gameType === 'room' && !!state.player?.submitted;
  }

  function startPolling() {
    stopPolling();
    if (gameType !== 'room') return;
    pollingTimer = window.setInterval(refreshRoom, 1300);
  }

  function stopPolling() {
    if (pollingTimer) window.clearInterval(pollingTimer);
    pollingTimer = null;
    roomRefreshing = false;
  }

  function showHome(clearActiveGame = true) {
    stopPolling();
    if (panoramaViewer) {
      panoramaViewer.remove();
      panoramaViewer = null;
    }
    if (googlePanoramaViewer) {
      window.google?.maps?.event?.clearInstanceListeners(googlePanoramaViewer);
      googlePanoramaViewer.setVisible(false);
      googlePanoramaViewer = null;
      document.getElementById('geo-panorama-viewer').replaceChildren();
    }
    activePanoramaId = '';
    activePanoramaProvider = '';
    googleLastPanoramaId = '';
    googlePanoramaRoundKey = '';
    googleNavigationPending = false;
    googleNavigationRollback = false;
    lastResultSignature = '';
    state = null;
    gameType = null;
    home.hidden = false;
    play.hidden = true;
    if (clearActiveGame) {
      localStorage.setItem('geoguessr_active_game_mode', 'home');
      localStorage.removeItem('geoguessr_active_room_id');
    }
    history.replaceState(null, '', window.location.pathname);
    refreshRoomDirectory();
  }

  function renderRoomDirectory(rooms) {
    roomDirectory.replaceChildren();
    if (!rooms.length) {
      const empty = document.createElement('p');
      empty.className = 'geo-room-empty';
      empty.textContent = 'Aucun salon ouvert pour le moment.';
      roomDirectory.append(empty);
      return;
    }
    for (const room of rooms) {
      const card = document.createElement('div');
      card.className = 'geo-room-card';
      const copy = document.createElement('span');
      copy.className = 'geo-room-card-copy';
      const title = document.createElement('strong');
      title.textContent = `Salon ${room.room_id}`;
      const details = document.createElement('small');
      const phase = room.status === 'playing' ? 'En cours' : 'En attente';
      details.textContent = `${room.player_count}/${room.max_players} joueurs · ${regionLabel(room.region)} · ${phase}`;
      copy.append(title, details);
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'geo-secondary-button';
      button.textContent = room.is_member ? 'Reprendre' : room.status === 'lobby' ? 'Rejoindre' : 'En cours';
      button.disabled = !room.is_member && room.status !== 'lobby';
      if (!button.disabled) button.addEventListener('click', () => joinRoom(room.room_id));
      card.append(copy, button);
      roomDirectory.append(card);
    }
  }

  async function refreshRoomDirectory() {
    roomDirectory.textContent = 'Chargement des salons…';
    try {
      const data = await request(`/api/geoguessr/rooms?player_id=${encodeURIComponent(playerId)}`);
      renderRoomDirectory(data.rooms || []);
    } catch (error) {
      roomDirectory.textContent = `Impossible de charger les salons : ${error.message}`;
    }
  }

  function renderPlayers() {
    const list = document.getElementById('geo-player-list');
    list.replaceChildren(...state.players.map((player) => {
      const item = document.createElement('li');
      const name = document.createElement('span');
      name.textContent = `${player.name}${player.player_id === state.host_player_id ? ' (hôte)' : ''}`;
      const status = document.createElement('small');
      status.textContent = state.status === 'lobby'
        ? 'Dans le salon'
        : player.submitted ? 'Estimation validée' : `${player.total_score.toLocaleString('fr-FR')} points`;
      item.append(name, status);
      return item;
    }));
  }

  function renderLobby() {
    const lobby = document.getElementById('geo-lobby');
    lobby.hidden = false;
    const inviteUrl = new URL(window.location.href);
    inviteUrl.search = new URLSearchParams({ room: state.room_id }).toString();
    document.getElementById('geo-lobby-status').textContent =
      `${state.players.length}/${state.max_players} joueurs · ${regionLabel(state.region)}. Il faut au moins deux joueurs pour démarrer.`;
    document.getElementById('geo-invite-code').textContent = `Code : ${state.room_id}`;
    document.getElementById('geo-copy-invite').dataset.inviteUrl = inviteUrl.href;
    renderPlayers();
    const startButton = document.getElementById('geo-start-game');
    startButton.hidden = playerId !== state.host_player_id;
    startButton.disabled = !state.can_start || roomBusy;
    document.getElementById('geo-map-stage').hidden = true;
    document.getElementById('geo-target-name').textContent = state.variant === 'panorama'
      ? 'La photo sera dévoilée au lancement'
      : 'La ville sera dévoilée au lancement';
    document.getElementById('geo-game-mode').textContent =
      `Salon multijoueur · ${variantLabel(state.variant)}`;
    document.getElementById('geo-round-heading').textContent = `Salon ${state.room_id}`;
    document.getElementById('geo-game-hint').textContent =
      `${variantLabel(state.variant)} · ${regionLabel(state.region)} · 5 manches communes`;
  }

  function renderRoundResult(round, ownResult) {
    if (!round?.target) return;
    const signature = roundResultSignature(round);
    const waitingForNextRound = isWaitingForNextRound();
    if (signature === lastResultSignature && waitingForNextRound) return;
    if (!waitingForNextRound && state?.status !== 'finished') {
      roundResult.hidden = true;
      roundResult.replaceChildren();
      lastResultSignature = signature;
      return;
    }
    if (signature === lastResultSignature && state?.status === 'finished') return;
    lastResultSignature = signature;
    roundResult.replaceChildren();
    roundResult.hidden = false;
    const heading = document.createElement('h2');
    heading.textContent = state?.variant === 'panorama'
      ? `Manche ${round.round_number} : lieu de la photo`
      : `Manche ${round.round_number} : ${round.target.city}, ${round.target.country}`;
    roundResult.append(heading);
    if (ownResult) {
      const detail = document.createElement('p');
      detail.textContent =
        `Votre estimation était à ${ownResult.distance_km.toLocaleString('fr-FR')} km · ${ownResult.score.toLocaleString('fr-FR')} points.`;
      roundResult.append(detail);
    }
    if (Array.isArray(round.guesses)) {
      const ranking = document.createElement('ol');
      [...round.guesses].sort((a, b) => b.score - a.score).forEach((guess) => {
        const item = document.createElement('li');
        item.textContent = `${guess.name} · ${guess.distance_km.toLocaleString('fr-FR')} km · ${guess.score.toLocaleString('fr-FR')} points`;
        ranking.append(item);
      });
      roundResult.append(ranking);
    }
    if (waitingForNextRound) {
      const continueButton = document.createElement('button');
      continueButton.type = 'button';
      continueButton.className = 'geo-primary-button';
      continueButton.textContent = state?.variant === 'panorama' ? 'Manche suivante' : 'Ville suivante';
      continueButton.addEventListener('click', () => {
        localStorage.setItem(roundResultStorageKey(), signature);
        clearMapMarkers();
        const view = mapView(state.region);
        map.setView(view.center, view.zoom);
        renderView();
      });
      roundResult.append(continueButton);
    }
  }

  function renderFinalScoreboard() {
    scoreboard.replaceChildren();
    scoreboard.hidden = false;
    const heading = document.createElement('h2');
    const ownScore = state.total_score ?? state.player?.total_score ?? 0;
    heading.textContent = `Partie terminée · ${ownScore.toLocaleString('fr-FR')} points`;
    scoreboard.append(heading);
    const list = document.createElement('ol');
    const scores = gameType === 'solo'
      ? [{ name: playerName, total_score: state.total_score }]
      : [...state.players].sort((a, b) => b.total_score - a.total_score);
    for (const player of scores) {
      const item = document.createElement('li');
      item.textContent = `${player.name} · ${player.total_score.toLocaleString('fr-FR')} points`;
      list.append(item);
    }
    scoreboard.append(list);
  }

  function renderView() {
    if (!state) return;
    home.hidden = true;
    play.hidden = false;
    hideError(playError);
    const region = state.region || regionSelect.value;
    const isRoom = gameType === 'room';
    const isPanorama = state.variant === 'panorama';
    const waitingForNextRound = isWaitingForNextRound();
    if (!isPanorama) {
      if (panoramaViewer) {
        panoramaViewer.remove();
        panoramaViewer = null;
      }
      if (googlePanoramaViewer) {
        window.google?.maps?.event?.clearInstanceListeners(googlePanoramaViewer);
        googlePanoramaViewer.setVisible(false);
        googlePanoramaViewer = null;
      }
      activePanoramaId = '';
      activePanoramaProvider = '';
      googleLastPanoramaId = '';
      googlePanoramaRoundKey = '';
      googleNavigationPending = false;
      googleNavigationRollback = false;
    }
    document.getElementById('geo-game-mode').textContent =
      `${isRoom ? 'Multijoueur' : 'Solo'} · ${variantLabel(state.variant)} · ${regionLabel(region)}`;
    const completedRound = currentRoundResult();
    document.getElementById('geo-round-heading').textContent = state.status === 'finished'
      ? 'Partie terminée'
      : waitingForNextRound
        ? `Résultat de la manche ${completedRound.round_number}`
        : `Manche ${state.round_number} sur ${state.round_count}`;
    document.getElementById('geo-game-hint').textContent = isPanorama
      ? 'Explorez la photo avec la souris ou le tactile, puis situez-la sur la carte.'
      : isRoom
        ? 'Une estimation par joueur et par manche. Le score apparaît quand tout le monde a répondu.'
        : 'Placez un marqueur sur la carte, puis validez votre estimation.';
    document.getElementById('geo-total-score').textContent =
      (state.total_score ?? state.player?.total_score ?? 0).toLocaleString('fr-FR');
    document.getElementById('geo-target-label').textContent = isPanorama ? 'Lieu à retrouver' : 'Ville à placer';
    document.getElementById('geo-target-name').textContent = waitingForNextRound
      ? 'Consultez la distance avant de continuer'
      : isPanorama
      ? 'Explorez la photo, puis faites votre estimation'
      : state.prompt
      ? `${state.prompt.city}, ${state.prompt.country}`
      : state.target ? `${state.target.city}, ${state.target.country}` : 'En attente de la manche';
    document.getElementById('geo-lobby').hidden = !isRoom || state.status !== 'lobby';
    mapStage.hidden = state.status === 'lobby';
    document.getElementById('geo-panorama-panel').hidden = !isPanorama || state.status === 'lobby';

    if (isRoom && state.status === 'lobby') {
      renderLobby();
      return;
    }
    if (!ensureMap()) return;
    setMapStyle(isPanorama);
    requestAnimationFrame(() => map.invalidateSize());
    if (isPanorama && state.status === 'playing' && state.image_id) showPanorama(state.image_id);
    const roundNumber = state.round_number;
    if (renderedRound !== roundNumber) {
      clearMapMarkers();
      renderedRound = roundNumber;
      document.getElementById('geo-submit-guess').disabled = true;
      roundResult.hidden = true;
      roundResult.replaceChildren();
      lastResultSignature = '';
    }
    const locked = guessLocked();
    document.getElementById('geo-submit-guess').disabled = locked || !selectedPosition;
    document.getElementById('geo-map').classList.toggle('geo-map-disabled', locked);
    document.getElementById('geo-round-message').textContent = state.status === 'finished'
      ? 'Toutes les manches sont terminées.'
      : locked ? 'Votre position est validée. En attente des autres joueurs…'
        : isPanorama
          ? 'Naviguez dans la photo, puis cliquez sur la carte pour choisir votre estimation.'
          : 'Cliquez sur la carte pour placer votre estimation.';

    if (isRoom) {
      renderPlayers();
      if (state.last_round) {
        const ownResult = state.last_round.guesses.find((guess) => guess.player_id === playerId);
        renderRoundResult(state.last_round, ownResult);
        if (waitingForNextRound && ownResult) {
          showAnswerOnMap(state.last_round.target, ownResult);
        }
      }
      if (state.player?.guess && locked) {
        selectedPosition = state.player.guess;
        setGuessMarker(selectedPosition.latitude, selectedPosition.longitude);
      }
    } else if (state.last_result) {
      renderRoundResult({
        round_number: state.last_result.round_number,
        target: state.last_result,
      }, state.last_result);
      if (waitingForNextRound) {
        showAnswerOnMap(state.last_result, soloGuessMarker(state.last_result));
      }
    }

    if (state.status === 'finished') {
      const finalTarget = isRoom ? state.last_round?.target : state.last_result;
      const finalGuess = isRoom
        ? state.last_round?.guesses.find((guess) => guess.player_id === playerId)
        : state.last_result ? soloGuessMarker(state.last_result) : null;
      if (finalTarget && finalGuess) showAnswerOnMap(finalTarget, finalGuess);
      renderFinalScoreboard();
      stopPolling();
    } else {
      scoreboard.hidden = true;
      if (isRoom && !pollingTimer) startPolling();
    }
  }

  async function startSolo() {
    if (!ensureMap()) return;
    const button = document.getElementById('geo-solo-button');
    setBusy(button, true, 'Préparation…');
    hideError(homeError);
    try {
      state = await post('/api/geoguessr/solo/new', {
        player_id: playerId,
        player_name: playerName,
        region: regionSelect.value,
        variant: variantSelect.value,
      });
      gameType = 'solo';
      localStorage.setItem('geoguessr_active_game_mode', 'solo');
      localStorage.setItem('geoguessr_solo_game_id', state.game_id);
      localStorage.removeItem('geoguessr_active_room_id');
      history.replaceState(null, '', `${window.location.pathname}?mode=solo`);
      renderedRound = null;
      renderView();
      const view = mapView(state.region);
      map.setView(view.center, view.zoom);
    } catch (error) {
      showError(homeError, error.message);
    } finally {
      setBusy(button, false);
    }
  }

  async function resumeSolo(gameId) {
    try {
      state = await request(`/api/geoguessr/solo/${encodeURIComponent(gameId)}?player_id=${encodeURIComponent(playerId)}`);
      gameType = 'solo';
      localStorage.setItem('geoguessr_active_game_mode', 'solo');
      localStorage.setItem('geoguessr_solo_game_id', state.game_id);
      regionSelect.value = state.region;
      renderedRound = null;
      lastResultSignature = '';
      renderView();
      const view = mapView(state.region);
      map.setView(view.center, view.zoom);
    } catch (error) {
      showError(homeError, `Impossible de reprendre cette partie : ${error.message}`);
    }
  }

  async function submitGuess() {
    if (!state || !selectedPosition || guessLocked() || roomBusy) return;
    roomBusy = true;
    const button = document.getElementById('geo-submit-guess');
    button.disabled = true;
    hideError(playError);
    try {
      if (gameType === 'solo') {
        const response = await post('/api/geoguessr/solo/guess', {
          game_id: state.game_id,
          player_id: playerId,
          player_name: playerName,
          region: state.region,
          ...selectedPosition,
        });
        state = response;
        renderedRound = null;
        renderView();
        if (state.status !== 'finished') {
          const view = mapView(state.region);
          map.setView(view.center, view.zoom);
        }
      } else {
        const response = await post('/api/geoguessr/room/guess', {
          room_id: state.room_id,
          player_id: playerId,
          player_name: playerName,
          ...selectedPosition,
        });
        state = response;
        renderView();
      }
    } catch (error) {
      showError(playError, error.message);
      button.disabled = false;
    } finally {
      roomBusy = false;
      if (state?.status === 'lobby') renderLobby();
    }
  }

  async function createRoom() {
    const button = document.getElementById('geo-create-room');
    setBusy(button, true, 'Création…');
    hideError(homeError);
    try {
      state = await post('/api/geoguessr/room/create', {
        player_id: playerId,
        player_name: playerName,
        region: roomRegionSelect.value,
        variant: roomVariantSelect.value,
      });
      enterRoom();
    } catch (error) {
      showError(homeError, error.message);
    } finally {
      setBusy(button, false);
    }
  }

  async function joinRoom(rawRoomId) {
    const roomId = rawRoomId.trim().toUpperCase();
    if (!roomId) {
      showError(homeError, 'Saisissez le code du salon.');
      return;
    }
    hideError(homeError);
    try {
      state = await post('/api/geoguessr/room/join', {
        room_id: roomId,
        player_id: playerId,
        player_name: playerName,
      });
      enterRoom();
    } catch (error) {
      showError(homeError, error.message);
    }
  }

  function enterRoom() {
    gameType = 'room';
    variantSelect.value = state.variant || 'cities';
    roomVariantSelect.value = state.variant || 'cities';
    roomRegionSelect.value = state.region;
    regionSelect.value = state.region;
    localStorage.setItem('geoguessr_active_game_mode', 'room');
    localStorage.setItem('geoguessr_active_room_id', state.room_id);
    history.replaceState(null, '', `${window.location.pathname}?room=${encodeURIComponent(state.room_id)}`);
    renderedRound = null;
    lastResultSignature = '';
    renderView();
    startPolling();
    if (state.status === 'playing') {
      const view = mapView(state.region);
      map.setView(view.center, view.zoom);
    }
  }

  async function startRoom() {
    if (!state || roomBusy) return;
    roomBusy = true;
    const button = document.getElementById('geo-start-game');
    button.disabled = true;
    hideError(playError);
    try {
      state = await post('/api/geoguessr/room/start', {
        room_id: state.room_id,
        player_id: playerId,
        player_name: playerName,
      });
      renderView();
      const view = mapView(state.region);
      map.setView(view.center, view.zoom);
    } catch (error) {
      showError(playError, error.message);
    } finally {
      roomBusy = false;
      if (state?.status === 'lobby') renderLobby();
    }
  }

  async function refreshRoom() {
    if (!state || gameType !== 'room' || roomRefreshing) return;
    roomRefreshing = true;
    try {
      state = await request(
        `/api/geoguessr/room/${encodeURIComponent(state.room_id)}?player_id=${encodeURIComponent(playerId)}`,
      );
      renderView();
    } catch (error) {
      stopPolling();
      showError(playError, `Connexion au salon interrompue : ${error.message}`);
    } finally {
      roomRefreshing = false;
    }
  }

  document.getElementById('geo-solo-button').addEventListener('click', startSolo);
  document.getElementById('geo-create-room').addEventListener('click', createRoom);
  document.getElementById('geo-refresh-rooms').addEventListener('click', refreshRoomDirectory);
  document.getElementById('geo-join-room').addEventListener('click', () => joinRoom(roomInput.value));
  roomInput.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      joinRoom(roomInput.value);
    }
  });
  document.getElementById('geo-start-game').addEventListener('click', startRoom);
  document.getElementById('geo-submit-guess').addEventListener('click', submitGuess);
  document.getElementById('geo-home-button').addEventListener('click', () => showHome());
  document.getElementById('geo-copy-invite').addEventListener('click', async (event) => {
    const url = event.currentTarget.dataset.inviteUrl;
    try {
      await navigator.clipboard.writeText(url);
      event.currentTarget.textContent = 'Lien copié !';
      window.setTimeout(() => { event.currentTarget.textContent = 'Copier le lien'; }, 1600);
    } catch {
      window.prompt('Copiez ce lien pour inviter vos amis :', url);
    }
  });
  document.querySelectorAll('[data-shared-game-mode="multi"]').forEach((button) => {
    button.addEventListener('click', () => {
      roomRegionSelect.value = regionSelect.value;
      roomVariantSelect.value = variantSelect.value;
    });
  });
  variantSelect.addEventListener('change', () => {
    roomVariantSelect.value = variantSelect.value;
    const panorama = variantSelect.value === 'panorama';
    document.getElementById('geo-home-title').textContent =
      panorama ? 'Où cette photo a-t-elle été prise ?' : 'Où se trouve cette ville ?';
    document.querySelector('#geo-home .geo-intro').textContent = panorama
      ? 'Explorez une vraie photo de rue avec Google Street View ou Mapillary, puis placez votre estimation sur la carte. Jusqu’à 5 000 points par manche.'
      : 'Un nom de ville s’affiche. Placez votre estimation sur la carte : plus vous êtes proche, plus vous marquez de points. Jusqu’à 5 000 points par manche.';
    document.querySelector('#geo-solo-button strong').textContent =
      panorama ? 'Jouer avec des photos' : 'Jouer en solo';
    document.querySelector('#geo-solo-button small').textContent = panorama
      ? 'Explorez cinq lieux réels et retrouvez-les sur la carte.'
      : 'Enchaînez cinq villes et comparez votre score.';
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !play.hidden) showHome();
  });

  if (params.has('room')) {
    joinRoom(params.get('room'));
  } else if (localStorage.getItem('geoguessr_active_game_mode') === 'room'
    && localStorage.getItem('geoguessr_active_room_id')) {
    joinRoom(localStorage.getItem('geoguessr_active_room_id'));
  } else if (localStorage.getItem('geoguessr_active_game_mode') === 'solo'
    && localStorage.getItem('geoguessr_solo_game_id')) {
    resumeSolo(localStorage.getItem('geoguessr_solo_game_id'));
  } else {
    localStorage.removeItem('geoguessr_active_room_id');
    showHome(false);
  }
  loadPanoramaConfig();
})();
