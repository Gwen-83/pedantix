(() => {
  const apiBase = window.PEDANTIX_CONFIG?.BACKEND_URL?.replace(/\/+$/, '') || '';
  const playerIdKey = 'bitoguessr_player_id';
  let playerId = localStorage.getItem(playerIdKey);
  if (!playerId) {
    playerId = globalThis.crypto?.randomUUID?.()
      || `gate-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    localStorage.setItem(playerIdKey, playerId);
  }

  const authUser = (localStorage.getItem('pedantix_auth_user') || '').trim();
  const form = document.getElementById('gate-form');
  const input = document.getElementById('gate-input');
  const submitBtn = document.getElementById('gate-submit');
  const feedback = document.getElementById('gate-feedback');
  const card = document.getElementById('gate-card');
  const riddleStep = document.getElementById('gate-riddle-step');
  const riddleCategory = document.getElementById('gate-riddle-category');
  const riddleTitle = document.getElementById('gate-riddle-title');
  const riddleEpigraph = document.getElementById('gate-riddle-epigraph');
  const riddlePrompt = document.getElementById('gate-riddle-prompt');
  const riddleDetail = document.getElementById('gate-riddle-detail');
  const stepper = document.getElementById('gate-stepper');

  let currentStep = 1;
  let isSubmitting = false;

  async function request(path, options = {}) {
    const headers = {
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      'x-player-id': playerId,
      ...(authUser ? { 'x-auth-user': authUser } : {}),
      ...options.headers,
    };
    const response = await fetch(`${apiBase}${path}`, { ...options, headers });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || data.error || `Erreur serveur (${response.status})`);
    }
    return data;
  }

  function setFeedback(msg, isError = false) {
    feedback.textContent = msg;
    feedback.className = `gate-feedback ${isError ? 'error' : 'success'}`;
    feedback.hidden = false;
  }

  function clearFeedback() {
    feedback.textContent = '';
    feedback.hidden = true;
  }

  function renderStepper(activeStep, completed = false) {
    stepper.replaceChildren();
    const romanNumerals = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X'];
    for (let i = 1; i <= 10; i++) {
      const node = document.createElement('div');
      node.className = 'gate-step-node';
      const icon = document.createElement('div');
      icon.className = 'gate-step-icon';

      if (completed || i < activeStep) {
        node.classList.add('completed');
        icon.textContent = '✓';
      } else if (i === activeStep && !completed) {
        node.classList.add('active');
        icon.textContent = '🗝️';
      } else {
        icon.textContent = '🔒';
      }

      const label = document.createElement('span');
      label.textContent = romanNumerals[i - 1];
      node.append(icon, label);
      stepper.appendChild(node);
    }
  }

  function renderRiddle(riddleData) {
    currentStep = riddleData.step;
    renderStepper(currentStep, false);

    riddleStep.textContent = `Sceau ${riddleData.step} / 10`;
    riddleCategory.textContent = riddleData.category || 'Arcane';
    riddleTitle.textContent = riddleData.title;

    if (riddleData.epigraph) {
      riddleEpigraph.textContent = riddleData.epigraph;
      riddleEpigraph.hidden = false;
    } else {
      riddleEpigraph.hidden = true;
    }

    riddlePrompt.textContent = riddleData.prompt;

    if (riddleData.detail) {
      riddleDetail.textContent = riddleData.detail;
      riddleDetail.hidden = false;
    } else {
      riddleDetail.hidden = true;
    }

    input.value = '';
    input.disabled = false;
    submitBtn.disabled = false;
    input.focus();
  }

  function renderUnlocked(token) {
    if (token) {
      localStorage.setItem('bitoguessr_gate_token', token);
      document.cookie = `bitoguessr_access_token=${encodeURIComponent(token)}; path=/; max-age=31536000; SameSite=Lax`;
    }

    renderStepper(10, true);
    card.innerHTML = `
      <div class="gate-unlocked-card">
        <div class="gate-unlocked-icon">🌌</div>
        <h2 style="font-size: 2rem; color: #f3c76d; margin: 0 0 12px;">Les 10 Sceaux sont brisés</h2>
        <p style="font-size: 1.05rem; color: var(--game-text); max-width: 540px; margin: 0 auto 28px; line-height: 1.6;">
          Vous avez triomphé des arcanes du Gardien. Votre esprit a percé le voile de l'ignorance.
          L'accès au sanctuaire de <strong>Bitoguessr</strong> vous est désormais accordé.
        </p>
        <button id="gate-enter-game" class="gate-submit" style="font-size: 1.1rem; padding: 16px 36px;">
          Entrer dans Bitoguessr →
        </button>
      </div>
    `;

    document.getElementById('gate-enter-game')?.addEventListener('click', () => {
      window.location.reload();
    });

    // Redirection automatique après 3 secondes si le joueur n'a pas cliqué
    setTimeout(() => {
      window.location.reload();
    }, 3500);
  }

  async function loadCurrentRiddle() {
    try {
      clearFeedback();
      const data = await request(`/api/secret-gate/current?player_id=${encodeURIComponent(playerId)}`);
      if (data.completed) {
        renderUnlocked(data.token);
      } else {
        renderRiddle(data.riddle);
      }
    } catch (err) {
      setFeedback(`Impossible d'invoquer le Gardien : ${err.message}`, true);
    }
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (isSubmitting) return;

    const guess = input.value.trim();
    if (!guess) return;

    isSubmitting = true;
    submitBtn.disabled = true;
    clearFeedback();

    try {
      const res = await request('/api/secret-gate/guess', {
        method: 'POST',
        body: JSON.stringify({
          player_id: playerId,
          guess: guess,
        }),
      });

      if (res.error) {
        setFeedback(res.error, true);
        if (res.retry_after) {
          const cooldown = Math.ceil(res.retry_after);
          submitBtn.disabled = true;
          input.disabled = true;
          let remaining = cooldown;
          const timer = setInterval(() => {
            remaining -= 1;
            if (remaining <= 0) {
              clearInterval(timer);
              submitBtn.disabled = false;
              input.disabled = false;
              input.focus();
            }
          }, 1000);
        }
        return;
      }

      if (res.correct) {
        if (res.completed) {
          renderUnlocked(res.token);
        } else {
          setFeedback(res.message || 'Sceau brisé ! Chargement du suivant...', false);
          card.classList.add('pulse');
          setTimeout(() => {
            card.classList.remove('pulse');
            clearFeedback();
            renderRiddle(res.riddle);
          }, 800);
        }
      } else {
        card.classList.add('shake');
        setFeedback(res.message || 'Ce n’est pas la réponse attendue.', true);
        setTimeout(() => card.classList.remove('shake'), 500);
      }
    } catch (err) {
      setFeedback(err.message, true);
    } finally {
      isSubmitting = false;
      if (!submitBtn.disabled) {
        submitBtn.disabled = false;
        input.focus();
      }
    }
  });

  loadCurrentRiddle();
})();
