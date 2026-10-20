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
  const roomRoundCountInput = document.getElementById('geo-room-round-count');
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
  let revealedGuessMarkers = [];
  let revealedAnswerLines = [];
  let countryBoundaryLayer = null;
  let countryBoundaryLoading = null;
  let mapLabelsLayer = null;
  let mapLabelsLayerFallback = false;
  let mapLabelsFallbackErrorShown = false;
  let mapCitiesLayer = null;
  let physicalFeaturesLoading = null;
  let physicalFeatureLayers = [];
  let mountainRangeLabelMarkers = [];
  let selectedPosition = null;
  let pollingTimer = null;
  let roundCountdownTimer = null;
  let roomRefreshing = false;
  let roomBusy = false;
  let renderedRound = null;
  let renderedResultRound = null;
  let lastResultSignature = '';
  let leaderboardLoading = false;
  let lastLeaderboardGame = '';
  let mapillaryToken = '';
  let googleMapsApiKey = '';
  let googleMapsLoading = null;
  let googleMapsAuthFailed = false;
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
    if (!button) return;
    if (!button.dataset.label) button.dataset.label = button.textContent;
    button.disabled = busy;
    button.textContent = busy ? busyText : button.dataset.label;
  }

  async function refreshLeaderboard() {
    if (leaderboardLoading) return;
    leaderboardLoading = true;
    const list = document.getElementById('geo-leaderboard');
    const button = document.getElementById('geo-refresh-leaderboard');
    button.disabled = true;
    try {
      const scores = await request('/api/geoguessr/leaderboard');
      list.replaceChildren();
      if (!scores.length) {
        const empty = document.createElement('li');
        empty.className = 'geo-leaderboard-empty';
        empty.textContent = 'Aucun score enregistré pour le moment.';
        list.append(empty);
        return;
      }
      scores.forEach((score, index) => {
        const item = document.createElement('li');
        const rank = document.createElement('span');
        rank.className = 'geo-leaderboard-rank';
        rank.textContent = `${index + 1}.`;
        const player = document.createElement('span');
        player.className = 'geo-leaderboard-player';
        player.textContent = score.player_name;
        const details = document.createElement('span');
        details.className = 'geo-leaderboard-score';
        details.textContent = `${Number(score.score || 0).toLocaleString('fr-FR')} pts`;
        item.append(rank, player, details);
        list.append(item);
      });
    } catch (error) {
      list.replaceChildren();
      const failure = document.createElement('li');
      failure.className = 'geo-leaderboard-empty';
      failure.textContent = `Classement indisponible : ${error.message}`;
      list.append(failure);
    } finally {
      leaderboardLoading = false;
      button.disabled = false;
    }
  }

  function refreshLeaderboardAfterFinishedGame() {
    if (state?.status !== 'finished') return;
    const gameKey = `${gameType}:${state.game_id || state.room_id}:${state.match_number || 1}`;
    if (gameKey === lastLeaderboardGame) return;
    lastLeaderboardGame = gameKey;
    refreshLeaderboard();
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

  function roundAnswerSignature(roundNumber) {
    return `${gameType}:${state?.game_id || state?.room_id}:${state?.match_number || 1}:${roundNumber}`;
  }

  function isWaitingForNextRound() {
    const round = currentRoundResult();
    const signature = roundResultSignature(round);
    if (!signature) return false;
    if (gameType === 'solo') {
      return state?.status === 'playing'
        && state.awaiting_next_round === true
        && round.round_number === state.round_number;
    }
    if (gameType !== 'room') return false;
    return state?.status === 'playing'
      && state.awaiting_next_round === true
      && round.round_number === state.round_number;
  }

  function reportGoogleMapsAuthFailure() {
    googleMapsAuthFailed = true;
    showError(
      playError,
      googleMapsAuthFailureMessage(),
    );
  }

  function googleMapsAuthFailureMessage() {
    return 'Google Maps a refusé la clé navigateur. Vérifiez que Maps JavaScript API est activée, que la facturation Google Maps est active et que les restrictions HTTP referrer incluent le domaine de production (avec et sans www si nécessaire). Utilisez la clé navigateur, pas la clé serveur.';
  }

  window.gm_authFailure = reportGoogleMapsAuthFailure;

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
        if (variantSelect.value === 'panorama') variantSelect.value = 'cities';
        if (roomVariantSelect.value === 'panorama') roomVariantSelect.value = 'cities';
        let message = 'Le mode photo est indisponible. ';
        if (config.google_streetview_configured && !config.google_streetview_available) {
          message += `Quota Google atteint (${config.google_monthly_events_reserved}/${config.google_monthly_event_limit}). `;
        } else {
          const missingGoogleKeys = [];
          if (!config.google_maps_browser_key_configured) {
            missingGoogleKeys.push('GOOGLE_MAPS_BROWSER_API_KEY');
          }
          if (!config.google_maps_server_key_configured) {
            missingGoogleKeys.push('GOOGLE_MAPS_SERVER_API_KEY');
          }
          if (missingGoogleKeys.length) {
            message += `Clé(s) manquante(s) : ${missingGoogleKeys.join(', ')}. `;
          }
        }
        if (!mapillaryToken) message += 'MAPILLARY_ACCESS_TOKEN est également absent. ';
        setup.replaceChildren(document.createTextNode(message));
        const link = document.createElement('a');
        link.href = config.google_streetview_configured
          ? 'https://www.mapillary.com/dashboard/developers'
          : 'https://console.cloud.google.com/google/maps-apis/credentials';
        link.target = '_blank';
        link.rel = 'noopener';
        link.textContent = config.google_maps_browser_key_configured
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
      if (variantSelect.value === 'panorama') variantSelect.value = 'cities';
      if (roomVariantSelect.value === 'panorama') roomVariantSelect.value = 'cities';
    }
  }

  function loadGoogleMaps() {
    if (window.google?.maps?.StreetViewPanorama) return Promise.resolve();
    if (googleMapsLoading) return googleMapsLoading;
    if (!googleMapsApiKey) {
      return Promise.reject(new Error(
        'La clé GOOGLE_MAPS_BROWSER_API_KEY n’est pas configurée sur le serveur.',
      ));
    }
    googleMapsLoading = new Promise((resolve, reject) => {
      googleMapsAuthFailed = false;
      const script = document.createElement('script');
      script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(googleMapsApiKey)}&v=weekly&language=fr&region=FR&loading=async`;
      script.async = true;
      script.onload = () => {
        window.setTimeout(() => {
          if (googleMapsAuthFailed) {
            googleMapsLoading = null;
            reject(new Error('Google Maps a refusé la clé navigateur ou son domaine autorisé.'));
            return;
          }
          resolve();
        }, 100);
      };
      script.onerror = () => {
        googleMapsLoading = null;
        reject(new Error(
          'Google Maps JavaScript API ne s’est pas chargée. Vérifiez que la clé navigateur autorise Maps JavaScript API et le domaine de production, ainsi que la connexion au service.',
        ));
      };
      document.head.append(script);
    });
    return googleMapsLoading;
  }

  function googleGameRoundKey() {
    return `${gameType}:${state?.game_id || state?.room_id}:${state?.match_number || 1}:${state?.round_number}`;
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
        provider === 'google'
          ? 'Google Street View extérieur'
          : 'Séquences navigables · Images © Mapillary contributors';
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
          'Google Street View extérieur · Cliquez sur les flèches pour avancer.';
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
      showError(
        playError,
        googleMapsAuthFailed
          ? googleMapsAuthFailureMessage()
          : `Impossible d’ouvrir cette photo : ${error.message || 'erreur du lecteur'}`,
      );
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
    map = L.map('geo-map', { worldCopyJump: true, minZoom: 2, maxZoom: 19 })
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
    map.on('zoomend', () => {
      updatePhysicalFeatureVisibility(state?.variant === 'panorama');
    });
    return true;
  }

  function countryBoundaryStyle(isPanorama) {
    return {
      color: isPanorama ? '#63716f' : '#31444a',
      weight: isPanorama ? 1 : 0.9,
      opacity: isPanorama ? 0.9 : 0.76,
      fillColor: '#65a84a',
      fillOpacity: isPanorama ? 0 : 0.22,
    };
  }

  function createPanoramaLabelsLayer(useFallback = false) {
    const layer = L.tileLayer(
      useFallback
        ? 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}'
        : 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
      {
        maxZoom: 19,
        attribution: useFallback
          ? '&copy; Esri &mdash; Sources: HERE, Garmin, USGS, Intermap, INCREMENT P, NRCan, Esri Japan, METI, Esri China (Hong Kong), OpenStreetMap contributors, and the GIS User Community'
          : '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>',
      },
    );
    layer.on('tileerror', () => {
      if (mapLabelsLayer !== layer) return;
      if (!useFallback) {
        mapLabelsLayerFallback = true;
        map.removeLayer(layer);
        mapLabelsLayer = createPanoramaLabelsLayer(true).addTo(map);
        document.querySelector('.geo-map-actions > span').textContent =
          'Carte de secours © Esri · frontières © Natural Earth';
      } else if (!mapLabelsFallbackErrorShown) {
        mapLabelsFallbackErrorShown = true;
        showError(
          playError,
          'Impossible de charger le fond de carte. Vérifiez votre connexion ou désactivez le bloqueur de contenu.',
        );
      }
    });
    return layer;
  }

  function setMapStyle(isPanorama) {
    if (!map) return;
    if (isPanorama && !mapLabelsLayer) {
      mapLabelsLayerFallback = false;
      mapLabelsFallbackErrorShown = false;
      mapLabelsLayer = createPanoramaLabelsLayer().addTo(map);
    } else if (!isPanorama) {
      if (mapLabelsLayer) {
        map.removeLayer(mapLabelsLayer);
        mapLabelsLayer = null;
      }
      mapLabelsLayerFallback = false;
      mapLabelsFallbackErrorShown = false;
      if (!mapCitiesLayer) {
        mapCitiesLayer = L.tileLayer(
          'https://server.arcgisonline.com/ArcGIS/rest/services/World_Terrain_Base/MapServer/tile/{z}/{y}/{x}',
          {
            maxNativeZoom: 9,
            maxZoom: 19,
            attribution: 'Sources : Esri, USGS, NOAA',
          },
        ).addTo(map);
      }
      loadPhysicalFeatures();
    } else {
      if (mapCitiesLayer) map.removeLayer(mapCitiesLayer);
      mapCitiesLayer = null;
    }

    const maxZoom = 19;
    map.setMaxZoom(maxZoom);
    if (map.getZoom() > maxZoom) map.setZoom(maxZoom);
    updatePhysicalFeatureVisibility(isPanorama);

    countryBoundaryLayer?.setStyle(countryBoundaryStyle(isPanorama));
    const attribution = document.querySelector('.geo-map-actions > span');
    attribution.textContent = isPanorama
      ? 'Carte © OpenStreetMap · frontières © Natural Earth'
      : 'Relief © Esri, USGS, NOAA · fleuves et massifs © Natural Earth · sans noms de villes';
  }

  function updatePhysicalFeatureVisibility(isPanorama) {
    if (!map) return;
    for (const layer of physicalFeatureLayers) {
      if (isPanorama && map.hasLayer(layer)) map.removeLayer(layer);
      else if (!isPanorama && !map.hasLayer(layer)) layer.addTo(map);
    }

    const showMountainLabels = !isPanorama && map.getZoom() >= 4;
    for (const marker of mountainRangeLabelMarkers) {
      if (showMountainLabels && !map.hasLayer(marker)) marker.addTo(map);
      else if (!showMountainLabels && map.hasLayer(marker)) map.removeLayer(marker);
    }
  }

  function loadPhysicalFeatures() {
    if (physicalFeatureLayers.length || physicalFeaturesLoading) return;
    const basePath = '/static/games/geoguessr/data/';
    physicalFeaturesLoading = Promise.all(
      ['rivers_50m.geojson', 'mountain_ranges_50m.geojson'].map((filename) =>
        fetch(`${basePath}${filename}`).then((response) => {
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          return response.json();
        }),
      ),
    )
      .then(([rivers, mountainRanges]) => {
        const riverLayer = L.geoJSON(rivers, {
          interactive: false,
          style: (feature) => ({
            color: '#328da4',
            opacity: 0.88,
            weight: feature.properties.scalerank <= 2 ? 1.8 : 1.2,
          }),
        });
        const mountainRangeLayer = L.geoJSON(mountainRanges, {
          interactive: false,
          style: (feature) => ({
            color: '#526b45',
            opacity: 0.78,
            weight: feature.properties.scalerank <= 2 ? 1.1 : 0.75,
            dashArray: '4 4',
            fillColor: '#83966b',
            fillOpacity: 0.08,
          }),
          onEachFeature: (feature, layer) => {
            if (feature.properties.scalerank > 2) return;
            const label = document.createElement('span');
            label.textContent = feature.properties.name_fr || feature.properties.name;
            mountainRangeLabelMarkers.push(
              L.marker(layer.getBounds().getCenter(), {
                icon: L.divIcon({
                  className: 'geo-mountain-label',
                  html: label,
                  iconSize: [0, 0],
                  iconAnchor: [0, 0],
                }),
                interactive: false,
                keyboard: false,
              }),
            );
          },
        });
        physicalFeatureLayers = [mountainRangeLayer, riverLayer];
        updatePhysicalFeatureVisibility(state?.variant === 'panorama');
      })
      .catch((error) => {
        physicalFeaturesLoading = null;
        showError(
          playError,
          `Impossible de charger les fleuves et chaînes de montagnes : ${error.message}`,
        );
      });
  }

  function loadCountryBoundaries() {
    if (countryBoundaryLayer || countryBoundaryLoading) return;
    countryBoundaryLoading = fetch('/static/games/geoguessr/data/countries_50m.geojson')
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
      })
      .then((countries) => {
        const isPanorama = state?.variant === 'panorama';
        countryBoundaryLayer = L.geoJSON(countries, {
          interactive: false,
          style: countryBoundaryStyle(isPanorama),
          smoothFactor: 0.5,
        }).addTo(map);
        countryBoundaryLayer.bringToBack();
      })
      .catch((error) => {
        countryBoundaryLoading = null;
        showError(playError, `Impossible de charger les frontières de la carte : ${error.message}`);
      });
  }

  function clearMapMarkers() {
    for (const layer of [
      guessMarker,
      targetMarker,
      answerLine,
      ...revealedGuessMarkers,
      ...revealedAnswerLines,
    ]) {
      if (layer && map) map.removeLayer(layer);
    }
    guessMarker = null;
    targetMarker = null;
    answerLine = null;
    revealedGuessMarkers = [];
    revealedAnswerLines = [];
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

  function showAnswerOnMap(target, guesses) {
    clearMapMarkers();
    const revealedGuesses = Array.isArray(guesses)
      ? guesses
      : guesses ? [guesses] : [];
    targetMarker = L.circleMarker([target.latitude, target.longitude], {
      radius: 9,
      color: '#ffffff',
      weight: 3,
      fillColor: '#ef4444',
      fillOpacity: 1,
    }).addTo(map).bindTooltip(`${target.city}, ${target.country}`);
    if (revealedGuesses.length) {
      const answerBounds = L.latLngBounds([[target.latitude, target.longitude]]);
      for (const guess of revealedGuesses) {
        const isOwnGuess = !guess.player_id || guess.player_id === playerId;
        const color = isOwnGuess ? '#16a34a' : '#2563eb';
        const guessMarkerLayer = L.circleMarker([guess.latitude, guess.longitude], {
          radius: 8,
          color: '#ffffff',
          weight: 3,
          fillColor: color,
          fillOpacity: 1,
        }).addTo(map).bindTooltip(
          `${guess.name ? `${guess.name} · ` : ''}${isOwnGuess ? 'votre estimation' : 'estimation adverse'}`,
        );
        const answerLineLayer = L.polyline([
          [guess.latitude, guess.longitude],
          [target.latitude, target.longitude],
        ], { color, weight: 3, dashArray: '7 7' }).addTo(map);
        revealedGuessMarkers.push(guessMarkerLayer);
        revealedAnswerLines.push(answerLineLayer);
        answerBounds.extend([guess.latitude, guess.longitude]);
      }
      map.fitBounds(answerBounds.pad(0.22), { maxZoom: 7 });
    } else {
      map.setView([target.latitude, target.longitude], 5);
    }
  }

  function showRoundAnswer(roundNumber, target, guesses) {
    const resultKey = roundAnswerSignature(roundNumber);
    if (renderedResultRound === resultKey) return;
    showAnswerOnMap(target, guesses);
    renderedResultRound = resultKey;
  }

  function soloGuessMarker(result) {
    return {
      latitude: result.guess_latitude,
      longitude: result.guess_longitude,
    };
  }

  function guessLocked() {
    if (!state || state.status !== 'playing') return true;
    if (gameType === 'solo') return state.awaiting_next_round === true;
    return gameType === 'room'
      && (
        state.awaiting_next_round === true
        || !!state.player?.is_spectator
        || !!state.player?.submitted
      );
  }

  function startPolling() {
    stopPolling();
    if (gameType !== 'room') return;
    pollingTimer = window.setInterval(refreshRoom, 1300);
    updateRoundCountdown();
  }

  function stopPolling() {
    if (pollingTimer) window.clearInterval(pollingTimer);
    pollingTimer = null;
    roomRefreshing = false;
    if (roundCountdownTimer) window.clearInterval(roundCountdownTimer);
    roundCountdownTimer = null;
    document.getElementById('geo-round-timer').hidden = true;
  }

  function updateRoundCountdown() {
    const timer = document.getElementById('geo-round-timer');
    const deadline = Number(state?.round_deadline);
    if (
      gameType !== 'room'
      || state?.status !== 'playing'
      || !Number.isFinite(deadline)
      || deadline <= 0
    ) {
      timer.hidden = true;
      if (roundCountdownTimer) window.clearInterval(roundCountdownTimer);
      roundCountdownTimer = null;
      return;
    }

    const seconds = Math.max(0, Math.ceil(deadline - Date.now() / 1000));
    const activePlayers = state.players.filter((player) => !player.is_spectator);
    const waitingPlayers = activePlayers.filter((player) => !player.submitted).length;
    timer.textContent = state.player?.is_spectator
      ? 'Vous observez cette manche. Vous rejoindrez la prochaine.'
      : state.player?.submitted
      ? `${waitingPlayers} joueur${waitingPlayers !== 1 ? 's' : ''} n’a${waitingPlayers !== 1 ? 'ont' : ''} pas encore validé · ${seconds} s restantes`
      : `Vous avez ${seconds} s pour valider votre position.`;
    timer.hidden = false;
    if (!roundCountdownTimer) {
      roundCountdownTimer = window.setInterval(updateRoundCountdown, 1000);
    }
  }

  async function showHome(clearActiveGame = true) {
    if (clearActiveGame && gameType === 'room' && state?.room_id) {
      stopPolling();
      try {
        await post('/api/geoguessr/room/leave', {
          room_id: state.room_id,
          player_id: playerId,
        });
      } catch (error) {
        showError(playError, error.message);
        startPolling();
        return;
      }
    }
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
    renderedResultRound = null;
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
      details.textContent = `${room.player_count} joueurs + ${room.spectator_count || 0} spectateurs / ${room.max_players} places · ${room.round_count} manches · ${regionLabel(room.region)} · ${phase}`;
      copy.append(title, details);
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'geo-secondary-button';
      button.textContent = room.is_member
        ? 'Reprendre'
        : room.status === 'playing' ? 'Observer' : 'Rejoindre';
      button.disabled = !room.is_member && !['lobby', 'playing'].includes(room.status);
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
        ? player.ready ? 'Prêt pour démarrer' : 'En attente de confirmation'
        : player.is_spectator
          ? 'Spectateur · rejoindra la prochaine manche'
        : state.awaiting_next_round
          ? player.ready ? 'Prêt pour la prochaine manche' : 'En attente de confirmation'
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
      `${state.player_count} joueurs + ${state.spectator_count} spectateurs / ${state.max_players} places · ${state.round_count} manches · ${regionLabel(state.region)}. Chaque joueur doit confirmer sa présence avant le lancement.`;
    document.getElementById('geo-invite-code').textContent = `Code : ${state.room_id}`;
    document.getElementById('geo-copy-invite').dataset.inviteUrl = inviteUrl.href;
    renderPlayers();
    const readyButton = document.getElementById('geo-lobby-ready');
    readyButton.hidden = !!state.player?.is_spectator;
    readyButton.disabled = roomBusy;
    readyButton.textContent = state.player?.ready
      ? 'Présence confirmée · annuler'
      : 'Confirmer ma présence';
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
      `${variantLabel(state.variant)} · ${regionLabel(state.region)} · ${state.round_count} manches communes`;
  }

  function renderRoundResult(round, ownResult) {
    if (!round?.target) return;
    const signature = roundResultSignature(round);
    const waitingForNextRound = isWaitingForNextRound();
    if (!waitingForNextRound && state?.status !== 'finished') {
      roundResult.hidden = true;
      roundResult.replaceChildren();
      lastResultSignature = '';
      return;
    }
    const renderSignature = JSON.stringify([
      signature,
      state?.status,
      waitingForNextRound,
      ownResult?.distance_km,
      ownResult?.score,
      state?.ready_count,
      state?.player_count,
      state?.player?.ready,
      state?.all_ready,
      roomBusy,
    ]);
    if (renderSignature === lastResultSignature) return;
    lastResultSignature = renderSignature;
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
    if (round.missed_players?.length) {
      const missed = document.createElement('p');
      missed.textContent = `Temps écoulé pour : ${round.missed_players.join(', ')}.`;
      roundResult.append(missed);
    }
    if (waitingForNextRound && gameType === 'solo') {
      const continueButton = document.createElement('button');
      continueButton.type = 'button';
      continueButton.className = 'geo-primary-button';
      continueButton.textContent = `Manche suivante (${state.round_number + 1}/${state.round_count})`;
      continueButton.disabled = roomBusy;
      continueButton.addEventListener('click', advanceSoloRound);
      roundResult.append(continueButton);
      const waiting = document.createElement('p');
      waiting.textContent = 'Prenez le temps de comparer votre estimation à la cible avant de continuer.';
      roundResult.append(waiting);
    } else if (waitingForNextRound) {
      const continueButton = document.createElement('button');
      continueButton.type = 'button';
      continueButton.className = 'geo-primary-button';
      continueButton.textContent = state.player?.ready
        ? `Prêt · en attente des autres (${state.ready_count}/${state.player_count})`
        : `Confirmer pour la manche suivante (${state.ready_count}/${state.player_count})`;
      continueButton.disabled = !!state.player?.ready || roomBusy;
      continueButton.addEventListener('click', () => confirmRoomReady(true));
      roundResult.append(continueButton);
      const waiting = document.createElement('p');
      waiting.textContent = state.all_ready
        ? 'Tout le monde est prêt, la manche suivante démarre…'
        : `La manche suivante démarre quand les ${state.player_count} joueurs auront confirmé.`;
      roundResult.append(waiting);
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
      : [...state.players]
        .filter((player) => player.round_results.length > 0)
        .sort((a, b) => b.total_score - a.total_score);
    for (const player of scores) {
      const item = document.createElement('li');
      item.textContent = `${player.name} · ${player.total_score.toLocaleString('fr-FR')} points`;
      list.append(item);
    }
    scoreboard.append(list);
    if (gameType === 'solo' || playerId === state.host_player_id) {
      const replayButton = document.createElement('button');
      replayButton.type = 'button';
      replayButton.className = 'geo-primary-button';
      replayButton.id = 'geo-replay-game';
      replayButton.textContent = gameType === 'solo' ? 'Rejouer' : 'Relancer la partie';
      replayButton.addEventListener('click', () => {
        if (gameType === 'solo') {
          startSolo(true);
        } else {
          restartRoom();
        }
      });
      scoreboard.append(replayButton);
    } else {
      const waitingMessage = document.createElement('p');
      waitingMessage.textContent = 'En attente que l’hôte relance la partie.';
      scoreboard.append(waitingMessage);
    }
  }

  function renderView() {
    if (!state) return;
    home.hidden = true;
    play.hidden = false;
    hideError(playError);
    updateRoundCountdown();
    const region = state.region || regionSelect.value;
    const isRoom = gameType === 'room';
    const isSpectator = isRoom && !!state.player?.is_spectator;
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
        ? 'Une estimation par joueur et par manche. Après la première réponse, les autres ont 20 secondes.'
        : 'Placez un marqueur sur la carte, puis validez votre estimation.';
    document.getElementById('geo-total-score').textContent =
      (state.total_score ?? state.player?.total_score ?? 0).toLocaleString('fr-FR');
    document.getElementById('geo-target-label').textContent = isPanorama
      ? 'Lieu à retrouver'
      : 'Ville à trouver';
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
    document.getElementById('geo-round-message').textContent = isSpectator
      ? state.status === 'finished'
        ? 'Vous avez observé la partie. Vous pourrez jouer si l’hôte la relance.'
        : 'Vous observez cette manche et serez joueur à la prochaine.'
      : state.status === 'finished'
      ? 'Toutes les manches sont terminées.'
      : waitingForNextRound && !isRoom
        ? 'Votre réponse est verrouillée : la cible et la distance sont révélées.'
      : locked ? 'Votre position est validée. En attente des autres joueurs…'
        : isPanorama
          ? 'Naviguez dans la photo, puis cliquez sur la carte pour choisir votre estimation.'
          : 'Cliquez sur la carte pour placer votre estimation.';

    if (isRoom) {
      renderPlayers();
      if (state.last_round) {
        const ownResult = state.last_round.guesses.find((guess) => guess.player_id === playerId);
        renderRoundResult(state.last_round, ownResult);
        if (waitingForNextRound || state.status === 'finished') {
          showRoundAnswer(
            state.last_round.round_number,
            state.last_round.target,
            state.last_round.guesses,
          );
        }
      }
      if (state.status === 'playing' && state.player?.guess && locked) {
        selectedPosition = state.player.guess;
        setGuessMarker(selectedPosition.latitude, selectedPosition.longitude);
      }
    } else if (state.last_result) {
      renderRoundResult({
        round_number: state.last_result.round_number,
        target: state.last_result,
      }, state.last_result);
      if (waitingForNextRound || state.status === 'finished') {
        showRoundAnswer(
          state.last_result.round_number,
          state.last_result,
          soloGuessMarker(state.last_result),
        );
      }
    }

    if (state.status === 'finished') {
      const finalTarget = isRoom ? state.last_round?.target : state.last_result;
      const finalGuesses = isRoom
        ? state.last_round?.guesses
        : state.last_result ? soloGuessMarker(state.last_result) : null;
      if (finalTarget && finalGuesses) {
        showRoundAnswer(state.round_number, finalTarget, finalGuesses);
      }
      renderFinalScoreboard();
      refreshLeaderboardAfterFinishedGame();
      if (isRoom) {
        if (!pollingTimer) startPolling();
      } else {
        stopPolling();
      }
    } else {
      scoreboard.hidden = true;
      if (isRoom && !pollingTimer) startPolling();
    }
  }

  async function startSolo(isReplay = false) {
    const replayMode = isReplay === true;
    if (!ensureMap()) return;
    const button = document.getElementById(replayMode ? 'geo-replay-game' : 'geo-solo-button');
    setBusy(button, true, 'Préparation…');
    hideError(replayMode ? playError : homeError);
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
      renderedResultRound = null;
      lastResultSignature = '';
      selectedPosition = null;
      renderView();
      const view = mapView(state.region);
      map.setView(view.center, view.zoom);
    } catch (error) {
      showError(replayMode ? playError : homeError, error.message);
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
      renderedResultRound = null;
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
      else if (gameType === 'solo' && isWaitingForNextRound()) renderView();
    }
  }

  async function advanceSoloRound() {
    if (!state || gameType !== 'solo' || !isWaitingForNextRound() || roomBusy) return;
    roomBusy = true;
    hideError(playError);
    try {
      state = await post('/api/geoguessr/solo/next', {
        game_id: state.game_id,
        player_id: playerId,
      });
      selectedPosition = null;
      renderView();
      const view = mapView(state.region);
      map.setView(view.center, view.zoom);
    } catch (error) {
      showError(playError, error.message);
    } finally {
      roomBusy = false;
      if (state?.awaiting_next_round) renderView();
    }
  }

  async function createRoom() {
    if (!roomRoundCountInput.reportValidity()) return;
    const button = document.getElementById('geo-create-room');
    setBusy(button, true, 'Création…');
    hideError(homeError);
    try {
      state = await post('/api/geoguessr/room/create', {
        player_id: playerId,
        player_name: playerName,
        region: roomRegionSelect.value,
        variant: roomVariantSelect.value,
        round_count: Number(roomRoundCountInput.value),
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
    renderedResultRound = null;
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

  async function confirmRoomReady(ready = true) {
    if (!state || gameType !== 'room' || roomBusy) return;
    roomBusy = true;
    hideError(playError);
    try {
      state = await post('/api/geoguessr/room/ready', {
        room_id: state.room_id,
        player_id: playerId,
        player_name: playerName,
        ready,
      });
      if (state.status === 'lobby') renderLobby();
      else renderView();
    } catch (error) {
      showError(playError, error.message);
    } finally {
      roomBusy = false;
      if (state?.status === 'lobby') renderLobby();
      else if (state?.awaiting_next_round) renderView();
    }
  }

  async function restartRoom() {
    if (!state || roomBusy) return;
    roomBusy = true;
    hideError(playError);
    try {
      state = await post('/api/geoguessr/room/restart', {
        room_id: state.room_id,
        player_id: playerId,
        player_name: playerName,
      });
      renderedRound = null;
      renderedResultRound = null;
      lastResultSignature = '';
      selectedPosition = null;
      renderView();
      const view = mapView(state.region);
      map.setView(view.center, view.zoom);
      if (!pollingTimer) startPolling();
    } catch (error) {
      showError(playError, error.message);
    } finally {
      roomBusy = false;
    }
  }

  async function refreshRoom() {
    if (!state || gameType !== 'room' || roomRefreshing) return;
    roomRefreshing = true;
    try {
      const updatedState = await request(
        `/api/geoguessr/room/${encodeURIComponent(state.room_id)}?player_id=${encodeURIComponent(playerId)}`,
      );
      if ((updatedState.match_number || 1) < (state.match_number || 1)) return;
      const finalStateUnchanged = state.status === 'finished'
        && updatedState.status === 'finished'
        && (updatedState.match_number || 1) === (state.match_number || 1);
      state = updatedState;
      if (finalStateUnchanged) return;
      renderView();
    } catch (error) {
      stopPolling();
      showError(playError, `Connexion au salon interrompue : ${error.message}`);
    } finally {
      roomRefreshing = false;
    }
  }

  document.getElementById('geo-solo-button').addEventListener('click', () => startSolo(false));
  document.getElementById('geo-refresh-leaderboard').addEventListener(
    'click',
    refreshLeaderboard,
  );
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
  document.getElementById('geo-lobby-ready').addEventListener('click', () => {
  confirmRoomReady(!state?.player?.ready);
  });
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
    const title = document.getElementById('geo-home-title');
    const intro = document.querySelector('#geo-home .geo-intro');
    const soloButton = document.getElementById('geo-solo-button');
    const soloTitle = soloButton?.querySelector('strong');
    const soloDescription = soloButton?.querySelector('small');

    if (title) {
      title.textContent = panorama
        ? 'Où cette photo a-t-elle été prise ?'
        : 'Où se trouve cette ville ?';
    }
    if (intro) {
      intro.textContent = panorama
        ? 'Explorez des vues extérieures Google Street View ou des séquences Mapillary navigables, puis placez votre estimation sur la carte. Le type de caméra n’est pas certifié.'
        : 'Un nom de ville s’affiche. Placez votre estimation sur la carte : plus vous êtes proche, plus vous marquez de points. Jusqu’à 5 000 points par manche.';
    }
    if (soloTitle) {
      soloTitle.textContent = panorama ? 'Jouer avec des photos' : 'Jouer en solo';
    }
    if (soloDescription) {
      soloDescription.textContent = panorama
        ? 'Explorez cinq lieux réels et retrouvez-les sur la carte.'
        : 'Enchaînez cinq villes et comparez votre score.';
    }
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
  refreshLeaderboard();
  loadPanoramaConfig();
})();
