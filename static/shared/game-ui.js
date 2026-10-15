(() => {
  const themeColors = {
    'dark-colorful': '#273238',
    midnight: '#070b14',
    'light-colorful': '#f4e9e8',
    'light-grey': '#e8edf3',
    'dark-grey': '#18181b',
    parchment: '#eae2d3',
  };
  const themes = new Set(Object.keys(themeColors));
  const themeSelect = document.getElementById('shared-theme-select');
  if (!themeSelect) return;

  const theme = localStorage.getItem('pedantix_theme');
  const selectedTheme = themes.has(theme) ? theme : 'dark-colorful';
  function applyTheme(nextTheme) {
    document.documentElement.dataset.theme = nextTheme;
    themeSelect.value = nextTheme;
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', themeColors[nextTheme]);
  }

  applyTheme(selectedTheme);

  themeSelect.addEventListener('change', () => {
    const nextTheme = themeSelect.value;
    if (!themes.has(nextTheme)) return;
    localStorage.setItem('pedantix_theme', nextTheme);
    applyTheme(nextTheme);
  });

  const roomsOverlay = document.querySelector('[data-shared-rooms-modal]');
  if (!roomsOverlay) return;

  const dialog = roomsOverlay.querySelector('[role="dialog"]');
  const modeButtons = [...document.querySelectorAll('[data-shared-game-mode]')];
  const roomError = document.getElementById(roomsOverlay.dataset.homeErrorTarget);
  const roomErrorParent = roomError?.parentElement;
  const roomErrorNextSibling = roomError?.nextSibling;
  let lastTrigger = null;

  function closeRoomsModal() {
    roomsOverlay.hidden = true;
    if (roomError && roomErrorParent) {
      roomErrorParent.insertBefore(roomError, roomErrorNextSibling);
    }
    if (lastTrigger instanceof HTMLElement && !lastTrigger.closest('[hidden]')) lastTrigger.focus();
  }

  function openRoomsModal(trigger) {
    lastTrigger = trigger instanceof HTMLElement ? trigger : null;
    roomsOverlay.hidden = false;
    if (roomError && dialog) dialog.insertBefore(roomError, dialog.querySelector('.shared-rooms-actions'));
    dialog?.focus();
    roomsOverlay.querySelector('[data-shared-refresh-rooms]')?.click();
  }

  modeButtons.forEach((button) => {
    button.addEventListener('click', () => {
      const mode = button.dataset.sharedGameMode;
      modeButtons.forEach((candidate) => {
        const selected = candidate.dataset.sharedGameMode === mode;
        candidate.classList.toggle('active', selected);
        candidate.setAttribute('aria-pressed', String(selected));
      });
      if (mode === 'multi') openRoomsModal(button);
      else closeRoomsModal();
    });
  });
  document.querySelectorAll('[data-shared-open-rooms]').forEach((button) => {
    button.addEventListener('click', () => openRoomsModal(button));
  });

  roomsOverlay.querySelectorAll('[data-shared-modal-close]').forEach((button) => {
    button.addEventListener('click', closeRoomsModal);
  });
  roomsOverlay.addEventListener('click', (event) => {
    if (event.target === roomsOverlay) closeRoomsModal();
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !roomsOverlay.hidden) {
      event.preventDefault();
      event.stopImmediatePropagation();
      closeRoomsModal();
    }
  });

  const playSection = document.getElementById(roomsOverlay.dataset.playTarget);
  if (playSection) {
    new MutationObserver(() => {
      if (!playSection.hidden) closeRoomsModal();
    }).observe(playSection, { attributes: true, attributeFilter: ['hidden'] });
  }

  document.querySelectorAll('[data-shared-game-lobby]').forEach((lobby) => {
    const dialog = lobby.querySelector('[role="dialog"]');
    const closeButton = lobby.querySelector('[data-shared-lobby-close]');
    const openButton = [...document.querySelectorAll('[data-shared-lobby-open]')]
      .find((button) => button.dataset.sharedLobbyOpen === lobby.id);
    const nextStage = lobby.dataset.sharedLobbyNext
      ? document.getElementById(lobby.dataset.sharedLobbyNext)
      : null;
    const playSection = lobby.closest('section[id$="-play"]');
    let minimized = false;

    function closeLobby() {
      minimized = true;
      lobby.classList.add('is-minimized');
      if (openButton) {
        openButton.hidden = false;
        openButton.focus();
      }
    }

    function openLobby() {
      minimized = false;
      lobby.classList.remove('is-minimized');
      if (openButton) openButton.hidden = true;
      dialog?.focus();
    }

    function resetLobby() {
      minimized = false;
      lobby.classList.remove('is-minimized');
      if (openButton) openButton.hidden = true;
    }

    closeButton?.addEventListener('click', closeLobby);
    openButton?.addEventListener('click', openLobby);
    lobby.addEventListener('click', (event) => {
      if (event.target === lobby) closeLobby();
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && !lobby.hidden && !lobby.classList.contains('is-minimized')) {
        event.preventDefault();
        event.stopImmediatePropagation();
        closeLobby();
      }
    });

    new MutationObserver(() => {
      if (lobby.hidden) {
        if (!minimized) resetLobby();
      } else if (minimized) {
        if (openButton) openButton.hidden = !minimized;
      } else if (openButton) {
        openButton.hidden = true;
      }
    }).observe(lobby, { attributes: true, attributeFilter: ['hidden'] });

    if (playSection) {
      new MutationObserver(() => {
        if (playSection.hidden) resetLobby();
      }).observe(playSection, { attributes: true, attributeFilter: ['hidden'] });
    }

    if (nextStage) {
      new MutationObserver(() => {
        if (!nextStage.hidden) resetLobby();
      }).observe(nextStage, { attributes: true, attributeFilter: ['hidden'] });
    }
  });
})();
