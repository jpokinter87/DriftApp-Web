/**
 * DriftApp Web - Dashboard JavaScript
 *
 * Gère l'interface utilisateur et la communication avec l'API REST.
 */

// Configuration
const API_BASE = '';
const POLL_INTERVAL = 1000; // 1 seconde

// État de l'application
let state = {
    position: 0,
    target: null,
    status: 'unknown',
    trackingObject: null,
    searchedObject: null,
    lastUpdate: null
};

// Éléments DOM
const elements = {
    // Status
    serviceStatus: document.getElementById('service-status'),
    statusDot: null,
    statusText: null,

    // Boussole
    compass: document.getElementById('compass'),
    domePosition: document.getElementById('dome-position'),
    domeTarget: document.getElementById('dome-target'),
    encoderCalibrated: document.getElementById('encoder-calibrated'),

    // Tracking
    objectName: document.getElementById('object-name'),
    btnSearch: document.getElementById('btn-search'),
    objectInfo: document.getElementById('object-info'),
    objectCoords: document.getElementById('object-coords'),
    btnStartTracking: document.getElementById('btn-start-tracking'),
    btnStopTracking: document.getElementById('btn-stop-tracking'),

    // Tracking info
    trackingInfo: document.getElementById('tracking-info'),
    trackingObject: document.getElementById('tracking-object'),
    trackingAz: document.getElementById('tracking-az'),
    trackingAlt: document.getElementById('tracking-alt'),
    trackingMode: document.getElementById('tracking-mode'),
    trackingCorrections: document.getElementById('tracking-corrections'),
    trackingRemaining: document.getElementById('tracking-remaining'),

    // Contrôle manuel
    btnJogCCW10: document.getElementById('btn-jog-ccw-10'),
    btnJogCCW1: document.getElementById('btn-jog-ccw-1'),
    btnStop: document.getElementById('btn-stop'),
    btnJogCW1: document.getElementById('btn-jog-cw-1'),
    btnJogCW10: document.getElementById('btn-jog-cw-10'),
    gotoAngle: document.getElementById('goto-angle'),
    btnGoto: document.getElementById('btn-goto'),

    // Logs
    logs: document.getElementById('logs'),
    lastUpdate: document.getElementById('last-update')
};

// Initialisation
document.addEventListener('DOMContentLoaded', () => {
    initElements();
    initEventListeners();
    initCompass();
    startPolling();
    log('Interface initialisée');
});

function initElements() {
    elements.statusDot = elements.serviceStatus.querySelector('.status-dot');
    elements.statusText = elements.serviceStatus.querySelector('.status-text');
}

function initEventListeners() {
    // Recherche objet
    elements.btnSearch.addEventListener('click', searchObject);
    elements.objectName.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') searchObject();
    });

    // Suivi
    elements.btnStartTracking.addEventListener('click', startTracking);
    elements.btnStopTracking.addEventListener('click', stopTracking);

    // Contrôle manuel
    elements.btnJogCCW10.addEventListener('click', () => jog(-10));
    elements.btnJogCCW1.addEventListener('click', () => jog(-1));
    elements.btnStop.addEventListener('click', stopMotor);
    elements.btnJogCW1.addEventListener('click', () => jog(1));
    elements.btnJogCW10.addEventListener('click', () => jog(10));
    elements.btnGoto.addEventListener('click', gotoPosition);
    elements.gotoAngle.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') gotoPosition();
    });
}

// =========================================================================
// API Calls
// =========================================================================

async function apiCall(endpoint, method = 'GET', data = null) {
    const options = {
        method,
        headers: {
            'Content-Type': 'application/json',
        }
    };

    if (data) {
        options.body = JSON.stringify(data);
    }

    try {
        const response = await fetch(`${API_BASE}${endpoint}`, options);
        return await response.json();
    } catch (error) {
        console.error(`API Error: ${endpoint}`, error);
        return { error: error.message };
    }
}

async function fetchStatus() {
    const [motorStatus, encoderStatus] = await Promise.all([
        apiCall('/api/hardware/status/'),
        apiCall('/api/hardware/encoder/')
    ]);

    return { motor: motorStatus, encoder: encoderStatus };
}

// =========================================================================
// Actions
// =========================================================================

async function searchObject() {
    const name = elements.objectName.value.trim();
    if (!name) {
        log('Entrez un nom d\'objet', 'warning');
        return;
    }

    log(`Recherche de ${name}...`);
    const result = await apiCall(`/api/tracking/search/?q=${encodeURIComponent(name)}`);

    if (result.error) {
        log(`Objet "${name}" introuvable`, 'error');
        elements.objectInfo.classList.add('hidden');
        elements.btnStartTracking.disabled = true;
        state.searchedObject = null;
    } else {
        const ra = result.ra_deg?.toFixed(2) || result.coord?.ra_h || '--';
        const dec = result.dec_deg?.toFixed(2) || result.coord?.dec_d || '--';
        elements.objectCoords.textContent = `RA: ${ra}° | DEC: ${dec}°`;
        elements.objectInfo.classList.remove('hidden');
        elements.btnStartTracking.disabled = false;
        state.searchedObject = result.nom || name;
        log(`Trouvé: ${state.searchedObject}`, 'success');
    }
}

async function startTracking() {
    const name = state.searchedObject || elements.objectName.value.trim();
    if (!name) {
        log('Aucun objet sélectionné', 'warning');
        return;
    }

    log(`Démarrage du suivi de ${name}...`);
    const result = await apiCall('/api/tracking/start/', 'POST', { object: name });

    if (result.error) {
        log(`Erreur: ${result.error}`, 'error');
    } else {
        log(`Suivi de ${name} démarré`, 'success');
        elements.btnStartTracking.disabled = true;
        elements.btnStopTracking.disabled = false;
    }
}

async function stopTracking() {
    log('Arrêt du suivi...');
    const result = await apiCall('/api/tracking/stop/', 'POST');

    if (result.error) {
        log(`Erreur: ${result.error}`, 'error');
    } else {
        log('Suivi arrêté', 'success');
        elements.btnStartTracking.disabled = false;
        elements.btnStopTracking.disabled = true;
        elements.trackingInfo.classList.add('hidden');
    }
}

async function jog(delta) {
    log(`Rotation ${delta > 0 ? '+' : ''}${delta}°...`);
    const result = await apiCall('/api/hardware/jog/', 'POST', { delta });

    if (result.error) {
        log(`Erreur: ${result.error}`, 'error');
    }
}

async function stopMotor() {
    log('STOP!', 'warning');
    await apiCall('/api/hardware/stop/', 'POST');
}

async function gotoPosition() {
    const angle = parseFloat(elements.gotoAngle.value);
    if (isNaN(angle) || angle < 0 || angle > 360) {
        log('Angle invalide (0-360)', 'warning');
        return;
    }

    log(`GOTO ${angle}°...`);
    const result = await apiCall('/api/hardware/goto/', 'POST', { angle });

    if (result.error) {
        log(`Erreur: ${result.error}`, 'error');
    }
}

// =========================================================================
// Polling & Updates
// =========================================================================

function startPolling() {
    updateStatus();
    setInterval(updateStatus, POLL_INTERVAL);
}

async function updateStatus() {
    const { motor, encoder } = await fetchStatus();

    // Mettre à jour l'état
    state.status = motor.status || 'unknown';
    state.position = encoder.angle || motor.position || 0;
    state.target = motor.target;
    state.trackingObject = motor.tracking_object;
    state.lastUpdate = new Date();

    // Mettre à jour l'interface
    updateServiceStatus(motor, encoder);
    updatePositionDisplay(encoder);
    updateTrackingDisplay(motor);
    drawCompass();

    elements.lastUpdate.textContent = `Dernière mise à jour: ${state.lastUpdate.toLocaleTimeString()}`;
}

function updateServiceStatus(motor, encoder) {
    const status = motor.status || 'unknown';

    // Icône de statut
    elements.statusDot.className = 'status-dot';
    if (status === 'idle' || status === 'tracking') {
        elements.statusDot.classList.add('connected');
        elements.statusText.textContent = status === 'tracking' ? 'Suivi actif' : 'Connecté';
    } else if (status === 'moving') {
        elements.statusDot.classList.add('moving');
        elements.statusText.textContent = 'En mouvement';
    } else if (status === 'error') {
        elements.statusDot.classList.add('disconnected');
        elements.statusText.textContent = 'Erreur';
    } else {
        elements.statusText.textContent = 'Déconnecté';
    }
}

function updatePositionDisplay(encoder) {
    elements.domePosition.textContent = `${state.position.toFixed(1)}°`;
    elements.domeTarget.textContent = state.target ? `${state.target.toFixed(1)}°` : '--';
    elements.encoderCalibrated.textContent = encoder.calibrated ? 'Oui' : 'Non';
    elements.encoderCalibrated.style.color = encoder.calibrated ? 'var(--accent-green)' : 'var(--accent-orange)';
}

function updateTrackingDisplay(motor) {
    if (motor.status === 'tracking' && motor.tracking_object) {
        elements.trackingInfo.classList.remove('hidden');
        elements.btnStartTracking.disabled = true;
        elements.btnStopTracking.disabled = false;

        elements.trackingObject.textContent = motor.tracking_object;

        const info = motor.tracking_info || {};
        elements.trackingAz.textContent = info.azimut ? `${info.azimut.toFixed(1)}°` : '--';
        elements.trackingAlt.textContent = info.altitude ? `${info.altitude.toFixed(1)}°` : '--';

        const mode = motor.mode || 'normal';
        const modeEmoji = { normal: '🟢', critical: '🟠', continuous: '🔴', fast_track: '🟣' };
        elements.trackingMode.textContent = `${modeEmoji[mode] || ''} ${mode.toUpperCase()}`;
        elements.trackingMode.className = `mode-${mode}`;

        elements.trackingCorrections.textContent = info.total_corrections || '0';
        elements.trackingRemaining.textContent = info.remaining_seconds ? `${info.remaining_seconds}s` : '--';
    } else {
        elements.trackingInfo.classList.add('hidden');
        elements.btnStartTracking.disabled = !state.searchedObject;
        elements.btnStopTracking.disabled = true;
    }
}

// =========================================================================
// Compass Drawing
// =========================================================================

let compassCtx = null;

function initCompass() {
    compassCtx = elements.compass.getContext('2d');
    drawCompass();
}

function drawCompass() {
    if (!compassCtx) return;

    const canvas = elements.compass;
    const ctx = compassCtx;
    const cx = canvas.width / 2;
    const cy = canvas.height / 2;
    const radius = Math.min(cx, cy) - 20;

    // Clear
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Fond
    ctx.fillStyle = '#1a1a2e';
    ctx.beginPath();
    ctx.arc(cx, cy, radius + 10, 0, 2 * Math.PI);
    ctx.fill();

    // Cercle principal
    ctx.strokeStyle = '#2d4059';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, 2 * Math.PI);
    ctx.stroke();

    // Graduations
    ctx.fillStyle = '#a0a0a0';
    ctx.font = '12px Arial';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';

    for (let deg = 0; deg < 360; deg += 30) {
        const rad = (deg - 90) * Math.PI / 180;
        const x1 = cx + (radius - 10) * Math.cos(rad);
        const y1 = cy + (radius - 10) * Math.sin(rad);
        const x2 = cx + radius * Math.cos(rad);
        const y2 = cy + radius * Math.sin(rad);

        ctx.strokeStyle = '#4da6ff';
        ctx.lineWidth = deg % 90 === 0 ? 2 : 1;
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();

        // Labels cardinaux
        if (deg % 90 === 0) {
            const labels = { 0: 'N', 90: 'E', 180: 'S', 270: 'O' };
            const lx = cx + (radius - 25) * Math.cos(rad);
            const ly = cy + (radius - 25) * Math.sin(rad);
            ctx.fillStyle = '#4da6ff';
            ctx.fillText(labels[deg], lx, ly);
        }
    }

    // Cible (si définie)
    if (state.target !== null) {
        const targetRad = (state.target - 90) * Math.PI / 180;
        ctx.strokeStyle = '#ffa502';
        ctx.lineWidth = 2;
        ctx.setLineDash([5, 5]);
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.lineTo(cx + (radius - 30) * Math.cos(targetRad), cy + (radius - 30) * Math.sin(targetRad));
        ctx.stroke();
        ctx.setLineDash([]);
    }

    // Aiguille de position
    const posRad = (state.position - 90) * Math.PI / 180;

    // Pointe
    ctx.fillStyle = '#ff4757';
    ctx.beginPath();
    ctx.moveTo(cx + (radius - 30) * Math.cos(posRad), cy + (radius - 30) * Math.sin(posRad));
    ctx.lineTo(cx + 15 * Math.cos(posRad + 2.8), cy + 15 * Math.sin(posRad + 2.8));
    ctx.lineTo(cx + 15 * Math.cos(posRad - 2.8), cy + 15 * Math.sin(posRad - 2.8));
    ctx.closePath();
    ctx.fill();

    // Ligne de l'aiguille
    ctx.strokeStyle = '#ff4757';
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + (radius - 30) * Math.cos(posRad), cy + (radius - 30) * Math.sin(posRad));
    ctx.stroke();

    // Centre
    ctx.fillStyle = '#ff4757';
    ctx.beginPath();
    ctx.arc(cx, cy, 8, 0, 2 * Math.PI);
    ctx.fill();

    // Affichage angle au centre
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 16px Arial';
    ctx.fillText(`${state.position.toFixed(1)}°`, cx, cy + 40);
}

// =========================================================================
// Logging
// =========================================================================

function log(message, type = 'info') {
    const entry = document.createElement('div');
    entry.className = `log-entry ${type}`;
    entry.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;

    elements.logs.insertBefore(entry, elements.logs.firstChild);

    // Limiter à 50 entrées
    while (elements.logs.children.length > 50) {
        elements.logs.removeChild(elements.logs.lastChild);
    }
}
