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
    trackingInfo: {},  // Pour position_cible, etc.
    gotoInfo: null     // Pour la modal GOTO
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

// GOTO Modal state
let gotoModalVisible = false;
let gotoStartPosition = null;
let gotoStartTime = null;  // Timestamp du début du GOTO pour calcul position estimée

// Vitesse CONTINUOUS en degrés/seconde (41°/min selon config.json)
const CONTINUOUS_SPEED_DEG_PER_SEC = 41.0 / 60;  // ~0.683°/s

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
    lastUpdate: document.getElementById('last-update'),

    // GOTO Modal
    gotoModal: document.getElementById('goto-modal'),
    gotoModalObjectName: document.getElementById('goto-modal-object-name'),
    gotoModalStart: document.getElementById('goto-modal-start'),
    gotoModalTarget: document.getElementById('goto-modal-target'),
    gotoModalCurrentPos: document.getElementById('goto-modal-current-pos'),
    gotoChevrons: document.getElementById('goto-chevrons'),
    gotoProgressFill: document.getElementById('goto-progress-fill'),
    gotoProgressText: document.getElementById('goto-progress-text'),
    gotoModalDelta: document.getElementById('goto-modal-delta')
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
    elements.btnGoto.addEventListener('click', gotoPosition);
    elements.gotoAngle.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') gotoPosition();
    });

    // Boutons mouvement continu (toggle)
    if (elements.btnContCCW) {
        elements.btnContCCW.addEventListener('click', () => toggleContinuous('ccw'));
    }
    if (elements.btnContCW) {
        elements.btnContCW.addEventListener('click', () => toggleContinuous('cw'));
    }
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
        
        // Fermer la modal GOTO si ouverte
        hideGotoModal();
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
    // Fermer la modal GOTO si ouverte
    hideGotoModal();
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
// GOTO Modal Management
// =========================================================================

function showGotoModal(objectName, startPos, targetPos, currentPos, delta) {
    if (!elements.gotoModal) return;

    // Mémoriser la position de départ et le timestamp pour le calcul de position estimée
    gotoStartPosition = startPos;
    gotoStartTime = Date.now();

    // Mettre à jour le contenu
    if (elements.gotoModalObjectName) {
        elements.gotoModalObjectName.textContent = objectName || '--';
    }
    if (elements.gotoModalStart) {
        elements.gotoModalStart.textContent = `${startPos.toFixed(1)}°`;
    }
    if (elements.gotoModalTarget) {
        elements.gotoModalTarget.textContent = `${targetPos.toFixed(1)}°`;
    }
    if (elements.gotoModalDelta) {
        const deltaStr = delta >= 0 ? `+${delta.toFixed(1)}°` : `${delta.toFixed(1)}°`;
        elements.gotoModalDelta.textContent = deltaStr;
    }

    // Configurer la direction des chevrons
    updateGotoChevrons(delta);

    // Mettre à jour la position actuelle
    updateGotoModalPosition(currentPos, startPos, targetPos);

    // Afficher la modal
    elements.gotoModal.classList.remove('hidden');
    gotoModalVisible = true;
}

function hideGotoModal() {
    if (!elements.gotoModal) return;

    elements.gotoModal.classList.add('hidden');
    gotoModalVisible = false;
    gotoStartPosition = null;
    gotoStartTime = null;
}

function updateGotoChevrons(delta) {
    if (!elements.gotoChevrons) return;

    // Supprimer les classes de direction précédentes
    elements.gotoChevrons.classList.remove('direction-cw', 'direction-ccw');

    // Mettre à jour le contenu des chevrons selon la direction
    if (delta >= 0) {
        // Sens horaire (CW) : ›››
        elements.gotoChevrons.innerHTML = '<span class="chevron">›</span><span class="chevron">›</span><span class="chevron">›</span>';
        elements.gotoChevrons.classList.add('direction-cw');
    } else {
        // Sens anti-horaire (CCW) : ‹‹‹
        elements.gotoChevrons.innerHTML = '<span class="chevron">‹</span><span class="chevron">‹</span><span class="chevron">‹</span>';
        elements.gotoChevrons.classList.add('direction-ccw');
    }
}

function updateGotoModalPosition(currentPos, startPos, targetPos) {
    if (!elements.gotoModalCurrentPos) return;

    // Mettre à jour la position actuelle
    elements.gotoModalCurrentPos.textContent = `${currentPos.toFixed(1)}°`;

    // Calculer la direction du mouvement (delta signé)
    let delta = targetPos - startPos;
    
    // Gérer le cas où on traverse 0°/360° (prendre le chemin le plus court)
    if (delta > 180) {
        delta -= 360;
    } else if (delta < -180) {
        delta += 360;
    }
    
    const totalDistance = Math.abs(delta);
    let traveled;
    
    if (delta >= 0) {
        // Sens horaire : currentPos augmente de startPos vers targetPos
        traveled = currentPos - startPos;
        // Gérer le wrap si on traverse 0°
        if (traveled < 0) traveled += 360;
        // Ne pas dépasser la distance totale
        if (traveled > totalDistance) traveled = totalDistance;
    } else {
        // Sens anti-horaire : currentPos diminue de startPos vers targetPos
        traveled = startPos - currentPos;
        // Gérer le wrap si on traverse 0°
        if (traveled < 0) traveled += 360;
        // Ne pas dépasser la distance totale
        if (traveled > totalDistance) traveled = totalDistance;
    }

    // Calculer le pourcentage (plafonné à 100%)
    const progress = Math.min(100, (traveled / totalDistance) * 100);

    if (elements.gotoProgressFill) {
        elements.gotoProgressFill.style.width = `${progress}%`;
    }
    if (elements.gotoProgressText) {
        elements.gotoProgressText.textContent = `${Math.round(progress)}%`;
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
    state.gotoInfo = motor.goto_info || null;

    // Mettre à jour l'interface
    updateServiceStatus(motor, encoder);
    updatePositionDisplay(encoder);
    updateTrackingDisplay(motor);
    updateGotoModal(motor, encoder);
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
    } else if (status === 'initializing') {
        // Nouveau statut : GOTO initial en cours avant le tracking
        elements.statusDot.classList.add('moving');
        elements.statusText.textContent = 'GOTO initial...';
    } else if (status === 'error') {
        elements.statusDot.classList.add('disconnected');
        elements.statusText.textContent = 'Erreur';
    } else {
        elements.statusText.textContent = 'Déconnecté';
    }
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

// Mise à jour de la modal GOTO
// IMPORTANT: Utilise une position CALCULÉE à partir de la vitesse CONTINUOUS
// pour éviter toute lecture d'encodeur qui pourrait causer des micro-coupures moteur
function updateGotoModal(motor, encoder) {
    const isInitializing = motor.status === 'initializing' && motor.tracking_object;
    const gotoInfo = motor.goto_info;

    if (isInitializing && gotoInfo) {
        if (!gotoModalVisible) {
            // Première ouverture de la modal
            showGotoModal(
                motor.tracking_object,
                gotoInfo.current_position,  // Position au moment du démarrage
                gotoInfo.target_position,
                gotoInfo.current_position,  // Position initiale = position de départ
                gotoInfo.delta
            );
        } else {
            // Calculer la position ESTIMÉE à partir du temps écoulé et de la vitesse CONTINUOUS
            // Cela évite de lire l'encodeur pendant le GOTO (pas de micro-coupures)
            const estimatedPos = calculateEstimatedPosition(
                gotoStartPosition || gotoInfo.current_position,
                gotoInfo.delta,
                gotoStartTime
            );

            // Mise à jour en temps réel avec la position calculée
            updateGotoModalPosition(
                estimatedPos,
                gotoStartPosition || gotoInfo.current_position,
                gotoInfo.target_position
            );
            // Mettre à jour aussi l'affichage de la position
            if (elements.gotoModalCurrentPos) {
                elements.gotoModalCurrentPos.textContent = `${estimatedPos.toFixed(1)}°`;
            }
        }
    } else if (gotoModalVisible) {
        // Le GOTO est terminé, fermer la modal
        hideGotoModal();
    }
}

// Calcule la position estimée basée sur la vitesse CONTINUOUS (~41°/min)
// Aucune lecture d'encodeur - calcul purement basé sur le temps écoulé
function calculateEstimatedPosition(startPos, delta, startTime) {
    if (!startTime) return startPos;

    const elapsedSeconds = (Date.now() - startTime) / 1000;
    const distanceTraveled = CONTINUOUS_SPEED_DEG_PER_SEC * elapsedSeconds;

    // Ne pas dépasser la distance totale du GOTO
    const totalDistance = Math.abs(delta);
    const clampedDistance = Math.min(distanceTraveled, totalDistance);

    // Calculer la position estimée en tenant compte de la direction
    const direction = delta >= 0 ? 1 : -1;
    let estimatedPos = startPos + (direction * clampedDistance);

    // Normaliser entre 0 et 360
    estimatedPos = ((estimatedPos % 360) + 360) % 360;

    return estimatedPos;
}

function updateTrackingDisplay(motor) {
    // Afficher le panneau pendant l'initialisation (GOTO initial) OU pendant le tracking actif
    const isInitializing = motor.status === 'initializing' && motor.tracking_object;
    const isTracking = motor.status === 'tracking' && motor.tracking_object;

    if (isInitializing || isTracking) {
        elements.trackingInfo.classList.remove('hidden');
        elements.btnStartTracking.disabled = true;
        elements.btnStopTracking.disabled = false;

        // Afficher le nom de l'objet (simplifié - la modal gère les détails du GOTO)
        if (isInitializing) {
            elements.trackingObject.textContent = `${motor.tracking_object} (GOTO...)`;
        } else {
            elements.trackingObject.textContent = motor.tracking_object;
        }

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
    const canvas = elements.compass;
    if (canvas) {
        compassCtx = canvas.getContext('2d');
        drawCompass();
    }
}

function drawCompass() {
    const canvas = elements.compass;
    if (!canvas || !compassCtx) return;

    const ctx = compassCtx;
    const width = canvas.width;
    const height = canvas.height;
    const cx = width / 2;
    const cy = height / 2;
    const radius = Math.min(cx, cy) - 20;

    // Clear
    ctx.clearRect(0, 0, width, height);

    // Fond de la boussole
    ctx.fillStyle = '#1a1a2e';
    ctx.beginPath();
    ctx.arc(cx, cy, radius + 5, 0, 2 * Math.PI);
    ctx.fill();

    // Cercle extérieur
    ctx.strokeStyle = '#2d4059';
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, 2 * Math.PI);
    ctx.stroke();

    // =========================================================================
    // Arc représentant la trappe de la coupole (liseré rouge avec ouverture)
    // =========================================================================
    const OPENING_ANGLE = 40.1;  // degrés (70cm / pi x 200cm x 360)
    const domeAngle = state.position;

    // Calculer les limites de l'ouverture
    const openingStart = domeAngle - OPENING_ANGLE / 2;
    const openingEnd = domeAngle + OPENING_ANGLE / 2;

    // Arc rouge = partie FERMÉE (de openingEnd à openingStart, en passant par l'opposé)
    ctx.strokeStyle = 'rgba(196, 60, 60, 0.25)';
    ctx.lineWidth = 12;
    ctx.beginPath();
    const closedStartRad = (openingEnd - 90) * Math.PI / 180;
    const closedEndRad = (openingStart - 90 + 360) * Math.PI / 180;
    ctx.arc(cx, cy, radius - 6, closedStartRad, closedEndRad);
    ctx.stroke();

    // Graduations
    ctx.fillStyle = '#a0a0a0';
    ctx.font = '12px Arial';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';

    for (let deg = 0; deg < 360; deg += 30) {
        const rad = (deg - 90) * Math.PI / 180;
        const x1 = cx + (radius - 15) * Math.cos(rad);
        const y1 = cy + (radius - 15) * Math.sin(rad);
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
            const lx = cx + (radius - 30) * Math.cos(rad);
            const ly = cy + (radius - 30) * Math.sin(rad);
            ctx.fillStyle = '#4da6ff';
            ctx.fillText(labels[deg], lx, ly);
        }
    }

    // =========================================================================
    // Correction 4: Double indicateur TÉLESCOPE + COUPOLE
    // =========================================================================

    // Aiguille TÉLESCOPE (verte) - position cible qui évolue en continu
    const telescopeAngle = state.trackingInfo?.position_cible;
    if (telescopeAngle !== undefined && telescopeAngle !== null) {
        const teleRad = (telescopeAngle - 90) * Math.PI / 180;

        // Ligne de l'aiguille TÉLESCOPE
        ctx.strokeStyle = '#00d26a';
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.lineTo(cx + (radius - 45) * Math.cos(teleRad), cy + (radius - 45) * Math.sin(teleRad));
        ctx.stroke();

        // Pointe triangulaire verte
        drawArrowHead(ctx, cx, cy, teleRad, radius - 45, '#00d26a');
    }

    // Aiguille COUPOLE (bleue) - position actuelle de la coupole
    const domeRad = (state.position - 90) * Math.PI / 180;

    // Ligne de l'aiguille COUPOLE
    ctx.strokeStyle = '#4da6ff';
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + (radius - 40) * Math.cos(domeRad), cy + (radius - 40) * Math.sin(domeRad));
    ctx.stroke();

    // Pointe triangulaire bleue
    drawArrowHead(ctx, cx, cy, domeRad, radius - 40, '#4da6ff');

    // Centre avec représentation du télescope (rectangle comme GUI Kivy)
    drawTelescope(ctx, cx, cy, telescopeAngle);
}

// Dessiner le télescope au centre (tube rectangulaire)
function drawTelescope(ctx, cx, cy, angle) {
    // Si pas d'angle de tracking, utiliser la position coupole
    const teleAngle = (angle !== undefined && angle !== null) ? angle : state.position;
    // Le tube est dessiné vers le haut en coordonnées locales, donc PAS besoin de -90°
    // (contrairement aux aiguilles qui sont dessinées vers la droite)
    const teleRad = teleAngle * Math.PI / 180;

    // Dimensions du tube (agrandi)
    const tubeLength = 65;
    const tubeWidth = 24;

    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(teleRad);

    // Corps du tube (gris foncé)
    ctx.fillStyle = '#3d3d5c';
    ctx.fillRect(-tubeWidth/2, -tubeLength, tubeWidth, tubeLength);

    // Bordure du tube
    ctx.strokeStyle = '#5a5a7a';
    ctx.lineWidth = 2;
    ctx.strokeRect(-tubeWidth/2, -tubeLength, tubeWidth, tubeLength);

    // Ouverture du tube (cercle plus clair)
    ctx.fillStyle = '#4a4a6a';
    ctx.beginPath();
    ctx.ellipse(0, -tubeLength + 6, tubeWidth/2 - 3, 5, 0, 0, 2 * Math.PI);
    ctx.fill();

    // Monture (cercle au centre)
    ctx.fillStyle = '#2d4059';
    ctx.beginPath();
    ctx.arc(0, 0, 14, 0, 2 * Math.PI);
    ctx.fill();

    ctx.fillStyle = '#4da6ff';
    ctx.beginPath();
    ctx.arc(0, 0, 7, 0, 2 * Math.PI);
    ctx.fill();

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

    // Initialiser le contexte si nécessaire
    if (!timerCtx) {
        timerCtx = timerCanvas.getContext('2d');
    }

    // Afficher le widget
    timerWidget.classList.remove('hidden');

    const ctx = timerCtx;
    const cx = timerCanvas.width / 2;
    const cy = timerCanvas.height / 2;
    const radius = Math.min(cx, cy) - 10;

    // Clear
    ctx.clearRect(0, 0, timerCanvas.width, timerCanvas.height);

    // Fond du cercle
    ctx.fillStyle = '#1a1a2e';
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, 2 * Math.PI);
    ctx.fill();

    // Cercle de fond (gris)
    ctx.strokeStyle = '#2d4059';
    ctx.lineWidth = 8;
    ctx.beginPath();
    ctx.arc(cx, cy, radius - 4, 0, 2 * Math.PI);
    ctx.stroke();

    // Calcul de la progression (clampée à 1.0 max pour éviter arc > 100% lors changement de mode)
    const remaining = countdownValue !== null ? countdownValue : 0;
    const progress = Math.min(remaining / timerTotal, 1.0);

    // Couleur selon la progression
    let color;
    if (progress > 0.5) {
        color = '#00d26a';  // Vert
    } else if (progress > 0.25) {
        color = '#ffa502';  // Orange
    } else {
        color = '#ff4757';  // Rouge
    }

    // Arc de progression (sens anti-horaire depuis le haut)
    if (progress > 0) {
        ctx.strokeStyle = color;
        ctx.lineWidth = 8;
        ctx.lineCap = 'round';
        ctx.beginPath();
        const startAngle = -Math.PI / 2;
        const endAngle = startAngle + (2 * Math.PI * progress);
        ctx.arc(cx, cy, radius - 4, startAngle, endAngle);
        ctx.stroke();
    }

    // Texte au centre
    if (timerSeconds) {
        timerSeconds.textContent = remaining > 0 ? `${remaining}s` : '--';
        timerSeconds.style.color = color;
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
