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

  const gameId = document.documentElement.dataset.presenceGame;
  const settingControls = [...document.querySelectorAll('[data-game-setting]')];
  if (gameId && settingControls.length) {
    const settingsKey = `game_settings_v1:${gameId}`;

    function readGameSettings() {
      try {
        const savedSettings = localStorage.getItem(settingsKey);
        if (!savedSettings) return {};
        const parsed = JSON.parse(savedSettings);
        return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
          ? parsed
          : {};
      } catch (error) {
        console.warn(`Impossible de lire les paramètres enregistrés pour ${gameId}.`, error);
        return {};
      }
    }

    function isValidSetting(control, value) {
      if (typeof value !== 'string') return false;
      if (control instanceof HTMLSelectElement) {
        return [...control.options].some((option) => option.value === value && !option.disabled);
      }
      if (control instanceof HTMLInputElement) {
        const previousValue = control.value;
        control.value = value;
        const valid = control.checkValidity();
        if (!valid) control.value = previousValue;
        return valid;
      }
      return false;
    }

    const savedSettings = readGameSettings();
    settingControls.forEach((control) => {
      const settingName = control.dataset.gameSetting;
      if (!settingName || !Object.prototype.hasOwnProperty.call(savedSettings, settingName)) return;
      const value = savedSettings[settingName];
      if (isValidSetting(control, value)) control.value = value;
    });

    function saveGameSettings() {
      const settings = {};
      settingControls.forEach((control) => {
        const settingName = control.dataset.gameSetting;
        if (!settingName || !isValidSetting(control, control.value)) return;
        settings[settingName] = control.value;
      });
      try {
        localStorage.setItem(settingsKey, JSON.stringify(settings));
      } catch (error) {
        console.warn(`Impossible d’enregistrer les paramètres pour ${gameId}.`, error);
      }
    }

    settingControls.forEach((control) => {
      control.addEventListener('change', saveGameSettings);
      if (control instanceof HTMLInputElement) {
        control.addEventListener('input', saveGameSettings);
      }
    });
  }

  const roomsOverlay = document.querySelector('[data-shared-rooms-modal]');
  if (!roomsOverlay) return;

  const dialog = roomsOverlay.querySelector('[role="dialog"]');
  const modeButtons = [...document.querySelectorAll('[data-shared-game-mode]')];
  const roomError = document.getElementById(roomsOverlay.dataset.homeErrorTarget);
  const roomErrorParent = roomError?.parentElement;
  const roomErrorNextSibling = roomError?.nextSibling;
  let lastTrigger = null;

  const initialMode = modeButtons.find((button) => button.classList.contains('active'))
    ?.dataset.sharedGameMode || 'solo';
  document.body.dataset.sharedMode = initialMode;

  function trapDialogFocus(event, activeDialog) {
    if (event.key !== 'Tab') return;
    if (!activeDialog) return;
    const focusable = [...activeDialog.querySelectorAll(
      'a[href], button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])',
    )].filter((element) => !element.closest('[hidden]') && element.getClientRects().length > 0);
    if (!focusable.length) {
      event.preventDefault();
      activeDialog.focus();
      return;
    }
    const activeIndex = focusable.indexOf(document.activeElement);
    if (activeIndex < 0) {
      event.preventDefault();
      (event.shiftKey ? focusable[focusable.length - 1] : focusable[0]).focus();
    } else if (event.shiftKey && activeIndex === 0) {
      event.preventDefault();
      focusable[focusable.length - 1].focus();
    } else if (!event.shiftKey && activeIndex === focusable.length - 1) {
      event.preventDefault();
      focusable[0].focus();
    }
  }

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
      document.body.dataset.sharedMode = mode;
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
  roomsOverlay.addEventListener('keydown', (event) => trapDialogFocus(event, dialog));
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
    let wasHidden = lobby.hidden;

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
    if (dialog) {
      lobby.addEventListener('keydown', (event) => trapDialogFocus(event, dialog));
    }
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
      } else {
        if (openButton) openButton.hidden = true;
        if (wasHidden) dialog?.focus();
      }
      wasHidden = lobby.hidden;
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
