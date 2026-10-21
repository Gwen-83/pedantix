(() => {
  const periodSelect = document.getElementById('usage-period');
  const status = document.getElementById('usage-status');
  const content = document.getElementById('usage-content');
  let report = null;
  const gameNames = new Map();

  function authHeaders() {
    const username = localStorage.getItem('pedantix_auth_user');
    const token = localStorage.getItem('pedantix_auth_token');
    return username && token
      ? { 'X-Auth-User': username, 'X-Auth-Token': token }
      : {};
  }

  function formatDuration(seconds) {
    const value = Math.max(0, Math.round(Number(seconds) || 0));
    const hours = Math.floor(value / 3600);
    const minutes = Math.floor((value % 3600) / 60);
    if (hours) return `${hours} h ${minutes.toString().padStart(2, '0')} min`;
    if (minutes) return `${minutes} min`;
    return `${value} s`;
  }

  function number(value) {
    return new Intl.NumberFormat('fr-FR').format(Number(value) || 0);
  }

  function dateTime(value) {
    if (!value) return '—';
    const date = new Date(value);
    return Number.isNaN(date.getTime())
      ? '—'
      : new Intl.DateTimeFormat('fr-FR', { dateStyle: 'short', timeStyle: 'short' }).format(date);
  }

  function formatMetrics(metrics) {
    return Object.entries(metrics || {}).map(([key, value]) => {
      const formatted = value && typeof value === 'object'
        ? JSON.stringify(value)
        : value == null ? '—' : String(value);
      return `${key.replaceAll('_', ' ')} : ${formatted}`;
    });
  }

  function makeCell(row, value) {
    const cell = document.createElement('td');
    cell.textContent = value == null || value === '' ? '—' : String(value);
    row.append(cell);
    return cell;
  }

  function appendRow(target, values) {
    const row = document.createElement('tr');
    values.forEach((value) => makeCell(row, value));
    target.append(row);
    return row;
  }

  function renderKpis(summary) {
    const values = [
      ['Sessions lancées', number(summary.sessions_started)],
      ['Sessions terminées', `${number(summary.sessions_finished)} · ${summary.completion_rate_pct}%`],
      ['Sessions non terminées', number(summary.sessions_active)],
      ['Comptes avec résultats', number(summary.unique_players)],
      ['Temps de jeu cumulé', `${formatDuration(summary.player_seconds)} · ${summary.player_hours} h`],
      ['Temps mural', `${formatDuration(summary.wall_seconds)} · ${summary.wall_hours} h`],
      ['Résultats individuels', number(summary.participant_results)],
      ['Taux de victoire', `${summary.win_rate_pct}%`],
      ['Points cumulés', number(summary.total_points)],
      ['Tentatives cumulées', number(summary.total_attempts)],
      ['Abandons déclarés', number(summary.surrenders)],
    ];
    const container = document.getElementById('usage-kpis');
    container.replaceChildren();
    values.forEach(([label, value]) => {
      const card = document.createElement('div');
      card.className = 'usage-kpi';
      const heading = document.createElement('span');
      heading.textContent = label;
      const strong = document.createElement('strong');
      strong.textContent = value;
      card.append(heading, strong);
      container.append(card);
    });
  }

  function renderGoogleUsage(usage) {
    const panel = document.querySelector('.usage-google-panel');
    const percentage = Number(usage.usage_pct) || 0;
    const fillPercentage = Math.min(100, Math.max(0, percentage));
    const progress = document.getElementById('usage-google-progress');
    const monthDate = new Date(`${usage.month}-01T00:00:00Z`);

    document.getElementById('usage-google-month').textContent =
      `Utilisation du mois en cours (UTC) · ${new Intl.DateTimeFormat('fr-FR', {
        month: 'long',
        year: 'numeric',
        timeZone: 'UTC',
      }).format(monthDate)}`;
    document.getElementById('usage-google-percent').textContent =
      `${percentage.toLocaleString('fr-FR', { maximumFractionDigits: 1 })}%`;
    document.getElementById('usage-google-count').textContent = number(usage.events_reserved);
    document.getElementById('usage-google-limit').textContent = number(usage.monthly_limit);
    document.getElementById('usage-google-remaining').textContent =
      `${number(usage.remaining)} restantes`;
    progress.setAttribute('aria-valuenow', String(fillPercentage));
    document.getElementById('usage-google-progress-fill').style.width = `${fillPercentage}%`;
    panel.dataset.level = percentage >= 90 ? 'critical' : percentage >= 75 ? 'warning' : 'normal';
  }

  function makeSvg(name, attributes = {}) {
    const element = document.createElementNS('http://www.w3.org/2000/svg', name);
    Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
    return element;
  }

  function renderTimeline(rows) {
    const container = document.getElementById('usage-timeline');
    container.replaceChildren();
    if (!rows.length) {
      container.textContent = 'Aucune activité sur cette période.';
      return;
    }
    const width = 900;
    const height = 220;
    const margin = { top: 12, right: 22, bottom: 34, left: 40 };
    const plotWidth = width - margin.left - margin.right;
    const plotHeight = height - margin.top - margin.bottom;
    const maxValue = Math.max(1, ...rows.flatMap((row) => [row.sessions_started, row.sessions_finished]));
    const svg = makeSvg('svg', { viewBox: `0 0 ${width} ${height}`, role: 'img' });
    for (let step = 0; step <= 4; step += 1) {
      const y = margin.top + plotHeight * step / 4;
      svg.append(makeSvg('line', {
        x1: margin.left, x2: width - margin.right, y1: y, y2: y, class: 'usage-grid-line',
      }));
      const label = makeSvg('text', { x: margin.left - 8, y: y + 4, 'text-anchor': 'end' });
      label.textContent = String(Math.round(maxValue * (4 - step) / 4));
      svg.append(label);
    }
    const series = [
      { key: 'sessions_started', color: 'var(--game-accent)', label: 'Lancements' },
      { key: 'sessions_finished', color: '#62c6a5', label: 'Parties terminées' },
    ];
    series.forEach((item) => {
      const points = rows.map((row, index) => {
        const x = margin.left + (rows.length === 1 ? plotWidth / 2 : plotWidth * index / (rows.length - 1));
        const y = margin.top + plotHeight * (1 - row[item.key] / maxValue);
        return `${x},${y}`;
      }).join(' ');
      svg.append(makeSvg('polyline', {
        points, fill: 'none', stroke: item.color, 'stroke-width': 3,
        'stroke-linecap': 'round', 'stroke-linejoin': 'round',
      }));
    });
    [0, Math.floor((rows.length - 1) / 2), rows.length - 1].forEach((index) => {
      const label = makeSvg('text', {
        x: margin.left + (rows.length === 1 ? plotWidth / 2 : plotWidth * index / (rows.length - 1)),
        y: height - 8,
        'text-anchor': index === 0 ? 'start' : index === rows.length - 1 ? 'end' : 'middle',
      });
      label.textContent = rows[index].date;
      svg.append(label);
    });
    const legend = document.createElement('div');
    legend.className = 'usage-legend';
    series.forEach((item) => {
      const entry = document.createElement('span');
      const marker = document.createElement('i');
      marker.style.background = item.color;
      entry.append(marker, document.createTextNode(item.label));
      legend.append(entry);
    });
    container.append(svg, legend);
  }

  function renderBars(targetId, rows, labelFor, valueFor, unit = 'parties') {
    const container = document.getElementById(targetId);
    container.replaceChildren();
    const max = Math.max(1, ...rows.map(valueFor));
    const axis = document.createElement('div');
    axis.className = 'usage-bar-axis';
    axis.setAttribute('aria-hidden', 'true');
    [max, Math.floor(max / 2), 0].forEach((tick, index, ticks) => {
      if (index > 0 && tick === ticks[index - 1]) return;
      const label = document.createElement('span');
      label.textContent = number(tick);
      axis.append(label);
    });
    const plot = document.createElement('div');
    plot.className = 'usage-bars';
    plot.dataset.unit = unit;
    plot.setAttribute('role', 'img');
    plot.setAttribute('aria-label', `${unit} par période, échelle verticale de 0 à ${max}`);
    rows.forEach((row) => {
      const item = document.createElement('div');
      item.className = 'usage-bar-item';
      const bar = document.createElement('div');
      bar.className = 'usage-bar';
      bar.style.height = `${Math.max(valueFor(row) ? 3 : 0, valueFor(row) / max * 100)}%`;
      bar.title = `${labelFor(row)} : ${number(valueFor(row))}`;
      const label = document.createElement('span');
      label.className = 'usage-bar-label';
      label.textContent = labelFor(row);
      item.append(bar, label);
      plot.append(item);
    });
    container.append(axis, plot);
  }

  function renderGames(rows) {
    const target = document.getElementById('usage-games');
    target.replaceChildren();
    if (!rows.length) appendRow(target, ['Aucune partie enregistrée sur cette période.']);
    rows.forEach((game) => {
      const row = document.createElement('tr');
      makeCell(row, game.name);
      makeCell(row, number(game.sessions_started));
      makeCell(row, number(game.sessions_finished));
      makeCell(row, number(game.unique_players));
      makeCell(row, `${formatDuration(game.player_seconds)} (${game.player_hours} h)`);
      const share = document.createElement('td');
      const shareBox = document.createElement('div');
      shareBox.className = 'usage-share';
      const track = document.createElement('div');
      track.className = 'usage-share-track';
      const fill = document.createElement('span');
      fill.style.width = `${Math.min(100, game.player_time_share_pct)}%`;
      track.append(fill);
      const percent = document.createElement('span');
      percent.textContent = `${game.player_time_share_pct}%`;
      shareBox.append(track, percent);
      share.append(shareBox);
      row.append(share);
      makeCell(row, formatDuration(game.wall_seconds));
      makeCell(row, `${number(game.wins)} / ${number(game.participant_results)} (${game.win_rate_pct}%)`);
      makeCell(row, game.avg_attempts);
      makeCell(row, `${number(game.surrenders)} (${game.surrender_rate_pct}%)`);
      makeCell(row, number(game.points));
      target.append(row);
      gameNames.set(game.game_id, game.name);
    });
  }

  function renderTables(data) {
    const modes = document.getElementById('usage-modes');
    modes.replaceChildren();
    data.modes.forEach((item) => appendRow(modes, [
      item.mode, number(item.sessions), number(item.finished_sessions),
      number(item.results), number(item.wins), formatDuration(item.player_seconds),
    ]));

    const difficulties = document.getElementById('usage-difficulties');
    difficulties.replaceChildren();
    data.difficulties.forEach((item) => appendRow(difficulties, [
      item.difficulty, number(item.games), number(item.wins), item.games
        ? (item.attempts / item.games).toFixed(1) : '0',
      number(item.surrenders),
      formatDuration(item.player_seconds),
    ]));

    const players = document.getElementById('usage-players');
    players.replaceChildren();
    data.players.forEach((player) => {
      const row = document.createElement('tr');
      [
        player.username, number(player.games), number(player.wins), `${player.win_rate_pct}%`,
        player.avg_attempts, number(player.surrenders),
        `${formatDuration(player.player_seconds)} (${player.player_hours} h)`,
        number(player.points), gameNames.get(player.favorite_game) || player.favorite_game,
        dateTime(player.last_played_at),
      ].forEach((value) => makeCell(row, value));
      const detailsCell = document.createElement('td');
      const details = document.createElement('details');
      const summary = document.createElement('summary');
      summary.textContent = 'Voir par jeu';
      details.append(summary);
      const gameTable = document.createElement('table');
      gameTable.className = 'usage-player-games';
      const gameHead = document.createElement('thead');
      const heading = document.createElement('tr');
      ['Jeu', 'Parties', 'Victoires', 'Temps de jeu', 'Tentatives moy.', 'Abandons', 'Points', 'Statistiques détaillées']
        .forEach((label) => {
          const cell = document.createElement('th');
          cell.textContent = label;
          heading.append(cell);
        });
      gameHead.append(heading);
      gameTable.append(gameHead);
      const gameBody = document.createElement('tbody');
      (player.game_stats || []).forEach((game) => {
        const gameRow = document.createElement('tr');
        [
          game.game_name, number(game.games), `${number(game.wins)} (${game.win_rate_pct}%)`,
          formatDuration(game.player_seconds), game.avg_attempts, number(game.surrenders),
          number(game.points),
        ].forEach((value) => makeCell(gameRow, value));
        const metricsCell = document.createElement('td');
        const metricParts = formatMetrics(game.metrics);
        const resultDetails = document.createElement('details');
        const resultSummary = document.createElement('summary');
        resultSummary.textContent = metricParts.length
          ? metricParts.join(' · ')
          : 'Voir les résultats récents';
        resultDetails.append(resultSummary);
        (game.recent_results || []).forEach((result) => {
          const resultLine = document.createElement('p');
          const resultMetrics = formatMetrics(result.metrics);
          resultLine.textContent = [
            dateTime(result.finished_at),
            result.won ? 'Victoire' : 'Défaite',
            formatDuration(result.duration_seconds),
            `${number(result.points)} pts`,
            result.difficulty,
            ...resultMetrics,
          ].filter(Boolean).join(' · ');
          resultDetails.append(resultLine);
        });
        metricsCell.append(resultDetails);
        gameRow.append(metricsCell);
        gameBody.append(gameRow);
      });
      gameTable.append(gameBody);
      details.append(gameTable);
      detailsCell.append(details);
      row.append(detailsCell);
      players.append(row);
    });

    const recent = document.getElementById('usage-recent');
    recent.replaceChildren();
    data.recent_sessions.forEach((session) => appendRow(recent, [
      dateTime(session.started_at), session.game_name, session.mode,
      session.difficulty,
      (session.player_results || []).map((result) => {
        const metrics = formatMetrics(result.metrics);
        return [
          `${result.username} (${result.won ? 'victoire' : 'défaite'}`,
          formatDuration(result.duration_seconds),
          `${number(result.points)} pts`,
          result.difficulty,
          ...metrics,
        ].filter(Boolean).join(' · ') + ')';
      }).join(' | ') || session.players.join(', ') || 'Aucun résultat joueur enregistré',
      formatDuration(session.player_seconds), formatDuration(session.wall_seconds),
      session.finished_at ? 'Terminée' : 'En cours / abandonnée',
    ]));
  }

  function render(data) {
    report = data;
    renderKpis(data.summary);
    renderGoogleUsage(data.google_maps_usage);
    renderTimeline(data.timeline);
    renderBars('usage-hours', data.hourly_activity, (row) => `${String(row.hour).padStart(2, '0')}h`, (row) => row.sessions_started);
    renderBars('usage-weekdays', data.weekday_activity, (row) => ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim'][row.weekday], (row) => row.sessions_started);
    renderGames(data.games);
    renderTables(data);
    document.getElementById('usage-generated').textContent = `Données actualisées le ${dateTime(data.generated_at)}.`;
    content.hidden = false;
    status.textContent = '';
    status.dataset.error = 'false';
  }

  async function loadReport() {
    status.textContent = 'Chargement des statistiques…';
    status.dataset.error = 'false';
    try {
      const response = await fetch(`/api/admin/usage-analytics?period=${encodeURIComponent(periodSelect.value)}`, {
        headers: authHeaders(),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(response.status === 403
          ? 'Connectez-vous avec le compte administrateur Gwen pour consulter ces données.'
          : data.detail || 'Impossible de charger les statistiques.');
      }
      render(data);
    } catch (error) {
      content.hidden = true;
      status.textContent = error.message || 'Impossible de charger les statistiques.';
      status.dataset.error = 'true';
    }
  }

  function csvCell(value) {
    let text = value == null ? '' : String(value);
    if (typeof value === 'string' && /^[\u0000-\u0020]*[=+\-@]/.test(text)) {
      text = `'${text}`;
    }
    return `"${text.replaceAll('"', '""')}"`;
  }

  function exportCsv() {
    if (!report) return;
    const rows = [
      ['Section', 'Nom', 'Parties', 'Terminées', 'Joueurs', 'Temps joueur (secondes)', 'Part du temps (%)', 'Temps mural (secondes)', 'Victoires', 'Résultats', 'Tentatives moyennes', 'Abandons', 'Points'],
      ...report.games.map((game) => [
        'Jeu', game.name, game.sessions_started, game.sessions_finished, game.unique_players,
        game.player_seconds, game.player_time_share_pct, game.wall_seconds, game.wins,
        game.participant_results, game.avg_attempts, game.surrenders, game.points,
      ]),
      [],
      ['Section', 'Mois UTC', 'Événements réservés', 'Plafond interne mensuel', 'Restants', 'Utilisation (%)'],
      [
        'Quota Google Street View',
        report.google_maps_usage.month,
        report.google_maps_usage.events_reserved,
        report.google_maps_usage.monthly_limit,
        report.google_maps_usage.remaining,
        report.google_maps_usage.usage_pct,
      ],
      [],
      ['Mode', 'Sessions', 'Terminées', 'Résultats', 'Victoires', 'Temps joueur (secondes)'],
      ...report.modes.map((mode) => [
        mode.mode, mode.sessions, mode.finished_sessions, mode.results, mode.wins, mode.player_seconds,
      ]),
      [],
      ['Difficulté', 'Résultats', 'Victoires', 'Tentatives', 'Abandons', 'Temps joueur (secondes)'],
      ...report.difficulties.map((item) => [
        item.difficulty, item.games, item.wins, item.attempts, item.surrenders, item.player_seconds,
      ]),
      [],
      ['Date UTC', 'Sessions lancées', 'Sessions terminées', 'Temps joueur (secondes)', 'Joueurs'],
      ...report.timeline.map((day) => [day.date, day.sessions_started, day.sessions_finished, day.player_seconds, day.unique_players]),
      [],
      ['Joueur', 'Parties', 'Victoires', 'Taux de victoire (%)', 'Temps joueur (secondes)', 'Points', 'Jeu favori', 'Dernière activité'],
      ...report.players.map((player) => [
        player.username, player.games, player.wins, player.win_rate_pct,
        player.player_seconds, player.points, gameNames.get(player.favorite_game) || player.favorite_game,
        player.last_played_at,
      ]),
    ];
    const csv = `\uFEFF${rows.map((row) => row.map(csvCell).join(';')).join('\r\n')}`;
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `statistiques-utilisation-${report.period}-${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  periodSelect.addEventListener('change', loadReport);
  document.getElementById('usage-export').addEventListener('click', exportCsv);
  loadReport();
})();
