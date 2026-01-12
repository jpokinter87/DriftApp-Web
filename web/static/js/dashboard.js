/**
 * DriftApp Web - Dashboard JavaScript
 *
 * Gère l'interface utilisateur et la communication avec l'API REST.
 */

// Configuration
const API_BASE = '';
const POLL_INTERVAL = 1000;  // 1 seconde
const MAX_LOG_ENTRIES = 50;
const DEFAULT_TIMER_SECONDS = 60;
const UPDATE_CHECK_DELAY_MS = 3000;
const SERVICE_RESTART_MAX_ATTEMPTS = 30;
const SERVICE_RESTART_POLL_MS = 2000;
const FETCH_TIMEOUT_MS = 5000;

// État de l'application
let state = {
    position: 0,
    target: null,
    status: 'unknown',
    trackingObject: null,
    searchedObject: null,
    lastUpdate: null,
    trackingInfo: {},  // Pour position_cible, etc.
    gotoInfo: null,    // Pour la modal GOTO
    encoderFrozenLogged: false  // Pour éviter de logger l'alerte plusieurs fois
};

// Countdown timer (Correction 1)
let countdownValue = null;
let countdownInterval = null;
let lastRemainingFromApi = null;

// Logs tracking (Correction 3)
let displayedLogs = new Set();

// Timer settings
let timerTotal = DEFAULT_TIMER_SECONDS;

// GOTO Modal state
let gotoModalVisible = false;
let gotoStartPosition = null;
let gotoStartTime = null;  // Timestamp du début du GOTO pour calcul position estimée

// Vitesse CONTINUOUS en degrés/seconde (51°/min selon config.json ajusté 30/12/2025)
const CONTINUOUS_SPEED_DEG_PER_SEC = 51.0 / 60;  // ~0.85°/s

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

// Flag pour la synchronisation initiale (reconnexion à une session en cours)
let initialSyncDone = false;

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
    // Shift+clic = démarrer sans GOTO (position actuelle conservée)
    elements.btnStartTracking.addEventListener('click', (e) => {
        startTracking(e.shiftKey);
    });
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
        const raDeg = result.ra_deg ?? null;
        const decDeg = result.dec_deg ?? null;

        // Format décimal
        const raDecimal = raDeg !== null ? raDeg.toFixed(2) + '°' : '--';
        const decDecimal = decDeg !== null ? decDeg.toFixed(2) + '°' : '--';

        // Format sexagésimal : HMS pour RA, DMS pour DEC
        const raHMS = formatHMS(raDeg);
        const decDMS = formatDMS(decDeg);

        // Affichage sur deux lignes : décimal + sexagésimal
        elements.objectCoords.innerHTML =
            `RA: ${raDecimal} (${raHMS})<br>DEC: ${decDecimal} (${decDMS})`;
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

async function startTracking(skipGoto = false) {
    const name = state.searchedObject || elements.objectName.value.trim();
    if (!name) {
        log('Aucun objet sélectionné', 'warning');
        return;
    }

    if (skipGoto) {
        log(`Démarrage du suivi de ${name} (position actuelle conservée)...`);
    } else {
        log(`Démarrage du suivi de ${name}...`);
    }

    const result = await apiCall('/api/tracking/start/', 'POST', {
        object: name,
        skip_goto: skipGoto
    });

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

    // Affichage des positions : toujours dans l'ordre de lecture naturel
    // - Horaire (CW) : Départ >>> Cible (gauche vers droite)
    // - Anti-horaire (CCW) : Cible <<< Départ (les chevrons pointent vers la cible à gauche)
    const labelLeft = document.getElementById('goto-label-left');
    const labelRight = document.getElementById('goto-label-right');

    if (delta >= 0) {
        // Sens horaire : départ à gauche, cible à droite
        if (elements.gotoModalStart) {
            elements.gotoModalStart.textContent = `${startPos.toFixed(1)}°`;
        }
        if (elements.gotoModalTarget) {
            elements.gotoModalTarget.textContent = `${targetPos.toFixed(1)}°`;
        }
        if (labelLeft) labelLeft.textContent = 'Départ';
        if (labelRight) labelRight.textContent = 'Cible';
    } else {
        // Sens anti-horaire : cible à gauche, départ à droite
        // Pour que l'affichage soit "45° <<< 175°" au lieu de "175° <<< 45°"
        if (elements.gotoModalStart) {
            elements.gotoModalStart.textContent = `${targetPos.toFixed(1)}°`;
        }
        if (elements.gotoModalTarget) {
            elements.gotoModalTarget.textContent = `${startPos.toFixed(1)}°`;
        }
        if (labelLeft) labelLeft.textContent = 'Cible';
        if (labelRight) labelRight.textContent = 'Départ';
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

    // Position de la coupole:
    // - En suivi actif: utiliser motor.position (position LOGIQUE du tracker, compensée par l'offset encodeur)
    // - Sinon: utiliser encoder.angle (lecture brute pour manoeuvres manuelles)
    // Cela garantit que CIMIER ≈ CIBLE pendant le suivi
    if (motor.status === 'tracking' && motor.position !== undefined) {
        state.position = motor.position;
    } else {
        state.position = encoder.angle || motor.position || 0;
    }

    state.target = motor.target;
    state.trackingObject = motor.tracking_object;
    state.lastUpdate = new Date();
    state.gotoInfo = motor.goto_info || null;

    // Mettre à jour l'interface
    updateServiceStatus(motor, encoder);
    updatePositionDisplay(encoder, motor);
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

function updatePositionDisplay(encoder, motor) {
    elements.domePosition.textContent = `${state.position.toFixed(2)}°`;
    elements.domeTarget.textContent = state.target ? `${state.target.toFixed(2)}°` : '--';

    // Récupérer l'offset encodeur depuis tracking_info (si suivi actif)
    let encoderOffset = 0;
    if (motor && motor.tracking_info && motor.tracking_info.encoder_offset !== undefined) {
        encoderOffset = motor.tracking_info.encoder_offset;
    }

    // Cartouche ENC avec angle encodeur et état coloré
    const encItem = elements.encItem;
    if (encItem) {
        // Supprimer les classes d'état précédentes
        encItem.classList.remove('enc-absent', 'enc-uncalibrated', 'enc-calibrated', 'enc-frozen');

        if (!encoder || encoder.error || encoder.status === 'absent') {
            // Gris = absent (daemon non disponible)
            encItem.classList.add('enc-absent');
            elements.encoderCalibrated.textContent = 'ABSENT';
        } else if (encoder.frozen === true || encoder.status === 'FROZEN') {
            // ROUGE CLIGNOTANT = encodeur figé (dysfonctionnement détecté)
            encItem.classList.add('enc-frozen');
            const duration = encoder.frozen_duration ? encoder.frozen_duration.toFixed(1) : '?';
            elements.encoderCalibrated.textContent = `FIGÉ ${duration}s`;
            // Log l'alerte (une seule fois)
            if (!state.encoderFrozenLogged) {
                log(`ALERTE: Encodeur fige depuis ${duration}s - verifier connexion SPI!`, 'error');
                state.encoderFrozenLogged = true;
            }
        } else if (!encoder.calibrated) {
            // Marron = non calibré
            encItem.classList.add('enc-uncalibrated');
            elements.encoderCalibrated.textContent = `${(encoder.angle || 0).toFixed(2)}°`;
            state.encoderFrozenLogged = false;  // Reset pour prochaine alerte
        } else {
            // Vert = calibré
            encItem.classList.add('enc-calibrated');
            const angle = (encoder.angle || 0).toFixed(2);
            // Afficher l'offset si significatif (> 1°) pendant le suivi
            if (Math.abs(encoderOffset) > 1.0 && motor && motor.status === 'tracking') {
                const sign = encoderOffset >= 0 ? '+' : '';
                elements.encoderCalibrated.textContent = `${angle}° (${sign}${encoderOffset.toFixed(1)}°)`;
            } else {
                elements.encoderCalibrated.textContent = `${angle}°`;
            }
            state.encoderFrozenLogged = false;  // Reset pour prochaine alerte
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
        // === SYNCHRONISATION MULTI-APPAREILS ===
        // Si un suivi est en cours et qu'on vient de se connecter, synchroniser l'état
        if (!initialSyncDone && motor.tracking_object) {
            state.searchedObject = motor.tracking_object;
            elements.objectName.value = motor.tracking_object;

            // Log informatif pour l'utilisateur
            const info = motor.tracking_info || {};
            const corrections = info.total_corrections || 0;
            log(`Reconnexion à la session en cours: ${motor.tracking_object}`, 'success');
            if (corrections > 0) {
                log(`Session active: ${corrections} corrections effectuées`, 'info');
            }

            initialSyncDone = true;
        }

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

        // Mettre à jour le cartouche CIBLE avec position_cible pendant le tracking
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

        // Timer intégré dans la boussole - redessiner
        drawCompass();

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

        // Reset du flag de sync pour permettre la reconnexion à une future session
        // (permet de sync si un suivi démarre depuis un autre appareil)
        initialSyncDone = false;
    }
}

// Correction 1: Démarrer le countdown local
function startCountdown() {
    if (countdownInterval) clearInterval(countdownInterval);

    countdownInterval = setInterval(() => {
        if (countdownValue !== null && countdownValue > 0) {
            countdownValue--;
            elements.trackingRemaining.textContent = `${countdownValue}s`;
            drawCompass();  // Timer intégré dans la boussole
        } else if (countdownValue === 0) {
            // Réinitialiser pour permettre le redémarrage au prochain cycle
            lastRemainingFromApi = null;
            // Garder l'affichage "0s" en attendant la nouvelle valeur de l'API
            elements.trackingRemaining.textContent = '0s';
            drawCompass();
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

    // Rayons - couronne extérieure au maximum, coupole agrandie
    const outerRadius = Math.min(cx, cy) - 4;   // Couronne extérieure (timer) - au max
    const domeRadius = 95;                       // Couronne de la coupole (agrandie pour marge télescope)

    // Clear
    ctx.clearRect(0, 0, width, height);

    // =========================================================================
    // COUCHE 1: Fond général
    // =========================================================================
    ctx.fillStyle = '#1a1a2e';
    ctx.beginPath();
    ctx.arc(cx, cy, outerRadius + 2, 0, 2 * Math.PI);
    ctx.fill();

    // =========================================================================
    // COUCHE 2: Arc Timer sur couronne extérieure
    // =========================================================================
    const isTracking = state.trackingInfo && countdownValue !== null;
    const timerLineWidth = 6;  // Épaisseur réduite

    // Fond de la couronne timer (cercle discret)
    ctx.strokeStyle = '#1e2d42';
    ctx.lineWidth = timerLineWidth;
    ctx.beginPath();
    ctx.arc(cx, cy, outerRadius - timerLineWidth / 2, 0, 2 * Math.PI);
    ctx.stroke();

    // Arc de progression du timer
    let timerColor = '#2d8a5e';  // Couleur par défaut
    if (isTracking && countdownValue !== null && timerTotal > 0) {
        const progress = Math.min(countdownValue / timerTotal, 1.0);

        // Couleurs atténuées pour observatoire
        if (progress > 0.5) {
            timerColor = '#2d8a5e';  // Vert sombre
        } else if (progress > 0.25) {
            timerColor = '#b8860b';  // Or sombre
        } else {
            timerColor = '#8b3a3a';  // Rouge sombre
        }

        if (progress > 0) {
            ctx.strokeStyle = timerColor;
            ctx.lineWidth = timerLineWidth;
            ctx.lineCap = 'round';
            ctx.beginPath();
            const startAngle = -Math.PI / 2;
            const endAngle = startAngle + (2 * Math.PI * progress);
            ctx.arc(cx, cy, outerRadius - timerLineWidth / 2, startAngle, endAngle);
            ctx.stroke();
            ctx.lineCap = 'butt';
        }
    }

    // =========================================================================
    // COUCHE 3: Graduations cardinales sur couronne extérieure
    // =========================================================================
    ctx.strokeStyle = '#4a6a8a';
    for (let deg = 0; deg < 360; deg += 90) {
        const rad = (deg - 90) * Math.PI / 180;
        const x1 = cx + (outerRadius - timerLineWidth - 2) * Math.cos(rad);
        const y1 = cy + (outerRadius - timerLineWidth - 2) * Math.sin(rad);
        const x2 = cx + (outerRadius - timerLineWidth - 10) * Math.cos(rad);
        const y2 = cy + (outerRadius - timerLineWidth - 10) * Math.sin(rad);

        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();
    }

    // =========================================================================
    // COUCHE 4: Ciel étoilé (entre couronne extérieure et coupole)
    // =========================================================================
    drawStarField(ctx, cx, cy, outerRadius - timerLineWidth - 12, domeRadius + 10);

    // =========================================================================
    // COUCHE 5: Labels cardinaux (dans le ciel étoilé)
    // =========================================================================
    ctx.font = 'bold 13px Arial';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillStyle = '#5a8ab8';  // Bleu discret

    const labelRadius = outerRadius - 25;
    const labels = { 0: 'N', 90: 'E', 180: 'S', 270: 'O' };
    for (const [deg, label] of Object.entries(labels)) {
        const rad = (parseInt(deg) - 90) * Math.PI / 180;
        const lx = cx + labelRadius * Math.cos(rad);
        const ly = cy + labelRadius * Math.sin(rad);
        ctx.fillText(label, lx, ly);
    }

    // =========================================================================
    // COUCHE 6: Arc de la coupole (partie fermée en rouge sombre)
    // =========================================================================
    const OPENING_ANGLE = 40.1;  // degrés (70cm / pi x 200cm x 360)
    const domeAngle = state.position;

    // Calculer les limites de l'ouverture
    const openingStart = domeAngle - OPENING_ANGLE / 2;
    const openingEnd = domeAngle + OPENING_ANGLE / 2;

    // Bordure extérieure de la coupole
    ctx.strokeStyle = '#3d5068';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(cx, cy, domeRadius + 7, 0, 2 * Math.PI);
    ctx.stroke();

    // Graduations cardinales sur la coupole
    ctx.strokeStyle = '#4a6a8a';
    for (let deg = 0; deg < 360; deg += 90) {
        const rad = (deg - 90) * Math.PI / 180;
        const x1 = cx + (domeRadius + 7) * Math.cos(rad);
        const y1 = cy + (domeRadius + 7) * Math.sin(rad);
        const x2 = cx + (domeRadius + 14) * Math.cos(rad);
        const y2 = cy + (domeRadius + 14) * Math.sin(rad);

        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();
    }

    // Arc ambre = partie FERMÉE (de openingEnd à openingStart, en passant par l'opposé)
    // Couleur alignée avec cartouche CIMIER (--accent-amber: #d4a055)
    ctx.strokeStyle = 'rgba(212, 160, 85, 0.75)';
    ctx.lineWidth = 12;
    ctx.beginPath();
    const closedStartRad = (openingEnd - 90) * Math.PI / 180;
    const closedEndRad = (openingStart - 90 + 360) * Math.PI / 180;
    ctx.arc(cx, cy, domeRadius, closedStartRad, closedEndRad);
    ctx.stroke();

    // Bordure intérieure de la coupole
    ctx.strokeStyle = '#2d4059';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(cx, cy, domeRadius - 7, 0, 2 * Math.PI);
    ctx.stroke();

    // =========================================================================
    // COUCHE 7: Télescope au centre avec timer
    // =========================================================================
    const telescopeAngle = state.trackingInfo?.position_cible;
    drawTelescope(ctx, cx, cy, telescopeAngle, countdownValue, timerColor);
}

// Dessiner un champ d'étoiles dans une zone annulaire
function drawStarField(ctx, cx, cy, outerR, innerR) {
    // Utiliser une seed basée sur les rayons pour avoir un pattern stable
    const starCount = 60;

    ctx.fillStyle = '#ffffff';

    for (let i = 0; i < starCount; i++) {
        // Pseudo-random basé sur l'index (pattern stable)
        const seed1 = Math.sin(i * 12.9898) * 43758.5453;
        const seed2 = Math.sin(i * 78.233) * 43758.5453;
        const seed3 = Math.sin(i * 45.164) * 43758.5453;

        const angle = (seed1 - Math.floor(seed1)) * 2 * Math.PI;
        const radiusFactor = (seed2 - Math.floor(seed2));
        const r = innerR + (outerR - innerR) * radiusFactor;

        const x = cx + r * Math.cos(angle);
        const y = cy + r * Math.sin(angle);

        // Taille et opacité variables
        const size = 0.5 + (seed3 - Math.floor(seed3)) * 1.5;
        const opacity = 0.3 + (seed3 - Math.floor(seed3)) * 0.7;

        ctx.globalAlpha = opacity;
        ctx.beginPath();
        ctx.arc(x, y, size, 0, 2 * Math.PI);
        ctx.fill();
    }

    ctx.globalAlpha = 1.0;
}

// Dessiner la flèche de direction calculée (√x²) avec timer intégré
function drawTelescope(ctx, cx, cy, angle, countdownValue, timerColor) {
    // Si pas d'angle de tracking, utiliser la position coupole
    const teleAngle = (angle !== undefined && angle !== null) ? angle : state.position;
    const teleRad = teleAngle * Math.PI / 180;

    // Dimensions de la flèche
    const arrowLength = 65;
    const arrowHeadSize = 12;
    const arrowWidth = 3;

    // Rayon du centre pour le symbole √x² et timer
    const centerRadius = 28;

    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(teleRad);

    // === FLÈCHE ===
    // Tige de la flèche (du cercle central vers l'extérieur)
    ctx.strokeStyle = '#4ade80';  // Vert clair
    ctx.lineWidth = arrowWidth;
    ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.moveTo(0, -centerRadius - 2);
    ctx.lineTo(0, -arrowLength);
    ctx.stroke();

    // Pointe de la flèche (triangle)
    ctx.fillStyle = '#4ade80';
    ctx.beginPath();
    ctx.moveTo(0, -arrowLength - arrowHeadSize);  // Pointe
    ctx.lineTo(-arrowHeadSize/2, -arrowLength + 2);  // Coin gauche
    ctx.lineTo(arrowHeadSize/2, -arrowLength + 2);   // Coin droit
    ctx.closePath();
    ctx.fill();

    // === CERCLE CENTRAL avec symbole √x² ===
    // Cercle extérieur
    ctx.fillStyle = '#1e3a5f';
    ctx.beginPath();
    ctx.arc(0, 0, centerRadius, 0, 2 * Math.PI);
    ctx.fill();

    // Bordure du cercle
    ctx.strokeStyle = '#4ade80';
    ctx.lineWidth = 2;
    ctx.stroke();

    ctx.restore();

    // === CONTENU DU CERCLE CENTRAL ===
    const hasTimer = countdownValue !== undefined && countdownValue !== null && countdownValue !== '--';

    if (hasTimer) {
        // Mode avec timer: afficher timer + symbole √x² en dessous
        // Formater le texte du timer
        let timerText;
        if (typeof countdownValue === 'number') {
            timerText = Math.round(countdownValue) + 's';
        } else {
            timerText = String(countdownValue);
        }

        // Timer (légèrement au-dessus du centre)
        ctx.save();
        ctx.fillStyle = timerColor || '#4da6ff';
        ctx.font = 'bold 12px monospace';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(timerText, cx, cy - 7);
        ctx.restore();

        // Symbole √x² en dessous du timer
        ctx.save();
        ctx.fillStyle = '#4ade80';
        ctx.font = 'bold 14px serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('√x²', cx, cy + 10);
        ctx.restore();
    } else {
        // Mode sans timer: symbole √x² seul, centré
        ctx.save();
        ctx.fillStyle = '#4ade80';
        ctx.font = 'bold 20px serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('√x²', cx, cy);
        ctx.restore();
    }
}


// =========================================================================
// Formatage des coordonnées
// =========================================================================

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

    // Formater les secondes selon la précision demandée
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

    // Convertir degrés en heures (1h = 15°)
    const hours = degrees / 15;
    const absHours = Math.abs(hours);

    const h = Math.floor(absHours);
    const minFloat = (absHours - h) * 60;
    const m = Math.floor(minFloat);
    const s = (minFloat - m) * 60;

    const secStr = precision > 0 ? s.toFixed(precision) : Math.round(s).toString();

    return `${h}h${m.toString().padStart(2, '0')}m${secStr.padStart(2, '0')}s`;
}

// =========================================================================
// Logging
// =========================================================================

function log(message, type = 'info') {
    const entry = document.createElement('div');
    entry.className = `log-entry ${type}`;
    entry.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;

    elements.logs.insertBefore(entry, elements.logs.firstChild);

    // Limiter le nombre d'entrées
    while (elements.logs.children.length > MAX_LOG_ENTRIES) {
        elements.logs.removeChild(elements.logs.lastChild);
    }
}

// =========================================================================
// Update Notification System
// =========================================================================

// Elements for update modal
const updateElements = {
    modal: document.getElementById('update-modal'),
    currentVersion: document.getElementById('update-current-version'),
    currentCommit: document.getElementById('update-current-commit'),
    newCommit: document.getElementById('update-new-commit'),
    commitsBehind: document.getElementById('update-commits-behind'),
    commitMessages: document.getElementById('update-commit-messages'),
    changesList: document.getElementById('update-changes-list'),
    progress: document.getElementById('update-progress'),
    progressText: document.getElementById('update-progress-text'),
    error: document.getElementById('update-error'),
    errorText: document.getElementById('update-error-text'),
    buttons: document.getElementById('update-buttons'),
    btnLater: document.getElementById('btn-update-later'),
    btnNow: document.getElementById('btn-update-now'),
    // Update check button in header
    btnCheckUpdate: document.getElementById('btn-check-update'),
    updateBadge: document.getElementById('update-badge')
};

// Store update data
let updateData = null;

// Delay for "up to date" feedback display (ms)
const UPDATE_FEEDBACK_DELAY_MS = 2000;

/**
 * Check for updates on page load.
 * Called once during initialization after a short delay.
 * @param {boolean} showUpToDate - Whether to show "up to date" message if no update
 */
async function checkForUpdates(showUpToDate = false) {
    try {
        const response = await fetch('/api/health/update/check/');
        if (!response.ok) {
            console.warn('Update check failed:', response.status);
            if (showUpToDate) {
                log('Erreur lors de la verification des mises a jour', 'error');
            }
            return { error: true };
        }

        const result = await response.json();

        if (result.error) {
            console.warn('Update check error:', result.error);
            if (showUpToDate) {
                log(`Erreur: ${result.error}`, 'error');
            }
            return { error: true };
        }

        if (result.update_available) {
            updateData = result;
            toggleUpdateBadge(true);
            showUpdateModal(result);
            log(`Mise a jour disponible: ${result.commits_behind} commit(s)`, 'info');
        } else if (showUpToDate) {
            // Show "up to date" message only when manually checking
            log('Application a jour (aucune mise a jour disponible)', 'success');
        }

        return result;
    } catch (error) {
        console.warn('Update check exception:', error);
        if (showUpToDate) {
            log('Erreur de connexion lors de la verification', 'error');
        }
        return { error: true };
    }
}

/**
 * Set the update button loading state.
 * @param {boolean} loading - Whether button is in loading state
 * @returns {string} Original button text for restoration
 */
function setUpdateButtonLoading(loading) {
    const btn = updateElements.btnCheckUpdate;
    const textSpan = btn?.querySelector('.update-check-text');
    const originalText = textSpan?.textContent || 'MAJ';

    if (btn) {
        btn.classList.toggle('checking', loading);
        btn.disabled = loading;
    }
    if (textSpan) {
        textSpan.textContent = loading ? '...' : originalText;
    }

    return originalText;
}

/**
 * Show temporary "up to date" feedback on button.
 * @param {string} originalText - Text to restore after delay
 */
function showUpToDateFeedback(originalText) {
    const textSpan = updateElements.btnCheckUpdate?.querySelector('.update-check-text');
    if (!textSpan) return;

    textSpan.textContent = 'OK';
    textSpan.classList.add('up-to-date');

    setTimeout(() => {
        textSpan.textContent = originalText;
        textSpan.classList.remove('up-to-date');
    }, UPDATE_FEEDBACK_DELAY_MS);
}

/**
 * Manual update check triggered by user clicking the button.
 */
async function manualCheckForUpdates() {
    const btn = updateElements.btnCheckUpdate;

    // Prevent multiple simultaneous checks
    if (btn?.classList.contains('checking')) return;

    const originalText = setUpdateButtonLoading(true);
    log('Verification des mises a jour...', 'info');

    try {
        const result = await checkForUpdates(true);

        if (!result.error && !result.update_available) {
            showUpToDateFeedback(originalText);
            return;  // Feedback handles text reset
        }
    } finally {
        // Only reset if not showing up-to-date feedback
        const textSpan = btn?.querySelector('.update-check-text');
        if (!textSpan?.classList.contains('up-to-date')) {
            setUpdateButtonLoading(false);
        } else if (btn) {
            // Still need to re-enable button
            btn.classList.remove('checking');
            btn.disabled = false;
        }
    }
}

/**
 * Toggle the update badge visibility.
 * @param {boolean} visible - Whether to show the badge
 */
function toggleUpdateBadge(visible) {
    const btn = updateElements.btnCheckUpdate;
    const badge = updateElements.updateBadge;

    if (btn) {
        btn.classList.toggle('has-update', visible);
    }
    if (badge) {
        badge.classList.toggle('hidden', !visible);
    }
}

/**
 * Show the update modal with version info.
 * @param {Object} data - Update check result
 */
function showUpdateModal(data) {
    if (!updateElements.modal) return;

    // Populate version info
    if (updateElements.currentVersion) {
        updateElements.currentVersion.textContent = `v${data.local_version}`;
    }
    if (updateElements.currentCommit) {
        updateElements.currentCommit.textContent = `(${data.local_commit})`;
    }
    if (updateElements.newCommit) {
        updateElements.newCommit.textContent = data.remote_commit;
    }
    if (updateElements.commitsBehind) {
        updateElements.commitsBehind.textContent = `+${data.commits_behind} commit(s)`;
    }

    // Show commit messages if available
    if (data.commit_messages && data.commit_messages.length > 0 && updateElements.changesList) {
        updateElements.changesList.innerHTML = '';
        data.commit_messages.forEach(msg => {
            const li = document.createElement('li');
            li.textContent = msg;
            updateElements.changesList.appendChild(li);
        });
        if (updateElements.commitMessages) {
            updateElements.commitMessages.classList.remove('hidden');
        }
    }

    // Reset state
    if (updateElements.progress) updateElements.progress.classList.add('hidden');
    if (updateElements.error) updateElements.error.classList.add('hidden');
    if (updateElements.buttons) updateElements.buttons.style.display = 'flex';
    if (updateElements.btnNow) updateElements.btnNow.disabled = false;
    if (updateElements.btnLater) updateElements.btnLater.disabled = false;

    // Show modal
    updateElements.modal.classList.remove('hidden');
}

/**
 * Hide the update modal (dismiss until next page load).
 */
function hideUpdateModal() {
    if (!updateElements.modal) return;
    updateElements.modal.classList.add('hidden');
}

/**
 * Apply the update.
 * Shows progress, calls API, handles service restart.
 */
async function applyUpdate() {
    if (!updateElements.progress) return;

    // Show progress, disable buttons
    updateElements.progress.classList.remove('hidden');
    if (updateElements.error) updateElements.error.classList.add('hidden');
    if (updateElements.btnNow) updateElements.btnNow.disabled = true;
    if (updateElements.btnLater) updateElements.btnLater.disabled = true;
    if (updateElements.progressText) {
        updateElements.progressText.textContent = 'Mise a jour en cours...';
    }

    log('Mise a jour en cours...', 'info');

    try {
        const response = await fetch('/api/health/update/apply/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        const result = await response.json();

        if (result.success) {
            if (updateElements.progressText) {
                updateElements.progressText.textContent = 'Redemarrage des services...';
            }
            log('Mise a jour reussie, redemarrage...', 'success');

            // Wait for services to restart, then reload page
            await waitForServiceRestart();

        } else {
            showUpdateError(result.error || 'Erreur inconnue');
            log(`Erreur de mise a jour: ${result.error}`, 'error');
        }
    } catch (error) {
        // Connection error is expected during restart
        if (updateElements.progressText) {
            updateElements.progressText.textContent = 'Reconnexion en cours...';
        }
        log('Connexion perdue, attente du redemarrage...', 'warning');
        await waitForServiceRestart();
    }
}

/**
 * Show an error message in the update modal.
 * @param {string} message - Error message to display
 */
function showUpdateError(message) {
    if (updateElements.progress) updateElements.progress.classList.add('hidden');
    if (updateElements.error) {
        updateElements.error.classList.remove('hidden');
        if (updateElements.errorText) {
            updateElements.errorText.textContent = message;
        }
    }
    if (updateElements.btnNow) updateElements.btnNow.disabled = false;
    if (updateElements.btnLater) updateElements.btnLater.disabled = false;
}

/**
 * Wait for services to restart, then reload the page.
 * Polls the health endpoint until it responds.
 */
async function waitForServiceRestart() {
    const maxAttempts = SERVICE_RESTART_MAX_ATTEMPTS;
    let attempts = 0;

    while (attempts < maxAttempts) {
        await sleep(SERVICE_RESTART_POLL_MS);
        attempts++;

        if (updateElements.progressText) {
            updateElements.progressText.textContent = `Reconnexion... (${attempts}/${maxAttempts})`;
        }

        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);

            const response = await fetch('/api/health/', {
                signal: controller.signal
            });

            clearTimeout(timeoutId);

            if (response.ok) {
                // Service is back, reload page
                log('Services redemarres, rechargement...', 'success');
                if (updateElements.progressText) {
                    updateElements.progressText.textContent = 'Rechargement de la page...';
                }
                await sleep(500);
                window.location.reload();
                return;
            }
        } catch (e) {
            // Still waiting, continue polling
        }
    }

    // Timeout - ask user to reload manually
    if (updateElements.progressText) {
        updateElements.progressText.textContent = 'Delai depasse - rechargez la page manuellement';
    }
    log('Delai depasse, rechargez la page manuellement', 'warning');

    // Re-enable later button so user can dismiss
    if (updateElements.btnLater) updateElements.btnLater.disabled = false;
}

/**
 * Sleep utility function.
 * @param {number} ms - Milliseconds to sleep
 * @returns {Promise} Resolves after the specified time
 */
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Initialize update event listeners.
 */
function initUpdateListeners() {
    if (updateElements.btnLater) {
        updateElements.btnLater.addEventListener('click', hideUpdateModal);
    }
    if (updateElements.btnNow) {
        updateElements.btnNow.addEventListener('click', applyUpdate);
    }
    // Manual update check button in header
    if (updateElements.btnCheckUpdate) {
        updateElements.btnCheckUpdate.addEventListener('click', manualCheckForUpdates);
    }
}

// Initialize update system after page load
document.addEventListener('DOMContentLoaded', () => {
    // Initialize update event listeners
    initUpdateListeners();

    // Check for updates after a short delay (don't block initial load)
    setTimeout(checkForUpdates, UPDATE_CHECK_DELAY_MS);
});
