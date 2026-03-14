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
    lastUpdate: null,
    trackingInfo: {}  // Pour position_cible, etc.
};

// Countdown timer (Correction 1)
let countdownValue = null;
let countdownInterval = null;
let lastRemainingFromApi = null;

// Logs tracking (Correction 3)
let displayedLogs = new Set();

// Timer widget (Correction 2)
let timerCtx = null;
let timerTotal = 60;  // Valeur par défaut, sera mise à jour selon le mode

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
    btnContCCW: document.getElementById('btn-cont-ccw'),
    btnContCW: document.getElementById('btn-cont-cw'),
    gotoAngle: document.getElementById('goto-angle'),
    btnGoto: document.getElementById('btn-goto'),

    // Nouveaux cartouches
    trackingModeIndicator: document.getElementById('tracking-mode-indicator'),
    correctionsCount: document.getElementById('corrections-count'),
    correctionsTotal: document.getElementById('corrections-total'),
    encItem: document.getElementById('enc-item'),

    // Logs
    logs: document.getElementById('logs'),
    lastUpdate: document.getElementById('last-update')
};

// État mouvement continu
let continuousMovement = null;

// Initialisation
document.addEventListener('DOMContentLoaded', () => {
    try {
        initElements();
        initEventListeners();
        initCompass();
        startPolling();
        log('Interface initialisée');
    } catch (e) {
        console.error('Erreur initialisation:', e);
    }
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

    // GOTO (optionnel - peut être supprimé du UI)
    if (elements.btnGoto) {
        elements.btnGoto.addEventListener('click', gotoPosition);
    }
    if (elements.gotoAngle) {
        elements.gotoAngle.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') gotoPosition();
        });
    }

    // Boutons mouvement continu (toggle)
    if (elements.btnContCCW) {
        elements.btnContCCW.addEventListener('click', () => toggleContinuous('ccw'));
    }
    if (elements.btnContCW) {
        elements.btnContCW.addEventListener('click', () => toggleContinuous('cw'));
    }

    // Boutons parking
    const btnPark = document.getElementById('btn-park');
    const btnCalibrate = document.getElementById('btn-calibrate');
    const btnEndSession = document.getElementById('btn-end-session');

    if (btnPark) btnPark.addEventListener('click', parkDome);
    if (btnCalibrate) btnCalibrate.addEventListener('click', calibrateDome);
    if (btnEndSession) btnEndSession.addEventListener('click', endSession);
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

        // Effet clignotement vert du bouton pendant 5 secondes
        flashButtonSuccess(elements.btnStartTracking, 5000);
    }
}

// Effet de clignotement vert sur un bouton
function flashButtonSuccess(button, duration = 5000) {
    if (!button) {
        console.warn('flashButtonSuccess: bouton non trouvé');
        return;
    }

    console.log('flashButtonSuccess: démarrage animation sur', button.id);
    button.classList.add('flash-success');

    setTimeout(() => {
        button.classList.remove('flash-success');
        console.log('flashButtonSuccess: fin animation');
    }, duration);
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
    // Arrêter aussi le mouvement continu
    stopContinuousMovement();
}

// Mouvement continu (toggle)
async function toggleContinuous(direction) {
    // Si même direction et déjà actif, arrêter
    if (continuousMovement === direction) {
        await stopContinuousMovement();
        return;
    }

    // Arrêter l'autre direction si active
    await stopContinuousMovement();

    // Démarrer le mouvement continu
    continuousMovement = direction;
    const btn = direction === 'ccw' ? elements.btnContCCW : elements.btnContCW;
    if (btn) btn.classList.add('active');

    log(`Mouvement continu ${direction.toUpperCase()} démarré`, 'info');
    await apiCall('/api/hardware/continuous/', 'POST', { direction });
}

async function stopContinuousMovement() {
    if (continuousMovement) {
        log(`Mouvement continu arrêté`, 'info');
        continuousMovement = null;
        // Envoyer commande STOP au backend
        await apiCall('/api/hardware/stop/', 'POST');
    }
    // Désactiver les boutons
    if (elements.btnContCCW) elements.btnContCCW.classList.remove('active');
    if (elements.btnContCW) elements.btnContCW.classList.remove('active');
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

    // Version (une seule fois)
    if (motor.version && !state.versionSet) {
        const verEl = document.getElementById('app-version');
        const footerEl = document.getElementById('footer-version');
        if (verEl) verEl.textContent = 'v' + motor.version;
        if (footerEl) footerEl.textContent = 'v' + motor.version;
        state.versionSet = true;
    }

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
    } else if (status === 'parking') {
        elements.statusDot.classList.add('moving');
        elements.statusText.textContent = '🅿️ Parking...';
    } else if (status === 'calibrating') {
        elements.statusDot.classList.add('moving');
        elements.statusText.textContent = '🔧 Calibration...';
    } else if (status === 'error') {
        elements.statusDot.classList.add('disconnected');
        elements.statusText.textContent = 'Erreur';
    } else {
        elements.statusText.textContent = 'Déconnecté';
    }

    // Mettre à jour l'état de l'encodeur et des boutons parking
    updateEncoderStatus(motor);
    updateParkingButtons(motor);
}

function updatePositionDisplay(encoder) {
    elements.domePosition.textContent = `${state.position.toFixed(2)}°`;
    elements.domeTarget.textContent = state.target ? `${state.target.toFixed(2)}°` : '--';

    // Cartouche ENC avec angle encodeur et état coloré
    const encItem = elements.encItem;
    if (encItem) {
        // Supprimer les classes d'état précédentes
        encItem.classList.remove('enc-absent', 'enc-uncalibrated', 'enc-calibrated');

        if (!encoder || encoder.error || encoder.status === 'absent') {
            // Gris = absent (daemon non disponible)
            encItem.classList.add('enc-absent');
            elements.encoderCalibrated.textContent = 'ABSENT';
        } else if (!encoder.calibrated) {
            // Marron = non calibré
            encItem.classList.add('enc-uncalibrated');
            elements.encoderCalibrated.textContent = `${(encoder.angle || 0).toFixed(2)}°`;
        } else {
            // Vert = calibré
            encItem.classList.add('enc-calibrated');
            elements.encoderCalibrated.textContent = `${(encoder.angle || 0).toFixed(2)}°`;
        }
    }
}

function updateTrackingDisplay(motor) {
    if (motor.status === 'tracking' && motor.tracking_object) {
        elements.trackingInfo.classList.remove('hidden');
        elements.btnStartTracking.disabled = true;
        elements.btnStopTracking.disabled = false;

        elements.trackingObject.textContent = motor.tracking_object;

        const info = motor.tracking_info || {};
        state.trackingInfo = info;  // Stocker pour drawCompass

        // Mettre à jour le cartouche TÉLESCOPE avec position_cible pendant le tracking
        if (info.position_cible !== undefined && info.position_cible !== null) {
            elements.domeTarget.textContent = `${info.position_cible.toFixed(2)}°`;
        }

        elements.trackingAz.textContent = info.azimut ? `${info.azimut.toFixed(2)}°` : '--';
        elements.trackingAlt.textContent = info.altitude ? `${info.altitude.toFixed(2)}°` : '--';

        const mode = motor.mode || 'normal';
        const modeEmoji = { normal: '🟢', critical: '🟠', continuous: '🔴', fast_track: '🟣' };
        elements.trackingMode.textContent = `${modeEmoji[mode] || ''} ${mode.toUpperCase()}`;
        elements.trackingMode.className = `mode-${mode}`;

        // Cartouche MODE avec couleur (dans la section position)
        if (elements.trackingModeIndicator) {
            elements.trackingModeIndicator.textContent = mode.toUpperCase();
            elements.trackingModeIndicator.className = `mode-value ${mode}`;
        }

        elements.trackingCorrections.textContent = info.total_corrections || '0';

        // Cartouche CORRECTIONS avec count après label + total calé à droite
        if (elements.correctionsCount) {
            elements.correctionsCount.textContent = info.total_corrections || '0';
        }
        if (elements.correctionsTotal) {
            const totalDeg = info.total_correction_degrees || 0;
            elements.correctionsTotal.textContent = `${Math.abs(totalDeg).toFixed(2)}°`;
        }

        // Correction 1: Countdown client-side
        // Utiliser l'intervalle fourni par le programme principal (via API)
        const newTimerTotal = info.interval_sec || 60;

        // Si l'intervalle change et countdownValue dépasse, le réduire
        if (newTimerTotal !== timerTotal && countdownValue !== null && countdownValue > newTimerTotal) {
            countdownValue = newTimerTotal;
        }
        timerTotal = newTimerTotal;

        // Réinitialiser le countdown quand l'API donne une nouvelle valeur
        const apiRemaining = info.remaining_seconds;
        if (apiRemaining !== undefined && apiRemaining !== lastRemainingFromApi) {
            lastRemainingFromApi = apiRemaining;
            // Clamper la valeur API au maximum de l'intervalle actuel
            countdownValue = Math.min(apiRemaining, timerTotal);
            startCountdown();
        }

        // Afficher la valeur du countdown (pas celle de l'API)
        if (countdownValue !== null) {
            elements.trackingRemaining.textContent = `${countdownValue}s`;
        } else {
            elements.trackingRemaining.textContent = apiRemaining ? `${apiRemaining}s` : '--';
        }

        // Correction 2: Mettre à jour le timer circulaire
        drawTimer();

        // Correction 3: Afficher les logs de suivi du Motor Service
        if (motor.tracking_logs && Array.isArray(motor.tracking_logs)) {
            motor.tracking_logs.forEach(logEntry => {
                if (logEntry.time && !displayedLogs.has(logEntry.time)) {
                    log(logEntry.message, logEntry.type || 'info');
                    displayedLogs.add(logEntry.time);
                }
            });
        }
    } else {
        elements.trackingInfo.classList.add('hidden');
        elements.btnStartTracking.disabled = !state.searchedObject;
        elements.btnStopTracking.disabled = true;

        // Arrêter le countdown quand pas de suivi
        stopCountdown();
        state.trackingInfo = {};

        // Cacher le timer widget
        const timerWidget = document.getElementById('timer-widget');
        if (timerWidget) timerWidget.classList.add('hidden');

        // Réinitialiser les cartouches MODE et CORRECTIONS
        if (elements.trackingModeIndicator) {
            elements.trackingModeIndicator.textContent = '--';
            elements.trackingModeIndicator.className = 'mode-value';
        }
        if (elements.correctionsCount) {
            elements.correctionsCount.textContent = '0';
        }
        if (elements.correctionsTotal) {
            elements.correctionsTotal.textContent = '0.00°';
        }
    }
}

// Correction 1: Démarrer le countdown local
function startCountdown() {
    if (countdownInterval) clearInterval(countdownInterval);

    countdownInterval = setInterval(() => {
        if (countdownValue !== null && countdownValue > 0) {
            countdownValue--;
            elements.trackingRemaining.textContent = `${countdownValue}s`;
            drawTimer();  // Mettre à jour le timer visuel
        } else if (countdownValue === 0) {
            // Correction 2: Réinitialiser pour permettre le redémarrage au prochain cycle
            lastRemainingFromApi = null;
            // Garder l'affichage "0s" en attendant la nouvelle valeur de l'API
            elements.trackingRemaining.textContent = '0s';
            drawTimer();
        }
    }, 1000);
}

function stopCountdown() {
    if (countdownInterval) {
        clearInterval(countdownInterval);
        countdownInterval = null;
    }
    countdownValue = null;
    lastRemainingFromApi = null;
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

    // Night vision optimized colors
    const colors = {
        background: '#0a0a0f',
        panel: '#12121a',
        border: '#2a2a35',
        red: '#c43c3c',
        redDim: '#8b2d2d',
        amber: '#d4873f',
        green: '#4caf6a',
        blue: '#4a7a9e',
        textDim: '#5a5855',
        textSecondary: '#8a8680'
    };

    // Clear
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Fond with subtle gradient effect
    const gradient = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius + 10);
    gradient.addColorStop(0, '#1a1a24');
    gradient.addColorStop(1, colors.background);
    ctx.fillStyle = gradient;
    ctx.beginPath();
    ctx.arc(cx, cy, radius + 10, 0, 2 * Math.PI);
    ctx.fill();

    // Outer glow ring
    ctx.strokeStyle = 'rgba(196, 60, 60, 0.15)';
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.arc(cx, cy, radius + 5, 0, 2 * Math.PI);
    ctx.stroke();

    // Cercle principal
    ctx.strokeStyle = colors.border;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, 2 * Math.PI);
    ctx.stroke();

    // =========================================================================
    // Arc representing dome slit (trappe)
    // =========================================================================
    const OPENING_ANGLE = 40.1;  // degrees (70cm / pi x 200cm x 360)
    const domeAngle = state.position;

    // Calculate opening limits
    const openingStart = domeAngle - OPENING_ANGLE / 2;
    const openingEnd = domeAngle + OPENING_ANGLE / 2;

    // Red arc = CLOSED portion (from openingEnd to openingStart, through opposite)
    ctx.strokeStyle = 'rgba(196, 60, 60, 0.25)';
    ctx.lineWidth = 12;
    ctx.beginPath();
    const closedStartRad = (openingEnd - 90) * Math.PI / 180;
    const closedEndRad = (openingStart - 90 + 360) * Math.PI / 180;
    ctx.arc(cx, cy, radius - 6, closedStartRad, closedEndRad);
    ctx.stroke();

    // Graduations with amber/red tones for night vision
    ctx.font = '12px Inter, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';

    for (let deg = 0; deg < 360; deg += 30) {
        const rad = (deg - 90) * Math.PI / 180;
        const x1 = cx + (radius - 15) * Math.cos(rad);
        const y1 = cy + (radius - 15) * Math.sin(rad);
        const x2 = cx + radius * Math.cos(rad);
        const y2 = cy + radius * Math.sin(rad);

        // Tick marks - amber for cardinal, dimmer for others
        ctx.strokeStyle = deg % 90 === 0 ? colors.amber : colors.textDim;
        ctx.lineWidth = deg % 90 === 0 ? 2 : 1;
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();

        // Cardinal labels
        if (deg % 90 === 0) {
            const labels = { 0: 'N', 90: 'E', 180: 'S', 270: 'O' };
            const lx = cx + (radius - 30) * Math.cos(rad);
            const ly = cy + (radius - 30) * Math.sin(rad);
            ctx.fillStyle = colors.amber;
            ctx.font = 'bold 13px Inter, sans-serif';
            ctx.fillText(labels[deg], lx, ly);
        }
    }

    // =========================================================================
    // Double indicator: TELESCOPE + DOME
    // =========================================================================

    // TELESCOPE needle (green) - target position that evolves continuously
    const telescopeAngle = state.trackingInfo?.position_cible;
    if (telescopeAngle !== undefined && telescopeAngle !== null) {
        const teleRad = (telescopeAngle - 90) * Math.PI / 180;

        // Telescope needle line with glow
        ctx.shadowColor = 'rgba(76, 175, 106, 0.5)';
        ctx.shadowBlur = 8;
        ctx.strokeStyle = colors.green;
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.lineTo(cx + (radius - 45) * Math.cos(teleRad), cy + (radius - 45) * Math.sin(teleRad));
        ctx.stroke();
        ctx.shadowBlur = 0;

        // Green triangular arrowhead
        drawArrowHead(ctx, cx, cy, teleRad, radius - 45, colors.green);
    }

    // DOME needle (blue) - current dome position
    const domeRad = (state.position - 90) * Math.PI / 180;

    // Dome needle line with glow
    ctx.shadowColor = 'rgba(74, 122, 158, 0.5)';
    ctx.shadowBlur = 8;
    ctx.strokeStyle = colors.blue;
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + (radius - 40) * Math.cos(domeRad), cy + (radius - 40) * Math.sin(domeRad));
    ctx.stroke();
    ctx.shadowBlur = 0;

    // Blue triangular arrowhead
    drawArrowHead(ctx, cx, cy, domeRad, radius - 40, colors.blue);

    // Center with telescope representation
    drawTelescope(ctx, cx, cy, telescopeAngle);
}

// Draw telescope at center (rectangular tube)
function drawTelescope(ctx, cx, cy, angle) {
    // If no tracking angle, use dome position
    const teleAngle = (angle !== undefined && angle !== null) ? angle : state.position;
    const teleRad = teleAngle * Math.PI / 180;

    // Tube dimensions
    const tubeLength = 65;
    const tubeWidth = 24;

    // Night vision colors
    const colors = {
        tubeFill: '#1e1e28',
        tubeStroke: '#3a3a48',
        aperture: '#2a2a35',
        mountOuter: '#1a1a24',
        mountInner: '#c43c3c',  // Red accent for night vision
        mountGlow: 'rgba(196, 60, 60, 0.3)'
    };

    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(teleRad);

    // Tube body (dark)
    ctx.fillStyle = colors.tubeFill;
    ctx.fillRect(-tubeWidth/2, -tubeLength, tubeWidth, tubeLength);

    // Tube border
    ctx.strokeStyle = colors.tubeStroke;
    ctx.lineWidth = 2;
    ctx.strokeRect(-tubeWidth/2, -tubeLength, tubeWidth, tubeLength);

    // Tube aperture (slightly lighter ellipse)
    ctx.fillStyle = colors.aperture;
    ctx.beginPath();
    ctx.ellipse(0, -tubeLength + 6, tubeWidth/2 - 3, 5, 0, 0, 2 * Math.PI);
    ctx.fill();

    // Mount (outer circle)
    ctx.fillStyle = colors.mountOuter;
    ctx.beginPath();
    ctx.arc(0, 0, 14, 0, 2 * Math.PI);
    ctx.fill();

    // Mount glow effect
    ctx.shadowColor = colors.mountGlow;
    ctx.shadowBlur = 10;

    // Mount (inner circle with red accent)
    ctx.fillStyle = colors.mountInner;
    ctx.beginPath();
    ctx.arc(0, 0, 7, 0, 2 * Math.PI);
    ctx.fill();

    ctx.shadowBlur = 0;
    ctx.restore();
}

// Dessiner une pointe de flèche triangulaire
function drawArrowHead(ctx, cx, cy, angleRad, length, color) {
    const tipX = cx + length * Math.cos(angleRad);
    const tipY = cy + length * Math.sin(angleRad);

    const arrowSize = 10;
    const arrowAngle = 0.4;

    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.moveTo(tipX, tipY);
    ctx.lineTo(
        tipX - arrowSize * Math.cos(angleRad - arrowAngle),
        tipY - arrowSize * Math.sin(angleRad - arrowAngle)
    );
    ctx.lineTo(
        tipX - arrowSize * Math.cos(angleRad + arrowAngle),
        tipY - arrowSize * Math.sin(angleRad + arrowAngle)
    );
    ctx.closePath();
    ctx.fill();
}

// Légende de la boussole
function drawCompassLegend(ctx, x, y) {
    ctx.font = '10px Arial';
    ctx.textAlign = 'center';

    // TÉLESCOPE en vert
    ctx.fillStyle = '#00d26a';
    ctx.fillText('● TÉLESCOPE', x - 45, y);

    // COUPOLE en bleu
    ctx.fillStyle = '#4da6ff';
    ctx.fillText('● COUPOLE', x + 45, y);
}

// =========================================================================
// Correction 2: Timer circulaire widget
// =========================================================================

function initTimer() {
    const timerCanvas = document.getElementById('timer-canvas');
    if (timerCanvas) {
        timerCtx = timerCanvas.getContext('2d');
    }
}

function drawTimer() {
    const timerCanvas = document.getElementById('timer-canvas');
    const timerWidget = document.getElementById('timer-widget');
    const timerSeconds = document.getElementById('timer-seconds');

    if (!timerCanvas || !timerWidget) return;

    // Initialize context if needed
    if (!timerCtx) {
        timerCtx = timerCanvas.getContext('2d');
    }

    // Show widget
    timerWidget.classList.remove('hidden');

    const ctx = timerCtx;
    const cx = timerCanvas.width / 2;
    const cy = timerCanvas.height / 2;
    const radius = Math.min(cx, cy) - 10;

    // Night vision optimized colors
    const colors = {
        background: '#12121a',
        track: '#2a2a35',
        green: '#4caf6a',
        amber: '#d4873f',
        red: '#c43c3c'
    };

    // Clear
    ctx.clearRect(0, 0, timerCanvas.width, timerCanvas.height);

    // Background circle with subtle gradient
    const gradient = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius);
    gradient.addColorStop(0, '#1a1a24');
    gradient.addColorStop(1, colors.background);
    ctx.fillStyle = gradient;
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, 2 * Math.PI);
    ctx.fill();

    // Track circle (background ring)
    ctx.strokeStyle = colors.track;
    ctx.lineWidth = 8;
    ctx.beginPath();
    ctx.arc(cx, cy, radius - 4, 0, 2 * Math.PI);
    ctx.stroke();

    // Calculate progress (clamped to 1.0 max)
    const remaining = countdownValue !== null ? countdownValue : 0;
    const progress = Math.min(remaining / timerTotal, 1.0);

    // Color based on progress - night vision friendly
    let color;
    if (progress > 0.5) {
        color = colors.green;
    } else if (progress > 0.25) {
        color = colors.amber;
    } else {
        color = colors.red;
    }

    // Progress arc (clockwise from top)
    if (progress > 0) {
        // Add glow effect
        ctx.shadowColor = color;
        ctx.shadowBlur = 10;

        ctx.strokeStyle = color;
        ctx.lineWidth = 8;
        ctx.lineCap = 'round';
        ctx.beginPath();
        const startAngle = -Math.PI / 2;
        const endAngle = startAngle + (2 * Math.PI * progress);
        ctx.arc(cx, cy, radius - 4, startAngle, endAngle);
        ctx.stroke();

        ctx.shadowBlur = 0;
    }

    // Update center text
    if (timerSeconds) {
        timerSeconds.textContent = remaining > 0 ? `${remaining}s` : '--';
        timerSeconds.style.color = color;
        timerSeconds.style.textShadow = `0 0 10px ${color}40`;
    }
}

// =========================================================================
// Mode Parking
// =========================================================================

/**
 * Parque la coupole à la position 44° (avant le switch).
 */
async function parkDome() {
    log('🅿️ Parking de la coupole...', 'info');
    const result = await apiCall('/api/hardware/park/', 'POST');

    if (result.error) {
        log(`Erreur parking: ${result.error}`, 'error');
    } else {
        log('🅿️ Parking en cours vers 44°...', 'info');
    }
}

/**
 * Calibre l'encodeur en passant par le switch (45°).
 */
async function calibrateDome() {
    log('🔧 Calibration de l\'encodeur...', 'info');
    const result = await apiCall('/api/hardware/calibrate/', 'POST');

    if (result.error) {
        log(`Erreur calibration: ${result.error}`, 'error');
    } else {
        log('🔧 Calibration en cours (passage par 45°)...', 'info');
    }
}

/**
 * Termine la session d'observation.
 * Arrête le suivi et parque la coupole.
 */
async function endSession() {
    // Confirmation
    if (!confirm('Terminer la session et parquer la coupole ?')) {
        return;
    }

    log('🌙 Fin de session demandée...', 'info');

    // Afficher l'overlay de fin de session
    showEndSessionOverlay();

    const result = await apiCall('/api/hardware/end-session/', 'POST');

    if (result.error) {
        log(`Erreur fin de session: ${result.error}`, 'error');
        hideEndSessionOverlay();
    } else {
        log('🌙 Parking en cours - Veuillez patienter...', 'info');
        // L'overlay sera masqué quand le status passera à 'idle'
    }
}

/**
 * Affiche l'overlay de fin de session pendant le parking.
 */
function showEndSessionOverlay() {
    let overlay = document.getElementById('end-session-overlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'end-session-overlay';
        overlay.innerHTML = `
            <div class="end-session-content">
                <div class="end-session-icon">🌙</div>
                <div class="end-session-title">Fin de session</div>
                <div class="end-session-message">Parking en cours...</div>
                <div class="end-session-spinner"></div>
            </div>
        `;
        document.body.appendChild(overlay);
    }
    overlay.classList.add('visible');
}

/**
 * Masque l'overlay de fin de session.
 */
function hideEndSessionOverlay() {
    const overlay = document.getElementById('end-session-overlay');
    if (overlay) {
        // Afficher le message de confirmation avant de masquer
        const message = overlay.querySelector('.end-session-message');
        const spinner = overlay.querySelector('.end-session-spinner');
        if (message) message.textContent = 'Session terminée - Vous pouvez éteindre';
        if (spinner) spinner.style.display = 'none';

        // Masquer après 3 secondes
        setTimeout(() => {
            overlay.classList.remove('visible');
        }, 3000);
    }
}

/**
 * Met à jour l'indicateur d'état de l'encodeur.
 */
function updateEncoderStatus(motor) {
    const encoderStatus = document.getElementById('encoder-status');
    if (!encoderStatus) return;

    const isCalibrated = motor.encoder_calibrated || false;

    if (isCalibrated) {
        encoderStatus.textContent = '✓ Calibré';
        encoderStatus.className = 'encoder-calibrated';
    } else {
        encoderStatus.textContent = '⚠ Non calibré';
        encoderStatus.className = 'encoder-uncalibrated';
    }
}

/**
 * Met à jour l'état des boutons parking selon le status.
 */
function updateParkingButtons(motor) {
    const btnPark = document.getElementById('btn-park');
    const btnCalibrate = document.getElementById('btn-calibrate');
    const btnEndSession = document.getElementById('btn-end-session');

    const status = motor.status || 'unknown';
    const isMoving = ['parking', 'calibrating', 'moving', 'tracking'].includes(status);

    if (btnPark) {
        btnPark.disabled = isMoving;
        btnPark.classList.toggle('active', status === 'parking');
    }

    if (btnCalibrate) {
        btnCalibrate.disabled = isMoving;
        btnCalibrate.classList.toggle('active', status === 'calibrating');
    }

    if (btnEndSession) {
        btnEndSession.disabled = isMoving && status !== 'parking';
    }

    // Masquer l'overlay de fin de session quand le parking est terminé
    if (status === 'idle') {
        const overlay = document.getElementById('end-session-overlay');
        if (overlay && overlay.classList.contains('visible')) {
            hideEndSessionOverlay();
        }
    }
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
