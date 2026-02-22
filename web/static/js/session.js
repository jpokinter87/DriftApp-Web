/**
 * Session Report - JavaScript
 *
 * Gestion de la page de rapport de session:
 * - Affichage temps réel de la session en cours
 * - Historique des sessions passées
 * - Graphiques Chart.js avec couleurs par mode
 * - Statistiques et tables de corrections/GOTO
 *
 * Version: 4.5
 * Date: Décembre 2025
 */

// =============================================================================
// CONFIGURATION
// =============================================================================

const CONFIG = {
    API_BASE: '/api/session',
    MOTOR_STATUS_URL: '/api/hardware/status/',
    REFRESH_INTERVAL: 5000,  // 5 secondes

    // Couleurs par mode de tracking
    MODE_COLORS: {
        normal: '#00d26a',      // Vert
        critical: '#ffa502',    // Orange
        continuous: '#ff4757',  // Rouge
        default: '#3498db'      // Bleu par défaut
    },

    CORRECTION_DOT_COLOR: '#ff4757',  // Rouge pour les points de correction
    CORRECTION_DOT_RADIUS: 3          // Petit rayon pour éviter l'encombrement
};

// =============================================================================
// ALPINE.JS STORE — pont entre vanilla JS et couche reactive
// =============================================================================

document.addEventListener('alpine:init', () => {
    Alpine.store('session', {
        // Status indicator
        statusClass: '',
        statusText: '--',
        // Auto-refresh
        autoRefresh: true,
        // Tab switching
        currentTab: 'current',
    });
});

// =============================================================================
// ÉTAT GLOBAL (vanilla JS — Chart.js, data, timers)
// =============================================================================

let state = {
    refreshTimer: null,
    altitudeChart: null,
    azimutChart: null,
    currentSessionData: null,
    historyLoaded: false,
    _lastTab: 'current'
};

// =============================================================================
// INITIALISATION
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
    initCharts();
    startRefreshTimer();

    // Charger les données initiales
    loadCurrentSession();

    // Watch Alpine store pour sync auto-refresh et tab switching avec polling
    setInterval(() => {
        try {
            const store = Alpine.store('session');

            // Sync auto-refresh
            if (store.autoRefresh && !state.refreshTimer) {
                startRefreshTimer();
            } else if (!store.autoRefresh && state.refreshTimer) {
                stopRefreshTimer();
            }

            // Sync tab switching
            if (store.currentTab !== state._lastTab) {
                state._lastTab = store.currentTab;
                onTabChanged(store.currentTab);
            }
        } catch (e) { /* Alpine pas encore pret */ }
    }, 200);
});

/**
 * Reagit au changement de tab (declenche par le watcher)
 */
function onTabChanged(tabName) {
    if (tabName === 'current') {
        loadCurrentSession();
    } else {
        if (!state.historyLoaded) {
            loadHistory();
        }
    }
}

function startRefreshTimer() {
    stopRefreshTimer();
    state.refreshTimer = setInterval(() => {
        try {
            if (Alpine.store('session').currentTab === 'current') {
                loadCurrentSession();
            }
        } catch (e) {
            loadCurrentSession();
        }
    }, CONFIG.REFRESH_INTERVAL);
}

function stopRefreshTimer() {
    if (state.refreshTimer) {
        clearInterval(state.refreshTimer);
        state.refreshTimer = null;
    }
}

// =============================================================================
// CHARGEMENT DES DONNÉES
// =============================================================================

async function loadCurrentSession() {
    try {
        const response = await fetch(`${CONFIG.API_BASE}/current/`);

        if (response.status === 404) {
            // Pas de session active
            updateNoActiveSession();
            return;
        }

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        state.currentSessionData = data;
        updateSessionDisplay(data);
        updateLastUpdateTime();

    } catch (error) {
        console.error('Erreur chargement session:', error);
        updateSessionStatus('error', 'Erreur');
    }
}

async function loadHistory() {
    try {
        const response = await fetch(`${CONFIG.API_BASE}/history/?limit=50`);

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        displayHistory(data.sessions);
        state.historyLoaded = true;

    } catch (error) {
        console.error('Erreur chargement historique:', error);
        document.getElementById('history-list').innerHTML =
            '<div class="error">Erreur de chargement</div>';
    }
}

async function loadHistorySession(sessionId) {
    try {
        const response = await fetch(`${CONFIG.API_BASE}/history/${sessionId}/`);

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        state.currentSessionData = data;
        updateSessionDisplay(data);

    } catch (error) {
        console.error('Erreur chargement session:', error);
    }
}

// =============================================================================
// MISE À JOUR DE L'AFFICHAGE
// =============================================================================

function updateNoActiveSession() {
    updateSessionStatus('inactive', 'Pas de session');
    document.getElementById('session-object').textContent = '--';
    document.getElementById('session-duration').textContent = '--';
    document.getElementById('session-coords').textContent = '-- / --';

    // Vider les graphiques
    if (state.altitudeChart) {
        state.altitudeChart.data.datasets[0].data = [];
        state.altitudeChart.update('none');
    }
    if (state.azimutChart) {
        state.azimutChart.data.datasets[0].data = [];
        state.azimutChart.update('none');
    }

    // Vider les stats
    document.getElementById('stat-corrections').textContent = '0';
    document.getElementById('stat-total-movement').textContent = '0.00';
    document.getElementById('stat-cw').textContent = '0.00';
    document.getElementById('stat-ccw').textContent = '0.00';
    document.getElementById('stat-avg-correction').textContent = '0.00';

    // Vider les tables
    document.getElementById('corrections-tbody').innerHTML =
        '<tr><td colspan="5" class="empty">Aucune correction</td></tr>';
    document.getElementById('goto-tbody').innerHTML =
        '<tr><td colspan="5" class="empty">Aucun GOTO</td></tr>';
}

function updateSessionDisplay(data) {
    // Statut
    if (data.active) {
        updateSessionStatus('active', 'Session active');
    } else {
        updateSessionStatus('history', 'Historique');
    }

    // Info session
    const objectInfo = data.object || {};
    document.getElementById('session-object').textContent = objectInfo.name || '--';

    const duration = data.timing?.duration_seconds || 0;
    document.getElementById('session-duration').textContent = formatDuration(duration);

    const ra = objectInfo.ra_deg;
    const dec = objectInfo.dec_deg;

    // Affichage avec format décimal + sexagésimal (HMS pour RA, DMS pour DEC)
    if (ra !== null && ra !== undefined && dec !== null && dec !== undefined) {
        const raDecimal = ra.toFixed(2) + '°';
        const decDecimal = dec.toFixed(2) + '°';
        const raHMS = formatHMS(ra);
        const decDMS = formatDMS(dec);
        document.getElementById('session-coords').innerHTML =
            `${raDecimal} (${raHMS}) / ${decDecimal} (${decDMS})`;
    } else {
        document.getElementById('session-coords').textContent = '-- / --';
    }

    // Statistiques
    updateStats(data.summary || {});

    // Mode distribution
    updateModeDistribution(data.summary?.mode_distribution || {});

    // Graphiques
    updateCharts(data);

    // Tables
    updateCorrectionsTable(data.corrections_log || []);
    updateGotoTable(data.goto_log || []);
}

function updateSessionStatus(status, text) {
    const store = Alpine.store('session');
    store.statusClass = status;
    store.statusText = text;
}

function updateStats(summary) {
    document.getElementById('stat-corrections').textContent =
        summary.total_corrections || 0;
    document.getElementById('stat-total-movement').textContent =
        (summary.total_movement_deg || 0).toFixed(2) + '°';
    document.getElementById('stat-cw').textContent =
        (summary.clockwise_movement_deg || 0).toFixed(2) + '°';
    document.getElementById('stat-ccw').textContent =
        (summary.counterclockwise_movement_deg || 0).toFixed(2) + '°';
    document.getElementById('stat-avg-correction').textContent =
        (summary.avg_correction_deg || 0).toFixed(2) + '°';
}

function updateModeDistribution(distribution) {
    const normal = distribution.normal || 0;
    const critical = distribution.critical || 0;
    const continuous = distribution.continuous || 0;
    const total = normal + critical + continuous;

    if (total === 0) {
        document.getElementById('mode-bar-normal').style.width = '0%';
        document.getElementById('mode-bar-critical').style.width = '0%';
        document.getElementById('mode-bar-continuous').style.width = '0%';
        document.getElementById('mode-time-normal').textContent = '0s';
        document.getElementById('mode-time-critical').textContent = '0s';
        document.getElementById('mode-time-continuous').textContent = '0s';
        return;
    }

    document.getElementById('mode-bar-normal').style.width = `${(normal / total) * 100}%`;
    document.getElementById('mode-bar-critical').style.width = `${(critical / total) * 100}%`;
    document.getElementById('mode-bar-continuous').style.width = `${(continuous / total) * 100}%`;

    document.getElementById('mode-time-normal').textContent = formatDuration(normal);
    document.getElementById('mode-time-critical').textContent = formatDuration(critical);
    document.getElementById('mode-time-continuous').textContent = formatDuration(continuous);
}

function updateLastUpdateTime() {
    const now = new Date();
    document.getElementById('last-update').textContent =
        `Derniere mise a jour: ${now.toLocaleTimeString('fr-FR')}`;
}

// =============================================================================
// GRAPHIQUES CHART.JS
// =============================================================================

function initCharts() {
    const altitudeCtx = document.getElementById('altitude-chart').getContext('2d');
    const azimutCtx = document.getElementById('azimut-chart').getContext('2d');

    const commonOptions = {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: {
            legend: {
                display: false
            }
        },
        scales: {
            x: {
                type: 'linear',
                title: {
                    display: true,
                    text: 'Temps (minutes)',
                    color: 'rgba(160, 144, 128, 1)'
                },
                ticks: { color: 'rgba(160, 144, 128, 1)' },
                grid: { color: 'rgba(74, 61, 46, 0.5)' }
            },
            y: {
                ticks: { color: 'rgba(160, 144, 128, 1)' },
                grid: { color: 'rgba(74, 61, 46, 0.5)' }
            }
        }
    };

    state.altitudeChart = new Chart(altitudeCtx, {
        type: 'line',
        data: {
            datasets: [{
                label: 'Altitude',
                data: [],
                borderWidth: 2,
                pointRadius: 0,
                tension: 0.1,
                segment: {
                    borderColor: ctx => getSegmentColor(ctx, 'altitude')
                }
            }, {
                // Dataset pour les points de correction
                label: 'Corrections',
                data: [],
                borderWidth: 0,
                pointRadius: CONFIG.CORRECTION_DOT_RADIUS,
                pointBackgroundColor: CONFIG.CORRECTION_DOT_COLOR,
                pointBorderColor: CONFIG.CORRECTION_DOT_COLOR,
                pointBorderWidth: 0,
                showLine: false
            }]
        },
        options: {
            ...commonOptions,
            scales: {
                ...commonOptions.scales,
                y: {
                    ...commonOptions.scales.y,
                    min: 0,
                    max: 90,
                    title: {
                        display: true,
                        text: 'Altitude (°)',
                        color: 'rgba(160, 144, 128, 1)'
                    }
                }
            }
        }
    });

    state.azimutChart = new Chart(azimutCtx, {
        type: 'line',
        data: {
            datasets: [{
                label: 'Position Coupole',
                data: [],
                borderWidth: 2,
                pointRadius: 0,
                tension: 0.1,
                segment: {
                    borderColor: ctx => getSegmentColor(ctx, 'azimut')
                }
            }, {
                // Dataset pour les points de correction
                label: 'Corrections',
                data: [],
                borderWidth: 0,
                pointRadius: CONFIG.CORRECTION_DOT_RADIUS,
                pointBackgroundColor: CONFIG.CORRECTION_DOT_COLOR,
                pointBorderColor: CONFIG.CORRECTION_DOT_COLOR,
                pointBorderWidth: 0,
                showLine: false
            }]
        },
        options: {
            ...commonOptions,
            scales: {
                ...commonOptions.scales,
                y: {
                    ...commonOptions.scales.y,
                    min: 0,
                    max: 360,
                    title: {
                        display: true,
                        text: 'Position Coupole (°)',
                        color: 'rgba(160, 144, 128, 1)'
                    }
                }
            }
        }
    });
}

function getSegmentColor(ctx, chartType) {
    // Récupérer le mode du point courant via les données raw
    const data = ctx.chart.data.datasets[0].data;
    const index = ctx.p0DataIndex;

    if (index >= 0 && index < data.length) {
        const point = data[index];
        if (point && point.mode) {
            return CONFIG.MODE_COLORS[point.mode.toLowerCase()] || CONFIG.MODE_COLORS.default;
        }
    }

    return CONFIG.MODE_COLORS.default;
}

function updateCharts(sessionData) {
    const positionLog = sessionData.position_log || [];
    const correctionsLog = sessionData.corrections_log || [];
    const startTime = sessionData.timing?.start_time ? new Date(sessionData.timing.start_time) : null;

    if (positionLog.length === 0) {
        // Pas de données position, utiliser les corrections comme fallback
        if (correctionsLog.length > 0 && startTime) {
            updateChartsFromCorrections(correctionsLog, startTime);
        }
        return;
    }

    // Convertir position_log en données de graphique
    const altitudeData = [];
    const domePositionData = [];

    positionLog.forEach(point => {
        const pointTime = new Date(point.timestamp);
        const minutesFromStart = startTime ? (pointTime - startTime) / 60000 : 0;

        altitudeData.push({
            x: minutesFromStart,
            y: point.altitude,
            mode: point.mode
        });

        domePositionData.push({
            x: minutesFromStart,
            y: point.dome_position,
            mode: point.mode
        });
    });

    // Points de correction
    const altitudeCorrectionPoints = [];
    const domePositionCorrectionPoints = [];

    correctionsLog.forEach(corr => {
        const corrTime = new Date(corr.timestamp);
        const minutesFromStart = startTime ? (corrTime - startTime) / 60000 : 0;

        altitudeCorrectionPoints.push({
            x: minutesFromStart,
            y: corr.altitude
        });

        // Utiliser dome_position si disponible, sinon approximer avec azimut
        domePositionCorrectionPoints.push({
            x: minutesFromStart,
            y: corr.dome_position ?? corr.azimut
        });
    });

    // Mettre à jour les charts
    state.altitudeChart.data.datasets[0].data = altitudeData;
    state.altitudeChart.data.datasets[1].data = altitudeCorrectionPoints;
    state.altitudeChart.update('none');

    state.azimutChart.data.datasets[0].data = domePositionData;
    state.azimutChart.data.datasets[1].data = domePositionCorrectionPoints;
    state.azimutChart.update('none');
}

function updateChartsFromCorrections(correctionsLog, startTime) {
    // Fallback: utiliser les corrections comme points de données
    // Note: quand on n'a pas position_log, on trace uniquement les points de correction
    const altitudeData = [];
    const domePositionData = [];

    correctionsLog.forEach(corr => {
        const corrTime = new Date(corr.timestamp);
        const minutesFromStart = (corrTime - startTime) / 60000;

        altitudeData.push({
            x: minutesFromStart,
            y: corr.altitude,
            mode: corr.mode
        });

        // Utiliser dome_position si disponible, sinon azimut comme fallback
        domePositionData.push({
            x: minutesFromStart,
            y: corr.dome_position ?? corr.azimut,
            mode: corr.mode
        });
    });

    // Dataset 0 = ligne (vide car pas de position_log), Dataset 1 = points de correction
    state.altitudeChart.data.datasets[0].data = altitudeData;  // Courbe = corrections
    state.altitudeChart.data.datasets[1].data = altitudeData;  // Points = corrections
    state.altitudeChart.update('none');

    state.azimutChart.data.datasets[0].data = domePositionData;  // Courbe = corrections
    state.azimutChart.data.datasets[1].data = domePositionData;  // Points = corrections
    state.azimutChart.update('none');
}

// =============================================================================
// TABLES
// =============================================================================

function updateCorrectionsTable(corrections) {
    const tbody = document.getElementById('corrections-tbody');

    if (corrections.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty">Aucune correction</td></tr>';
        return;
    }

    // Afficher les 50 dernières corrections (les plus récentes en premier)
    const recentCorrections = corrections.slice(-50).reverse();

    tbody.innerHTML = recentCorrections.map(corr => {
        const time = new Date(corr.timestamp).toLocaleTimeString('fr-FR');
        const modeClass = (corr.mode || 'normal').toLowerCase();

        return `
            <tr>
                <td>${time}</td>
                <td>${corr.azimut?.toFixed(1) || '--'}°</td>
                <td>${corr.altitude?.toFixed(1) || '--'}°</td>
                <td class="correction-value ${corr.correction > 0 ? 'positive' : 'negative'}">
                    ${corr.correction > 0 ? '+' : ''}${corr.correction?.toFixed(2) || '--'}°
                </td>
                <td><span class="mode-badge ${modeClass}">${corr.mode || '--'}</span></td>
            </tr>
        `;
    }).join('');
}

function updateGotoTable(gotoList) {
    const tbody = document.getElementById('goto-tbody');

    if (gotoList.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty">Aucun GOTO</td></tr>';
        return;
    }

    tbody.innerHTML = gotoList.map(goto => {
        const time = new Date(goto.timestamp).toLocaleTimeString('fr-FR');
        const reasonText = goto.reason === 'initial' ? 'GOTO Initial' : 'Grand deplacement';

        return `
            <tr>
                <td>${time}</td>
                <td>${goto.start_position?.toFixed(1) || '--'}°</td>
                <td>${goto.target_position?.toFixed(1) || '--'}°</td>
                <td class="correction-value ${goto.delta > 0 ? 'positive' : 'negative'}">
                    ${goto.delta > 0 ? '+' : ''}${goto.delta?.toFixed(1) || '--'}°
                </td>
                <td>${reasonText}</td>
            </tr>
        `;
    }).join('');
}

// =============================================================================
// HISTORIQUE
// =============================================================================

function displayHistory(sessions) {
    const container = document.getElementById('history-list');

    if (sessions.length === 0) {
        container.innerHTML = '<div class="empty">Aucune session sauvegardee</div>';
        return;
    }

    container.innerHTML = sessions.map(session => {
        const startDate = new Date(session.start_time);
        const dateStr = startDate.toLocaleDateString('fr-FR');
        const timeStr = startDate.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });

        return `
            <div class="history-item" data-session-id="${session.session_id}">
                <div class="flex items-center justify-between">
                    <span class="font-mono text-sm text-accent-amber font-medium">${session.object_name || '--'}</span>
                    <span class="flex items-center gap-2">
                        <button class="btn-delete text-obs-text-muted hover:text-accent-red transition-colors cursor-pointer text-sm" data-session-id="${session.session_id}" title="Supprimer">&#x1F5D1;</button>
                        <span class="text-xs text-obs-text-muted font-mono">${dateStr} ${timeStr}</span>
                    </span>
                </div>
                <div class="flex gap-3 mt-1 text-xs text-obs-text-secondary font-mono">
                    <span>Duree: ${formatDuration(session.duration_seconds || 0)}</span>
                    <span>Corrections: ${session.total_corrections || 0}</span>
                </div>
            </div>
        `;
    }).join('');

    // Ajouter les listeners pour sélection
    container.querySelectorAll('.history-item').forEach(item => {
        item.addEventListener('click', (e) => {
            // Ignorer si clic sur bouton delete
            if (e.target.classList.contains('btn-delete')) return;

            const sessionId = item.dataset.sessionId;
            loadHistorySession(sessionId);

            // Surligner l'élément sélectionné
            container.querySelectorAll('.history-item').forEach(i => i.classList.remove('selected'));
            item.classList.add('selected');
        });
    });

    // Ajouter les listeners pour suppression
    container.querySelectorAll('.btn-delete').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const sessionId = btn.dataset.sessionId;
            deleteSession(sessionId);
        });
    });
}

async function deleteSession(sessionId) {
    if (!confirm('Supprimer cette session ?')) {
        return;
    }

    try {
        const response = await fetch(`${CONFIG.API_BASE}/delete/${sessionId}/`, {
            method: 'DELETE'
        });

        if (response.ok) {
            // Recharger l'historique
            state.historyLoaded = false;
            loadHistory();
        } else {
            alert('Erreur lors de la suppression');
        }
    } catch (error) {
        console.error('Erreur suppression:', error);
        alert('Erreur de connexion');
    }
}

// =============================================================================
// UTILITAIRES
// =============================================================================

/**
 * Convertit une valeur décimale en format DMS (Degrés, Minutes, Secondes)
 * Ex: -1.59 → "-1°35'24''"
 * @param {number} decimal - Valeur en degrés décimaux
 * @param {number} precision - Nombre de décimales pour les secondes (défaut: 0)
 * @returns {string} Format DMS
 */
function formatDMS(decimal, precision = 0) {
    if (decimal === null || decimal === undefined || isNaN(decimal)) {
        return '--';
    }

    const sign = decimal < 0 ? '-' : '';
    const absVal = Math.abs(decimal);

    const degrees = Math.floor(absVal);
    const minFloat = (absVal - degrees) * 60;
    const minutes = Math.floor(minFloat);
    const seconds = (minFloat - minutes) * 60;

    const secStr = precision > 0 ? seconds.toFixed(precision) : Math.round(seconds).toString();

    return `${sign}${degrees}°${minutes}'${secStr}''`;
}

/**
 * Convertit une valeur en degrés vers le format horaire HMS (Heures, Minutes, Secondes)
 * Utilisé pour l'Ascension Droite (RA) : 1h = 15°
 * Ex: 45.0° → "3h00m00s"
 * @param {number} degrees - Valeur en degrés
 * @param {number} precision - Nombre de décimales pour les secondes (défaut: 0)
 * @returns {string} Format HMS
 */
function formatHMS(degrees, precision = 0) {
    if (degrees === null || degrees === undefined || isNaN(degrees)) {
        return '--';
    }

    const hours = degrees / 15;
    const absHours = Math.abs(hours);

    const h = Math.floor(absHours);
    const minFloat = (absHours - h) * 60;
    const m = Math.floor(minFloat);
    const s = (minFloat - m) * 60;

    const secStr = precision > 0 ? s.toFixed(precision) : Math.round(s).toString();

    return `${h}h${m.toString().padStart(2, '0')}m${secStr.padStart(2, '0')}s`;
}

function formatDuration(seconds) {
    if (seconds < 60) {
        return `${Math.floor(seconds)}s`;
    }

    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);

    if (hours > 0) {
        return `${hours}h ${minutes}m`;
    }

    return `${minutes}m ${secs}s`;
}
