/**
 * Pédantix - Moteur Concours Multijoueur en Réseau Local
 */

class PedantixApp {
  constructor() {
    // Room & Player configuration
    const urlParams = new URLSearchParams(window.location.search);
    const modeParam = urlParams.get('mode');
    const roomParam = urlParams.get('room');

    // Default mode is Solo unless explicitly invited to a room with ?room or requested
    this.isSoloMode = modeParam === 'solo' || (!roomParam && localStorage.getItem('pedantix_play_mode') !== 'multi');

    this.playerId = localStorage.getItem('pedantix_player_id');
    if (!this.playerId) {
      this.playerId = 'p-' + Math.random().toString(36).substring(2, 10);
      localStorage.setItem('pedantix_player_id', this.playerId);
    }

    if (this.isSoloMode) {
      this.roomId = `solo-${this.playerId}`;
    } else {
      this.roomId = roomParam || localStorage.getItem('pedantix_last_room') || `salon-${Math.floor(Math.random() * 899 + 100)}`;
    }

    this.authUser = localStorage.getItem('pedantix_auth_user') || null;
    this.authToken = localStorage.getItem('pedantix_auth_token') || null;
    this.playerName = this.authUser || localStorage.getItem('pedantix_player_name');
    if (!this.playerName) {
      this.playerName = 'Joueur ' + Math.floor(Math.random() * 899 + 100);
      localStorage.setItem('pedantix_player_name', this.playerName);
    }

    this.sessionId = null;
    this.seed = null;
    this.tokens = [];
    this.tokensById = {};
    this.history = [];
    this.isWon = false;
    this.totalWords = 0;
    this.revealedWordsCount = 0;
    this.solution = null;

    // Multiplayer room state
    this.isHost = false;
    this.isReady = false;
    this.canStart = false;
    this.roomStatus = 'lobby'; // 'lobby', 'starting', 'playing', 'ending', 'round_over'
    this.myScore = 0;
    this.countdownTimer = null;
    this.sprintInterval = null;
    this.lastRound = null;
    this.revealedLetters = [];
    this.nextLetterHintTime = null;
    this.hintInterval = null;

    this.sortMode = 'chrono'; // 'chrono' or 'alpha'
    this.sortAsc = true;
    this.isCollapsed = false;
    this.filterQuery = '';
    this.isPinned = false;
    this.previousInputs = [];
    this.prevInputIdx = -1;
    this.startTime = Date.now();

    this.ws = null;
    this.pingInterval = null;
    this.leaderboard = [];
    this.selectedLeaderboardPlayerId = null;
    this.showAllLeaderboardExpanded = false;

    this.soundEnabled = localStorage.getItem('pedantix_sound') !== 'false';
    this.theme = localStorage.getItem('pedantix_theme') || 'dark-colorful';

    this.confetti = typeof ConfettiGenerator !== 'undefined' ? new ConfettiGenerator('confetti-canvas') : null;
    this.audioCtx = null;

    // Chat and Network State
    this.chatMessages = [];
    this.activeSidebarTab = 'contest';
    this.unreadChatCount = 0;
    this.networkInfo = null;
    this.activeNetMode = 'lan';

    // Game Mode & Teams State
    this.gameMode = 'individual'; // 'individual' or 'team'
    this.myTeam = 'blue';         // 'blue', 'red', 'green', 'yellow'
    this.teamsData = null;
    this.wsRoomId = null;

    this.initElements();
    this.initAudio();
    this.initEventListeners();
    this.setupChat();
    this.setupNetworkUI();
    this.applyTheme(this.theme);
    this.updateSoundIcon();

    // Setup pseudo input and fetch network IP
    if (this.dom.playerPseudoInput) this.dom.playerPseudoInput.value = this.playerName;
    if (this.dom.lobbyPseudoInput) this.dom.lobbyPseudoInput.value = this.playerName;
    this.fetchNetworkInfo();

    // Solo mode UI initialization
    if (this.isSoloMode) {
      document.body.classList.add('solo-mode');
      if (this.dom.btnTypeSolo) this.dom.btnTypeSolo.classList.add('active');
      if (this.dom.btnTypeMulti) this.dom.btnTypeMulti.classList.remove('active');
    } else {
      document.body.classList.remove('solo-mode');
      if (this.dom.btnTypeSolo) this.dom.btnTypeSolo.classList.remove('active');
      if (this.dom.btnTypeMulti) this.dom.btnTypeMulti.classList.add('active');
    }

    // Connect to room & start game
    this.joinRoom();

    // Check user authentication
    this.checkAuthOnLoad();
  }

  getBackendUrl() {
    if (window.PEDANTIX_CONFIG && window.PEDANTIX_CONFIG.BACKEND_URL) {
      return window.PEDANTIX_CONFIG.BACKEND_URL.replace(/\/+$/, '');
    }
    const saved = localStorage.getItem('pedantix_backend_url');
    if (saved) return saved.replace(/\/+$/, '');
    return '';
  }

  isHostedMode() {
    const h = window.location.hostname;
    return !(h === 'localhost' || h === '127.0.0.1' || /^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/.test(h));
  }

  getApiUrl(endpoint) {
    const base = this.getBackendUrl();
    const clean = endpoint.startsWith('/') ? endpoint : '/' + endpoint;
    return base ? `${base}${clean}` : clean;
  }

  getWsUrl(path) {
    const base = this.getBackendUrl();
    const clean = path.startsWith('/') ? path : '/' + path;
    if (base) {
      const wsProtocol = base.startsWith('https:') ? 'wss:' : 'ws:';
      const host = base.replace(/^https?:\/\//, '');
      return `${wsProtocol}//${host}${clean}`;
    }
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${window.location.host}${clean}`;
  }

  initElements() {
    this.dom = {
      // Navbar icons
      rulesBtn: document.getElementById('rules-button'),
      faqBtn: document.getElementById('faq-button'),
      themeBtn: document.getElementById('theme-button'),
      historyBtn: document.getElementById('history-button'),
      newGameBtn: document.getElementById('newgame-button'),
      soundBtn: document.getElementById('sound-button'),

      // Summary sidebar (Left)
      puzzleLabel: document.getElementById('puzzle-label'),
      puzzleNum: document.getElementById('puzzle-num'),
      dayMeter: document.getElementById('day-meter'),
      progressBarFill: document.getElementById('progress-bar-fill'),
      revealedStat: document.getElementById('revealed-stat'),
      totalStat: document.getElementById('total-stat'),
      pctStat: document.getElementById('pct-stat'),
      attemptsStat: document.getElementById('attempts-stat'),
      historyFilter: document.getElementById('history-filter'),
      guessableTable: document.getElementById('guessable'),
      chronoOrder: document.getElementById('chronoOrder'),
      alphaOrder: document.getElementById('alphaOrder'),
      collapseBtn: document.getElementById('collapse'),
      guessesTbody: document.getElementById('guesses'),
      btnSideNew: document.getElementById('btn-side-new'),
      yesterdayBox: document.getElementById('yesterday-box'),
      yesterdayLink: document.getElementById('yesterday-link'),

      // Header tabs & Room badges
      pedantixTitle: document.getElementById('pedantix-title'),
      btnTypeSolo: document.getElementById('btn-type-solo'),
      btnTypeMulti: document.getElementById('btn-type-multi'),
      modeBadge: document.getElementById('mode-badge'),
      roomCodeDisplay: document.getElementById('room-code-display'),
      btnBrowseRooms: document.getElementById('btn-browse-rooms'),
      btnCreateRoom: document.getElementById('btn-create-room'),
      btnHeaderInvite: document.getElementById('btn-header-invite'),
      hostPill: document.getElementById('host-pill'),
      hintTimerBadge: document.getElementById('hint-timer-badge'),
      hintTimerVal: document.getElementById('hint-timer-val'),
      navRoomsBtn: document.getElementById('nav-rooms-button'),
      navConfigBtn: document.getElementById('nav-config-button'),

      // Rooms Browser Modal
      roomsModal: document.getElementById('rooms-modal'),
      btnModalCreateRoom: document.getElementById('btn-modal-create-room'),
      inputJoinCode: document.getElementById('input-join-code'),
      btnModalJoinCode: document.getElementById('btn-modal-join-code'),
      btnRefreshRooms: document.getElementById('btn-refresh-rooms'),
      btnCopyCurrentLink: document.getElementById('btn-copy-current-link'),
      roomsList: document.getElementById('rooms-list'),
      roomsCountBadge: document.getElementById('rooms-count-badge'),
      currentRoomNameText: document.getElementById('current-room-name-text'),

      // Server Settings Modal
      serverSettingsModal: document.getElementById('server-settings-modal'),
      inputBackendUrl: document.getElementById('input-backend-url'),
      btnSaveBackendUrl: document.getElementById('btn-save-backend-url'),
      serverModalStatusIndicator: document.getElementById('server-modal-status-indicator'),
      serverModalStatusText: document.getElementById('server-modal-status-text'),

      // 30s Sprint Banner
      sprintTimerBanner: document.getElementById('sprint-timer-banner'),
      sprintWinnerName: document.getElementById('sprint-winner-name'),
      sprintCountdownNum: document.getElementById('sprint-countdown-num'),
      sprintBarFill: document.getElementById('sprint-bar-fill'),

      // 5s Countdown overlay
      countdownOverlay: document.getElementById('countdown-overlay'),
      countdownNumber: document.getElementById('countdown-number'),

      // Lobby Modal (Waiting salon overlay)
      lobbyModal: document.getElementById('lobby-modal'),
      lobbyMainTitle: document.getElementById('lobby-main-title'),
      lobbyInstructions: document.getElementById('lobby-instructions'),
      lobbyLastRoundBox: document.getElementById('lobby-last-round-box'),
      lobbyLastSolutionTitle: document.getElementById('lobby-last-solution-title'),
      lobbyLastSolutionLink: document.getElementById('lobby-last-solution-link'),
      lobbyPodiumCards: document.getElementById('lobby-podium-cards'),
      lobbyRoomNameDisplay: document.getElementById('lobby-room-name-display'),
      lobbyPseudoInput: document.getElementById('lobby-pseudo-input'),
      btnLobbySavePseudo: document.getElementById('btn-lobby-save-pseudo'),
      btnLobbyCopyLink: document.getElementById('btn-lobby-copy-link'),
      lobbyReadyRatio: document.getElementById('lobby-ready-ratio'),
      lobbyPlayersGrid: document.getElementById('lobby-players-grid'),
      btnLobbyToggleReady: document.getElementById('btn-lobby-toggle-ready'),
      lobbyReadyIcon: document.getElementById('lobby-ready-icon'),
      lobbyReadyLabel: document.getElementById('lobby-ready-label'),
      btnLobbyStartGame: document.getElementById('btn-lobby-start-game'),
      lobbyStatusHint: document.getElementById('lobby-status-hint'),

      // Mode & Teams DOM elements
      btnModeIndividual: document.getElementById('btn-mode-individual'),
      btnModeTeam: document.getElementById('btn-mode-team'),
      lobbyModeHint: document.getElementById('lobby-mode-hint'),
      lobbyTeamsBox: document.getElementById('lobby-teams-box'),
      lobbyTeamsGrid: document.getElementById('lobby-teams-grid'),
      lobbyRosterBox: document.getElementById('lobby-roster-box'),
      compTeamsSection: document.getElementById('comp-teams-section'),
      compIndividualSection: document.getElementById('comp-individual-section'),
      compTeamsConfrontation: document.getElementById('comp-teams-confrontation'),
      sideMyTeamBadge: document.getElementById('side-my-team-badge'),

      // Guess form (Center)
      form: document.getElementById('form'),
      pinBtn: document.getElementById('pin'),
      guessInput: document.getElementById('guess'),
      guessLenBadge: document.getElementById('guess-len-badge'),
      previousBtn: document.getElementById('previous'),
      guessBtn: document.getElementById('guess-btn'),
      errorLabel: document.getElementById('error'),

      // Wiki container
      wiki: document.getElementById('wiki'),
      wikiHeading: document.getElementById('wiki-heading'),
      wikiImg: document.getElementById('wiki-img'),
      article: document.getElementById('article'),

      // Victory / Win box
      successBox: document.getElementById('success'),
      solutionDisplay: document.getElementById('solution-display'),
      triesSpan: document.getElementById('tries'),
      meterSpan: document.getElementById('meter'),
      shareBtn: document.getElementById('share'),
      solutionLink: document.getElementById('solution'),
      seeFullPageBtn: document.getElementById('see-full-page'),

      // Opponent Win Banner
      opponentWinBanner: document.getElementById('opponent-win-banner'),
      opponentWinName: document.getElementById('opponent-win-name'),
      opponentWinTitle: document.getElementById('opponent-win-title'),
      opponentWinTries: document.getElementById('opponent-win-tries'),
      btnOpponentNewRound: document.getElementById('btn-opponent-new-round'),

      // Competition Panel (Right)
      compStatusBadge: document.getElementById('comp-status-badge'),
      inviteUrlInput: document.getElementById('invite-url-input'),
      btnCopyInvite: document.getElementById('btn-copy-invite'),
      btnCopyDrawer: document.getElementById('btn-copy-drawer'),
      playerPseudoInput: document.getElementById('player-pseudo-input'),
      btnSavePseudo: document.getElementById('btn-save-pseudo'),
      myPlayerScoreBadge: document.getElementById('my-player-score-badge'),
      sideHostPill: document.getElementById('side-host-pill'),
      btnSideReady: document.getElementById('btn-side-ready'),
      sideReadyIcon: document.getElementById('side-ready-icon'),
      sideReadyText: document.getElementById('side-ready-text'),
      btnSideStart: document.getElementById('btn-side-start'),
      btnOpenLobby: document.getElementById('btn-open-lobby'),
      playersList: document.getElementById('players-list'),
      activityFeed: document.getElementById('activity-feed'),
      btnNewRoundComp: document.getElementById('btn-new-round-comp'),

      // Round Over Modal
      roundOverModal: document.getElementById('round-over-modal'),
      roundOverWinnerTitle: document.getElementById('round-over-winner-title'),
      roundOverSolutionText: document.getElementById('round-over-solution-text'),
      roundOverWikiLink: document.getElementById('round-over-wiki-link'),
      roundOverScoresList: document.getElementById('round-over-scores-list'),
      btnRoundReady: document.getElementById('btn-round-ready'),
      roundReadyIcon: document.getElementById('round-ready-icon'),
      roundReadyLabel: document.getElementById('round-ready-label'),
      btnRoundNextGame: document.getElementById('btn-round-next-game'),
      roundNextStatusHint: document.getElementById('round-next-status-hint'),

      // Surrender controls & modal
      btnSurrenderRoom: document.getElementById('btn-surrender-room'),
      btnSideSurrender: document.getElementById('btn-side-surrender'),
      surrenderModal: document.getElementById('surrender-modal'),
      surrenderModalTitle: document.getElementById('surrender-modal-title'),
      surrenderPromptText: document.getElementById('surrender-prompt-text'),
      surrenderVoteCount: document.getElementById('surrender-vote-count'),
      surrenderActionsVoting: document.getElementById('surrender-actions-voting'),
      surrenderActionsWaiting: document.getElementById('surrender-actions-waiting'),
      btnSurrenderAccept: document.getElementById('btn-surrender-accept'),
      btnSurrenderRefuse: document.getElementById('btn-surrender-refuse'),
      btnSurrenderCancel: document.getElementById('btn-surrender-cancel'),

      // Modals
      rulesModal: document.getElementById('rules-modal'),
      faqModal: document.getElementById('faq-modal'),
      themesModal: document.getElementById('themes-modal'),
      statsModal: document.getElementById('stats-modal'),
      statsUserName: document.getElementById('stats-user-name'),
      statsUserScore: document.getElementById('stats-user-score'),
      btnAuthLogout: document.getElementById('btn-auth-logout'),
      sPlayed: document.getElementById('s-played'),
      sWon: document.getElementById('s-won'),
      sWinRate: document.getElementById('s-winrate'),
      sAvg: document.getElementById('s-avg'),
      sBest: document.getElementById('s-best'),
      statsFavWordsList: document.getElementById('stats-fav-words-list'),
      statsRecentList: document.getElementById('stats-recent-list'),
      toast: document.getElementById('toast'),

      // User Authentication Modal
      authModal: document.getElementById('auth-modal'),
      authModalTitle: document.getElementById('auth-modal-title'),
      authStepUsername: document.getElementById('auth-step-username'),
      authUsernameForm: document.getElementById('auth-username-form'),
      authUsernameInput: document.getElementById('auth-username-input'),
      btnAuthContinue: document.getElementById('btn-auth-continue'),
      authStepLogin: document.getElementById('auth-step-login'),
      authLoginForm: document.getElementById('auth-login-form'),
      authPasswordInput: document.getElementById('auth-password-input'),
      authLoginUsernameDisplay: document.getElementById('auth-login-username-display'),
      btnAuthBackLogin: document.getElementById('btn-auth-back-login'),
      authStepRegister: document.getElementById('auth-step-register'),
      authRegisterForm: document.getElementById('auth-register-form'),
      authNewPasswordInput: document.getElementById('auth-new-password-input'),
      authRegisterUsernameDisplay: document.getElementById('auth-register-username-display'),
      btnAuthBackRegister: document.getElementById('btn-auth-back-register'),
      authErrorBox: document.getElementById('auth-error-box'),

      // Competition Sidebar Tabs & Chat
      tabBtnContest: document.getElementById('tab-btn-contest'),
      tabBtnChat: document.getElementById('tab-btn-chat'),
      compTabContest: document.getElementById('comp-tab-contest'),
      compTabChat: document.getElementById('comp-tab-chat'),
      chatUnreadBadge: document.getElementById('chat-unread-badge'),
      chatMessagesSidebar: document.getElementById('chat-messages-sidebar'),
      chatInputSidebar: document.getElementById('chat-input-sidebar'),
      chatFormSidebar: document.getElementById('chat-form-sidebar'),
      chatQuickReactionsSidebar: document.getElementById('chat-quick-reactions-sidebar'),

      // Lobby Chat
      chatMessagesLobby: document.getElementById('chat-messages-lobby'),
      chatInputLobby: document.getElementById('chat-input-lobby'),
      chatFormLobby: document.getElementById('chat-form-lobby'),
      chatQuickReactionsLobby: document.getElementById('chat-quick-reactions-lobby'),

      // Floating Chat Toast
      chatFloatingToast: document.getElementById('chat-floating-toast'),
      chatToastSender: document.getElementById('chat-toast-sender'),
      chatToastText: document.getElementById('chat-toast-text'),
      btnChatToastClose: document.getElementById('btn-chat-toast-close'),

      // Network Modes & Tunnel
      btnNetModeLan: document.getElementById('btn-net-mode-lan'),
      btnNetModeTunnel: document.getElementById('btn-net-mode-tunnel'),
      netLanView: document.getElementById('net-lan-view'),
      netTunnelView: document.getElementById('net-tunnel-view'),
      tunnelUrlInput: document.getElementById('tunnel-url-input'),
      btnCopyTunnel: document.getElementById('btn-copy-tunnel'),
      btnToggleTunnel: document.getElementById('btn-toggle-tunnel'),
      tunnelBtnLabel: document.getElementById('tunnel-btn-label'),
      localIpWarning: document.getElementById('local-ip-warning'),
    };
  }

  initAudio() {
    try {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (AudioContext) {
        this.audioCtx = new AudioContext();
      }
    } catch (e) {
      console.warn("AudioContext non supporté", e);
    }
  }

  playTone(type) {
    if (!this.soundEnabled || !this.audioCtx) return;
    if (this.audioCtx.state === 'suspended') {
      this.audioCtx.resume();
    }

    const now = this.audioCtx.currentTime;
    const osc = this.audioCtx.createOscillator();
    const gain = this.audioCtx.createGain();
    osc.connect(gain);
    gain.connect(this.audioCtx.destination);

    if (type === 'click') {
      osc.type = 'sine';
      osc.frequency.setValueAtTime(520, now);
      gain.gain.setValueAtTime(0.06, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.05);
      osc.start(now);
      osc.stop(now + 0.05);
    } else if (type === 'beep') {
      osc.type = 'sine';
      osc.frequency.setValueAtTime(880, now);
      gain.gain.setValueAtTime(0.12, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.08);
      osc.start(now);
      osc.stop(now + 0.08);
    } else if (type === 'go') {
      const notes = [523.25, 659.25, 783.99, 1046.5];
      notes.forEach((freq, idx) => {
        const o = this.audioCtx.createOscillator();
        const g = this.audioCtx.createGain();
        o.type = 'triangle';
        o.frequency.setValueAtTime(freq, now + idx * 0.06);
        g.gain.setValueAtTime(0.15, now + idx * 0.06);
        g.gain.exponentialRampToValueAtTime(0.001, now + idx * 0.06 + 0.25);
        o.connect(g);
        g.connect(this.audioCtx.destination);
        o.start(now + idx * 0.06);
        o.stop(now + idx * 0.06 + 0.25);
      });
    } else if (type === 'match') {
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(523.25, now);
      osc.frequency.setValueAtTime(659.25, now + 0.08);
      osc.frequency.setValueAtTime(783.99, now + 0.16);
      gain.gain.setValueAtTime(0.12, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
      osc.start(now);
      osc.stop(now + 0.35);
    } else if (type === 'close') {
      osc.type = 'sine';
      osc.frequency.setValueAtTime(440, now);
      osc.frequency.setValueAtTime(493.88, now + 0.09);
      gain.gain.setValueAtTime(0.08, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.22);
      osc.start(now);
      osc.stop(now + 0.22);
    } else if (type === 'miss') {
      osc.type = 'sine';
      osc.frequency.setValueAtTime(220, now);
      gain.gain.setValueAtTime(0.05, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.12);
      osc.start(now);
      osc.stop(now + 0.12);
    } else if (type === 'win') {
      const notes = [523.25, 659.25, 783.99, 1046.5];
      notes.forEach((freq, idx) => {
        const o = this.audioCtx.createOscillator();
        const g = this.audioCtx.createGain();
        o.type = 'triangle';
        o.frequency.setValueAtTime(freq, now + idx * 0.1);
        g.gain.setValueAtTime(0.15, now + idx * 0.1);
        g.gain.exponentialRampToValueAtTime(0.001, now + idx * 0.1 + 0.4);
        o.connect(g);
        g.connect(this.audioCtx.destination);
        o.start(now + idx * 0.1);
        o.stop(now + idx * 0.1 + 0.4);
      });
    } else if (type === 'message') {
      osc.type = 'sine';
      osc.frequency.setValueAtTime(659.25, now);
      osc.frequency.exponentialRampToValueAtTime(880, now + 0.08);
      gain.gain.setValueAtTime(0.09, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.16);
      osc.start(now);
      osc.stop(now + 0.16);
    } else if (type === 'hint') {
      const notes = [659.25, 880, 1046.5];
      notes.forEach((freq, idx) => {
        const o = this.audioCtx.createOscillator();
        const g = this.audioCtx.createGain();
        o.type = 'sine';
        o.frequency.setValueAtTime(freq, now + idx * 0.08);
        g.gain.setValueAtTime(0.12, now + idx * 0.08);
        g.gain.exponentialRampToValueAtTime(0.001, now + idx * 0.08 + 0.35);
        o.connect(g);
        g.connect(this.audioCtx.destination);
        o.start(now + idx * 0.08);
        o.stop(now + idx * 0.08 + 0.35);
      });
    }
  }

  initEventListeners() {
    // Nav buttons
    if (this.dom.rulesBtn) this.dom.rulesBtn.addEventListener('click', () => this.openModal(this.dom.rulesModal));
    if (this.dom.faqBtn) this.dom.faqBtn.addEventListener('click', () => this.copyInviteUrl());
    if (this.dom.navConfigBtn) this.dom.navConfigBtn.addEventListener('click', () => this.openServerSettingsModal());
    if (this.dom.themeBtn) this.dom.themeBtn.addEventListener('click', () => this.openModal(this.dom.themesModal));
    if (this.dom.historyBtn) this.dom.historyBtn.addEventListener('click', () => {
      this.refreshStatsModal();
      this.openModal(this.dom.statsModal);
    });

    // Sound toggle
    this.dom.soundBtn.addEventListener('click', () => {
      this.soundEnabled = !this.soundEnabled;
      localStorage.setItem('pedantix_sound', this.soundEnabled);
      this.updateSoundIcon();
      this.showToast(this.soundEnabled ? 'Sons activés' : 'Sons désactivés');
      if (this.soundEnabled) this.playTone('click');
    });

    // Solo vs Multiplayer toggle buttons
    if (this.dom.btnTypeSolo) {
      this.dom.btnTypeSolo.addEventListener('click', () => this.switchPlayMode('solo'));
    }
    if (this.dom.btnTypeMulti) {
      this.dom.btnTypeMulti.addEventListener('click', () => this.switchPlayMode('multi'));
    }

    // Create new party / room button
    if (this.dom.btnCreateRoom) {
      this.dom.btnCreateRoom.addEventListener('click', () => this.createNewRoom());
    }

    // Room browser & discovery buttons
    if (this.dom.btnBrowseRooms) {
      this.dom.btnBrowseRooms.addEventListener('click', () => this.openRoomsBrowser());
    }
    if (this.dom.navRoomsBtn) {
      this.dom.navRoomsBtn.addEventListener('click', () => this.openRoomsBrowser());
    }
    const roomBadgeEl = document.getElementById('room-badge');
    if (roomBadgeEl) {
      roomBadgeEl.addEventListener('click', () => this.openRoomsBrowser());
    }
    if (this.dom.btnModalCreateRoom) {
      this.dom.btnModalCreateRoom.addEventListener('click', () => this.createNewRoom());
    }
    if (this.dom.btnRefreshRooms) {
      this.dom.btnRefreshRooms.addEventListener('click', () => this.fetchRoomsList());
    }
    if (this.dom.btnCopyCurrentLink) {
      this.dom.btnCopyCurrentLink.addEventListener('click', () => this.copyInviteUrl());
    }
    if (this.dom.btnModalJoinCode) {
      this.dom.btnModalJoinCode.addEventListener('click', () => {
        const val = this.dom.inputJoinCode ? this.dom.inputJoinCode.value.trim() : '';
        if (val) this.switchRoom(val);
      });
    }
    if (this.dom.inputJoinCode) {
      this.dom.inputJoinCode.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          const val = this.dom.inputJoinCode.value.trim();
          if (val) this.switchRoom(val);
        }
      });
    }

    // Game mode toggle buttons
    if (this.dom.btnModeIndividual) {
      this.dom.btnModeIndividual.addEventListener('click', () => this.switchGameMode('individual'));
    }
    if (this.dom.btnModeTeam) {
      this.dom.btnModeTeam.addEventListener('click', () => this.switchGameMode('team'));
    }

    // Ready toggle buttons
    const handleReadyToggle = () => this.toggleReady();
    if (this.dom.btnLobbyToggleReady) this.dom.btnLobbyToggleReady.addEventListener('click', handleReadyToggle);
    if (this.dom.btnSideReady) this.dom.btnSideReady.addEventListener('click', handleReadyToggle);
    if (this.dom.btnRoundReady) this.dom.btnRoundReady.addEventListener('click', handleReadyToggle);

    // Host Start Game buttons
    const handleStartGame = () => this.startGame();
    if (this.dom.btnLobbyStartGame) this.dom.btnLobbyStartGame.addEventListener('click', handleStartGame);
    if (this.dom.btnSideStart) this.dom.btnSideStart.addEventListener('click', handleStartGame);

    // Lobby copy link button
    if (this.dom.btnLobbyCopyLink) {
      this.dom.btnLobbyCopyLink.addEventListener('click', () => this.copyInviteUrl());
    }

    // Reopen lobby button from sidebar
    if (this.dom.btnOpenLobby) {
      this.dom.btnOpenLobby.addEventListener('click', () => {
        this.lobbyMinimized = false;
        this.openModal(this.dom.lobbyModal);
      });
    }

    // Host Launch Next Round button
    if (this.dom.btnRoundNextGame) {
      this.dom.btnRoundNextGame.addEventListener('click', () => this.startNextRound());
    }

    // "Nouvelle page" triggers
    const handleNewRoundTrigger = () => this.requestNewRound();
    if (this.dom.newGameBtn) this.dom.newGameBtn.addEventListener('click', handleNewRoundTrigger);
    if (this.dom.btnSideNew) this.dom.btnSideNew.addEventListener('click', handleNewRoundTrigger);
    if (this.dom.btnNewRoundComp) this.dom.btnNewRoundComp.addEventListener('click', handleNewRoundTrigger);
    if (this.dom.btnOpponentNewRound) this.dom.btnOpponentNewRound.addEventListener('click', handleNewRoundTrigger);

    // Server settings save
    if (this.dom.btnSaveBackendUrl) {
      this.dom.btnSaveBackendUrl.addEventListener('click', () => this.saveServerSettings());
    }

    // User authentication form events
    if (this.dom.authUsernameForm) {
      this.dom.authUsernameForm.addEventListener('submit', (e) => {
        e.preventDefault();
        this.handleAuthUsernameSubmit();
      });
    }
    if (this.dom.authLoginForm) {
      this.dom.authLoginForm.addEventListener('submit', (e) => {
        e.preventDefault();
        this.handleAuthLoginSubmit();
      });
    }
    if (this.dom.authRegisterForm) {
      this.dom.authRegisterForm.addEventListener('submit', (e) => {
        e.preventDefault();
        this.handleAuthRegisterSubmit();
      });
    }
    if (this.dom.btnAuthBackLogin) {
      this.dom.btnAuthBackLogin.addEventListener('click', () => this.showAuthStep('username'));
    }
    if (this.dom.btnAuthBackRegister) {
      this.dom.btnAuthBackRegister.addEventListener('click', () => this.showAuthStep('username'));
    }
    if (this.dom.btnAuthLogout) {
      this.dom.btnAuthLogout.addEventListener('click', () => this.handleAuthLogout());
    }

    // Surrender buttons
    const handleSurrender = () => this.handleSurrenderClick();
    if (this.dom.btnSurrenderRoom) this.dom.btnSurrenderRoom.addEventListener('click', handleSurrender);
    if (this.dom.btnSideSurrender) this.dom.btnSideSurrender.addEventListener('click', handleSurrender);
    if (this.dom.btnSurrenderAccept) this.dom.btnSurrenderAccept.addEventListener('click', () => this.voteSurrender('yes'));
    if (this.dom.btnSurrenderRefuse) this.dom.btnSurrenderRefuse.addEventListener('click', () => this.voteSurrender('no'));
    if (this.dom.btnSurrenderCancel) this.dom.btnSurrenderCancel.addEventListener('click', () => this.voteSurrender('cancel'));

    // Theme choices
    document.querySelectorAll('.theme-choice-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const t = btn.getAttribute('data-theme');
        if (t) {
          this.applyTheme(t);
          this.closeModal(this.dom.themesModal);
          const nameEl = btn.querySelector('b');
          this.showToast(`Thème activé : ${nameEl ? nameEl.textContent : t}`);
        }
      });
    });

    // Guess form submit
    this.dom.form.addEventListener('submit', (e) => {
      e.preventDefault();
      this.handleGuessSubmit();
    });

    // Live word length indicator
    this.dom.guessInput.addEventListener('input', (e) => {
      const len = e.target.value.trim().length;
      if (this.dom.guessLenBadge) {
        if (len > 0) {
          this.dom.guessLenBadge.textContent = `${len} lettre${len > 1 ? 's' : ''}`;
          this.dom.guessLenBadge.style.display = 'inline-block';
        } else {
          this.dom.guessLenBadge.style.display = 'none';
        }
      }
    });

    // Pin sticky input
    this.dom.pinBtn.addEventListener('click', () => {
      this.isPinned = !this.isPinned;
      this.dom.pinBtn.textContent = this.isPinned ? '📌' : '📍';
      if (this.isPinned) {
        this.dom.form.classList.add('sticky-pinned');
      } else {
        this.dom.form.classList.remove('sticky-pinned');
      }
      this.dom.guessInput.focus();
    });

    // Previous button recall
    this.dom.previousBtn.addEventListener('click', () => {
      if (this.previousInputs.length === 0) return;
      if (this.prevInputIdx === -1) {
        this.prevInputIdx = this.previousInputs.length - 1;
      } else {
        this.prevInputIdx = (this.prevInputIdx - 1 + this.previousInputs.length) % this.previousInputs.length;
      }
      this.dom.guessInput.value = this.previousInputs[this.prevInputIdx];
      this.dom.guessInput.focus();
    });

    // Copy invite IP address
    if (this.dom.btnHeaderInvite) {
      this.dom.btnHeaderInvite.addEventListener('click', () => this.copyInviteUrl());
    }
    if (this.dom.btnCopyInvite) {
      this.dom.btnCopyInvite.addEventListener('click', () => this.copyInviteUrl());
    }
    if (this.dom.btnCopyDrawer) {
      this.dom.btnCopyDrawer.addEventListener('click', () => this.copyInviteUrl());
    }
    if (this.dom.inviteUrlInput) {
      this.dom.inviteUrlInput.addEventListener('click', () => this.copyInviteUrl());
    }

    // Save pseudo (synced between sidebar and lobby)
    const savePseudoAction = (rawVal) => {
      const val = (rawVal !== undefined ? rawVal : (this.dom.playerPseudoInput ? this.dom.playerPseudoInput.value : '')).trim();
      if (val && val !== this.playerName) {
        this.playerName = val;
        localStorage.setItem('pedantix_player_name', val);
        if (this.dom.playerPseudoInput) this.dom.playerPseudoInput.value = val;
        if (this.dom.lobbyPseudoInput) this.dom.lobbyPseudoInput.value = val;
        this.showToast(`Pseudo enregistré : "${val}"`);
        this.joinRoom();
      }
    };

    if (this.dom.btnSavePseudo) {
      this.dom.btnSavePseudo.addEventListener('click', () => savePseudoAction(this.dom.playerPseudoInput.value));
    }
    if (this.dom.playerPseudoInput) {
      this.dom.playerPseudoInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          savePseudoAction(this.dom.playerPseudoInput.value);
        }
      });
    }
    if (this.dom.btnLobbySavePseudo) {
      this.dom.btnLobbySavePseudo.addEventListener('click', () => savePseudoAction(this.dom.lobbyPseudoInput.value));
    }
    if (this.dom.lobbyPseudoInput) {
      this.dom.lobbyPseudoInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          savePseudoAction(this.dom.lobbyPseudoInput.value);
        }
      });
    }

    // Table sorting & collapsing
    this.dom.chronoOrder.addEventListener('click', () => {
      if (this.sortMode === 'chrono') {
        this.sortAsc = !this.sortAsc;
      } else {
        this.sortMode = 'chrono';
        this.sortAsc = true;
      }
      this.renderHistory();
    });

    this.dom.alphaOrder.addEventListener('click', () => {
      if (this.sortMode === 'alpha') {
        this.sortAsc = !this.sortAsc;
      } else {
        this.sortMode = 'alpha';
        this.sortAsc = true;
      }
      this.renderHistory();
    });

    this.dom.collapseBtn.addEventListener('click', () => {
      this.isCollapsed = !this.isCollapsed;
      this.dom.collapseBtn.textContent = this.isCollapsed ? '🔺' : '🔻';
      this.renderHistory();
    });

    this.dom.historyFilter.addEventListener('input', (e) => {
      this.filterQuery = e.target.value.trim().toLowerCase();
      this.renderHistory();
    });

    // Success actions
    this.dom.shareBtn.addEventListener('click', () => this.copyShareScore());
    this.dom.seeFullPageBtn.addEventListener('click', () => this.unmaskAllWords());

    // Modal close triggers
    document.querySelectorAll('.modal-close, [data-close]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const id = e.currentTarget.getAttribute('data-close');
        if (id) {
          if (id === 'lobby-modal') this.lobbyMinimized = true;
          this.closeModal(document.getElementById(id));
        } else {
          const overlay = e.currentTarget.closest('.modal-overlay');
          if (overlay) {
            if (overlay === this.dom.lobbyModal) this.lobbyMinimized = true;
            this.closeModal(overlay);
          }
        }
      });
    });

    document.querySelectorAll('.modal-overlay').forEach(overlay => {
      overlay.addEventListener('click', (e) => {
        if (e.target === overlay) {
          if (overlay === this.dom.authModal && !this.authUser) return;
          if (overlay === this.dom.lobbyModal) this.lobbyMinimized = true;
          this.closeModal(overlay);
        }
      });
    });
  }

  applyTheme(theme) {
    this.theme = theme;
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('pedantix_theme', theme);

    document.querySelectorAll('.theme-choice-btn').forEach(btn => {
      if (btn.getAttribute('data-theme') === theme) {
        btn.classList.add('active');
        btn.style.borderColor = '#f59e0b';
        btn.style.boxShadow = '0 0 0 2px rgba(245, 158, 11, 0.4)';
      } else {
        btn.classList.remove('active');
        btn.style.borderColor = '';
        btn.style.boxShadow = '';
      }
    });
  }

  updateSoundIcon() {
    this.dom.soundBtn.textContent = this.soundEnabled ? '🔊' : '🔇';
  }

  openModal(modalElem) {
    if (modalElem) {
      const alreadyOpen = modalElem.classList.contains('active');
      modalElem.classList.add('active');
      if (!alreadyOpen) {
        const inner = modalElem.querySelector('.modal');
        if (inner) inner.scrollTop = 0;
        modalElem.scrollTop = 0;
      }
    }
  }

  closeModal(modalElem) {
    if (modalElem) modalElem.classList.remove('active');
  }

  showToast(message) {
    this.dom.toast.textContent = message;
    this.dom.toast.classList.add('visible');
    setTimeout(() => {
      this.dom.toast.classList.remove('visible');
    }, 2800);
  }

  escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  getGreyColor(score) {
    const clamped = Math.max(45, Math.min(99, Number(score) || 50));
    const t = (clamped - 45) / 54;
    const v = Math.round(95 + Math.pow(t, 0.85) * 140);
    return `rgb(${v}, ${v}, ${v})`;
  }

  getFlashColor(score) {
    const clamped = Math.max(45, Math.min(99, Number(score) || 50));
    const t = (clamped - 45) / 54;
    const g = Math.round(90 + t * 150);
    return `rgb(255, ${g}, 0)`;
  }

  // =========================================================================
  // NETWORK & MULTIPLAYER ROOM ENGINE
  // =========================================================================

  async fetchNetworkInfo() {
    try {
      const resp = await fetch(this.getApiUrl('/api/network-info'));
      this.networkInfo = await resp.json();
      this.updateNetworkDisplay();
    } catch (e) {
      console.warn("Erreur fetchNetworkInfo", e);
    }
  }

  updateNetworkDisplay() {
    if (!this.networkInfo) return;
    const data = this.networkInfo;
    const roomParam = this.roomId !== 'default' ? `?room=${encodeURIComponent(this.roomId)}` : '';

    if (this.isHostedMode()) {
      // 1. En ligne (Netlify) : Le site est déjà public et accessible sur Internet pour tous !
      const hostedUrl = `${window.location.origin}/${roomParam}`;
      if (this.dom.inviteUrlInput) {
        this.dom.inviteUrlInput.value = hostedUrl;
      }
      const pills = document.querySelector('.network-mode-pills');
      if (pills) pills.style.display = 'none';
      if (this.dom.netLanView) this.dom.netLanView.style.display = 'flex';
      if (this.dom.netTunnelView) this.dom.netTunnelView.style.display = 'none';
      const helper = document.querySelector('#net-lan-view .network-helper-text');
      if (helper) {
        helper.innerHTML = '<span class="helper-badge-tunnel">🌍 En ligne</span> Partagez ce lien avec vos amis, ils peuvent rejoindre depuis n\'importe où !';
      }
      if (this.dom.localIpWarning) this.dom.localIpWarning.style.display = 'none';
      return;
    }

    // 1. LAN invite URL: NEVER fallback to 127.0.0.1 if lan_ip exists
    const lanHost = (data.lan_ip && data.lan_ip !== '127.0.0.1') ? data.lan_ip : (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1' ? window.location.hostname : data.lan_ip);
    const lanPort = window.location.port ? `:${window.location.port}` : (data.port ? `:${data.port}` : '');
    const lanUrl = `${window.location.protocol}//${lanHost}${lanPort}/${roomParam}`;

    if (this.dom.inviteUrlInput) {
      this.dom.inviteUrlInput.value = lanUrl;
    }

    // 2. Tunnel / Internet URL
    if (this.dom.tunnelUrlInput) {
      if (data.tunnel_url) {
        this.dom.tunnelUrlInput.value = `${data.tunnel_url}/${roomParam}`;
        if (this.dom.btnCopyTunnel) this.dom.btnCopyTunnel.disabled = false;
        if (this.dom.tunnelBtnLabel) this.dom.tunnelBtnLabel.textContent = "Désactiver le lien Internet";
        if (this.dom.btnToggleTunnel) this.dom.btnToggleTunnel.classList.add('tunnel-active');
      } else {
        this.dom.tunnelUrlInput.value = "Lien Internet non activé";
        if (this.dom.btnCopyTunnel) this.dom.btnCopyTunnel.disabled = true;
        if (this.dom.tunnelBtnLabel) this.dom.tunnelBtnLabel.textContent = "Activer le lien Internet (amis distants)";
        if (this.dom.btnToggleTunnel) this.dom.btnToggleTunnel.classList.remove('tunnel-active');
      }
    }

    // 3. Localhost warning: show if host is browsing via 127.0.0.1 or localhost
    const curHost = window.location.hostname;
    if (this.dom.localIpWarning) {
      if (curHost === 'localhost' || curHost === '127.0.0.1') {
        this.dom.localIpWarning.style.display = 'block';
      } else {
        this.dom.localIpWarning.style.display = 'none';
      }
    }
  }

  setupNetworkUI() {
    if (this.dom.btnNetModeLan) {
      this.dom.btnNetModeLan.addEventListener('click', () => this.switchNetMode('lan'));
    }
    if (this.dom.btnNetModeTunnel) {
      this.dom.btnNetModeTunnel.addEventListener('click', () => this.switchNetMode('tunnel'));
    }
    if (this.dom.btnCopyTunnel) {
      this.dom.btnCopyTunnel.addEventListener('click', () => this.copyInviteUrl('tunnel'));
    }
    if (this.dom.btnToggleTunnel) {
      this.dom.btnToggleTunnel.addEventListener('click', () => this.toggleTunnel());
    }
  }

  switchNetMode(mode) {
    this.activeNetMode = mode;
    if (this.dom.btnNetModeLan) this.dom.btnNetModeLan.classList.toggle('active', mode === 'lan');
    if (this.dom.btnNetModeTunnel) this.dom.btnNetModeTunnel.classList.toggle('active', mode === 'tunnel');
    if (this.dom.netLanView) this.dom.netLanView.style.display = (mode === 'lan') ? 'flex' : 'none';
    if (this.dom.netTunnelView) this.dom.netTunnelView.style.display = (mode === 'tunnel') ? 'flex' : 'none';
  }

  async toggleTunnel() {
    if (!this.networkInfo) return;
    const isActive = !!this.networkInfo.tunnel_url;
    if (this.dom.tunnelBtnLabel) {
      this.dom.tunnelBtnLabel.textContent = isActive ? "Arrêt en cours..." : "Démarrage du lien Internet (3s)...";
    }
    try {
      const endpoint = isActive ? '/api/tunnel/stop' : '/api/tunnel/start';
      const resp = await fetch(this.getApiUrl(endpoint), { method: 'POST' });
      const info = await resp.json();
      this.networkInfo.tunnel_url = info.url;
      this.networkInfo.tunnel_status = info.status;
      this.updateNetworkDisplay();
      if (!isActive && info.url) {
        this.showToast("🌍 Lien Internet activé ! Partagez-le avec vos amis.");
      } else if (isActive) {
        this.showToast("Lien Internet désactivé.");
      }
    } catch (e) {
      this.showToast("Erreur lors de l'activation du tunnel Internet.");
    }
  }

  copyInviteUrl(forcedMode = null) {
    const roomParam = this.roomId !== 'default' ? `?room=${encodeURIComponent(this.roomId)}` : '';
    let urlToCopy = '';

    // En mode hébergé (Netlify), on copie toujours l'URL publique de la page
    if (this.isHostedMode()) {
      urlToCopy = `${window.location.origin}/${roomParam}`;
    } else {
      const mode = forcedMode || this.activeNetMode || 'lan';
      if (mode === 'tunnel' && this.networkInfo && this.networkInfo.tunnel_url) {
        urlToCopy = `${this.networkInfo.tunnel_url}/${roomParam}`;
      } else if (this.networkInfo && this.networkInfo.lan_ip && this.networkInfo.lan_ip !== '127.0.0.1') {
        const portStr = this.networkInfo.port ? `:${this.networkInfo.port}` : '';
        urlToCopy = `http://${this.networkInfo.lan_ip}${portStr}/${roomParam}`;
      } else if (this.dom.inviteUrlInput && this.dom.inviteUrlInput.value && !this.dom.inviteUrlInput.value.includes('127.0.0.1')) {
        urlToCopy = this.dom.inviteUrlInput.value;
      } else {
        urlToCopy = window.location.href;
      }
    }

    navigator.clipboard.writeText(urlToCopy).then(() => {
      const copyBtns = [
        this.dom.btnCopyInvite,
        this.dom.btnHeaderInvite,
        this.dom.btnCopyDrawer,
        this.dom.btnLobbyCopyLink,
        this.dom.btnCopyTunnel
      ];
      copyBtns.forEach(btn => {
        if (btn) btn.innerHTML = '<span>✅</span> Copié !';
      });
      if (this.dom.faqBtn) this.dom.faqBtn.textContent = '✅';
      const modeLabel = this.isHostedMode() ? 'du salon' : ((forcedMode || this.activeNetMode) === 'tunnel' ? 'Internet' : 'Réseau Wi-Fi');
      this.showToast(`Lien ${modeLabel} copié ! Partagez-le avec vos amis 📋`);
      setTimeout(() => {
        if (this.dom.btnCopyInvite) this.dom.btnCopyInvite.innerHTML = '<span>🔗</span> Inviter';
        if (this.dom.btnHeaderInvite) this.dom.btnHeaderInvite.innerHTML = '<span>🔗</span> Inviter';
        if (this.dom.btnCopyDrawer) this.dom.btnCopyDrawer.innerHTML = '<span>📋</span> Copier';
        if (this.dom.btnCopyTunnel) this.dom.btnCopyTunnel.innerHTML = '<span>📋</span> Copier';
        if (this.dom.btnLobbyCopyLink) this.dom.btnLobbyCopyLink.innerHTML = '<span>📋</span> Copier le lien';
        if (this.dom.faqBtn) this.dom.faqBtn.textContent = '❓';
      }, 2500);
    }).catch(() => {
      prompt('Adresse à partager à vos amis :', urlToCopy);
    });
  }

  escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  async leaveRoom(roomId) {
    if (!roomId) return;
    try {
      if (this.ws) {
        try {
          this.ws.onclose = null;
          this.ws.close();
        } catch (e) {}
        this.ws = null;
        this.wsRoomId = null;
      }
      await fetch(this.getApiUrl('/api/room/leave'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          room_id: roomId,
          player_id: this.playerId
        })
      });
    } catch (e) {
      console.warn('Erreur leaveRoom:', e);
    }
  }

  async switchRoom(newRoomId) {
    const cleanId = (newRoomId || '').trim();
    if (!cleanId) return;

    if (this.roomId && this.roomId !== cleanId) {
      if (!this.roomId.startsWith('solo-')) {
        await this.leaveRoom(this.roomId);
      } else if (this.ws) {
        try {
          this.ws.onclose = null;
          this.ws.close();
        } catch (e) {}
        this.ws = null;
        this.wsRoomId = null;
      }
    }

    this.isSoloMode = false;
    localStorage.setItem('pedantix_play_mode', 'multi');
    localStorage.setItem('pedantix_last_room', cleanId);
    this.roomId = cleanId;

    const url = new URL(window.location.href);
    url.searchParams.delete('mode');
    url.searchParams.set('room', cleanId);
    window.history.replaceState({}, '', url.toString());

    document.body.classList.remove('solo-mode');
    if (this.dom.btnTypeSolo) this.dom.btnTypeSolo.classList.remove('active');
    if (this.dom.btnTypeMulti) this.dom.btnTypeMulti.classList.add('active');

    this.closeModal(this.dom.roomsModal);
    this.showToast(`Salon « ${cleanId} » rejoint 🌐`);
    this.fetchNetworkInfo();
    this.joinRoom();
  }

  async openRoomsBrowser() {
    this.playTone('click');
    if (this.dom.currentRoomNameText) {
      this.dom.currentRoomNameText.textContent = this.isSoloMode ? '(Mode Solo)' : this.roomId;
    }
    this.openModal(this.dom.roomsModal);
    await this.fetchRoomsList();
  }

  async fetchRoomsList() {
    if (!this.dom.roomsList) return;
    this.dom.roomsList.innerHTML = '<div class="rooms-loading-placeholder">Chargement des salons en ligne...</div>';

    try {
      const resp = await fetch(this.getApiUrl('/api/rooms'));
      const data = await resp.json();
      const rooms = (data.rooms || []).filter(r => !r.room_id.startsWith('solo-'));

      if (this.dom.roomsCountBadge) {
        this.dom.roomsCountBadge.textContent = `${rooms.length} salon${rooms.length > 1 ? 's' : ''} actif${rooms.length > 1 ? 's' : ''}`;
      }

      if (rooms.length === 0) {
        this.dom.roomsList.innerHTML = `
          <div class="rooms-empty-state" style="grid-column: 1 / -1; text-align: center; padding: 2rem; opacity: 0.85;">
            <p style="font-size: 1rem; font-weight: 600;">Aucun salon public disponible pour l'instant.</p>
            <p style="font-size: 0.85rem; margin-top: 0.5rem; opacity: 0.8;">Créez le vôtre avec le bouton <b>« ➕ Créer un nouveau salon »</b> ci-dessus pour jouer avec vos amis !</p>
          </div>
        `;
        return;
      }

      this.dom.roomsList.innerHTML = '';
      rooms.forEach(r => {
        const isCurrent = (!this.isSoloMode && r.room_id === this.roomId);
        const card = document.createElement('div');
        card.className = `room-card ${isCurrent ? 'current-active-card' : ''}`;

        const statusLabel = r.status === 'playing' ? 'En jeu' : 'Salon d\'attente';
        const statusClass = r.status === 'playing' ? 'playing' : 'lobby';
        const modeLabel = r.game_mode === 'team' ? 'Par équipes' : 'Chacun pour soi';
        const playersText = (r.players && r.players.length > 0) ? r.players.join(', ') : 'Aucun joueur';

        card.innerHTML = `
          <div class="room-card-header">
            <span class="room-card-title">${this.escapeHtml(r.room_id)}</span>
            <span class="room-card-status-badge ${statusClass}">${statusLabel}</span>
          </div>
          <div class="room-card-meta">
            <span>👥 <b>${r.players_count}</b> joueur${r.players_count > 1 ? 's' : ''} • Host : <b>${this.escapeHtml(r.host_name || 'Anonyme')}</b></span>
            <span>🎮 Mode : ${modeLabel}</span>
            <span class="room-card-players-list" title="${this.escapeHtml(playersText)}">Joueurs : ${this.escapeHtml(playersText)}</span>
          </div>
          <div class="room-card-footer">
            ${isCurrent
              ? '<span style="font-size: 0.82rem; font-weight: 700; color: #10b981;">✓ Vous êtes dans ce salon</span>'
              : `<button type="button" class="btn-join-room-card btn-join-code" data-room-id="${this.escapeHtml(r.room_id)}">Rejoindre</button>`
            }
          </div>
        `;

        if (!isCurrent) {
          const btn = card.querySelector('.btn-join-room-card');
          if (btn) {
            btn.addEventListener('click', () => this.switchRoom(r.room_id));
          }
        }

        this.dom.roomsList.appendChild(card);
      });
    } catch (e) {
      console.warn('Erreur fetchRoomsList:', e);
      if (this.dom.roomsList) {
        this.dom.roomsList.innerHTML = '<div class="rooms-loading-placeholder" style="color: #ef4444;">Erreur de connexion au serveur.</div>';
      }
    }
  }

  async createNewRoom() {
    this.playTone('click');
    const customCode = prompt('Nom ou code du nouveau salon (laissez vide pour générer un code aléatoire) :');
    if (customCode === null) return;
    const roomId = (customCode && customCode.trim()) ? customCode.trim() : `salon-${Math.floor(Math.random() * 899 + 100)}`;

    try {
      if (this.roomId && this.roomId !== roomId) {
        if (!this.roomId.startsWith('solo-')) {
          await this.leaveRoom(this.roomId);
        } else if (this.ws) {
          try {
            this.ws.onclose = null;
            this.ws.close();
          } catch (e) {}
          this.ws = null;
          this.wsRoomId = null;
        }
      }

      const resp = await fetch(this.getApiUrl('/api/room/create'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          host_player_id: this.playerId,
          room_id: roomId
        })
      });
      const data = await resp.json();

      this.roomId = data.room_id || roomId;
      this.isSoloMode = false;
      localStorage.setItem('pedantix_play_mode', 'multi');
      localStorage.setItem('pedantix_last_room', this.roomId);

      const newUrl = new URL(window.location.href);
      newUrl.searchParams.delete('mode');
      newUrl.searchParams.set('room', this.roomId);
      window.history.replaceState({}, '', newUrl.toString());

      document.body.classList.remove('solo-mode');
      if (this.dom.btnTypeSolo) this.dom.btnTypeSolo.classList.remove('active');
      if (this.dom.btnTypeMulti) this.dom.btnTypeMulti.classList.add('active');

      this.closeModal(this.dom.roomsModal);
      this.showToast(`Salon « ${this.roomId} » créé ! Vous êtes l'Host 👑`);
      this.fetchNetworkInfo();
      this.joinRoom();
    } catch (e) {
      console.error(e);
      this.showToast('Erreur lors de la création du salon.');
    }
  }

  // =========================================================================
  // LIVE CHAT ENGINE
  // =========================================================================

  setupChat() {
    // Sidebar Tabs
    if (this.dom.tabBtnContest) {
      this.dom.tabBtnContest.addEventListener('click', () => this.switchSidebarTab('contest'));
    }
    if (this.dom.tabBtnChat) {
      this.dom.tabBtnChat.addEventListener('click', () => this.switchSidebarTab('chat'));
    }

    // Sidebar Chat form
    if (this.dom.chatFormSidebar) {
      this.dom.chatFormSidebar.addEventListener('submit', (e) => {
        e.preventDefault();
        const text = this.dom.chatInputSidebar.value;
        if (text && text.trim()) {
          this.sendChatMessage(text.trim());
          this.dom.chatInputSidebar.value = '';
        }
      });
    }

    // Lobby Chat form
    if (this.dom.chatFormLobby) {
      this.dom.chatFormLobby.addEventListener('submit', (e) => {
        e.preventDefault();
        const text = this.dom.chatInputLobby.value;
        if (text && text.trim()) {
          this.sendChatMessage(text.trim());
          this.dom.chatInputLobby.value = '';
        }
      });
    }

    // Quick emoji reactions (sidebar)
    if (this.dom.chatQuickReactionsSidebar) {
      this.dom.chatQuickReactionsSidebar.querySelectorAll('.btn-chat-reaction').forEach(btn => {
        btn.addEventListener('click', () => {
          const emoji = btn.dataset.emoji;
          if (emoji) this.sendChatMessage(emoji);
        });
      });
    }

    // Quick emoji reactions (lobby)
    if (this.dom.chatQuickReactionsLobby) {
      this.dom.chatQuickReactionsLobby.querySelectorAll('.btn-chat-reaction').forEach(btn => {
        btn.addEventListener('click', () => {
          const emoji = btn.dataset.emoji;
          if (emoji) this.sendChatMessage(emoji);
        });
      });
    }

    // Floating chat toast click
    if (this.dom.chatFloatingToast) {
      this.dom.chatFloatingToast.addEventListener('click', (e) => {
        if (e.target.id === 'btn-chat-toast-close') {
          this.dom.chatFloatingToast.style.display = 'none';
          return;
        }
        this.switchSidebarTab('chat');
        this.dom.chatFloatingToast.style.display = 'none';
      });
    }
    if (this.dom.btnChatToastClose) {
      this.dom.btnChatToastClose.addEventListener('click', (e) => {
        e.stopPropagation();
        this.dom.chatFloatingToast.style.display = 'none';
      });
    }
  }

  switchSidebarTab(tabName) {
    this.activeSidebarTab = tabName;
    if (this.dom.tabBtnContest) this.dom.tabBtnContest.classList.toggle('active', tabName === 'contest');
    if (this.dom.tabBtnChat) this.dom.tabBtnChat.classList.toggle('active', tabName === 'chat');
    if (this.dom.compTabContest) this.dom.compTabContest.style.display = (tabName === 'contest') ? 'flex' : 'none';
    if (this.dom.compTabChat) this.dom.compTabChat.style.display = (tabName === 'chat') ? 'flex' : 'none';

    if (tabName === 'chat') {
      this.unreadChatCount = 0;
      if (this.dom.chatUnreadBadge) {
        this.dom.chatUnreadBadge.style.display = 'none';
        this.dom.chatUnreadBadge.textContent = '0';
      }
      this.scrollChatToBottom();
      if (this.dom.chatInputSidebar) this.dom.chatInputSidebar.focus();
    }
  }

  async sendChatMessage(text) {
    if (!text || !text.trim()) return;
    const msgPayload = {
      type: 'chat',
      room_id: this.roomId,
      player_id: this.playerId,
      sender_name: this.playerName || 'Joueur',
      text: text.trim()
    };

    // Send via WebSocket if open
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msgPayload));
    } else {
      // Fallback REST endpoint
      try {
        await fetch(this.getApiUrl('/api/room/chat'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(msgPayload)
        });
      } catch (e) {
        console.warn("Erreur envoi chat", e);
      }
    }
  }

  handleIncomingChatMessage(msg) {
    if (!msg || !msg.text) return;
    this.chatMessages.push(msg);

    // Remove empty hints
    const hints = document.querySelectorAll('.chat-empty-hint');
    hints.forEach(el => el.remove());

    const isMine = msg.player_id === this.playerId;
    const msgEl1 = this.createChatMessageElement(msg, isMine);
    const msgEl2 = this.createChatMessageElement(msg, isMine);

    if (this.dom.chatMessagesSidebar) {
      this.dom.chatMessagesSidebar.appendChild(msgEl1);
    }
    if (this.dom.chatMessagesLobby) {
      this.dom.chatMessagesLobby.appendChild(msgEl2);
    }

    this.scrollChatToBottom();

    if (!isMine) {
      this.playTone('message');
      if (this.activeSidebarTab !== 'chat') {
        this.unreadChatCount += 1;
        if (this.dom.chatUnreadBadge) {
          this.dom.chatUnreadBadge.textContent = this.unreadChatCount > 9 ? '9+' : this.unreadChatCount;
          this.dom.chatUnreadBadge.style.display = 'inline-flex';
        }
        this.showFloatingChatToast(msg);
      }
    }
  }

  createChatMessageElement(msg, isMine) {
    const row = document.createElement('div');
    row.className = `chat-msg-row ${isMine ? 'mine' : 'theirs'}`;

    let teamTagHtml = '';
    const playerObj = (this.leaderboard || []).find(p => p.player_id === msg.player_id);
    const pTeam = playerObj ? playerObj.team : (msg.team || null);
    if (this.gameMode === 'team' && pTeam) {
      const teamTags = {
        blue: { label: '🔵 Bleu', class: 'blue' },
        red: { label: '🔴 Rouge', class: 'red' },
        green: { label: '🟢 Vert', class: 'green' },
        yellow: { label: '🟡 Jaune', class: 'yellow' }
      };
      const tt = teamTags[pTeam] || teamTags.blue;
      teamTagHtml = `<span class="chat-team-tag ${tt.class}">${tt.label}</span>`;
    }

    const authorLine = document.createElement('div');
    authorLine.className = 'chat-author-line';
    authorLine.innerHTML = `${teamTagHtml}<span class="chat-author-name">${this.escapeHtml(msg.sender_name)}</span><span class="chat-time-tag">${msg.timestamp || ''}</span>`;

    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble';
    bubble.textContent = msg.text;

    row.appendChild(authorLine);
    row.appendChild(bubble);
    return row;
  }

  loadHistoricalChatMessages(messages) {
    if (!Array.isArray(messages)) return;
    this.chatMessages = [];
    if (this.dom.chatMessagesSidebar) this.dom.chatMessagesSidebar.innerHTML = '';
    if (this.dom.chatMessagesLobby) this.dom.chatMessagesLobby.innerHTML = '';

    if (messages.length === 0) {
      if (this.dom.chatMessagesSidebar) {
        this.dom.chatMessagesSidebar.innerHTML = `<div class="chat-empty-hint">💬 Aucun message pour l'instant.<br>Discutez en direct avec vos amis !</div>`;
      }
      if (this.dom.chatMessagesLobby) {
        this.dom.chatMessagesLobby.innerHTML = `<div class="chat-empty-hint">Dites un mot ou réagissez avec un emoji ci-dessous ! 👋</div>`;
      }
      return;
    }

    messages.forEach(m => {
      this.chatMessages.push(m);
      const isMine = m.player_id === this.playerId;
      const el1 = this.createChatMessageElement(m, isMine);
      const el2 = this.createChatMessageElement(m, isMine);
      if (this.dom.chatMessagesSidebar) this.dom.chatMessagesSidebar.appendChild(el1);
      if (this.dom.chatMessagesLobby) this.dom.chatMessagesLobby.appendChild(el2);
    });

    this.scrollChatToBottom();
  }

  scrollChatToBottom() {
    if (this.dom.chatMessagesSidebar) {
      this.dom.chatMessagesSidebar.scrollTop = this.dom.chatMessagesSidebar.scrollHeight;
    }
    if (this.dom.chatMessagesLobby) {
      this.dom.chatMessagesLobby.scrollTop = this.dom.chatMessagesLobby.scrollHeight;
    }
  }

  showFloatingChatToast(msg) {
    if (!this.dom.chatFloatingToast) return;
    if (this.dom.chatToastSender) this.dom.chatToastSender.textContent = msg.sender_name;
    if (this.dom.chatToastText) this.dom.chatToastText.textContent = msg.text;
    this.dom.chatFloatingToast.style.display = 'flex';

    if (this._chatToastTimeout) clearTimeout(this._chatToastTimeout);
    this._chatToastTimeout = setTimeout(() => {
      if (this.dom.chatFloatingToast) {
        this.dom.chatFloatingToast.style.display = 'none';
      }
    }, 4500);
  }

  async joinRoom() {
    this.startTime = Date.now();
    this.previousInputs = [];
    this.prevInputIdx = -1;
    this.isWon = false;
    this.dom.successBox.classList.remove('active');
    this.dom.errorLabel.textContent = '';
    this.dom.wikiImg.style.display = 'none';
    this.hideOpponentWin();

    if (this.dom.roomCodeDisplay) {
      this.dom.roomCodeDisplay.textContent = this.roomId;
    }

    try {
      const resp = await fetch(this.getApiUrl('/api/room/join'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          room_id: this.roomId,
          player_id: this.playerId,
          player_name: this.playerName
        })
      });

      if (!resp.ok) throw new Error('Erreur de connexion');
      const data = await resp.json();

      this.sessionId = data.session.session_id;
      this.seed = data.seed;
      this.tokens = data.session.tokens;
      this.tokensById = {};
      this.tokens.forEach(t => {
        t.is_word = (t.type === 'word' || !!t.is_word);
        this.tokensById[t.id] = t;
      });

      this.history = data.session.history || [];
      this.totalWords = data.session.total_words;
      this.revealedWordsCount = data.session.revealed_words_count;
      this.solution = data.session.solution;
      this.isWon = data.player ? data.player.is_won : false;
      this.isHost = data.player ? data.player.is_host : false;
      this.isReady = data.player ? data.player.is_ready : false;
      this.myScore = data.player ? data.player.score : 0;
      this.canStart = data.can_start || false;
      this.roomStatus = data.status || 'lobby';
      this.lastRound = data.last_round || null;

      this.gameMode = data.game_mode || 'individual';
      if (data.player && data.player.team) this.myTeam = data.player.team;
      if (data.teams) this.teamsData = data.teams;

      this.updateBadges();
      this.renderBoard();
      this.updateDayMeter();
      this.renderHistory();

      if (data.leaderboard) this.updateLeaderboard(data.leaderboard);
      if (data.activity) this.updateActivity(data.activity);
      if (data.chat_messages) this.loadHistoricalChatMessages(data.chat_messages);

      this.updateModeUI();
      this.syncRoomUI();
      this.initWebSocket();

      // Check current phase
      if (data.revealed_letters) this.revealedLetters = data.revealed_letters;
      if (data.next_letter_hint_time) this.nextLetterHintTime = data.next_letter_hint_time;

      if (this.roomStatus === 'starting' && data.countdown_end) {
        this.stopHintTimer();
        const left = Math.max(1, Math.ceil(data.countdown_end - (Date.now() / 1000)));
        this.startCountdown(left);
      } else if (this.roomStatus === 'ending' && data.timer_30s_end) {
        this.stopHintTimer();
        const left = Math.max(1, Math.ceil(data.timer_30s_end - (Date.now() / 1000)));
        this.startSprintTimer(data.first_winner_name || 'Un joueur', left, data.timer_30s_end);
      } else if (this.roomStatus === 'playing' && this.nextLetterHintTime && !this.isWon) {
        this.startHintTimer(this.nextLetterHintTime);
      } else {
        this.stopHintTimer();
      }

    } catch (err) {
      console.error(err);
      this.showToast('Erreur lors de la connexion au concours.');
    }
  }

  async reloadGameSession() {
    try {
      const resp = await fetch(this.getApiUrl(`/api/room/${encodeURIComponent(this.roomId)}/state?player_id=${encodeURIComponent(this.playerId)}`));
      if (!resp.ok) return;
      const data = await resp.json();
      if (data.session) {
        this.sessionId = data.session.session_id;
        this.seed = data.seed;
        this.tokens = data.session.tokens || [];
        this.tokensById = {};
        this.tokens.forEach(t => {
          t.is_word = (t.type === 'word' || !!t.is_word);
          this.tokensById[t.id] = t;
        });
        this.history = data.session.history || [];
        this.totalWords = data.session.total_words || 0;
        this.revealedWordsCount = data.session.revealed_words_count || 0;
        this.solution = data.session.solution || null;
        this.isWon = false;
        this.dom.successBox.classList.remove('active');
        this.dom.errorLabel.textContent = '';
        this.dom.wikiImg.style.display = 'none';
        this.hideOpponentWin();

        if (data.game_mode) this.gameMode = data.game_mode;
        if (data.player && data.player.team) this.myTeam = data.player.team;
        if (data.teams) this.teamsData = data.teams;

        this.updateBadges();
        this.renderBoard();
        this.updateDayMeter();
        this.renderHistory();
        this.updateModeUI();

        if (data.revealed_letters) this.revealedLetters = data.revealed_letters;
        if (data.next_letter_hint_time) this.nextLetterHintTime = data.next_letter_hint_time;
        if (this.roomStatus === 'playing' && this.nextLetterHintTime && !this.isWon) {
          this.startHintTimer(this.nextLetterHintTime);
        } else {
          this.stopHintTimer();
        }
      }
    } catch (e) {
      console.error("Erreur rechargement session de jeu:", e);
    }
  }

  initWebSocket() {
    // Si la socket est déjà connectée au même salon, on la conserve
    if (this.ws && this.wsRoomId === this.roomId && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }

    if (this.ws) {
      try {
        this.ws.onclose = null;
        this.ws.close();
      } catch (e) {}
      this.ws = null;
    }

    this.wsRoomId = this.roomId;
    const wsUrl = this.getWsUrl(`/ws/room/${encodeURIComponent(this.roomId)}?player_id=${encodeURIComponent(this.playerId)}`);

    try {
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        this.ws.send(JSON.stringify({ type: 'identify', player_id: this.playerId }));
        if (this.pingInterval) clearInterval(this.pingInterval);
        this.pingInterval = setInterval(() => {
          if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ type: 'ping' }));
          }
        }, 20000);
      };

      this.ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          this.handleWebSocketMessage(msg);
        } catch (e) {
          console.error("Message WS invalide", e);
        }
      };

      this.ws.onclose = () => {
        if (this.pingInterval) clearInterval(this.pingInterval);
        if (this.wsRoomId === this.roomId) {
          setTimeout(() => {
            if (this.wsRoomId === this.roomId && (!this.ws || this.ws.readyState === WebSocket.CLOSED)) {
              this.initWebSocket();
            }
          }, 3000);
        }
      };
    } catch (e) {
      console.warn("WebSocket non disponible", e);
    }
  }

  handleWebSocketMessage(msg) {
    if (msg.type === 'init') {
      if (msg.game_mode) this.gameMode = msg.game_mode;
      if (msg.teams) this.teamsData = msg.teams;
      if (msg.leaderboard) this.updateLeaderboard(msg.leaderboard);
      if (msg.activity) this.updateActivity(msg.activity);
      if (msg.chat_messages) this.loadHistoricalChatMessages(msg.chat_messages);
      if (msg.revealed_letters) this.revealedLetters = msg.revealed_letters;
      if (msg.next_letter_hint_time) this.nextLetterHintTime = msg.next_letter_hint_time;
      this.roomStatus = msg.status || this.roomStatus;
      this.canStart = msg.can_start || this.canStart;
      this.updateModeUI();
      this.syncRoomUI();

      if (this.roomStatus === 'playing' && this.nextLetterHintTime && !this.isWon) {
        this.startHintTimer(this.nextLetterHintTime);
      } else {
        this.stopHintTimer();
      }

    } else if (msg.type === 'chat_message') {
      this.handleIncomingChatMessage(msg.message);

    } else if (msg.type === 'mode_changed') {
      this.gameMode = msg.game_mode;
      if (msg.teams) this.teamsData = msg.teams;
      if (msg.leaderboard) this.updateLeaderboard(msg.leaderboard);
      if (msg.activity) this.updateActivity(msg.activity);
      if (msg.can_start !== undefined) this.canStart = msg.can_start;
      this.updateModeUI();
      this.syncRoomUI();
      const modeLabel = this.gameMode === 'team' ? 'Par Équipes (Bleu, Rouge, Vert, Jaune)' : 'Chacun pour soi';
      this.showToast(`🎮 Mode : ${modeLabel}`);

    } else if (msg.type === 'team_changed') {
      const lobbyInner = this.dom.lobbyModal ? this.dom.lobbyModal.querySelector('.modal') : null;
      const savedLobbyScroll = lobbyInner ? lobbyInner.scrollTop : 0;
      const savedOverlayScroll = this.dom.lobbyModal ? this.dom.lobbyModal.scrollTop : 0;
      const savedWindowScroll = window.scrollY;

      if (msg.player_id === this.playerId) {
        this.myTeam = msg.team;
      }
      if (msg.teams) this.teamsData = msg.teams;
      if (msg.leaderboard) this.updateLeaderboard(msg.leaderboard);
      if (msg.activity) this.updateActivity(msg.activity);
      if (msg.can_start !== undefined) this.canStart = msg.can_start;
      this.renderTeamsRoster();
      this.renderTeamConfrontation();
      this.syncRoomUI();

      if (lobbyInner && savedLobbyScroll) lobbyInner.scrollTop = savedLobbyScroll;
      if (this.dom.lobbyModal && savedOverlayScroll) this.dom.lobbyModal.scrollTop = savedOverlayScroll;
      if (savedWindowScroll) window.scrollTo(0, savedWindowScroll);

    } else if (msg.type === 'player_joined' || msg.type === 'player_ready_changed' || msg.type === 'player_left' || msg.type === 'player_disconnected') {
      const lobbyInner = this.dom.lobbyModal ? this.dom.lobbyModal.querySelector('.modal') : null;
      const savedLobbyScroll = lobbyInner ? lobbyInner.scrollTop : 0;
      const savedOverlayScroll = this.dom.lobbyModal ? this.dom.lobbyModal.scrollTop : 0;
      const savedWindowScroll = window.scrollY;

      const wasHost = this.isHost;
      if (msg.game_mode) this.gameMode = msg.game_mode;
      if (msg.teams) this.teamsData = msg.teams;
      if (msg.leaderboard) this.updateLeaderboard(msg.leaderboard);
      if (msg.activity) this.updateActivity(msg.activity);
      if (msg.can_start !== undefined) this.canStart = msg.can_start;
      if (msg.host_player_id) {
        this.isHost = (msg.host_player_id === this.playerId);
      }
      if (msg.player_id === this.playerId && msg.is_ready !== undefined) {
        this.isReady = msg.is_ready;
      }
      if (msg.type === 'player_left' && msg.player_name) {
        if (this.isHost && !wasHost) {
          this.showToast(`👑 ${msg.player_name} a quitté le salon. Vous êtes maintenant l'Host !`);
        } else {
          this.showToast(`👋 ${msg.player_name} a quitté le salon.`);
        }
      }
      if (this.gameMode === 'team') {
        this.renderTeamsRoster();
        this.renderTeamConfrontation();
      }
      this.syncRoomUI();

      if (lobbyInner && savedLobbyScroll) lobbyInner.scrollTop = savedLobbyScroll;
      if (this.dom.lobbyModal && savedOverlayScroll) this.dom.lobbyModal.scrollTop = savedOverlayScroll;
      if (savedWindowScroll) window.scrollTo(0, savedWindowScroll);

    } else if (msg.type === 'countdown_started') {
      this.roomStatus = 'starting';
      this.stopHintTimer();
      if (msg.game_mode) this.gameMode = msg.game_mode;
      if (msg.teams) this.teamsData = msg.teams;
      this.reloadGameSession();
      this.startCountdown(msg.seconds || 5, msg.end_time);

    } else if (msg.type === 'game_started') {
      this.roomStatus = 'playing';
      if (this.countdownTimer) clearInterval(this.countdownTimer);
      if (this.dom.countdownOverlay) this.dom.countdownOverlay.style.display = 'none';
      if (this.gameMode === 'team') {
        this.renderTeamConfrontation();
      }
      if (msg.revealed_letters) this.revealedLetters = msg.revealed_letters;
      if (msg.next_letter_hint_time) this.nextLetterHintTime = msg.next_letter_hint_time;
      if (this.nextLetterHintTime && !this.isWon) {
        this.startHintTimer(this.nextLetterHintTime);
      }
      this.syncRoomUI();
      this.showToast('🚀 C\'est parti ! Trouvez le titre en premier !');
      this.playTone('go');
      this.dom.guessInput.focus();

    } else if (msg.type === 'progress_update') {
      if (msg.game_mode) this.gameMode = msg.game_mode;
      if (msg.teams) {
        this.teamsData = msg.teams;
        if (this.gameMode === 'team') this.renderTeamConfrontation();
      }
      if (msg.leaderboard) this.updateLeaderboard(msg.leaderboard);
      if (msg.activity) this.updateActivity(msg.activity);

      // Cooperative guess update for teammates
      if (this.gameMode === 'team' && msg.team === this.myTeam && msg.team_guess) {
        const tg = msg.team_guess;
        const isTeammate = (tg.player_id !== this.playerId);

        let hasNewReveals = false;
        if (tg.newly_revealed && Object.keys(tg.newly_revealed).length > 0) {
          this.revealTokens(tg.newly_revealed);
          this.revealedWordsCount += Object.keys(tg.newly_revealed).length;
          hasNewReveals = true;
        }

        if (tg.close_tokens && tg.close_tokens.length > 0) {
          this.applyCloseTokens(tg.close_tokens, tg.word);
        }

        this.updateDayMeter();

        if (isTeammate) {
          if (hasNewReveals) {
            this.playTone('match');
            this.showToast(`🤝 ${tg.player_name} a trouvé "${tg.word}" (${tg.matches_count} occurrence${tg.matches_count > 1 ? 's' : ''}) !`);
          } else if (tg.status === 'close' || (tg.close_tokens && tg.close_tokens.length > 0)) {
            this.playTone('close');
            this.showToast(`🤝 Mot proche trouvé par ${tg.player_name} : "${tg.word}" (${tg.score || 50}%)`);
          }
          if (tg.word && tg.word !== '••••') {
            this.addTeammateGuessToHistory(tg);
          }
        }
      }

      // Check win in team mode
      if (this.gameMode === 'team' && msg.is_game_won && !this.isWon) {
        if (msg.team === this.myTeam) {
          this.isWon = true;
          this.handleVictory();
          this.showToast(`🏆 Victoire ! Votre équipe a trouvé le titre !`);
        } else {
          this.hideOpponentWin();
          this.showToast(`⏱️ L'équipe adverse a trouvé le titre ! Il vous reste 30 secondes pour le trouver aussi (+1 pt) !`);
        }
      }

    } else if (msg.type === 'first_winner') {
      this.roomStatus = 'ending';
      this.stopHintTimer();
      this.hideOpponentWin();
      this.startSprintTimer(msg.winner_name, msg.seconds || 30, msg.end_time);
      this.showToast(`🏆 ${msg.winner_name} a trouvé le titre ! Il vous reste 30 secondes pour trouver (+2 pt au 2e, +1 pt au 3e) !`);

    } else if (msg.type === 'round_over' || msg.type === 'round_over_to_lobby') {
      this.stopHintTimer();
      if (this.sprintInterval) clearInterval(this.sprintInterval);
      if (this.dom.sprintTimerBanner) this.dom.sprintTimerBanner.style.display = 'none';
      this.roomStatus = 'lobby';
      this.isReady = false;
      this.lastRound = msg.last_round || null;
      if (msg.game_mode) this.gameMode = msg.game_mode;
      if (msg.teams) this.teamsData = msg.teams;
      if (msg.leaderboard) this.updateLeaderboard(msg.leaderboard);
      if (msg.activity) this.updateActivity(msg.activity);
      this.playTone('win');
      this.showToast('🎉 Manche terminée ! Les scores ont été mis à jour.');
      this.updateModeUI();
      this.syncRoomUI();

    } else if (msg.type === 'new_round') {
      this.stopHintTimer();
      this.hideOpponentWin();
      this.closeModal(this.dom.roundOverModal);
      this.dom.successBox.classList.remove('active');
      this.showToast('🎲 Nouvelle partie lancée !');
      this.joinRoom();

    } else if (msg.type === 'letter_hint') {
      const letter = msg.letter || '';
      if (msg.revealed_letters) this.revealedLetters = msg.revealed_letters;
      if (msg.next_letter_hint_time) this.nextLetterHintTime = msg.next_letter_hint_time;

      this.playTone('hint');
      this.showToast(`💡 Indice (5 min) : La lettre « ${letter} » a été dévoilée partout dans l'article !`);

      const patterns = msg.token_patterns || msg.token_hints;
      if (patterns) {
        Object.entries(patterns).forEach(([tid, pattern]) => {
          const token = this.tokensById[tid];
          if (token && !token.revealed) {
            token.hint_pattern = pattern;
            const el = document.getElementById(`token-${tid}`);
            if (el) {
              this.renderTokenContent(token, el);
              el.classList.add('hint-pulse');
              setTimeout(() => {
                el.classList.remove('hint-pulse');
              }, 1200);
            }
          }
        });
      }

      if (this.roomStatus === 'playing' && !this.isWon && this.nextLetterHintTime) {
        this.startHintTimer(this.nextLetterHintTime);
      } else {
        this.stopHintTimer();
      }

    } else if (msg.type === 'surrender_update') {
      if (msg.activity) this.updateActivity(msg.activity);
      this.showSurrenderModal(msg);

    } else if (msg.type === 'surrender_rejected') {
      this.closeModal(this.dom.surrenderModal);
      if (msg.activity) this.updateActivity(msg.activity);
      this.playTone('error');
      this.showToast(`❌ L'abandon a été refusé par ${msg.refuser_name || 'un joueur'}. La partie continue !`);

    } else if (msg.type === 'surrender_cancelled') {
      this.closeModal(this.dom.surrenderModal);
      if (msg.activity) this.updateActivity(msg.activity);
      this.showToast(`↩️ ${msg.initiator_name || 'L\'initiateur'} a annulé la demande d'abandon.`);

    } else if (msg.type === 'surrender_passed') {
      this.handleSurrenderPassed(msg);
    }
  }

  // =========================================================================
  // MULTIPLAYER CONTROLS: READY, START & NEXT ROUND
  // =========================================================================

  async toggleReady() {
    this.playTone('click');
    const lobbyInner = this.dom.lobbyModal ? this.dom.lobbyModal.querySelector('.modal') : null;
    const savedLobbyScroll = lobbyInner ? lobbyInner.scrollTop : 0;
    const savedOverlayScroll = this.dom.lobbyModal ? this.dom.lobbyModal.scrollTop : 0;
    const savedWindowScroll = window.scrollY;

    try {
      const resp = await fetch(this.getApiUrl('/api/room/ready'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          room_id: this.roomId,
          player_id: this.playerId
        })
      });
      const data = await resp.json();
      this.isReady = data.is_ready;
      this.canStart = data.can_start;
      if (data.leaderboard) this.updateLeaderboard(data.leaderboard);
      this.syncRoomUI();

      if (lobbyInner && savedLobbyScroll) lobbyInner.scrollTop = savedLobbyScroll;
      if (this.dom.lobbyModal && savedOverlayScroll) this.dom.lobbyModal.scrollTop = savedOverlayScroll;
      if (savedWindowScroll) window.scrollTo(0, savedWindowScroll);
    } catch (e) {
      console.error(e);
      this.showToast('Erreur lors du changement de statut prêt.');
    }
  }

  async startGame() {
    this.playTone('click');
    try {
      const resp = await fetch(this.getApiUrl('/api/room/start'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          room_id: this.roomId,
          player_id: this.playerId
        })
      });
      const data = await resp.json();
      if (data.error) {
        this.showToast(data.error);
      }
    } catch (e) {
      console.error(e);
      this.showToast('Erreur lors du démarrage de la partie.');
    }
  }

  async startNextRound() {
    this.playTone('click');
    try {
      const resp = await fetch(this.getApiUrl('/api/room/next-round'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          room_id: this.roomId,
          player_id: this.playerId
        })
      });
      const data = await resp.json();
      if (data.error) {
        this.showToast(data.error);
      }
    } catch (e) {
      console.error(e);
      this.showToast('Erreur lors du lancement de la manche suivante.');
    }
  }

  async requestNewRound() {
    // If in multiplayer and host, start next round directly; else join/request
    if (this.isHost || this.isSoloMode) {
      return this.startNextRound();
    }
    this.showToast('Seul l\'Host peut lancer une nouvelle manche.');
  }

  startCountdown(seconds, endTime) {
    if (this.countdownTimer) clearInterval(this.countdownTimer);
    if (this.dom.countdownOverlay) this.dom.countdownOverlay.style.display = 'flex';
    this.closeModal(this.dom.lobbyModal);

    let remaining = seconds || 5;
    this.dom.countdownNumber.textContent = remaining;
    this.playTone('beep');

    this.countdownTimer = setInterval(() => {
      remaining -= 1;
      if (remaining > 0) {
        this.dom.countdownNumber.textContent = remaining;
        this.playTone('beep');
      } else if (remaining === 0) {
        this.dom.countdownNumber.textContent = 'GO !';
        this.playTone('go');
      } else {
        clearInterval(this.countdownTimer);
        if (this.dom.countdownOverlay) this.dom.countdownOverlay.style.display = 'none';
        this.roomStatus = 'playing';
        this.syncRoomUI();
        this.dom.guessInput.focus();
      }
    }, 1000);
  }

  startSprintTimer(winnerName, seconds, endTime) {
    if (this.sprintInterval) clearInterval(this.sprintInterval);
    this.roomStatus = 'ending';
    if (this.dom.sprintWinnerName) this.dom.sprintWinnerName.textContent = winnerName;
    if (this.dom.sprintTimerBanner) this.dom.sprintTimerBanner.style.display = 'block';

    const totalSec = seconds || 30;
    let remaining = totalSec;
    if (this.dom.sprintCountdownNum) this.dom.sprintCountdownNum.textContent = remaining;
    if (this.dom.sprintBarFill) this.dom.sprintBarFill.style.width = '100%';

    const startMs = Date.now();
    const endMs = endTime ? (endTime * 1000) : (startMs + totalSec * 1000);

    this.sprintInterval = setInterval(() => {
      const now = Date.now();
      const leftMs = Math.max(0, endMs - now);
      const leftSec = Math.ceil(leftMs / 1000);
      if (this.dom.sprintCountdownNum) this.dom.sprintCountdownNum.textContent = leftSec;

      const pct = Math.max(0, Math.min(100, (leftMs / (totalSec * 1000)) * 100));
      if (this.dom.sprintBarFill) this.dom.sprintBarFill.style.width = `${pct}%`;

      if (leftSec <= 5 && leftSec > 0 && Math.floor(leftMs / 1000) !== remaining) {
        this.playTone('beep');
      }
      remaining = leftSec;

      if (leftMs <= 0) {
        clearInterval(this.sprintInterval);
        if (this.dom.sprintTimerBanner) this.dom.sprintTimerBanner.style.display = 'none';
      }
    }, 150);
  }

  startHintTimer(targetEpoch) {
    this.stopHintTimer();
    if (!targetEpoch || this.roomStatus !== 'playing' || this.isWon) {
      if (this.dom.hintTimerBadge) this.dom.hintTimerBadge.style.display = 'none';
      return;
    }

    if (this.dom.hintTimerBadge) this.dom.hintTimerBadge.style.display = 'inline-flex';

    const update = () => {
      if (this.roomStatus !== 'playing' || this.isWon) {
        this.stopHintTimer();
        return;
      }
      const now = Date.now() / 1000;
      const left = Math.max(0, Math.ceil(targetEpoch - now));
      const mins = Math.floor(left / 60);
      const secs = left % 60;
      const formatted = `${mins}:${secs < 10 ? '0' : ''}${secs}`;
      if (this.dom.hintTimerVal) {
        this.dom.hintTimerVal.textContent = formatted;
      }
      if (this.dom.hintTimerBadge) {
        if (left <= 30 && left > 0) {
          this.dom.hintTimerBadge.classList.add('hint-urgent');
        } else {
          this.dom.hintTimerBadge.classList.remove('hint-urgent');
        }
      }
    };

    update();
    this.hintInterval = setInterval(update, 1000);
  }

  stopHintTimer() {
    if (this.hintInterval) {
      clearInterval(this.hintInterval);
      this.hintInterval = null;
    }
    if (this.dom.hintTimerBadge) {
      this.dom.hintTimerBadge.style.display = 'none';
      this.dom.hintTimerBadge.classList.remove('hint-urgent');
    }
  }

  showRoundOverModal(msg) {
    this.playTone('win');
    if (this.dom.roundOverWinnerTitle) {
      if (msg.abandoned || (msg.last_round && msg.last_round.abandoned)) {
        this.dom.roundOverWinnerTitle.textContent = "Partie abandonnée à l'unanimité (0 point)";
      } else {
        this.dom.roundOverWinnerTitle.textContent = `${msg.winner_name || 'Un joueur'} a remporté la manche !`;
      }
    }

    const sol = msg.solution || {};
    const solTitle = sol.title || msg.title || '...';
    if (this.dom.roundOverSolutionText) this.dom.roundOverSolutionText.textContent = solTitle;
    if (this.dom.roundOverWikiLink) {
      this.dom.roundOverWikiLink.href = sol.url || `https://fr.wikipedia.org/wiki/${encodeURIComponent(solTitle)}`;
    }

    // Populate scoreboard
    if (this.dom.roundOverScoresList) {
      this.dom.roundOverScoresList.innerHTML = '';
      const list = this.leaderboard || [];
      list.forEach((p, idx) => {
        const row = document.createElement('div');
        row.className = `score-row-item ${p.name === msg.winner_name ? 'winner-row' : ''}`;
        row.innerHTML = `
          <span><b>${idx + 1}. ${this.escapeHtml(p.name)}</b> ${p.player_id === this.playerId ? '(Vous)' : ''}</span>
          <span style="font-weight: 800; color: #fbbf24;">🏆 ${p.score} pt${p.score > 1 ? 's' : ''}</span>
        `;
        this.dom.roundOverScoresList.appendChild(row);
      });
    }

    // Show host launch button or waiting message
    this.syncRoomUI();
    this.openModal(this.dom.roundOverModal);
  }

  syncRoomUI() {
    // 1. Room Code and Host Badges
    if (this.dom.roomCodeDisplay) this.dom.roomCodeDisplay.textContent = this.roomId;
    if (this.dom.lobbyRoomNameDisplay) this.dom.lobbyRoomNameDisplay.textContent = this.roomId;
    if (this.dom.hostPill) this.dom.hostPill.style.display = this.isHost ? 'inline-block' : 'none';
    if (this.dom.sideHostPill) this.dom.sideHostPill.style.display = this.isHost ? 'inline-block' : 'none';
    if (this.dom.myPlayerScoreBadge) {
      this.dom.myPlayerScoreBadge.textContent = `${this.myScore} pt${this.myScore > 1 ? 's' : ''}`;
    }

    // 2. Ready status on buttons
    const readyLabel = this.isReady ? 'Je suis prêt ! ✓' : 'Cliquer pour être prêt';
    const readyIcon = this.isReady ? '🟢' : '⏳';

    if (this.dom.btnLobbyToggleReady) {
      this.dom.btnLobbyToggleReady.className = `btn-lobby-ready ${this.isReady ? 'is-ready' : ''}`;
      if (this.dom.lobbyReadyIcon) this.dom.lobbyReadyIcon.textContent = readyIcon;
      if (this.dom.lobbyReadyLabel) this.dom.lobbyReadyLabel.textContent = readyLabel;
    }

    if (this.dom.btnSideReady) {
      this.dom.btnSideReady.className = `btn-side-ready ${this.isReady ? 'is-ready' : ''}`;
      if (this.dom.sideReadyIcon) this.dom.sideReadyIcon.textContent = readyIcon;
      if (this.dom.sideReadyText) this.dom.sideReadyText.textContent = readyLabel;
    }

    if (this.dom.btnRoundReady) {
      this.dom.btnRoundReady.className = `btn-lobby-ready ${this.isReady ? 'is-ready' : ''}`;
      if (this.dom.roundReadyIcon) this.dom.roundReadyIcon.textContent = readyIcon;
      if (this.dom.roundReadyLabel) this.dom.roundReadyLabel.textContent = readyLabel;
    }

    // 3. Phase-specific view toggling
    if (this.isSoloMode) {
      this.closeModal(this.dom.lobbyModal);
      if (this.dom.countdownOverlay) this.dom.countdownOverlay.style.display = 'none';
      if (this.dom.sprintTimerBanner) this.dom.sprintTimerBanner.style.display = 'none';
      if (this.dom.form) {
        this.dom.form.style.opacity = '1';
        this.dom.form.style.pointerEvents = 'auto';
      }
      if (this.dom.wiki) this.dom.wiki.style.opacity = '1';
      if (this.dom.btnSideNew) this.dom.btnSideNew.style.display = 'inline-flex';
      if (!this.isWon) {
        if (this.dom.btnSurrenderRoom) this.dom.btnSurrenderRoom.style.display = 'inline-flex';
        if (this.dom.btnSideSurrender) this.dom.btnSideSurrender.style.display = 'flex';
      } else {
        if (this.dom.btnSurrenderRoom) this.dom.btnSurrenderRoom.style.display = 'none';
        if (this.dom.btnSideSurrender) this.dom.btnSideSurrender.style.display = 'none';
      }
      return;
    }

    if (this.roomStatus === 'lobby') {
      if (this.dom.btnSurrenderRoom) this.dom.btnSurrenderRoom.style.display = 'none';
      if (this.dom.btnSideSurrender) this.dom.btnSideSurrender.style.display = 'none';
      if (!this.lobbyMinimized && !this.dom.lobbyModal.classList.contains('active')) {
        if (!this.dom.roundOverModal || !this.dom.roundOverModal.classList.contains('active')) {
          this.openModal(this.dom.lobbyModal);
        }
      }
      if (this.dom.lobbyModal.classList.contains('active')) {
        this.closeModal(this.dom.roundOverModal);
      }
      if (this.dom.countdownOverlay) this.dom.countdownOverlay.style.display = 'none';
      if (this.dom.sprintTimerBanner) this.dom.sprintTimerBanner.style.display = 'none';

      if (this.dom.form) {
        this.dom.form.style.opacity = '0.3';
        this.dom.form.style.pointerEvents = 'none';
      }
      if (this.dom.wiki) this.dom.wiki.style.opacity = '0.3';

      // Right sidebar controls (only accessible if modal minimized)
      if (this.dom.btnSideStart) {
        this.dom.btnSideStart.style.display = this.isHost ? 'inline-flex' : 'none';
        this.dom.btnSideStart.disabled = !this.canStart;
      }
      if (this.dom.btnSideReady) this.dom.btnSideReady.style.display = 'inline-flex';
      if (this.dom.btnOpenLobby) this.dom.btnOpenLobby.style.display = 'inline-flex';
      if (this.dom.btnNewRoundComp) this.dom.btnNewRoundComp.style.display = 'none';
      if (this.dom.btnSideNew) this.dom.btnSideNew.style.display = 'none';
      if (this.dom.btnOpponentNewRound) this.dom.btnOpponentNewRound.style.display = 'none';

      // Update previous round recap in lobby modal if available
      if (this.lastRound && this.lastRound.abandoned) {
        if (this.dom.lobbyLastRoundBox) this.dom.lobbyLastRoundBox.style.display = 'block';
        if (this.dom.lobbyLastSolutionTitle) this.dom.lobbyLastSolutionTitle.textContent = this.lastRound.title || '...';
        if (this.dom.lobbyLastSolutionLink) {
          this.dom.lobbyLastSolutionLink.href = this.lastRound.url || `https://fr.wikipedia.org/wiki/${encodeURIComponent(this.lastRound.title || '')}`;
        }
        if (this.dom.lobbyPodiumCards) {
          this.dom.lobbyPodiumCards.innerHTML = `
            <div style="grid-column: 1 / -1; padding: 12px; text-align: center; color: #f87171; font-weight: 700; background: rgba(239, 68, 68, 0.12); border-radius: 12px; border: 1px dashed rgba(239, 68, 68, 0.35);">
              🏳️ Manche abandonnée à l'unanimité — Aucun point attribué.
            </div>
          `;
        }
        if (this.dom.lobbyMainTitle) this.dom.lobbyMainTitle.textContent = 'Partie abandonnée ! Prêt pour la suivante ?';
        if (this.dom.lobbyInstructions) {
          this.dom.lobbyInstructions.innerHTML = 'Indiquez que vous êtes <b>prêt</b> pour la manche suivante. L\'Host pourra relancer une partie dès que tout le monde est prêt.';
        }
        if (this.dom.btnLobbyStartGame) {
          this.dom.btnLobbyStartGame.innerHTML = '<span>🎲</span> Relancer une partie';
        }
      } else if (this.lastRound && this.lastRound.podium && this.lastRound.podium.length > 0) {
        if (this.dom.lobbyLastRoundBox) this.dom.lobbyLastRoundBox.style.display = 'block';
        if (this.dom.lobbyLastSolutionTitle) this.dom.lobbyLastSolutionTitle.textContent = this.lastRound.title || '...';
        if (this.dom.lobbyLastSolutionLink) {
          this.dom.lobbyLastSolutionLink.href = this.lastRound.url || `https://fr.wikipedia.org/wiki/${encodeURIComponent(this.lastRound.title || '')}`;
        }
        if (this.dom.lobbyPodiumCards) {
          this.dom.lobbyPodiumCards.innerHTML = '';
          const medals = ['🥇 1er', '🥈 2ème', '🥉 3ème'];
          this.lastRound.podium.forEach(item => {
            const card = document.createElement('div');
            card.className = `podium-card rank-${item.rank}`;
            card.innerHTML = `
              <div class="podium-card-top">
                <span>${medals[item.rank - 1] || `${item.rank}e`}</span>
                <span class="podium-card-points">+${item.points} pt${item.points > 1 ? 's' : ''}</span>
              </div>
              <div class="podium-card-name" title="${this.escapeHtml(item.name)}">${this.escapeHtml(item.name)}</div>
              <div style="font-size: 0.78rem; opacity: 0.75;">${item.attempts} coups (Total: ${item.score} pt)</div>
            `;
            this.dom.lobbyPodiumCards.appendChild(card);
          });
        }
        if (this.dom.lobbyMainTitle) this.dom.lobbyMainTitle.textContent = 'Manche terminée ! Prêt pour la suivante ?';
        if (this.dom.lobbyInstructions) {
          this.dom.lobbyInstructions.innerHTML = 'Indiquez que vous êtes <b>prêt</b> pour la manche suivante. L\'Host pourra relancer une partie dès que tout le monde est prêt.';
        }
        if (this.dom.btnLobbyStartGame) {
          this.dom.btnLobbyStartGame.innerHTML = '<span>🎲</span> Relancer une partie';
        }
      } else {
        if (this.dom.lobbyLastRoundBox) this.dom.lobbyLastRoundBox.style.display = 'none';
        if (this.dom.lobbyMainTitle) this.dom.lobbyMainTitle.textContent = 'Préparez-vous pour le Concours !';
        if (this.dom.lobbyInstructions) {
          this.dom.lobbyInstructions.innerHTML = 'Chaque joueur doit cliquer sur <b>« Je suis prêt »</b>. L\'Host pourra lancer la partie dès que tout le monde est prêt.';
        }
        if (this.dom.btnLobbyStartGame) {
          this.dom.btnLobbyStartGame.innerHTML = '<span>🚀</span> Démarrer la partie';
        }
      }

      // Host controls in lobby modal
      if (this.dom.btnLobbyStartGame) {
        this.dom.btnLobbyStartGame.style.display = this.isHost ? 'inline-flex' : 'none';
        this.dom.btnLobbyStartGame.disabled = !this.canStart;
      }

      if (this.dom.lobbyStatusHint) {
        if (this.isHost) {
          this.dom.lobbyStatusHint.textContent = this.canStart
            ? "Tout le monde est prêt ! Cliquez sur le bouton pour lancer le compte à rebours 🚀"
            : "En attente que tous les joueurs cliquent sur « Je suis prêt »...";
        } else {
          this.dom.lobbyStatusHint.textContent = this.canStart
            ? "Tout le monde est prêt ! En attente du lancement par l'Host 👑..."
            : "En attente que tous les joueurs soient prêts...";
        }
      }

    } else if (this.roomStatus === 'starting') {
      this.closeModal(this.dom.lobbyModal);
      this.closeModal(this.dom.roundOverModal);
      if (this.dom.btnSurrenderRoom) this.dom.btnSurrenderRoom.style.display = 'none';
      if (this.dom.btnSideSurrender) this.dom.btnSideSurrender.style.display = 'none';
      if (this.dom.btnOpenLobby) this.dom.btnOpenLobby.style.display = 'none';
      if (this.dom.btnSideStart) this.dom.btnSideStart.style.display = 'none';
      if (this.dom.btnSideReady) this.dom.btnSideReady.style.display = 'none';
      if (this.dom.btnNewRoundComp) this.dom.btnNewRoundComp.style.display = 'none';
      if (this.dom.btnSideNew) this.dom.btnSideNew.style.display = 'none';
      if (this.dom.btnOpponentNewRound) this.dom.btnOpponentNewRound.style.display = 'none';
      if (this.dom.countdownOverlay) this.dom.countdownOverlay.style.display = 'flex';
      if (this.dom.form) {
        this.dom.form.style.opacity = '0.3';
        this.dom.form.style.pointerEvents = 'none';
      }

    } else if (this.roomStatus === 'playing') {
      this.closeModal(this.dom.lobbyModal);
      this.closeModal(this.dom.roundOverModal);
      if (this.dom.btnSurrenderRoom) this.dom.btnSurrenderRoom.style.display = 'inline-flex';
      if (this.dom.btnSideSurrender) this.dom.btnSideSurrender.style.display = 'flex';
      if (this.dom.btnOpenLobby) this.dom.btnOpenLobby.style.display = 'none';
      if (this.dom.btnSideStart) this.dom.btnSideStart.style.display = 'none';
      if (this.dom.btnSideReady) this.dom.btnSideReady.style.display = 'none';
      if (this.dom.btnNewRoundComp) this.dom.btnNewRoundComp.style.display = 'none';
      if (this.dom.btnSideNew) this.dom.btnSideNew.style.display = 'none';
      if (this.dom.btnOpponentNewRound) this.dom.btnOpponentNewRound.style.display = 'none';
      if (this.dom.countdownOverlay) this.dom.countdownOverlay.style.display = 'none';
      if (this.dom.sprintTimerBanner) this.dom.sprintTimerBanner.style.display = 'none';
      if (this.dom.form) {
        this.dom.form.style.opacity = '1';
        this.dom.form.style.pointerEvents = 'auto';
      }
      if (this.dom.wiki) this.dom.wiki.style.opacity = '1';

    } else if (this.roomStatus === 'ending') {
      this.closeModal(this.dom.lobbyModal);
      this.closeModal(this.dom.roundOverModal);
      if (this.dom.btnSurrenderRoom) this.dom.btnSurrenderRoom.style.display = 'inline-flex';
      if (this.dom.btnSideSurrender) this.dom.btnSideSurrender.style.display = 'flex';
      if (this.dom.btnOpenLobby) this.dom.btnOpenLobby.style.display = 'none';
      if (this.dom.btnSideStart) this.dom.btnSideStart.style.display = 'none';
      if (this.dom.btnSideReady) this.dom.btnSideReady.style.display = 'none';
      if (this.dom.btnNewRoundComp) this.dom.btnNewRoundComp.style.display = 'none';
      if (this.dom.btnSideNew) this.dom.btnSideNew.style.display = 'none';
      if (this.dom.btnOpponentNewRound) this.dom.btnOpponentNewRound.style.display = 'none';
      if (this.dom.countdownOverlay) this.dom.countdownOverlay.style.display = 'none';
      if (this.dom.form) {
        this.dom.form.style.opacity = '1';
        this.dom.form.style.pointerEvents = 'auto';
      }
      if (this.dom.wiki) this.dom.wiki.style.opacity = '1';
      if (this.dom.sprintTimerBanner) this.dom.sprintTimerBanner.style.display = 'block';
    }

    this.updateModeUI();
  }

  async switchPlayMode(mode) {
    const isSolo = mode === 'solo';
    if (isSolo === this.isSoloMode) return;
    this.playTone('click');

    const previousRoomId = this.roomId;
    this.isSoloMode = isSolo;
    localStorage.setItem('pedantix_play_mode', mode);

    const url = new URL(window.location.href);
    if (this.isSoloMode) {
      // Leave previous multiplayer room cleanly
      if (previousRoomId && !previousRoomId.startsWith('solo-')) {
        await this.leaveRoom(previousRoomId);
      }
      url.searchParams.set('mode', 'solo');
      url.searchParams.delete('room');
      document.body.classList.add('solo-mode');
      if (this.dom.btnTypeSolo) this.dom.btnTypeSolo.classList.add('active');
      if (this.dom.btnTypeMulti) this.dom.btnTypeMulti.classList.remove('active');
      this.roomId = `solo-${this.playerId}`;
      this.closeModal(this.dom.lobbyModal);
      this.closeModal(this.dom.roomsModal);
      this.showToast('🎯 Mode Solo activé');
      window.history.replaceState({}, '', url.toString());
      this.joinRoom();
    } else {
      // Switching to multiplayer:
      // If no room is specified in URL, open the Rooms Browser modal so player can choose or create one!
      const currentParam = url.searchParams.get('room');
      document.body.classList.remove('solo-mode');
      if (this.dom.btnTypeSolo) this.dom.btnTypeSolo.classList.remove('active');
      if (this.dom.btnTypeMulti) this.dom.btnTypeMulti.classList.add('active');

      if (!currentParam) {
        this.openRoomsBrowser();
        return;
      }

      this.roomId = currentParam;
      this.showToast('🌐 Mode Multijoueur activé');
      window.history.replaceState({}, '', url.toString());
      this.joinRoom();
    }
  }

  async switchGameMode(mode) {
    if (!this.isHost) {
      this.showToast("Seul l'Host 👑 peut changer le mode de jeu.");
      return;
    }
    if (this.roomStatus !== 'lobby') {
      this.showToast("Le mode ne peut être modifié que dans le salon d'attente.");
      return;
    }
    this.playTone('click');
    try {
      const resp = await fetch(this.getApiUrl('/api/room/mode'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          room_id: this.roomId,
          player_id: this.playerId,
          game_mode: mode
        })
      });
      const data = await resp.json();
      if (data.error) {
        this.showToast(data.error);
        return;
      }
      this.gameMode = data.game_mode;
      this.teamsData = data.teams;
      this.canStart = data.can_start;
      this.updateModeUI();
      this.syncRoomUI();
      const modeLabel = mode === 'team' ? 'Par Équipes (Rouge vs Bleu)' : 'Chacun pour soi';
      this.showToast(`🎮 Mode : ${modeLabel}`);
    } catch (e) {
      console.error(e);
      this.showToast("Erreur lors du changement de mode.");
    }
  }

  async chooseTeam(team) {
    if (this.myTeam === team) return;
    this.playTone('click');
    try {
      const resp = await fetch(this.getApiUrl('/api/room/team'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          room_id: this.roomId,
          player_id: this.playerId,
          team: team
        })
      });
      const data = await resp.json();
      if (data.error) {
        this.showToast(data.error);
        return;
      }
      this.myTeam = data.team;
      this.teamsData = data.teams;
      this.canStart = data.can_start;
      this.renderTeamsRoster();
      this.renderTeamConfrontation();
      this.syncRoomUI();
      const teamNameMap = {
        blue: 'Bleue 🔵',
        red: 'Rouge 🔴',
        green: 'Verte 🟢',
        yellow: 'Jaune 🟡'
      };
      const teamName = teamNameMap[team] || team;
      this.showToast(`👕 Vous avez rejoint l'Équipe ${teamName}`);
    } catch (e) {
      console.error(e);
      this.showToast("Erreur lors du changement d'équipe.");
    }
  }

  updateModeUI() {
    const isTeam = this.gameMode === 'team';
    if (this.dom.btnModeIndividual) {
      this.dom.btnModeIndividual.classList.toggle('active', !isTeam);
      this.dom.btnModeIndividual.disabled = !this.isHost;
    }
    if (this.dom.btnModeTeam) {
      this.dom.btnModeTeam.classList.toggle('active', isTeam);
      this.dom.btnModeTeam.disabled = !this.isHost;
    }
    if (this.dom.lobbyModeHint) {
      this.dom.lobbyModeHint.textContent = this.isHost ? "(Configuré par vous 👑)" : "(Configuré par l'Host 👑)";
    }

    if (this.dom.lobbyTeamsBox) {
      this.dom.lobbyTeamsBox.style.display = isTeam ? 'flex' : 'none';
    }
    if (this.dom.lobbyRosterBox) {
      this.dom.lobbyRosterBox.style.display = isTeam ? 'none' : 'flex';
    }
    if (this.dom.compTeamsSection) {
      this.dom.compTeamsSection.style.display = isTeam ? 'flex' : 'none';
    }
    if (this.dom.compIndividualSection) {
      this.dom.compIndividualSection.style.display = isTeam ? 'none' : 'flex';
    }

    if (isTeam) {
      this.renderTeamsRoster();
      this.renderTeamConfrontation();
    }
  }

  renderTeamsRoster() {
    if (!this.dom.lobbyTeamsGrid || !this.teamsData) return;
    this.dom.lobbyTeamsGrid.innerHTML = '';

    const teams = [
      { key: 'blue', name: 'Équipe Bleue', icon: '🔵', colorClass: 'blue', data: this.teamsData.blue || {} },
      { key: 'red', name: 'Équipe Rouge', icon: '🔴', colorClass: 'red', data: this.teamsData.red || {} },
      { key: 'green', name: 'Équipe Verte', icon: '🟢', colorClass: 'green', data: this.teamsData.green || {} },
      { key: 'yellow', name: 'Équipe Jaune', icon: '🟡', colorClass: 'yellow', data: this.teamsData.yellow || {} }
    ];

    const teamLabelMap = {
      blue: 'Bleus 🔵',
      red: 'Rouges 🔴',
      green: 'Verts 🟢',
      yellow: 'Jaunes 🟡'
    };

    teams.forEach(t => {
      const players = t.data.players || [];
      const isMyTeam = this.myTeam === t.key;
      const card = document.createElement('div');
      card.className = `lobby-team-card team-${t.colorClass}`;

      let playersHtml = '';
      if (players.length === 0) {
        playersHtml = `<div class="team-empty-hint">Aucun joueur pour l'instant</div>`;
      } else {
        players.forEach(p => {
          const isMe = p.player_id === this.playerId;
          const hostIcon = p.is_host ? '👑 ' : '';
          playersHtml += `
            <div class="team-player-item ${isMe ? 'is-me' : ''}">
              <div class="team-player-name-wrap">
                <span>${hostIcon}</span>
                <span class="team-player-name" title="${this.escapeHtml(p.name)}">${this.escapeHtml(p.name)}</span>
                ${isMe ? '<span class="player-you-tag">Vous</span>' : ''}
              </div>
              <div class="team-player-status">
                <span style="color: #fbbf24; margin-right: 4px;">🏆 ${p.score || 0}</span>
                <span>${p.is_ready ? '🟢' : '⏳'}</span>
              </div>
            </div>
          `;
        });
      }

      const btnJoinText = isMyTeam ? `Votre équipe ✓` : `Rejoindre les ${teamLabelMap[t.key] || t.name}`;
      const btnDisabled = isMyTeam ? 'disabled' : '';

      card.innerHTML = `
        <div class="team-card-header">
          <div class="team-badge-title ${t.colorClass}">
            <span>${t.icon}</span>
            <span>${t.name}</span>
          </div>
          <span class="team-count-pill">${players.length} joueur${players.length > 1 ? 's' : ''}</span>
        </div>
        <div class="team-roster-list">
          ${playersHtml}
        </div>
        <button type="button" class="btn-join-team ${t.colorClass} ${isMyTeam ? 'current-team' : ''}" data-team="${t.key}" ${btnDisabled}>
          ${btnJoinText}
        </button>
      `;

      const joinBtn = card.querySelector('.btn-join-team');
      if (joinBtn && !isMyTeam) {
        joinBtn.addEventListener('click', () => this.chooseTeam(t.key));
      }

      this.dom.lobbyTeamsGrid.appendChild(card);
    });
  }

  renderTeamConfrontation() {
    if (!this.dom.compTeamsConfrontation || !this.teamsData) return;

    const teamList = [
      { key: 'blue', name: 'Équipe Bleue', short: 'Bleu', icon: '🔵', color: '#60a5fa', fillClass: 'team-bar-fill-blue', data: this.teamsData.blue || {} },
      { key: 'red', name: 'Équipe Rouge', short: 'Rouge', icon: '🔴', color: '#f87171', fillClass: 'team-bar-fill-red', data: this.teamsData.red || {} },
      { key: 'green', name: 'Équipe Verte', short: 'Vert', icon: '🟢', color: '#34d399', fillClass: 'team-bar-fill-green', data: this.teamsData.green || {} },
      { key: 'yellow', name: 'Équipe Jaune', short: 'Jaune', icon: '🟡', color: '#facc15', fillClass: 'team-bar-fill-yellow', data: this.teamsData.yellow || {} }
    ];

    const myTeamMeta = teamList.find(t => t.key === this.myTeam) || teamList[0];
    if (this.dom.sideMyTeamBadge) {
      this.dom.sideMyTeamBadge.className = `team-my-indicator ${this.myTeam}`;
      this.dom.sideMyTeamBadge.textContent = `${myTeamMeta.icon} ${myTeamMeta.name}`;
    }

    // Determine active teams (teams with players or at least 2 teams by default)
    let activeTeams = teamList.filter(t => (t.data.players && t.data.players.length > 0));
    if (activeTeams.length === 0) {
      activeTeams = teamList.slice(0, 2);
    }

    const vsLabelsHtml = activeTeams.map(t => {
      const pct = t.data.pct || 0;
      return `<span style="color: ${t.color}; font-weight: 800;">${t.icon} ${t.short} (${pct}%)</span>`;
    }).join('<span class="team-vs-divider">VS</span>');

    const barsHtml = activeTeams.map(t => {
      const pct = Math.max(2, t.data.pct || 0);
      return `
        <div style="flex: 1; height: 8px; background: rgba(0, 0, 0, 0.5); border-radius: 9999px; overflow: hidden; border: 1px solid rgba(255, 255, 255, 0.08);">
          <div class="${t.fillClass}" style="width: ${pct}%; height: 100%;"></div>
        </div>
      `;
    }).join('<div style="width: 4px;"></div>');

    const cardsHtml = activeTeams.map(t => {
      const isMyTeam = this.myTeam === t.key;
      const pct = t.data.pct || 0;
      const players = t.data.players || [];
      const playersText = players.map(p => this.escapeHtml(p.name)).join(', ') || 'Aucun';
      return `
        <div class="team-side-card ${t.key} ${isMyTeam ? 'is-my-team' : ''}">
          <div class="team-side-top">
            <span class="team-side-title ${t.key}">${t.icon} ${t.short} ${isMyTeam ? '★' : ''}</span>
            <span class="team-side-pct" style="color: ${t.color};">${pct}%</span>
          </div>
          <div style="height: 4px; background: rgba(0, 0, 0, 0.3); border-radius: 9999px; overflow: hidden; margin: 3px 0 5px 0;">
            <div class="${t.fillClass}" style="width: ${Math.max(2, pct)}%; height: 100%;"></div>
          </div>
          <div class="team-side-stats">
            <span><b>${t.data.attempts || 0}</b> coups</span>
            <span><b>${t.data.revealed_words_count || 0}</b> mots</span>
          </div>
          <div class="team-side-members" title="${players.map(p => p.name).join(', ')}">
            👥 ${playersText}
          </div>
        </div>
      `;
    }).join('');

    this.dom.compTeamsConfrontation.innerHTML = `
      <div class="teams-versus-bar-wrap">
        <div class="teams-vs-labels">
          ${vsLabelsHtml}
        </div>
        <div style="display: flex; gap: 4px; align-items: center; width: 100%; margin-top: 4px;">
          ${barsHtml}
        </div>
      </div>
      <div class="teams-cards-split">
        ${cardsHtml}
      </div>
    `;
  }

  revealTokens(newlyRevealed) {
    if (!newlyRevealed) return;
    Object.entries(newlyRevealed).forEach(([tid, text]) => {
      const token = this.tokensById[tid];
      if (token) {
        token.revealed = true;
        token.text = text;
        delete token.heat;
        delete token.close_word;
        delete token.hint_pattern;
      }
      const el = document.getElementById(`token-${tid}`);
      if (el) {
        el.classList.remove('showing-len', 'close-heat', 'close-heat-grey', 'heat-flash', 'has-hint', 'hint-pulse');
        el.style.backgroundColor = '';
        el.style.borderColor = '';
        el.style.color = '';
        el.title = '';
        delete el.dataset.heat;
        delete el.dataset.word;
        el.classList.add('revealed', 'just-revealed');
        el.textContent = text;
      }
    });
  }

  applyCloseTokens(closeTokens, fallbackWord = '') {
    if (!closeTokens || closeTokens.length === 0) return;
    closeTokens.forEach(item => {
      const score = Number(item.score || 50);
      const closeWord = item.word || fallbackWord;
      const token = this.tokensById[item.id];
      if (token && !token.revealed) {
        const currentHeat = Number(token.heat || 0);
        if (score >= currentHeat) {
          token.heat = score;
          token.close_word = closeWord;
        }
      }

      const el = document.getElementById(`token-${item.id}`);
      if (el && !el.classList.contains('revealed')) {
        const currentHeat = Number(el.dataset.heat || 0);
        if (score >= currentHeat) {
          el.dataset.heat = score;
          el.dataset.word = closeWord;
          if (token && token.hint_pattern && token.hint_pattern.replace(/_/g, '').length > 0) {
            this.renderTokenContent(token, el);
          } else {
            el.innerHTML = `&nbsp;${this.escapeHtml(closeWord)}&nbsp;`;
            el.classList.remove('close-heat');
            el.classList.add('close-heat-grey');
            el.style.backgroundColor = '#222222';
            el.title = `Proximité : ${score}% (proche de « ${closeWord} »)`;

            const grey = this.getGreyColor(score);
            const flash = this.getFlashColor(score);

            el.classList.add('heat-flash');
            el.style.color = flash;
            setTimeout(() => {
              if (!el.classList.contains('revealed') && !el.classList.contains('showing-len')) {
                el.classList.remove('heat-flash');
                el.style.color = grey;
              }
            }, 1200);
          }
        }
      }
    });
  }

  addTeammateGuessToHistory(tg) {
    if (!tg || !tg.word) return;
    const exists = this.history.some(h => h.word.toLowerCase() === tg.word.toLowerCase());
    if (exists) return;
    this.history.unshift({
      attempt: tg.attempt_number || (this.history.length + 1),
      word: tg.word,
      status: tg.status,
      count: tg.matches_count || 0,
      score: tg.score || 0,
      guessed_by: tg.player_name
    });
    this.renderHistory();
    this.updateDayMeter();
  }

  renderPlayerCard(p, idx, isMe) {
    const medals = ['🥇', '🥈', '🥉'];
    const rankDisplay = medals[idx] || `#${idx + 1}`;
    let statusHtml = '';
    if (p.is_won) {
      statusHtml = `<span class="player-status-tag status-win">🏆 Gagné !</span>`;
    } else if (p.last_status === 'close') {
      const scoreStr = p.last_score ? ` (${p.last_score}%)` : '';
      statusHtml = `<span class="player-status-tag status-hot">🔥 Proche${scoreStr}</span>`;
    } else if (p.last_status === 'match') {
      statusHtml = `<span class="player-status-tag status-match">🟩 Trouvé (+${p.last_count})</span>`;
    } else {
      statusHtml = `<span class="player-status-tag ${p.is_ready ? 'status-ready' : 'status-wait'}">${p.is_ready ? '🟢 Prêt' : '⏳ En attente'}</span>`;
    }

    const card = document.createElement('div');
    card.className = `comp-player-card ${isMe ? 'is-me' : ''} ${p.is_won ? 'is-winner' : ''}`;
    card.innerHTML = `
      <div class="comp-player-top">
        <div class="comp-player-left">
          <span class="comp-rank-badge">${rankDisplay}</span>
          <span class="comp-player-name" title="${this.escapeHtml(p.name)}">${this.escapeHtml(p.name)}</span>
          ${p.is_host ? '<span class="host-icon-mini" title="Host">👑</span>' : ''}
          ${isMe ? '<span class="player-you-tag">Vous</span>' : ''}
        </div>
        <div class="comp-player-right">
          <span class="comp-player-score-tag" title="Score persistant en BDD">🏆 ${p.score || 0}</span>
          <span class="comp-pct-number">${p.pct}%</span>
        </div>
      </div>
      <div class="comp-prog-bar">
        <div class="comp-prog-fill" style="width: ${p.pct}%;"></div>
      </div>
      <div class="comp-player-bottom">
        <span class="comp-sub-stats"><b>${p.attempts}</b> coup${p.attempts > 1 ? 's' : ''} • <b>${p.revealed_words_count || 0}</b> mot${(p.revealed_words_count || 0) > 1 ? 's' : ''}</span>
        ${statusHtml}
      </div>
    `;
    return card;
  }

  updateLeaderboard(players) {
    if (!players || !Array.isArray(players)) return;
    this.leaderboard = players;

    const me = players.find(p => p.player_id === this.playerId);
    if (me) {
      this.isHost = me.is_host;
      this.isReady = me.is_ready;
      this.myScore = me.score || 0;
    }

    const readyCount = players.filter(p => p.is_ready).length;
    const totalCount = players.length;
    this.canStart = totalCount > 0 && readyCount === totalCount;

    const connectedCount = players.filter(p => p.connected).length;
    this.dom.compStatusBadge.textContent = `🟢 ${connectedCount} joueur${connectedCount > 1 ? 's' : ''}`;

    // 1. Update Lobby Grid
    if (this.dom.lobbyReadyRatio) {
      this.dom.lobbyReadyRatio.textContent = `${readyCount}/${totalCount} prêt${readyCount > 1 ? 's' : ''}`;
    }

    if (this.dom.lobbyPlayersGrid) {
      this.dom.lobbyPlayersGrid.innerHTML = '';
      players.forEach(p => {
        const isMe = p.player_id === this.playerId;
        const card = document.createElement('div');
        card.className = `lobby-player-card ${isMe ? 'is-me' : ''} ${p.is_ready ? 'is-ready' : ''}`;
        const avatarIcon = p.is_host ? '👑' : '👤';
        card.innerHTML = `
          <div class="lobby-card-avatar-wrap">
            <span class="lobby-avatar-icon">${avatarIcon}</span>
          </div>
          <div class="lobby-card-info">
            <div class="lobby-card-name-row">
              <span class="lobby-card-name" title="${this.escapeHtml(p.name)}">${this.escapeHtml(p.name)}</span>
              ${isMe ? '<span class="player-you-tag">Vous</span>' : ''}
              ${p.is_host ? '<span class="host-pill" style="font-size:0.68rem;padding:0.1rem 0.45rem;">👑 Host</span>' : ''}
            </div>
            <div class="lobby-card-score">
              🏆 <b>${p.score || 0}</b> victoire${(p.score || 0) > 1 ? 's' : ''}
            </div>
          </div>
          <div class="lobby-card-state ${p.is_ready ? 'state-ready' : 'state-wait'}">
            ${p.is_ready ? '🟢 Prêt' : '⏳ En attente'}
          </div>
        `;
        this.dom.lobbyPlayersGrid.appendChild(card);
      });
    }

    // 2. Update Sidebar Leaderboard
    if (this.dom.playersList) {
      this.dom.playersList.innerHTML = '';

      if (players.length <= 5) {
        // Mode direct : affiche tous les joueurs si 5 joueurs ou moins
        players.forEach((p, idx) => {
          const isMe = p.player_id === this.playerId;
          const card = this.renderPlayerCard(p, idx, isMe);
          this.dom.playersList.appendChild(card);
        });
      } else {
        // Mode menu déroulant : menu déroulant avec tous les joueurs si plus de 5 joueurs
        const container = document.createElement('div');
        container.className = 'comp-dropdown-leaderboard-container';

        // Sélection par défaut : le joueur local ou le 1er au classement
        if (!this.selectedLeaderboardPlayerId || !players.some(p => p.player_id === this.selectedLeaderboardPlayerId)) {
          const mePlayer = players.find(p => p.player_id === this.playerId);
          this.selectedLeaderboardPlayerId = mePlayer ? mePlayer.player_id : players[0].player_id;
        }

        const medals = ['🥇', '🥈', '🥉'];
        let optionsHtml = '';
        players.forEach((p, idx) => {
          const isMe = p.player_id === this.playerId;
          const rankDisplay = medals[idx] || `#${idx + 1}`;
          const meTag = isMe ? ' (Vous)' : '';
          const winTag = p.is_won ? ' • 🏆 GAGNÉ' : '';
          const label = `${rankDisplay} ${p.name}${meTag} — ${p.pct}% (${p.attempts} c., 🏆 ${p.score || 0})${winTag}`;
          const isSelected = p.player_id === this.selectedLeaderboardPlayerId ? 'selected' : '';
          optionsHtml += `<option value="${p.player_id}" ${isSelected}>${this.escapeHtml(label)}</option>`;
        });

        container.innerHTML = `
          <div class="comp-dropdown-select-row">
            <div class="comp-dropdown-title-label">
              <span class="comp-dropdown-badge">👥 ${players.length} joueurs</span>
              <span class="comp-dropdown-hint">Menu déroulant du classement</span>
            </div>
            <div class="comp-dropdown-select-wrap">
              <select id="comp-leaderboard-dropdown" class="comp-leaderboard-dropdown" aria-label="Menu déroulant du classement des joueurs">
                ${optionsHtml}
              </select>
              <span class="comp-dropdown-chevron-icon">▼</span>
            </div>
          </div>
          <div id="comp-dropdown-player-view" class="comp-dropdown-player-view"></div>
          <button type="button" class="btn-toggle-dropdown-all" id="btn-toggle-dropdown-all">
            <span class="toggle-icon">${this.showAllLeaderboardExpanded ? '▲' : '📜'}</span>
            <span class="toggle-text">${this.showAllLeaderboardExpanded ? 'Replier le classement' : 'Dérouler la liste complète'}</span>
          </button>
          <div class="comp-dropdown-all-cards" id="comp-dropdown-all-cards" style="display: ${this.showAllLeaderboardExpanded ? 'flex' : 'none'};"></div>
        `;

        this.dom.playersList.appendChild(container);

        // Affichage de la carte détaillée du joueur sélectionné dans le menu déroulant
        const selectedPlayerView = container.querySelector('#comp-dropdown-player-view');
        const selectedPlayerObj = players.find(p => p.player_id === this.selectedLeaderboardPlayerId) || players[0];
        const selectedIdx = players.indexOf(selectedPlayerObj);
        if (selectedPlayerView && selectedPlayerObj) {
          selectedPlayerView.appendChild(this.renderPlayerCard(selectedPlayerObj, selectedIdx, selectedPlayerObj.player_id === this.playerId));
        }

        // Si la liste complète est dépliée, afficher également toutes les cartes
        const allCardsContainer = container.querySelector('#comp-dropdown-all-cards');
        if (allCardsContainer && this.showAllLeaderboardExpanded) {
          players.forEach((p, idx) => {
            allCardsContainer.appendChild(this.renderPlayerCard(p, idx, p.player_id === this.playerId));
          });
        }

        // Événement de changement dans le menu déroulant
        const dropdown = container.querySelector('#comp-leaderboard-dropdown');
        if (dropdown) {
          dropdown.addEventListener('change', (e) => {
            this.selectedLeaderboardPlayerId = e.target.value;
            const updatedPlayer = players.find(p => p.player_id === this.selectedLeaderboardPlayerId);
            const updatedIdx = players.indexOf(updatedPlayer);
            if (selectedPlayerView && updatedPlayer) {
              selectedPlayerView.innerHTML = '';
              selectedPlayerView.appendChild(this.renderPlayerCard(updatedPlayer, updatedIdx, updatedPlayer.player_id === this.playerId));
            }
          });
        }

        // Événement déplier/replier
        const toggleBtn = container.querySelector('#btn-toggle-dropdown-all');
        if (toggleBtn && allCardsContainer) {
          toggleBtn.addEventListener('click', () => {
            this.showAllLeaderboardExpanded = !this.showAllLeaderboardExpanded;
            allCardsContainer.style.display = this.showAllLeaderboardExpanded ? 'flex' : 'none';
            toggleBtn.querySelector('.toggle-icon').textContent = this.showAllLeaderboardExpanded ? '▲' : '📜';
            toggleBtn.querySelector('.toggle-text').textContent = this.showAllLeaderboardExpanded ? 'Replier le classement' : 'Dérouler la liste complète';
            if (this.showAllLeaderboardExpanded && allCardsContainer.children.length === 0) {
              players.forEach((p, idx) => {
                allCardsContainer.appendChild(this.renderPlayerCard(p, idx, p.player_id === this.playerId));
              });
            }
          });
        }
      }
    }

    this.syncRoomUI();
  }

  updateActivity(events) {
    if (!events || !Array.isArray(events)) return;
    this.dom.activityFeed.innerHTML = '';
    events.slice(0, 15).forEach(ev => {
      const div = document.createElement('div');
      div.className = 'activity-item';
      div.innerHTML = `<span class="activity-time">${ev.timestamp}</span> ${this.escapeHtml(ev.text)}`;
      this.dom.activityFeed.appendChild(div);
    });
  }

  showOpponentWin(winnerName, title, attempts) {
    this.dom.opponentWinName.textContent = winnerName;
    this.dom.opponentWinTitle.textContent = title;
    this.dom.opponentWinTries.textContent = attempts;
    this.dom.opponentWinBanner.style.display = 'block';
  }

  hideOpponentWin() {
    this.dom.opponentWinBanner.style.display = 'none';
  }

  updateBadges() {
    if (this.dom.puzzleNum && this.seed) {
      this.dom.puzzleNum.textContent = this.seed.replace('P-', '').replace('D-', '');
    }
    if (this.dom.puzzleLabel) {
      this.dom.puzzleLabel.textContent = this.isSoloMode ? 'Solo' : 'Partie';
    }
    if (this.dom.modeBadge) {
      this.dom.modeBadge.textContent = this.isSoloMode ? 'Mode Solo' : 'Concours Réseau';
    }
  }

  // =========================================================================
  // BOARD RENDERING (.W WORD BLOCKS)
  // =========================================================================

  renderBoard() {
    // 1. Render Title
    this.dom.wikiHeading.innerHTML = '';
    const titleTokens = this.tokens.filter(t => t.is_title);
    titleTokens.forEach(t => {
      this.dom.wikiHeading.appendChild(this.createTokenElement(t, true));
    });

    // 2. Render Paragraphs
    this.dom.article.innerHTML = '';
    const bodyTokens = this.tokens.filter(t => !t.is_title);

    const pGroups = {};
    bodyTokens.forEach(t => {
      const pIdx = t.paragraph_idx;
      if (!pGroups[pIdx]) pGroups[pIdx] = [];
      pGroups[pIdx].push(t);
    });

    Object.keys(pGroups).sort((a,b) => Number(a)-Number(b)).forEach(pIdx => {
      const pEl = document.createElement('p');
      pGroups[pIdx].forEach(t => {
        pEl.appendChild(this.createTokenElement(t, false));
      });
      this.dom.article.appendChild(pEl);
    });
  }

  renderTokenContent(token, span) {
    if (token.revealed) {
      span.classList.add('revealed');
      span.classList.remove('has-hint', 'close-heat-grey', 'hint-pulse', 'showing-len');
      span.textContent = token.text;
      span.style.color = '';
      span.style.backgroundColor = '';
      span.style.borderColor = '';
      span.title = '';
      delete span.dataset.heat;
      delete span.dataset.word;
      return;
    }

    // Not revealed yet
    span.classList.remove('revealed');

    // Check if token has revealed letters from 5-min hint
    const hasHintLetter = token.hint_pattern && token.hint_pattern.replace(/_/g, '').length > 0;

    if (hasHintLetter) {
      span.classList.add('has-hint');
      let html = '';
      for (let i = 0; i < token.hint_pattern.length; i++) {
        const ch = token.hint_pattern[i];
        if (ch === '_') {
          html += '<span class="hint-blank">·</span>';
        } else {
          html += `<span class="hint-char">${this.escapeHtml(ch)}</span>`;
        }
      }
      span.innerHTML = html;

      if (token.close_word && token.heat) {
        span.dataset.heat = token.heat;
        span.dataset.word = token.close_word;
        span.classList.add('close-heat-grey');
        span.style.backgroundColor = '#222222';
        span.style.color = '';
        span.title = `Proximité : ${token.heat}% (proche de « ${token.close_word} ») | Indice actif (${token.length} lettres)`;
      } else {
        span.classList.remove('close-heat-grey');
        span.style.backgroundColor = '';
        span.style.color = '';
        span.title = `Indice actif (${token.length} lettres)`;
      }
    } else if (token.close_word && token.heat) {
      span.classList.remove('has-hint');
      span.dataset.heat = token.heat;
      span.dataset.word = token.close_word;
      span.classList.add('close-heat-grey');
      span.innerHTML = `&nbsp;${this.escapeHtml(token.close_word)}&nbsp;`;
      span.style.color = this.getGreyColor(Number(token.heat));
      span.style.backgroundColor = '#222222';
      span.title = `Proximité : ${token.heat}% (proche de « ${token.close_word} »)`;
    } else {
      span.classList.remove('has-hint', 'close-heat-grey');
      span.innerHTML = '&nbsp;'.repeat(Math.max(1, token.length));
      span.dataset.len = token.length;
      span.style.color = '';
      span.style.backgroundColor = '';
      span.style.borderColor = '';
      span.title = '';
    }
  }

  createTokenElement(token, isTitle) {
    if (token.type === 'space') {
      const span = document.createElement('span');
      span.className = 'space-span';
      span.innerHTML = ' ';
      return span;
    }

    if (token.type === 'punct') {
      const span = document.createElement('span');
      span.className = 'punct-span';
      span.textContent = token.text;
      return span;
    }

    // Word token (.w)
    const span = document.createElement('span');
    span.id = `token-${token.id}`;
    span.dataset.id = token.id;
    span.className = `w ${isTitle ? 'h' : ''}`;

    this.renderTokenContent(token, span);

    span.addEventListener('click', () => {
      if (!span.classList.contains('revealed')) {
        this.playTone('click');
        span.classList.add('showing-len');
        span.innerHTML = `&nbsp;${token.length}&nbsp;`;
        span.style.color = '#00f0ff';
        span.style.backgroundColor = '#0b1320';
        setTimeout(() => {
          if (!span.classList.contains('revealed')) {
            span.classList.remove('showing-len');
            this.renderTokenContent(token, span);
          }
        }, 2000);
      }
    });

    return span;
  }

  // =========================================================================
  // GUESS SUBMISSION & HANDLING
  // =========================================================================

  async handleGuessSubmit() {
    const rawWord = this.dom.guessInput.value.trim();
    if (!rawWord) return;

    if (this.roomStatus === 'lobby') {
      this.showToast('Attendez que l\'Host démarre la partie !');
      return;
    }

    this.dom.guessInput.value = '';
    if (this.dom.guessLenBadge) {
      this.dom.guessLenBadge.style.display = 'none';
    }
    this.dom.guessInput.focus();

    if (!this.previousInputs.includes(rawWord)) {
      this.previousInputs.push(rawWord);
    }
    this.prevInputIdx = -1;

    try {
      const resp = await fetch(this.getApiUrl('/api/room/guess'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          room_id: this.roomId,
          player_id: this.playerId,
          word: rawWord
        })
      });

      if (!resp.ok) throw new Error('Erreur réseau');
      const data = await resp.json();

      this.processGuessResult(data, rawWord);

    } catch (err) {
      console.error(err);
      this.dom.errorLabel.textContent = 'Erreur lors de la vérification.';
    }
  }

  processGuessResult(data, word) {
    if (data.status === 'already_won') {
      this.showToast(data.message);
      return;
    }

    // Check if word was already found or already written
    if (data.is_repeat || data.status === 'already_guessed') {
      this.playTone('miss');
      this.dom.errorLabel.innerHTML = `⚠️ <b>"${this.escapeHtml(word)}"</b> : Déjà écrit`;
      this.showToast(`« ${this.escapeHtml(word)} » : Déjà écrit`);
      return;
    }

    // French word validation rejection check
    if (data.status === 'invalid_word' || (data.error && data.status !== 'already_won')) {
      this.playTone('miss');
      this.dom.errorLabel.innerHTML = `⚠️ <b>"${this.escapeHtml(word)}"</b> : ${data.error || "Ce mot n'est pas français ou n'existe pas."}`;
      this.showToast(data.error || "Mot non reconnu");
      return;
    }

    // Reset previous flash states
    document.querySelectorAll('.w.just-revealed').forEach(el => {
      el.classList.remove('just-revealed');
    });

    const matchCount = data.matches_count || 0;
    const closeCount = (data.close_tokens && data.close_tokens.length) || 0;

    // 1. Audio and feedback indicator
    if (matchCount > 0) {
      this.playTone('match');
      const greenBlocks = '🟩'.repeat(Math.min(5, matchCount));
      this.dom.errorLabel.innerHTML = `${greenBlocks} <b>"${this.escapeHtml(word)}"</b> : ${matchCount} occurrence${matchCount > 1 ? 's' : ''}`;
    } else if (closeCount > 0 || data.status === 'close') {
      this.playTone('close');
      const maxScore = data.score || 50;
      if (closeCount > 0) {
        this.dom.errorLabel.innerHTML = `🔥 <b>"${this.escapeHtml(word)}"</b> : Mot proche (${maxScore}%, ${closeCount} lié${closeCount > 1 ? 's' : ''})`;
      } else {
        this.dom.errorLabel.innerHTML = `🔥 <b>"${this.escapeHtml(word)}"</b> : Mot proche (${maxScore}%)`;
      }
    } else {
      this.playTone('miss');
      this.dom.errorLabel.innerHTML = `🟥 <b>"${this.escapeHtml(word)}"</b> : Absent`;
    }

    // 2. Reveal newly discovered tokens
    if (data.newly_revealed) {
      this.revealTokens(data.newly_revealed);
    }

    // 3. Highlight close proximity tokens
    if (data.close_tokens && data.close_tokens.length > 0) {
      this.applyCloseTokens(data.close_tokens, word);
    }

    // 4. Update stats and history
    this.revealedWordsCount = data.revealed_words_count || this.revealedWordsCount;
    this.history = data.history || this.history;
    this.updateDayMeter();
    this.renderHistory();

    // 5. Check victory
    if (data.is_won && !this.isWon) {
      this.isWon = true;
      this.handleVictory();
    }
  }

  updateDayMeter() {
    const attempts = this.history.length;
    this.dom.attemptsStat.textContent = `${attempts} coup${attempts > 1 ? 's' : ''}`;
    this.dom.revealedStat.textContent = this.revealedWordsCount;
    this.dom.totalStat.textContent = this.totalWords;

    const pct = this.totalWords > 0 ? Math.round((this.revealedWordsCount / this.totalWords) * 100) : 0;
    this.dom.pctStat.textContent = `${pct}%`;

    const totalBlocks = 10;
    const greenBlocks = Math.round((this.revealedWordsCount / Math.max(1, this.totalWords)) * totalBlocks);
    
    const closeTokensCount = document.querySelectorAll('.w.close-heat-grey:not(.revealed), .w.close-heat:not(.revealed)').length;
    const orangeBlocks = Math.min(totalBlocks - greenBlocks, Math.round((closeTokensCount / Math.max(1, this.totalWords)) * totalBlocks * 2));
    const redBlocks = Math.max(0, totalBlocks - greenBlocks - orangeBlocks);

    const meterStr = '🟩'.repeat(greenBlocks) + '🟧'.repeat(orangeBlocks) + '🟥'.repeat(redBlocks);
    this.dom.dayMeter.textContent = meterStr;
    this.dom.meterSpan.textContent = meterStr;

    if (this.dom.progressBarFill) {
      this.dom.progressBarFill.style.width = `${pct}%`;
    }
  }

  // =========================================================================
  // HISTORY TABLE
  // =========================================================================

  renderHistory() {
    const tbody = this.dom.guessesTbody;
    tbody.innerHTML = '';

    let items = [...this.history];

    if (this.filterQuery) {
      items = items.filter(h => h.word.toLowerCase().includes(this.filterQuery));
    }

    if (this.sortMode === 'chrono') {
      items.sort((a,b) => this.sortAsc ? (b.attempt - a.attempt) : (a.attempt - b.attempt));
    } else {
      items.sort((a,b) => this.sortAsc ? a.word.localeCompare(b.word) : b.word.localeCompare(a.word));
    }

    if (this.isCollapsed) {
      items = items.slice(0, 5);
    }

    if (items.length === 0) {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td colspan="3" style="text-align: center; color: rgba(0,0,0,0.5); padding: 10px 0;">Aucun mot</td>`;
      tbody.appendChild(tr);
      return;
    }

    items.forEach(item => {
      const tr = document.createElement('tr');

      let badge = '';
      if (item.status === 'match') {
        badge = `<span class="guess-tag tag-match">🟩 ${item.count}</span>`;
      } else if (item.status === 'close') {
        const grey = this.getGreyColor(item.score);
        badge = `<span class="guess-tag tag-close-grey" style="background-color: #222222; border: 1px solid rgba(255, 255, 255, 0.22); color: ${grey}; font-weight: 700;" title="Proximité : ${item.score}%">🔥 ${item.score}%</span>`;
      } else {
        badge = `<span class="guess-tag tag-miss">🟥 Absent</span>`;
      }

      tr.innerHTML = `
        <td class="number">${item.attempt}</td>
        <td class="word">${this.escapeHtml(item.word)}</td>
        <td class="count" style="text-align: right;">${badge}</td>
      `;
      tbody.appendChild(tr);
    });
  }

  // =========================================================================
  // VICTORY
  // =========================================================================

  handleVictory() {
    this.stopHintTimer();
    this.playTone('win');
    try {
      if (this.confetti) {
        if (typeof this.confetti.render === 'function') {
          this.confetti.render();
        } else if (typeof this.confetti.start === 'function') {
          this.confetti.start();
        }
      }
    } catch (e) {
      console.warn('Erreur confetti:', e);
    }

    this.dom.triesSpan.textContent = `${this.history.length} coup${this.history.length > 1 ? 's' : ''}`;
    this.dom.successBox.classList.add('active');
    this.hideOpponentWin();

    const title = this.tokens.filter(t => t.is_title).map(t => t.text).join('');
    this.dom.solutionDisplay.textContent = title;

    if (this.solution) {
      this.dom.solutionLink.href = this.solution.url;
      if (this.solution.image) {
        this.dom.wikiImg.src = this.solution.image;
        this.dom.wikiImg.style.display = 'block';
      }
    } else {
      this.dom.solutionLink.href = `https://fr.wikipedia.org/wiki/${encodeURIComponent(title)}`;
    }

    this.recordWinStats(title, this.history.length);
    this.updateYesterdayLink(title, this.dom.solutionLink.href);

    this.dom.successBox.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  async unmaskAllWords() {
    try {
      if (this.dom.seeFullPageBtn) {
        this.dom.seeFullPageBtn.disabled = true;
        this.dom.seeFullPageBtn.innerHTML = '<span>⏳</span> Démasquage en cours...';
      }

      let tokensMap = {};

      // 1. Try room unmask endpoint
      if (this.roomId) {
        try {
          const resp = await fetch(this.getApiUrl('/api/room/unmask'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              room_id: this.roomId,
              player_id: this.playerId
            })
          });
          if (resp.ok) {
            const data = await resp.json();
            tokensMap = data.tokens || {};
          }
        } catch (e) {
          console.warn('Erreur room unmask, tentative game unmask:', e);
        }
      }

      // 2. Fallback to solo game unmask endpoint if needed
      if (Object.keys(tokensMap).length === 0 && this.sessionId) {
        try {
          const resp = await fetch(this.getApiUrl('/api/game/unmask'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: this.sessionId })
          });
          if (resp.ok) {
            const data = await resp.json();
            tokensMap = data.tokens || {};
          }
        } catch (e) {
          console.warn('Erreur game unmask:', e);
        }
      }

      // 3. Reveal all tokens using the map
      let unmaskedCount = 0;
      Object.entries(tokensMap).forEach(([tid, text]) => {
        const token = this.tokensById[tid];
        if (token) {
          token.revealed = true;
          token.text = text;
        }
        const el = document.getElementById(`token-${tid}`);
        if (el) {
          el.classList.remove('showing-len', 'close-heat', 'close-heat-grey', 'heat-flash', 'has-hint', 'hint-pulse');
          el.style.backgroundColor = '';
          el.style.borderColor = '';
          el.style.color = '';
          el.title = '';
          delete el.dataset.heat;
          delete el.dataset.word;
          el.classList.add('revealed');
          el.textContent = text;
          unmaskedCount++;
        }
      });

      // 4. Also unmask any client tokens that already have text
      this.tokens.forEach(t => {
        const el = document.getElementById(`token-${t.id}`);
        if (el && (t.type === 'word' || t.is_word)) {
          el.classList.remove('showing-len', 'close-heat', 'close-heat-grey', 'heat-flash', 'has-hint', 'hint-pulse');
          el.style.backgroundColor = '';
          el.style.borderColor = '';
          el.style.color = '';
          el.title = '';
          delete el.dataset.heat;
          delete el.dataset.word;
          el.classList.add('revealed');
          if (t.text) {
            el.textContent = t.text;
          }
        }
      });

      if (this.dom.seeFullPageBtn) {
        this.dom.seeFullPageBtn.disabled = false;
        this.dom.seeFullPageBtn.innerHTML = '<span>✅</span> Article démasqué';
      }
      this.showToast('Article entièrement démasqué 📖');
    } catch (err) {
      console.error('Erreur démasquage complet:', err);
      if (this.dom.seeFullPageBtn) {
        this.dom.seeFullPageBtn.disabled = false;
        this.dom.seeFullPageBtn.innerHTML = '<span>👁️</span> Voir tout démasqué';
      }
      this.showToast('Erreur lors du démasquage de l\'article.');
    }
  }

  applyUnmaskedTokens(tokensMap) {
    if (!tokensMap || typeof tokensMap !== 'object') return;
    Object.entries(tokensMap).forEach(([tid, text]) => {
      const token = this.tokensById[tid];
      if (token) {
        token.revealed = true;
        token.text = text;
      }
      const el = document.getElementById(`token-${tid}`);
      if (el) {
        el.classList.remove('showing-len', 'close-heat', 'close-heat-grey', 'heat-flash', 'has-hint', 'hint-pulse');
        el.style.backgroundColor = '';
        el.style.borderColor = '';
        el.style.color = '';
        el.title = '';
        delete el.dataset.heat;
        delete el.dataset.word;
        el.classList.add('revealed');
        el.textContent = text;
      }
    });

    this.tokens.forEach(t => {
      const el = document.getElementById(`token-${t.id}`);
      if (el && (t.type === 'word' || t.is_word)) {
        el.classList.remove('showing-len', 'close-heat', 'close-heat-grey', 'heat-flash', 'has-hint', 'hint-pulse');
        el.style.backgroundColor = '';
        el.style.borderColor = '';
        el.style.color = '';
        el.title = '';
        delete el.dataset.heat;
        delete el.dataset.word;
        el.classList.add('revealed');
        if (t.text) {
          el.textContent = t.text;
        }
      }
    });
  }

  async handleSurrenderClick() {
    if (this.roomStatus !== 'playing' && this.roomStatus !== 'ending') {
      this.showToast('Aucune partie en cours à abandonner.');
      return;
    }

    const confirmMsg = this.isSoloMode
      ? "Voulez-vous abandonner cette partie ?\nL'article sera entièrement dévoilé et aucun point ne sera attribué."
      : "Voulez-vous proposer d'abandonner la partie à tous les joueurs ?\nSi tous les joueurs acceptent, l'article sera révélé et aucun point ne sera attribué.";

    if (!confirm(confirmMsg)) return;

    this.playTone('click');
    try {
      const resp = await fetch(this.getApiUrl('/api/room/surrender'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          room_id: this.roomId,
          player_id: this.playerId,
          vote: 'yes'
        })
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        this.showToast(err.detail || 'Erreur lors de la demande d\'abandon.');
      }
    } catch (err) {
      console.error('Erreur demande abandon:', err);
      this.showToast('Erreur de connexion lors de la demande d\'abandon.');
    }
  }

  async voteSurrender(vote) {
    this.playTone('click');
    try {
      const resp = await fetch(this.getApiUrl('/api/room/surrender'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          room_id: this.roomId,
          player_id: this.playerId,
          vote: vote
        })
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        this.showToast(err.detail || 'Erreur lors du vote.');
      } else {
        if (vote === 'cancel') {
          this.closeModal(this.dom.surrenderModal);
          this.showToast('Demande d\'abandon annulée.');
        } else if (vote === 'no') {
          this.closeModal(this.dom.surrenderModal);
        }
      }
    } catch (err) {
      console.error('Erreur vote abandon:', err);
    }
  }

  showSurrenderModal(data) {
    if (!this.dom.surrenderModal) return;
    const initiatorName = data.initiator_name || 'Un joueur';
    const votesCount = data.votes_count || 1;
    const totalRequired = data.total_required || 1;
    const votedIds = data.voted_player_ids || [];
    const hasVoted = votedIds.includes(this.playerId);
    const isInitiator = data.initiator_id === this.playerId;

    if (this.dom.surrenderVoteCount) {
      this.dom.surrenderVoteCount.textContent = `${votesCount} / ${totalRequired} joueur${totalRequired > 1 ? 's' : ''}`;
    }

    if (this.dom.surrenderPromptText) {
      if (isInitiator) {
        this.dom.surrenderPromptText.innerHTML = `Vous avez proposé d'abandonner la partie.<br>En attente de la validation de <b>tous les joueurs</b> (${votesCount}/${totalRequired})...`;
      } else if (hasVoted) {
        this.dom.surrenderPromptText.innerHTML = `Vous avez accepté l'abandon.<br>En attente des autres joueurs (${votesCount}/${totalRequired})...`;
      } else {
        this.dom.surrenderPromptText.innerHTML = `<b>${this.escapeHtml(initiatorName)}</b> propose d'abandonner la partie en cours. Acceptez-vous d'abandonner ?`;
      }
    }

    if (hasVoted) {
      if (this.dom.surrenderActionsVoting) this.dom.surrenderActionsVoting.style.display = 'none';
      if (this.dom.surrenderActionsWaiting) {
        this.dom.surrenderActionsWaiting.style.display = isInitiator ? 'flex' : 'none';
      }
    } else {
      if (this.dom.surrenderActionsVoting) this.dom.surrenderActionsVoting.style.display = 'flex';
      if (this.dom.surrenderActionsWaiting) this.dom.surrenderActionsWaiting.style.display = 'none';
    }

    this.openModal(this.dom.surrenderModal);
  }

  handleSurrenderPassed(msg) {
    this.closeModal(this.dom.surrenderModal);
    this.stopHintTimer();
    if (this.sprintInterval) clearInterval(this.sprintInterval);
    if (this.dom.sprintTimerBanner) this.dom.sprintTimerBanner.style.display = 'none';
    this.hideOpponentWin();

    this.roomStatus = 'lobby';
    this.isReady = false;
    this.lastRound = msg.last_round || null;
    if (msg.leaderboard) this.updateLeaderboard(msg.leaderboard);
    if (msg.teams) this.teamsData = msg.teams;
    if (msg.activity) this.updateActivity(msg.activity);

    if (msg.solution) {
      this.solution = msg.solution;
    }

    if (msg.tokens && Object.keys(msg.tokens).length > 0) {
      this.applyUnmaskedTokens(msg.tokens);
    } else {
      this.unmaskAllWords();
    }

    this.playTone('hint');
    this.showToast('🏳️ Partie abandonnée à l\'unanimité ! L\'article a été entièrement démasqué. Aucun point attribué.');

    const title = msg.title || (msg.solution && msg.solution.title) || '';
    if (this.dom.solutionDisplay) {
      this.dom.solutionDisplay.textContent = title;
    }
    if (this.dom.solutionLink && (msg.url || (msg.solution && msg.solution.url))) {
      this.dom.solutionLink.href = msg.url || msg.solution.url;
    }

    this.updateModeUI();
    this.syncRoomUI();
  }

  copyShareScore() {
    const attempts = this.history.length;
    const title = this.tokens.filter(t => t.is_title).map(t => t.text).join('');
    const meter = this.dom.dayMeter.textContent;
    const num = this.dom.puzzleNum.textContent;

    const shareText = `J'ai remporté le concours Pédantix nº ${num} (${title}) en ${attempts} coup${attempts > 1 ? 's' : ''} !\n${meter}\nhttps://pedantix.certitudes.org`;

    const origHTML = this.dom.shareBtn.innerHTML;
    navigator.clipboard.writeText(shareText).then(() => {
      this.showToast('Résumé copié dans le presse-papiers ! 📋');
      this.dom.shareBtn.innerHTML = '<span>✅</span> Copié !';
      setTimeout(() => {
        this.dom.shareBtn.innerHTML = origHTML;
      }, 2500);
    }).catch(() => {
      prompt('Copiez votre résumé :', shareText);
    });
  }

  updateYesterdayLink(title, url) {
    this.dom.yesterdayLink.innerHTML = `<b><u>${this.escapeHtml(title)}</u></b>`;
    this.dom.yesterdayLink.href = url;
  }

  // =========================================================================
  // STATS STORAGE
  // =========================================================================

  recordWinStats(title, attempts) {
    const raw = localStorage.getItem('pedantix_user_stats');
    let stats = raw ? JSON.parse(raw) : { played: 0, won: 0, total_attempts: 0, recent: [] };

    stats.played += 1;
    stats.won += 1;
    stats.total_attempts += attempts;
    stats.recent.unshift({
      title: title,
      attempts: attempts,
      date: new Date().toLocaleDateString('fr-FR')
    });
    if (stats.recent.length > 15) stats.recent.pop();

    localStorage.setItem('pedantix_user_stats', JSON.stringify(stats));
  }

  async refreshStatsModal() {
    const raw = localStorage.getItem('pedantix_user_stats');
    let localStats = raw ? JSON.parse(raw) : { played: 0, won: 0, total_attempts: 0, recent: [] };

    // Initial render from local cache
    if (this.dom.statsUserName) this.dom.statsUserName.textContent = this.playerName || 'Mon Compte';
    if (this.dom.statsUserScore) this.dom.statsUserScore.textContent = `${this.myScore} pt${this.myScore > 1 ? 's' : ''}`;
    if (this.dom.sPlayed) this.dom.sPlayed.textContent = localStats.played;
    if (this.dom.sWon) this.dom.sWon.textContent = localStats.won;
    const localAvg = localStats.won > 0 ? Math.round(localStats.total_attempts / localStats.won) : 0;
    if (this.dom.sAvg) this.dom.sAvg.textContent = localAvg;
    if (this.dom.sWinRate) {
      const wr = localStats.played > 0 ? Math.round((localStats.won / localStats.played) * 100) : 0;
      this.dom.sWinRate.textContent = `${wr}%`;
    }
    if (this.dom.sBest) this.dom.sBest.textContent = '-';

    this.dom.statsRecentList.innerHTML = '';
    if (localStats.recent.length === 0) {
      this.dom.statsRecentList.innerHTML = '<tr><td colspan="3" style="text-align:center; opacity:0.6;">Aucune victoire enregistrée</td></tr>';
    } else {
      localStats.recent.forEach(r => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><b>${this.escapeHtml(r.title)}</b></td>
          <td style="text-align: center;">${r.attempts}</td>
          <td style="text-align: right;">${r.date}</td>
        `;
        this.dom.statsRecentList.appendChild(tr);
      });
    }

    // Fetch persistent stats from database
    try {
      const resp = await fetch(this.getApiUrl(`/api/user/stats?username=${encodeURIComponent(this.playerName)}`));
      if (resp.ok) {
        const data = await resp.json();
        if (this.dom.statsUserName) this.dom.statsUserName.textContent = data.username || this.playerName;
        if (this.dom.statsUserScore) this.dom.statsUserScore.textContent = `${data.score} pt${data.score > 1 ? 's' : ''}`;
        if (this.dom.sPlayed) this.dom.sPlayed.textContent = data.games_played;
        if (this.dom.sWon) this.dom.sWon.textContent = data.wins;
        if (this.dom.sWinRate) this.dom.sWinRate.textContent = `${data.win_rate}%`;
        if (this.dom.sAvg) this.dom.sAvg.textContent = data.avg_attempts;
        if (this.dom.sBest) this.dom.sBest.textContent = (data.best_attempts !== null && data.best_attempts !== undefined) ? data.best_attempts : '-';

        // Favorite words
        if (this.dom.statsFavWordsList) {
          if (data.favorite_words && data.favorite_words.length > 0) {
            this.dom.statsFavWordsList.innerHTML = data.favorite_words.map(fw => `
              <span class="fav-word-badge" title="${fw.count} fois joué">
                <span class="fav-word-text">${this.escapeHtml(fw.word)}</span>
                <span class="fav-word-count">${fw.count}</span>
              </span>
            `).join('');
          } else {
            this.dom.statsFavWordsList.innerHTML = '<span class="empty-fav-hint">Jouez des mots pour découvrir vos mots fétiches !</span>';
          }
        }
      }
    } catch (e) {
      console.warn('Erreur chargement statistiques utilisateur :', e);
    }
  }

  // =========================================================================
  // USER ACCOUNT & AUTHENTICATION
  // =========================================================================

  checkAuthOnLoad() {
    this.authUser = localStorage.getItem('pedantix_auth_user') || null;
    this.authToken = localStorage.getItem('pedantix_auth_token') || null;

    if (!this.authUser) {
      // First connection on this browser: prompt for username
      this.openAuthModal();
    } else {
      this.playerName = this.authUser;
      if (this.dom.playerPseudoInput) this.dom.playerPseudoInput.value = this.authUser;
      if (this.dom.lobbyPseudoInput) this.dom.lobbyPseudoInput.value = this.authUser;
    }
  }

  openAuthModal() {
    this.pendingAuthUsername = '';
    this.showAuthStep('username');
    this.openModal(this.dom.authModal);
  }

  showAuthStep(step) {
    if (this.dom.authErrorBox) {
      this.dom.authErrorBox.style.display = 'none';
      this.dom.authErrorBox.textContent = '';
    }

    if (this.dom.authStepUsername) this.dom.authStepUsername.style.display = (step === 'username') ? 'block' : 'none';
    if (this.dom.authStepLogin) this.dom.authStepLogin.style.display = (step === 'login') ? 'block' : 'none';
    if (this.dom.authStepRegister) this.dom.authStepRegister.style.display = (step === 'register') ? 'block' : 'none';

    if (step === 'username') {
      if (this.dom.authUsernameInput) {
        this.dom.authUsernameInput.value = (this.playerName && !this.playerName.startsWith('Joueur ')) ? this.playerName : '';
        setTimeout(() => this.dom.authUsernameInput.focus(), 150);
      }
    } else if (step === 'login') {
      if (this.dom.authLoginUsernameDisplay) this.dom.authLoginUsernameDisplay.textContent = this.pendingAuthUsername;
      if (this.dom.authPasswordInput) {
        this.dom.authPasswordInput.value = '';
        setTimeout(() => this.dom.authPasswordInput.focus(), 150);
      }
    } else if (step === 'register') {
      if (this.dom.authRegisterUsernameDisplay) this.dom.authRegisterUsernameDisplay.textContent = this.pendingAuthUsername;
      if (this.dom.authNewPasswordInput) {
        this.dom.authNewPasswordInput.value = '';
        setTimeout(() => this.dom.authNewPasswordInput.focus(), 150);
      }
    }
  }

  showAuthError(msg) {
    if (this.dom.authErrorBox) {
      this.dom.authErrorBox.textContent = `⚠️ ${msg}`;
      this.dom.authErrorBox.style.display = 'flex';
    }
  }

  async handleAuthUsernameSubmit() {
    const raw = this.dom.authUsernameInput ? this.dom.authUsernameInput.value.trim() : '';
    if (!raw) {
      this.showAuthError("Veuillez saisir un nom d'utilisateur.");
      return;
    }
    if (raw.length < 2) {
      this.showAuthError("Le nom d'utilisateur doit contenir au moins 2 caractères.");
      return;
    }

    const btn = this.dom.btnAuthContinue;
    if (btn) {
      btn.disabled = true;
      btn.textContent = 'Vérification...';
    }

    try {
      const resp = await fetch(this.getApiUrl('/api/auth/check-username'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: raw })
      });

      if (!resp.ok) throw new Error('Erreur réseau');
      const data = await resp.json();

      this.pendingAuthUsername = data.username || raw;
      if (data.exists) {
        this.showAuthStep('login');
      } else {
        this.showAuthStep('register');
      }
    } catch (e) {
      this.showAuthError("Impossible de joindre le serveur. Vérifiez votre connexion.");
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = 'Continuer ➔';
      }
    }
  }

  async handleAuthLoginSubmit() {
    const pwd = this.dom.authPasswordInput ? this.dom.authPasswordInput.value : '';
    if (!pwd) {
      this.showAuthError("Veuillez saisir votre mot de passe.");
      return;
    }

    const btn = document.getElementById('btn-auth-login');
    if (btn) {
      btn.disabled = true;
      btn.textContent = 'Connexion...';
    }

    try {
      const resp = await fetch(this.getApiUrl('/api/auth/login'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: this.pendingAuthUsername, password: pwd })
      });

      const data = await resp.json();
      if (!resp.ok) {
        this.showAuthError(data.detail || data.error || "Mot de passe incorrect.");
        return;
      }

      this.completeAuth(data.username, data.token, data.stats);
    } catch (e) {
      this.showAuthError("Erreur de connexion. Vérifiez le serveur.");
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = 'Se connecter ✅';
      }
    }
  }

  async handleAuthRegisterSubmit() {
    const pwd = this.dom.authNewPasswordInput ? this.dom.authNewPasswordInput.value : '';
    if (!pwd || pwd.length < 3) {
      this.showAuthError("Le mot de passe doit contenir au moins 3 caractères.");
      return;
    }

    const btn = document.getElementById('btn-auth-register');
    if (btn) {
      btn.disabled = true;
      btn.textContent = 'Création du compte...';
    }

    try {
      const resp = await fetch(this.getApiUrl('/api/auth/register'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: this.pendingAuthUsername, password: pwd })
      });

      const data = await resp.json();
      if (!resp.ok) {
        this.showAuthError(data.detail || data.error || "Erreur lors de la création du compte.");
        return;
      }

      this.completeAuth(data.username, data.token, data.stats);
    } catch (e) {
      this.showAuthError("Erreur de communication avec le serveur.");
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = 'Créer mon compte & Jouer 🚀';
      }
    }
  }

  completeAuth(username, token, stats) {
    this.authUser = username;
    this.authToken = token;
    this.playerName = username;

    localStorage.setItem('pedantix_auth_user', username);
    localStorage.setItem('pedantix_auth_token', token);
    localStorage.setItem('pedantix_player_name', username);

    if (this.dom.playerPseudoInput) this.dom.playerPseudoInput.value = username;
    if (this.dom.lobbyPseudoInput) this.dom.lobbyPseudoInput.value = username;

    this.closeModal(this.dom.authModal);
    this.showToast(`Bienvenue, ${username} ! Profil connecté 🎮`);

    // Synchronize room with the new player name
    this.joinRoom();
  }

  handleAuthLogout() {
    localStorage.removeItem('pedantix_auth_user');
    localStorage.removeItem('pedantix_auth_token');
    this.authUser = null;
    this.authToken = null;

    this.closeModal(this.dom.statsModal);
    this.openAuthModal();
    this.showToast("Déconnecté. Choisissez un compte pour continuer.");
  }

  // =========================================================================
  // SERVER SETTINGS MODAL
  // =========================================================================

  openServerSettingsModal() {
    if (this.dom.inputBackendUrl) {
      this.dom.inputBackendUrl.value = this.getBackendUrl();
    }
    this.testServerConnectivity();
    this.openModal(this.dom.serverSettingsModal);
  }

  async testServerConnectivity() {
    if (!this.dom.serverModalStatusText || !this.dom.serverModalStatusIndicator) return;
    this.dom.serverModalStatusText.textContent = "Test de la connexion au serveur...";
    this.dom.serverModalStatusIndicator.className = "server-status-indicator checking";

    try {
      const resp = await fetch(this.getApiUrl('/api/network-info'), { signal: AbortSignal.timeout(6000) });
      if (resp.ok) {
        this.dom.serverModalStatusText.textContent = "Connecté au serveur API ✅";
        this.dom.serverModalStatusIndicator.className = "server-status-indicator online";
      } else {
        this.dom.serverModalStatusText.textContent = `Erreur HTTP (${resp.status}) ⚠️`;
        this.dom.serverModalStatusIndicator.className = "server-status-indicator offline";
      }
    } catch (e) {
      this.dom.serverModalStatusText.textContent = "Serveur injoignable ou en cours de réveil ⚠️";
      this.dom.serverModalStatusIndicator.className = "server-status-indicator offline";
    }
  }

  async saveServerSettings() {
    const raw = this.dom.inputBackendUrl ? this.dom.inputBackendUrl.value.trim() : '';
    localStorage.setItem('pedantix_backend_url', raw);
    this.showToast("Configuration du serveur enregistrée ! Test en cours...");
    await this.testServerConnectivity();
  }
}

// Start app on DOMContentLoaded
window.addEventListener('DOMContentLoaded', () => {
  window.app = new PedantixApp();
});