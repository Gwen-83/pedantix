(() => {
  const username = (localStorage.getItem('pedantix_auth_user') || '').trim();
  const token = localStorage.getItem('pedantix_auth_token') || '';
  const intro = document.getElementById('intro');
  const taskPanel = document.getElementById('task-panel');
  const resultPanel = document.getElementById('result');
  const error = document.getElementById('error');
  const startButton = document.getElementById('start-button');
  const retryButton = document.getElementById('retry-button');
  const timer = document.getElementById('timer');
  const progress = document.getElementById('progress');
  const sessionStorageKey = 'fermeture-express-session';
  let sessionId = null;
  let startedAt = null;
  let timerInterval = null;
  let busy = false;

  function formatTime(milliseconds) {
    const value = Math.max(0, Math.floor(milliseconds));
    const minutes = Math.floor(value / 60000);
    const seconds = Math.floor((value % 60000) / 1000);
    const millis = value % 1000;
    return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}.${String(millis).padStart(3, '0')}`;
  }

  function request(path, options = {}) {
    return fetch(path, {
      ...options,
      headers: {
        'X-Auth-User': username,
        'X-Auth-Token': token,
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...options.headers,
      },
    }).then(async (response) => {
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || 'Une erreur est survenue. Réessayez.');
      return data;
    });
  }

  function showError(message) {
    error.textContent = message;
    error.hidden = false;
  }

  function clearError() {
    error.textContent = '';
    error.hidden = true;
  }

  function setTimer(startTimestamp) {
    startedAt = startTimestamp;
    if (timerInterval) window.clearInterval(timerInterval);
    const update = () => { timer.textContent = formatTime(Date.now() - startedAt); };
    update();
    timerInterval = window.setInterval(update, 30);
  }

  function stopTimer(elapsedMs) {
    if (timerInterval) window.clearInterval(timerInterval);
    timerInterval = null;
    timer.textContent = formatTime(elapsedMs);
  }

  function renderState(state) {
    sessionId = state.session_id;
    progress.textContent = state.finished
      ? 'Tournée terminée'
      : `Tâche ${state.completed + 1} / ${state.task_count}`;
    if (state.finished) {
      stopTimer(state.elapsed_ms);
      sessionStorage.removeItem(sessionStorageKey);
      intro.hidden = true;
      taskPanel.hidden = true;
      resultPanel.hidden = false;
      document.getElementById('result-time').textContent = formatTime(state.elapsed_ms);
      document.getElementById('result-detail').textContent =
        `${state.mistakes} erreur${state.mistakes === 1 ? '' : 's'} · ${formatTime(state.penalty_ms)} de pénalité`;
      document.getElementById('result-title').textContent =
        state.record?.is_record ? 'Nouveau record personnel !' : 'Musée fermé !';
      loadLeaderboard();
      loadPersonalRecord();
      return;
    }

    intro.hidden = true;
    resultPanel.hidden = true;
    taskPanel.hidden = false;
    document.getElementById('task-prompt').textContent = state.task.prompt;
    document.getElementById('mistakes').textContent =
      `${state.mistakes} erreur${state.mistakes === 1 ? '' : 's'} · pénalité actuelle : ${formatTime(state.penalty_ms)}`;

    const options = document.getElementById('options');
    options.replaceChildren();
    state.task.options.forEach((label, index) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'option-button';
      button.textContent = label;
      button.addEventListener('click', () => submitAnswer(index));
      options.append(button);
    });
  }

  async function startGame() {
    if (busy) return;
    busy = true;
    clearError();
    startButton.disabled = true;
    try {
      const state = await request('/api/fermeture-express/solo/new', { method: 'POST' });
      const timestamp = Date.now();
      sessionStorage.setItem(sessionStorageKey, JSON.stringify({
        sessionId: state.session_id,
        startedAt: timestamp,
      }));
      setTimer(timestamp);
      renderState(state);
    } catch (requestError) {
      showError(requestError.message);
    } finally {
      busy = false;
      startButton.disabled = false;
    }
  }

  async function submitAnswer(answer) {
    if (busy || !sessionId) return;
    busy = true;
    clearError();
    const buttons = [...document.querySelectorAll('.option-button')];
    buttons.forEach((button) => { button.disabled = true; });
    try {
      const state = await request('/api/fermeture-express/solo/submit', {
        method: 'POST',
        body: JSON.stringify({ session_id: sessionId, answer }),
      });
      renderState(state);
      if (!state.finished) {
        sessionStorage.setItem(sessionStorageKey, JSON.stringify({
          sessionId,
          startedAt,
        }));
      }
    } catch (requestError) {
      buttons.forEach((button) => { button.disabled = false; });
      showError(requestError.message);
    } finally {
      busy = false;
    }
  }

  async function loadLeaderboard() {
    const list = document.getElementById('leaderboard');
    try {
      const data = await request('/api/fermeture-express/leaderboard');
      list.replaceChildren();
      document.getElementById('leaderboard-empty').hidden = data.records.length > 0;
      data.records.forEach((record) => {
        const item = document.createElement('li');
        const name = document.createElement('strong');
        const time = document.createElement('span');
        name.textContent = record.username;
        time.className = 'time';
        time.textContent = formatTime(record.elapsed_ms);
        item.append(name, time);
        list.append(item);
      });
    } catch (requestError) {
      document.getElementById('leaderboard-empty').hidden = false;
      document.getElementById('leaderboard-empty').textContent = requestError.message;
    }
  }

  async function loadPersonalRecord() {
    if (!username || !token) return;
    try {
      const data = await request('/api/fermeture-express/record');
      const target = document.getElementById('personal-best');
      target.textContent = data.record
        ? `Votre meilleur temps : ${formatTime(data.record.elapsed_ms)}`
        : 'Vous n’avez pas encore de record.';
    } catch (requestError) {
      document.getElementById('personal-best').textContent = requestError.message;
    }
  }

  async function resumeGame() {
    const saved = sessionStorage.getItem(sessionStorageKey);
    if (!saved) return;
    try {
      const { sessionId: savedId, startedAt: savedStartedAt } = JSON.parse(saved);
      const state = await request(`/api/fermeture-express/solo/${encodeURIComponent(savedId)}`);
      setTimer(savedStartedAt);
      renderState(state);
    } catch (requestError) {
      sessionStorage.removeItem(sessionStorageKey);
      intro.hidden = false;
      showError(requestError.message);
    }
  }

  startButton.addEventListener('click', startGame);
  retryButton.addEventListener('click', startGame);
  loadLeaderboard();

  if (!username || !token) {
    startButton.disabled = true;
    retryButton.disabled = true;
    document.getElementById('auth-note').hidden = false;
  } else {
    loadPersonalRecord();
    resumeGame();
  }
})();
