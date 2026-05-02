/**
 * DriftApp Web - Dashboard JavaScript
 *
 * Gère l'interface utilisateur et la communication avec l'API REST.
 * Alpine.js store pour les modales, logs et visibilité tracking.
 */

// =========================================================================
// Alpine.js Store — Couche réactive (modales, logs, tracking visibility)
// =========================================================================

document.addEventListener('alpine:init', () => {
    Alpine.store('dashboard', {
        // GOTO Modal visibility
        gotoModalVisible: false,
        // Update Modal visibility
        updateModalVisible: false,
        // Update Modal state
        updateShowProgress: false,
        updateShowError: false,
        updateButtonsDisabled: false,
        // Tracking panel visibility
        trackingVisible: false,
        // Cimier state (v6.0 Phase 1) — payload brut de /api/cimier/status/
        cimier: null,
        // Cimier close confirmation modal (v6.0 Phase 2 sub-plan 01)
        cimierCloseConfirmVisible: false,
        cimierCloseConfirmObject: null,
        cimierCloseConfirmCountdown: 0,
        // Cimier automation lifecycle (v6.0 Phase 4 sub-plan 04-02)
        automationMode: 'manual',                  // 'manual' | 'semi' | 'full'
        automationRestartHint: '',                 // hint affiché 8s après POST mode
        automationNextOpenAt: null,                // ISO 8601 UTC string ou null
        automationNextCloseAt: null,               // ISO 8601 UTC string ou null
        automationCountdownLabel: '',              // libellé contextualisé pré-calculé
        parkingConfirmVisible: false,
        parkingConfirmObject: null,
        parkingConfirmCountdown: 0,
        // Suivi progression parking session (v6.0 Phase 4 sub-plan 04-02 fix UX) —
        // banner permanent dashboard tant que la séquence stop+goto+close n'est pas terminée.
        parkingInProgress: false,
        parkingTargetDeg: 45,
        parkingStepTracking: 'pending',  // 'pending' | 'done'
        parkingStepGoto: 'pending',      // 'pending' | 'in_progress' | 'done'
        parkingStepCimier: 'pending',    // 'pending' | 'cycle' | 'closed' | 'failed'
        parkingStartedAt: null,          // epoch ms
        cimierTimeline: [],                        // FIFO buffer max 50 entrées
        // Logs (reactive array)
        logs: [],

        addLog(message, type = 'info') {
            this.logs.unshift({
                message,
                type,
                time: new Date().toLocaleTimeString()
            });
            if (this.logs.length > 50) {
                this.logs.length = 50;
            }
        }
    });
});

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
    gotoInfo: null,    // Pour la modal GOTO
    encoderFrozenLogged: false  // Pour éviter de logger l'alerte plusieurs fois
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

    // Méridien
    meridianCartouche: document.getElementById('meridian-cartouche'),
    meridianValue: document.getElementById('meridian-value'),

    // Nouveaux cartouches
    correctionsCount: document.getElementById('corrections-count'),
    correctionsTotal: document.getElementById('corrections-total'),
    encItem: document.getElementById('enc-item'),

    // Logs
    logs: document.getElementById('logs'),
    lastUpdate: document.getElementById('last-update'),

    // Update button
    btnCheckUpdate: document.getElementById('btn-check-update'),
    updateBadge: document.getElementById('update-badge'),

    // GOTO Modal
    gotoModal: document.getElementById('goto-modal'),
    gotoModalObjectName: document.getElementById('goto-modal-object-name'),
    gotoModalStart: document.getElementById('goto-modal-start'),
    gotoModalTarget: document.getElementById('goto-modal-target'),
    gotoModalCurrentPos: document.getElementById('goto-modal-current-pos'),
    gotoChevrons: document.getElementById('goto-chevrons'),
    gotoProgressFill: document.getElementById('goto-progress-fill'),
    gotoProgressText: document.getElementById('goto-progress-text'),
    gotoModalDelta: document.getElementById('goto-modal-delta'),

    // Cimier (v6.0 Phase 1)
    btnCimierOpen: document.getElementById('btn-cimier-open'),
    btnCimierClose: document.getElementById('btn-cimier-close'),
    btnCimierStop: document.getElementById('btn-cimier-stop'),
    cimierDetail: document.getElementById('cimier-detail'),
    // Cimier close confirmation modal (v6.0 Phase 2 sub-plan 01)
    btnCimierCloseCancel: document.getElementById('btn-cimier-close-cancel'),
    btnCimierCloseConfirm: document.getElementById('btn-cimier-close-confirm'),
    // Cimier automation + parking session (v6.0 Phase 4 sub-plan 04-02)
    selectAutomationMode: document.getElementById('cimier-automation-mode'),
    btnCimierParking: document.getElementById('btn-cimier-parking'),
    btnParkingCancel: document.getElementById('btn-parking-cancel'),
    btnParkingConfirm: document.getElementById('btn-parking-confirm')
};

// Countdown interval handle for the cimier close confirmation modal.
let cimierCloseConfirmInterval = null;
// Countdown interval handle for the parking confirmation modal (v6.0 Phase 4 sub-plan 04-02).
let parkingConfirmInterval = null;
// Compteur monotonique pour les IDs Alpine x-for de la timeline cimier.
let cimierTimelineSeq = 0;
// Hint « Redémarrage cimier_service requis » timeout handle (v6.0 Phase 4 sub-plan 04-02).
let automationRestartHintTimeout = null;
// Watcher progression parking session (setInterval handle).
let parkingWatcherInterval = null;
// Position tracking pour détection « coupole arrivée à 45° ».
let parkingLastObservedPosition = null;
// Verrou utilisateur sur le mode auto : tant que le service ne rapporte pas le mode
// que l'utilisateur vient de choisir (cimier_service non redémarré), on n'écrase pas
// le sélecteur depuis pollCimierStatus. Reset automatiquement quand le service confirme.
// Fix smoke 2026-05-02 : sans ce verrou, le sélecteur revenait à MANUAL après chaque
// poll car cimier_service garde sa config en mémoire jusqu'au restart.
let lastUserSelectedMode = null;

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

    // Cimier (v6.0 Phase 1) — pilotage Pico W via Shelly
    if (elements.btnCimierOpen) {
        elements.btnCimierOpen.addEventListener('click', () => sendCimierAction('open'));
    }
    if (elements.btnCimierClose) {
        // Phase 2 sub-plan 01 : intercept conditionnel — modale de confirmation
        // si tracking actif, sinon action immédiate (anti clic-fantôme NGC 3675).
        elements.btnCimierClose.addEventListener('click', confirmCimierClose);
    }
    if (elements.btnCimierStop) {
        elements.btnCimierStop.addEventListener('click', () => sendCimierAction('stop'));
    }

    // Cimier close confirmation modal — handlers Cancel/Confirm (v6.0 Phase 2 sub-plan 01).
    if (elements.btnCimierCloseCancel) {
        elements.btnCimierCloseCancel.addEventListener('click', closeCimierCloseConfirmModal);
    }
    if (elements.btnCimierCloseConfirm) {
        elements.btnCimierCloseConfirm.addEventListener('click', () => {
            // Double-garde côté code en plus du :disabled du template.
            if (Alpine.store('dashboard').cimierCloseConfirmCountdown > 0) return;
            closeCimierCloseConfirmModal();
            sendCimierAction('close');
        });
    }

    // Bouton Parking session (v6.0 Phase 4 sub-plan 04-02) — séquence
    // tracking_stop + GOTO 45° + close cimier. Modale conditionnelle si tracking actif.
    if (elements.btnCimierParking) {
        elements.btnCimierParking.addEventListener('click', triggerParkingSession);
    }
    if (elements.btnParkingCancel) {
        elements.btnParkingCancel.addEventListener('click', closeParkingConfirmModal);
    }
    if (elements.btnParkingConfirm) {
        elements.btnParkingConfirm.addEventListener('click', () => {
            if (Alpine.store('dashboard').parkingConfirmCountdown > 0) return;
            closeParkingConfirmModal();
            executeParkingSession();
        });
    }

    // Hydratation initiale du sélecteur mode auto + countdown depuis l'API
    // (avant le 1er pollCimierStatus qui n'arrive qu'à T+1s).
    fetchAutomationState();
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
        updateMeridianCartouche(null);
    } else {
        const raHMS = formatHMS(result.ra_deg ?? null);
        const decDMS = formatDMS(result.dec_deg ?? null);

        // Affichage compact sur une ligne
        elements.objectCoords.innerHTML =
            `RA: ${raHMS} &mdash; DEC: ${decDMS}`;
        elements.objectInfo.classList.remove('hidden');
        elements.btnStartTracking.disabled = false;
        state.searchedObject = result.nom || name;
        log(`Trouvé: ${state.searchedObject}`, 'success');

        // Afficher le cartouche méridien dès la recherche
        updateMeridianCartouche(result.meridian_seconds, result.meridian_time);

        // Effet clignotement vert du bouton pendant 5 secondes
        flashButtonSuccess(elements.btnStartTracking, 5000);

        // Focus sur le bouton pour lancer le suivi avec ENTER
        elements.btnStartTracking.focus();
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

    // Cascade auto cimier (v6.0 Phase 2 sub-plan 01) — ouvre le cimier si fermé,
    // attend state="open" (timeout 30 s). Abort propre sur cycle/cooldown/error.
    const cimierReady = await ensureCimierOpenForTracking();
    if (!cimierReady) return;

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
        state.searchedObject = null;
        updateMeridianCartouche(null);

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

    // Afficher la modal via Alpine.js store
    Alpine.store('dashboard').gotoModalVisible = true;
    gotoModalVisible = true;
}

function hideGotoModal() {
    Alpine.store('dashboard').gotoModalVisible = false;
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
    pollCimierStatus();
    setInterval(updateStatus, POLL_INTERVAL);
    setInterval(pollCimierStatus, POLL_INTERVAL);
    // Tick local 1s pour décrémenter le countdown automation (v6.0 Phase 4 sub-plan 04-02).
    // Indépendant du polling /status/ pour fluidité visuelle (sinon countdown saute par seconds).
    setInterval(recomputeAutomationCountdown, 1000);
    // Re-hydratation périodique du sélecteur mode depuis /api/cimier/automation/
    // (au cas où le mode est changé depuis un autre onglet/device).
    setInterval(fetchAutomationState, 30_000);
}

// =========================================================================
// Cimier — pilotage cycle ouverture/fermeture (v6.0 Phase 1)
// =========================================================================

// Étiquettes humaines pour les états/phases publiés par cimier_service.
const CIMIER_STATE_LABELS = {
    open: 'Ouvert',
    closed: 'Fermé',
    cycle: 'Cycle en cours',
    cooldown: 'Anti-rebond',
    error: 'Erreur',
    idle: 'Inactif',
    disabled: 'Désactivé',
    unknown: 'Inconnu'
};

const CIMIER_PHASE_LABELS = {
    idle: 'idle',
    power_on: 'Mise sous tension',
    boot_poll: 'Démarrage Pico',
    push_config: 'Config push',
    command_pico: 'Commande Pico',
    cycle_poll: 'Cycle moteur',
    power_off: 'Coupure',
    cooldown: 'Anti-rebond'
};

// Grise/réactive Ouvrir+Fermer pendant un cycle (pattern v5.12.1).
// STOP reste TOUJOURS actif (sécurité — interrompt le cycle en cours).
function setCimierControlsDisabled(disabled) {
    if (elements.btnCimierOpen) elements.btnCimierOpen.disabled = disabled;
    if (elements.btnCimierClose) elements.btnCimierClose.disabled = disabled;
}

async function pollCimierStatus() {
    const status = await apiCall('/api/cimier/status/');
    const store = Alpine.store('dashboard');

    if (!status || status.error && status.state === undefined) {
        // Service Django KO complet — on reset à null sans spammer les logs.
        store.cimier = null;
        setCimierControlsDisabled(true);
        if (elements.cimierDetail) elements.cimierDetail.textContent = '';
        return;
    }

    // Détection changement d'état cimier pour timeline (avant assignation).
    const prevState = store.cimier?.state;
    if (prevState && prevState !== status.state) {
        const from = (CIMIER_STATE_LABELS[prevState] || prevState).toLowerCase();
        const to = (CIMIER_STATE_LABELS[status.state] || status.state).toLowerCase();
        const level = status.state === 'error' ? 'ERROR' : 'INFO';
        pushCimierTimeline(level, `Cimier : ${from} → ${to}`);
    }

    store.cimier = status;

    // Hydratation des `next_*_at` depuis le status (calculés par le scheduler
    // du service, donc seul le status fait foi) — UNIQUEMENT si le service
    // n'est pas stale (sinon on conserve les valeurs venues du fallback Django
    // via fetchAutomationState, qui sont calculées on-demand).
    // NOTE : on n'hydrate **plus** `automationMode` depuis status — il est
    // désormais piloté uniquement par `fetchAutomationState()` qui interroge
    // `/api/cimier/automation/` (source vérité = data/config.json côté backend
    // depuis fix smoke 2026-05-02).
    const lastUpdate = status?.last_update;
    const statusStale = !lastUpdate ||
        !Number.isFinite(Date.parse(lastUpdate)) ||
        (Date.now() - Date.parse(lastUpdate)) > 90_000;
    if (!statusStale) {
        // Service vivant : ses calculs prennent priorité.
        store.automationNextOpenAt = status.next_open_at || null;
        store.automationNextCloseAt = status.next_close_at || null;
    }
    // Si stale (typiquement dev avec cimier.enabled=false), on ne touche PAS
    // automationNextOpenAt/CloseAt — laisse le fallback Django (fetchAutomationState
    // toutes les 30s) hydrater ces valeurs.
    // Recalcule immédiatement le countdown sans attendre le tick 1s.
    recomputeAutomationCountdown();

    // Disable Ouvrir/Fermer pendant cycle/cooldown/disabled/unknown.
    const lockedStates = ['cycle', 'cooldown', 'disabled', 'unknown'];
    setCimierControlsDisabled(lockedStates.includes(status.state));

    // Ligne détail : phase + pico_state + erreur éventuelle.
    if (elements.cimierDetail) {
        const parts = [];
        if (status.state === 'error' && status.error_message) {
            parts.push(`Erreur : ${status.error_message}`);
        } else {
            if (status.last_action) {
                parts.push(`Dernière action : ${status.last_action}`);
            }
            if (status.pico_state && status.pico_state !== 'unknown') {
                parts.push(`Pico : ${status.pico_state}`);
            }
            if (status.remaining_quiet_s !== undefined && status.remaining_quiet_s > 0) {
                parts.push(`Anti-rebond ${status.remaining_quiet_s.toFixed(0)}s`);
            }
        }
        elements.cimierDetail.textContent = parts.join('  •  ');
    }
}

async function sendCimierAction(action) {
    const labels = { open: 'Ouverture', close: 'Fermeture', stop: 'Arrêt cycle' };

    // Détection cimier service inactif (status stale > 90 s) : la commande sera
    // écrite dans /dev/shm/cimier_command.json mais jamais consommée. On émet
    // un message timeline clair pour éviter à l'utilisateur de se demander
    // pourquoi ÉTAT/PHASE ne changent pas.
    const cimier = Alpine.store('dashboard').cimier;
    const lastUpdate = cimier?.last_update;
    const cimierStale = !lastUpdate ||
        !Number.isFinite(Date.parse(lastUpdate)) ||
        (Date.now() - Date.parse(lastUpdate)) > 90_000;

    log(`Cimier : ${labels[action]} demandée`, 'info');
    if (cimierStale) {
        pushCimierTimeline('INFO', `${labels[action]} demandée (service inactif — commande non exécutée)`);
    } else {
        pushCimierTimeline('INFO', `${labels[action]} demandée`);
    }
    const result = await apiCall(`/api/cimier/${action}/`, 'POST');
    if (result && result.error) {
        log(`Cimier : échec (${result.error})`, 'error');
        pushCimierTimeline('ERROR', `${labels[action]} échouée : ${result.error}`);
    }
    // Le polling 1s rafraîchit l'état affiché ; pas besoin de poll immédiat.
}

// Ferme la modale de confirmation et nettoie le compteur (v6.0 Phase 2 sub-plan 01).
function closeCimierCloseConfirmModal() {
    const store = Alpine.store('dashboard');
    store.cimierCloseConfirmVisible = false;
    store.cimierCloseConfirmObject = null;
    store.cimierCloseConfirmCountdown = 0;
    if (cimierCloseConfirmInterval) {
        clearInterval(cimierCloseConfirmInterval);
        cimierCloseConfirmInterval = null;
    }
}

// Intercept conditionnel sur Fermer cimier : si tracking actif, ouvrir la modale
// de confirmation avec compteur anti-double-clic 2 s ; sinon, action immédiate
// (pas de friction inutile). v6.0 Phase 2 sub-plan 01 — pattern incident NGC 3675.
function confirmCimierClose() {
    const trackingActive = ['tracking', 'initializing'].includes(state.status)
                           && state.trackingObject;
    if (!trackingActive) {
        sendCimierAction('close');
        return;
    }

    const store = Alpine.store('dashboard');
    store.cimierCloseConfirmObject = state.trackingObject;
    store.cimierCloseConfirmCountdown = 2;
    store.cimierCloseConfirmVisible = true;

    if (cimierCloseConfirmInterval) clearInterval(cimierCloseConfirmInterval);
    cimierCloseConfirmInterval = setInterval(() => {
        const remaining = Alpine.store('dashboard').cimierCloseConfirmCountdown - 1;
        Alpine.store('dashboard').cimierCloseConfirmCountdown = Math.max(0, remaining);
        if (remaining <= 0) {
            clearInterval(cimierCloseConfirmInterval);
            cimierCloseConfirmInterval = null;
        }
    }, 1000);
}

// Cascade auto avant démarrage du tracking : si cimier fermé, l'ouvrir d'abord
// puis attendre state="open" (timeout 30 s). Short-circuits gracieux pour
// open/disabled/unknown (passent direct) et cycle/cooldown/error (abort).
// v6.0 Phase 2 sub-plan 01 — cadrage interview thème B/D.
async function ensureCimierOpenForTracking() {
    const cimier = Alpine.store('dashboard').cimier;
    const cimierState = cimier?.state ?? 'unknown';

    // Pass-through : déjà ouvert, désactivé (machine dev) ou inconnu (service éteint).
    if (['open', 'disabled', 'unknown'].includes(cimierState)) return true;

    // Détection service silencieux (cimier_status.json non rafraîchi depuis >60s) :
    // typiquement machine dev sans cimier_service qui tourne, ou prod avec service
    // crashé/figé. On bypass la cascade pour éviter un timeout gratuit de 30 s.
    // Fix smoke 2026-05-02 : sur dev, /dev/shm/cimier_status.json traînait en "idle"
    // depuis un ancien run, ce qui déclenchait à tort la cascade ouverture.
    if (cimier?.last_update) {
        const lastUpdateMs = Date.parse(cimier.last_update);
        if (Number.isFinite(lastUpdateMs) && (Date.now() - lastUpdateMs) > 60_000) {
            log('Cimier Service inactif — tracking lancé sans cascade ouverture cimier', 'info');
            pushCimierTimeline('INFO', 'Cimier service inactif — tracking sans cascade');
            return true;
        }
    }

    // États transitoires bloquants — abort propre avec log explicite.
    if (cimierState === 'cycle') {
        log('Cycle cimier en cours, attendez la fin', 'warning');
        return false;
    }
    if (cimierState === 'cooldown') {
        const remaining = cimier?.remaining_quiet_s !== undefined
            ? cimier.remaining_quiet_s.toFixed(0)
            : '?';
        log(`Anti-rebond cimier actif (${remaining}s), réessayez`, 'warning');
        return false;
    }
    if (cimierState === 'error') {
        const err = cimier?.error_message || 'inconnue';
        log(`Cimier en erreur : ${err}. Tracking annulé.`, 'error');
        return false;
    }

    // cimierState === 'closed' → cascade ouverture.
    log('Cimier fermé : ouverture avant démarrage du suivi…', 'info');
    const openResult = await apiCall('/api/cimier/open/', 'POST');
    if (openResult && openResult.error) {
        log(`Échec ouverture cimier : ${openResult.error}. Tracking annulé.`, 'error');
        return false;
    }

    // Polling 1 s jusqu'à state="open", timeout 30 s. Réutilise le store
    // mis à jour par pollCimierStatus (pas de polling parallèle).
    for (let i = 0; i < 30; i++) {
        await new Promise((r) => setTimeout(r, 1000));
        const current = Alpine.store('dashboard').cimier?.state;
        if (current === 'open') return true;
        if (current === 'error') {
            const err = Alpine.store('dashboard').cimier?.error_message || 'inconnue';
            log(`Cimier en erreur pendant ouverture : ${err}. Tracking annulé.`, 'error');
            return false;
        }
    }

    log('Timeout : cimier non ouvert après 30 s. Tracking annulé.', 'error');
    return false;
}

// =========================================================================
// Cimier — Automatisation lifecycle session (v6.0 Phase 4 sub-plan 04-02)
// =========================================================================

// Push une entrée dans la timeline notifications cimier (FIFO, max 50).
// level ∈ {'INFO','WARNING','ERROR'}.
function pushCimierTimeline(level, message) {
    const store = Alpine.store('dashboard');
    if (!store.cimierTimeline) store.cimierTimeline = [];
    cimierTimelineSeq += 1;
    const now = new Date();
    store.cimierTimeline.unshift({
        id: cimierTimelineSeq,
        level,
        message,
        timeLabel: now.toLocaleTimeString('fr-FR', { hour12: false })
    });
    if (store.cimierTimeline.length > 50) {
        store.cimierTimeline.length = 50;
    }
}

// Formate une durée en ms restantes en libellé compact « Xh Ymin » ou « Ymin Zs »
// pour les fenêtres < 1 min, identique au pattern countdown méridien dynamique
// adopté en v5.6 P2 (décision session 2026-04-27).
function formatRemainingMs(ms) {
    if (ms == null || ms <= 0) return null;
    const totalSec = Math.floor(ms / 1000);
    const hours = Math.floor(totalSec / 3600);
    const minutes = Math.floor((totalSec % 3600) / 60);
    if (hours > 0) return `${hours}h ${minutes.toString().padStart(2, '0')}min`;
    if (minutes > 0) return `${minutes}min ${(totalSec % 60).toString().padStart(2, '0')}s`;
    return `${totalSec}s`;
}

// Recalcule le libellé contextualisé du countdown selon mode + fenêtre.
// 4 cas : manual, semi (close-only), full (open puis close), hors-fenêtre.
// Référence AC-3 du PLAN-04-02. Comparaisons en epoch ms UTC (Date.now()) —
// pas de mélange UTC / local (rigueur cohérente avec décision v5.9 P2 sur datetime).
function recomputeAutomationCountdown() {
    const store = Alpine.store('dashboard');
    const mode = store.automationMode;

    if (mode === 'manual') {
        store.automationCountdownLabel = 'Mode manuel — auto désactivée';
        return;
    }

    const now = Date.now();
    const openMs = store.automationNextOpenAt ? Date.parse(store.automationNextOpenAt) : NaN;
    const closeMs = store.automationNextCloseAt ? Date.parse(store.automationNextCloseAt) : NaN;
    const openValid = Number.isFinite(openMs) && openMs > now;
    const closeValid = Number.isFinite(closeMs) && closeMs > now;

    if (mode === 'semi') {
        if (closeValid) {
            store.automationCountdownLabel = `Fermeture auto dans ${formatRemainingMs(closeMs - now)}`;
        } else {
            // Fallback rare : le calcul backend n'a pas (encore) abouti.
            store.automationCountdownLabel = 'Calcul des éphémérides…';
        }
        return;
    }

    if (mode === 'full') {
        if (openValid && (!closeValid || openMs < closeMs)) {
            store.automationCountdownLabel = `Ouverture auto dans ${formatRemainingMs(openMs - now)}`;
        } else if (closeValid) {
            store.automationCountdownLabel = `Fermeture auto dans ${formatRemainingMs(closeMs - now)}`;
        } else {
            store.automationCountdownLabel = 'Calcul des éphémérides…';
        }
        return;
    }

    // Mode inconnu (rétro-compat / corruption) — fallback safe.
    store.automationCountdownLabel = '';
}

// Hydratation du sélecteur mode (source vérité = data/config.json côté backend).
// Appelée au boot ET sur intervalle (30 s) pour capter une éventuelle modif
// venue d'un autre onglet/device.
// Utilise la vue 04-01 enrichie post-smoke : retourne {mode, service_mode,
// restart_required, next_open_at, next_close_at}.
async function fetchAutomationState() {
    try {
        const data = await apiCall('/api/cimier/automation/');
        if (!data || data.error) return;
        const store = Alpine.store('dashboard');
        if (data.mode && ['manual', 'semi', 'full'].includes(data.mode)) {
            // Si l'user vient de POSTer un mode (verrou actif), on ne contredit
            // pas tant que le backend ne confirme pas le choix.
            if (lastUserSelectedMode === null) {
                store.automationMode = data.mode;
            } else if (lastUserSelectedMode === data.mode) {
                store.automationMode = data.mode;
                lastUserSelectedMode = null;
            }
            // Si data.mode != lastUserSelectedMode : on garde le choix user
            // (verrou — le backend reflète désormais config.json donc ça ne
            // devrait normalement pas arriver, mais belt-and-suspenders).
        }
        store.automationNextOpenAt = data.next_open_at || null;
        store.automationNextCloseAt = data.next_close_at || null;
        recomputeAutomationCountdown();
    } catch (_e) {
        // Silencieux : retry au prochain cycle.
    }
}

// Persiste un nouveau mode auto via POST /api/cimier/automation/.
// Sur 200 : timeline INFO + hint « Redémarrage cimier_service requis » 8s.
// Sur erreur : timeline ERROR + restore sélecteur sur valeur précédente.
// Exposée en window.* pour le @change Alpine du <select>.
async function updateAutomationMode(newMode) {
    const store = Alpine.store('dashboard');
    const previousMode = store.cimier?.mode || store.automationMode;

    if (!['manual', 'semi', 'full'].includes(newMode)) {
        pushCimierTimeline('ERROR', `Mode auto invalide : ${newMode}`);
        store.automationMode = previousMode;
        return;
    }

    const result = await apiCall('/api/cimier/automation/', 'POST', { mode: newMode });

    if (result && result.applied) {
        const labels = { manual: 'Manuel', semi: 'Semi-auto', full: 'Full auto' };
        pushCimierTimeline('INFO', `Mode auto → ${labels[newMode]} (prise en compte au prochain tick, max 60s)`);
        log(`Cimier : mode auto changé à ${labels[newMode]}`, 'info');

        // Pose le verrou utilisateur : pollCimierStatus n'écrasera pas le sélecteur
        // tant que le service ne rapporte pas ce mode. Le hot-reload du scheduler
        // (Phase 4 fix UX) propage automatiquement le mode au prochain tick (60s).
        lastUserSelectedMode = newMode;
        store.automationMode = newMode;

        store.automationRestartHint = '⏳ Application au prochain tick (max 60 s)';
        if (automationRestartHintTimeout) clearTimeout(automationRestartHintTimeout);
        automationRestartHintTimeout = setTimeout(() => {
            Alpine.store('dashboard').automationRestartHint = '';
            automationRestartHintTimeout = null;
        }, 8000);
    } else {
        const err = (result && (result.error || result.detail)) || 'erreur inconnue';
        pushCimierTimeline('ERROR', `Changement mode auto échoué : ${err}`);
        log(`Cimier : changement mode auto échoué (${err})`, 'error');
        // Restore le sélecteur sur l'ancienne valeur (le x-model sera réajusté
        // à la prochaine hydratation par pollCimierStatus, mais on remet tout de
        // suite pour éviter un flash visuel).
        store.automationMode = previousMode;
    }
}
window.updateAutomationMode = updateAutomationMode;

// Ferme la modale parking et nettoie le compteur (pattern modale fermeture cimier).
function closeParkingConfirmModal() {
    const store = Alpine.store('dashboard');
    store.parkingConfirmVisible = false;
    store.parkingConfirmObject = null;
    store.parkingConfirmCountdown = 0;
    if (parkingConfirmInterval) {
        clearInterval(parkingConfirmInterval);
        parkingConfirmInterval = null;
    }
}

// Bouton Parking session : si tracking actif, ouvre la modale de confirmation
// (countdown 3 s anti-clic-fantôme) ; sinon, action immédiate.
// Pattern incident NGC 3675 (v5.12.1) + modale fermeture cimier (Phase 2 sub-plan 01).
function triggerParkingSession() {
    const trackingActive = ['tracking', 'initializing'].includes(state.status)
                           && state.trackingObject;
    if (!trackingActive) {
        executeParkingSession();
        return;
    }

    const store = Alpine.store('dashboard');
    store.parkingConfirmObject = state.trackingObject;
    store.parkingConfirmCountdown = 3;
    store.parkingConfirmVisible = true;

    if (parkingConfirmInterval) clearInterval(parkingConfirmInterval);
    parkingConfirmInterval = setInterval(() => {
        const remaining = Alpine.store('dashboard').parkingConfirmCountdown - 1;
        Alpine.store('dashboard').parkingConfirmCountdown = Math.max(0, remaining);
        if (remaining <= 0) {
            clearInterval(parkingConfirmInterval);
            parkingConfirmInterval = null;
        }
    }, 1000);
}

// Lance effectivement la séquence parking session via POST /api/cimier/parking-session/
// (backend best-effort 3 IPC : tracking_stop + GOTO 45° + close cimier — v6.0 sub-plan 04-01).
// Démarre un watcher de progression qui surveille motor.status + cimier.state pour
// donner un feedback étape par étape côté UI (banner + timeline).
async function executeParkingSession() {
    log('Parking session : séquence stop + GOTO 45° + close cimier demandée', 'info');
    pushCimierTimeline('INFO', 'Parking session : séquence demandée');

    const store = Alpine.store('dashboard');
    // Reset état banner.
    store.parkingInProgress = true;
    store.parkingStepTracking = 'pending';
    store.parkingStepGoto = 'pending';
    store.parkingStepCimier = 'pending';
    store.parkingStartedAt = Date.now();
    parkingLastObservedPosition = null;

    const result = await apiCall('/api/cimier/parking-session/', 'POST');
    if (result && result.error && !result.applied) {
        const msg = result.error || result.detail || 'erreur';
        log(`Parking session : échec (${msg})`, 'error');
        pushCimierTimeline('ERROR', `Parking session échouée : ${msg}`);
        store.parkingInProgress = false;
        return;
    }

    // Hydrate la cible depuis la réponse backend (peut différer de 45° si
    // override config parking_target_azimuth_deg). Default 45° en fallback.
    if (result && typeof result.parking_target_deg === 'number') {
        store.parkingTargetDeg = result.parking_target_deg;
    } else {
        store.parkingTargetDeg = 45;
    }

    // Étape 1 (immédiate) : tracking_stop OK selon backend.
    if (result && result.tracking_stopped) {
        store.parkingStepTracking = 'done';
        pushCimierTimeline('INFO', '1/3 ✓ Tracking arrêté');
    } else {
        pushCimierTimeline('WARNING', '1/3 ⚠ Tracking_stop IPC échoué');
    }

    // Étape 2 (en cours) : GOTO émis, on attend que motor passe par
    // initializing/idle ET position ≈ target.
    if (result && result.goto_45_sent) {
        store.parkingStepGoto = 'in_progress';
        pushCimierTimeline('INFO', `2/3 ⏳ GOTO ${store.parkingTargetDeg}° en cours…`);
    } else {
        store.parkingStepGoto = 'failed';
        pushCimierTimeline('WARNING', `2/3 ⚠ GOTO ${store.parkingTargetDeg}° IPC échoué`);
    }

    // Étape 3 (en cours) : close cimier émis, on attend cimier.state == 'closed'.
    // Détection d'un service cimier inactif (status stale > 90s ou absent) :
    // dans ce cas on skip l'attente — le watcher timeoutait sinon à 2 min sans
    // gain (ex: machine dev avec cimier.enabled=false).
    const cimierLastUpdate = store.cimier?.last_update;
    const cimierIsStale = !cimierLastUpdate ||
        !Number.isFinite(Date.parse(cimierLastUpdate)) ||
        (Date.now() - Date.parse(cimierLastUpdate)) > 90_000;
    if (result && result.cimier_close_sent && !cimierIsStale) {
        store.parkingStepCimier = 'cycle';
        pushCimierTimeline('INFO', '3/3 ⏳ Fermeture cimier en cours…');
    } else if (cimierIsStale) {
        // Cimier service inactif (typiquement dev avec cimier.enabled=false)
        // → la commande a été écrite mais ne sera jamais consommée. On marque
        // l'étape comme « skip » (pas failed) avec un message INFO calme.
        store.parkingStepCimier = 'skipped';
        pushCimierTimeline('INFO', '3/3 ⊘ Cimier service inactif — étape passée');
    } else {
        store.parkingStepCimier = 'failed';
        pushCimierTimeline('ERROR', '3/3 ⚠ Close cimier IPC échoué');
    }

    // Démarre le watcher de progression (1 Hz, max 120 s = 2 min timeout).
    if (parkingWatcherInterval) clearInterval(parkingWatcherInterval);
    parkingWatcherInterval = setInterval(checkParkingProgress, 1000);
}

// Watcher tick : observe motor.status / position + cimier.state pour conclure
// chaque étape du parking. Timeout 120 s (2 min) max.
function checkParkingProgress() {
    const store = Alpine.store('dashboard');
    if (!store.parkingInProgress) {
        clearInterval(parkingWatcherInterval);
        parkingWatcherInterval = null;
        return;
    }

    const elapsedMs = Date.now() - (store.parkingStartedAt || 0);
    const target = store.parkingTargetDeg;

    // Étape 2 : motor a fini son GOTO ? On considère terminé si :
    //   - motor.status est 'idle' (plus de mouvement),
    //   - et la position est proche de la cible (±2°).
    if (store.parkingStepGoto === 'in_progress') {
        const pos = state.position;
        const motorStatus = state.status;
        if (motorStatus === 'idle' && Number.isFinite(pos)) {
            const delta = Math.abs(((pos - target + 540) % 360) - 180);
            if (delta < 2.0) {
                store.parkingStepGoto = 'done';
                pushCimierTimeline('INFO', `2/3 ✓ Coupole à ${pos.toFixed(1)}° (cible ${target}°)`);
            }
        }
    }

    // Étape 3 : cimier fermé ?
    if (store.parkingStepCimier === 'cycle') {
        const cimierState = store.cimier?.state;
        if (cimierState === 'closed') {
            store.parkingStepCimier = 'closed';
            pushCimierTimeline('INFO', '3/3 ✓ Cimier fermé');
        } else if (cimierState === 'error') {
            store.parkingStepCimier = 'failed';
            pushCimierTimeline('ERROR', '3/3 ⚠ Cimier en erreur');
        }
    }

    // Conclusion : toutes les étapes terminales atteintes ?
    // Étape 2 terminale = 'done' | 'failed'.
    // Étape 3 terminale = 'closed' | 'failed' | 'skipped' (service cimier inactif).
    const allDone = store.parkingStepGoto === 'done' || store.parkingStepGoto === 'failed';
    const cimierDone = ['closed', 'failed', 'skipped'].includes(store.parkingStepCimier);

    if (allDone && cimierDone) {
        const elapsedSec = Math.round(elapsedMs / 1000);
        const fullSuccess = store.parkingStepGoto === 'done' && store.parkingStepCimier === 'closed';
        const partialOk = store.parkingStepGoto === 'done' && store.parkingStepCimier === 'skipped';
        if (fullSuccess) {
            pushCimierTimeline('INFO', `✓ Parking terminé en ${elapsedSec}s`);
            log(`Parking session terminé en ${elapsedSec}s`, 'success');
        } else if (partialOk) {
            pushCimierTimeline('INFO', `✓ Parking coupole terminé en ${elapsedSec}s (cimier non vérifié)`);
            log(`Parking : coupole à 45° en ${elapsedSec}s, cimier service inactif`, 'info');
        } else {
            pushCimierTimeline('WARNING', `Parking terminé partiellement (${elapsedSec}s) — vérifier les étapes`);
        }
        store.parkingInProgress = false;
        clearInterval(parkingWatcherInterval);
        parkingWatcherInterval = null;
        return;
    }

    // Timeout 2 min : abandon du watcher (la séquence peut continuer côté backend).
    if (elapsedMs > 120_000) {
        pushCimierTimeline('WARNING', 'Parking : timeout watcher 2 min — état final non vérifié');
        store.parkingInProgress = false;
        clearInterval(parkingWatcherInterval);
        parkingWatcherInterval = null;
    }
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
                addLog(`⚠️ ALERTE: Encodeur figé depuis ${duration}s - vérifier connexion SPI!`, 'error');
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

// Grise/réactive les boutons de déplacement manuel + GOTO angulaire.
// STOP reste toujours actif (sécurité).
// Garde-fou anti-erreur (incident NGC 3675 24/04/2026) : empêche un GOTO ou JOG
// involontaire pendant tracking actif (clic fantôme sur écran tactile).
function setManualControlsDisabled(disabled) {
    const buttons = [
        elements.btnJogCCW10,
        elements.btnJogCCW1,
        elements.btnJogCW1,
        elements.btnJogCW10,
        elements.btnContCCW,
        elements.btnContCW,
        elements.btnGoto,
    ];
    for (const btn of buttons) {
        if (btn) btn.disabled = disabled;
    }
    if (elements.gotoAngle) elements.gotoAngle.disabled = disabled;
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

        Alpine.store('dashboard').trackingVisible = true;
        elements.trackingInfo.classList.remove('hidden');
        elements.btnStartTracking.disabled = true;
        elements.btnStopTracking.disabled = false;
        setManualControlsDisabled(true);

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
        elements.trackingMode.className = `hidden mode-${mode}`;
        // Cartouche MODE retiré du dashboard (vitesse unique v5.10) — le bloc
        // hidden tracking-mode reste pour le bookkeeping JS interne uniquement.

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

        // Cartouche méridien (ne pas masquer si absent — garder état précédent)
        if (info.meridian_seconds !== undefined) {
            updateMeridianCartouche(info.meridian_seconds, info.meridian_time);
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
        Alpine.store('dashboard').trackingVisible = false;
        elements.trackingInfo.classList.add('hidden');
        elements.btnStartTracking.disabled = !state.searchedObject;
        elements.btnStopTracking.disabled = true;
        setManualControlsDisabled(false);

        // Arrêter le countdown quand pas de suivi
        stopCountdown();
        state.trackingInfo = {};

        // Cacher le timer widget
        const timerWidget = document.getElementById('timer-widget');
        if (timerWidget) timerWidget.classList.add('hidden');

        // Réinitialiser les cartouches CORRECTIONS (cartouche MODE retiré v6.3.0).
        if (elements.correctionsCount) {
            elements.correctionsCount.textContent = '0';
        }
        if (elements.correctionsTotal) {
            elements.correctionsTotal.textContent = '0.00°';
        }

        // Masquer le cartouche méridien seulement si aucun objet recherché
        if (!state.searchedObject) {
            updateMeridianCartouche(null);
        }

        // Reset du flag de sync pour permettre la reconnexion à une future session
        // (permet de sync si un suivi démarre depuis un autre appareil)
        initialSyncDone = false;
    }
}

// Mise à jour du cartouche méridien
function updateMeridianCartouche(meridianSeconds, meridianTime) {
    const cart = elements.meridianCartouche;
    const val = elements.meridianValue;
    if (!cart || !val) return;

    // Supprimer toutes les classes d'état
    cart.classList.remove('meridian-safe', 'meridian-warning', 'meridian-danger',
                          'meridian-critical', 'meridian-passed', 'hidden');

    if (meridianSeconds === null || meridianSeconds === undefined) {
        cart.classList.add('hidden');
        return;
    }

    const sec = meridianSeconds;
    const minutes = sec / 60;
    const timeStr = meridianTime || '';

    if (sec <= 0) {
        // Méridien passé
        cart.classList.add('meridian-passed');
        val.textContent = `${timeStr} — PASSÉ`;
    } else if (minutes < 5) {
        cart.classList.add('meridian-critical');
        val.textContent = `${timeStr} (dans ${formatMeridianTime(sec)})`;
    } else if (minutes < 15) {
        cart.classList.add('meridian-danger');
        val.textContent = `${timeStr} (dans ${formatMeridianTime(sec)})`;
    } else if (minutes < 30) {
        cart.classList.add('meridian-warning');
        val.textContent = `${timeStr} (dans ${formatMeridianTime(sec)})`;
    } else {
        cart.classList.add('meridian-safe');
        val.textContent = `${timeStr} (dans ${formatMeridianTime(sec)})`;
    }
}

function formatMeridianTime(totalSeconds) {
    const h = Math.floor(totalSeconds / 3600);
    const m = Math.floor((totalSeconds % 3600) / 60);
    if (h > 0) {
        return `${h}h${String(m).padStart(2, '0')}`;
    }
    return `${m}min`;
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

// Dessiner la flèche de direction calculée (🎯) avec décompte au-dessus du compass
function drawTelescope(ctx, cx, cy, angle, countdownValue, timerColor) {
    // Si pas d'angle de tracking, utiliser la position coupole
    const teleAngle = (angle !== undefined && angle !== null) ? angle : state.position;
    const teleRad = teleAngle * Math.PI / 180;

    // Dimensions de la flèche
    const arrowLength = 65;
    const arrowHeadSize = 12;
    const arrowWidth = 3;

    // Rayon du centre pour la cible 🎯
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

    // === CERCLE CENTRAL avec 🎯 ===
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

    // === 🎯 centré, occupant tout le cercle ===
    ctx.save();
    const emojiSize = centerRadius * 1.6;
    ctx.font = `${emojiSize}px serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'alphabetic';
    ctx.fillText('🎯', cx, cy + emojiSize * 0.35);
    ctx.restore();

    // === Décompte affiché au-dessus du compass (élément HTML) ===
    const countdownEl = document.getElementById('compass-countdown');
    if (countdownEl) {
        const hasTimer = countdownValue !== undefined && countdownValue !== null && countdownValue !== '--';
        if (hasTimer) {
            let timerText;
            if (typeof countdownValue === 'number') {
                timerText = Math.round(countdownValue) + 's';
            } else {
                timerText = String(countdownValue);
            }
            countdownEl.textContent = `⏱ ${timerText}`;
            countdownEl.style.color = timerColor || '#4da6ff';
        } else {
            countdownEl.textContent = '';
        }
    }
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

    // CIBLE (direction calculée) en vert
    ctx.fillStyle = '#4ade80';
    ctx.fillText('● CIBLE (🎯)', x - 45, y);

    // CIMIER en ambre (aligné avec cartouche CSS --accent-amber)
    ctx.fillStyle = '#d4a055';
    ctx.fillText('● CIMIER', x + 45, y);
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
    // Utiliser le store Alpine.js pour les logs réactifs
    const store = Alpine.store('dashboard');
    if (store) {
        store.addLog(message, type);
    }
}

// Alias pour les appels legacy (addLog utilisé dans updateTrackingDisplay)
function addLog(message, type = 'info') {
    log(message, type);
}

// =========================================================================
// Update Notification System
// =========================================================================

// Update modal: éléments gérés via Alpine.js store + getElementById ponctuel

// Store update data
let updateData = null;

/**
 * Check for updates.
 * @param {boolean} showUpToDate - If true, show feedback when already up to date
 */
async function checkForUpdates(showUpToDate = false) {
    try {
        const response = await fetch('/api/health/update/check/');
        if (!response.ok) {
            console.warn('Update check failed:', response.status);
            return;
        }

        const result = await response.json();

        if (result.error) {
            console.warn('Update check error:', result.error);
            return;
        }

        if (result.update_available) {
            updateData = result;
            showUpdateBadge();
            showUpdateModal(result);
            log(`Mise a jour disponible: ${result.commits_behind} commit(s)`, 'info');
        } else {
            hideUpdateBadge();
            if (showUpToDate) {
                log('Systeme a jour', 'success');
            }
        }
    } catch (error) {
        console.warn('Update check exception:', error);
    }
}

/**
 * Manual update check triggered by the header button.
 * Shows loading state and feedback.
 */
async function manualCheckForUpdates() {
    const btn = elements.btnCheckUpdate;
    if (!btn) return;

    // Set loading state
    btn.classList.add('checking');
    btn.disabled = true;

    try {
        await checkForUpdates(true);
    } finally {
        // Remove loading state
        btn.classList.remove('checking');
        btn.disabled = false;
    }
}

/**
 * Show the update badge on the header button.
 */
function showUpdateBadge() {
    if (elements.updateBadge) elements.updateBadge.classList.remove('hidden');
    if (elements.btnCheckUpdate) elements.btnCheckUpdate.classList.add('has-update');
}

/**
 * Hide the update badge on the header button.
 */
function hideUpdateBadge() {
    if (elements.updateBadge) elements.updateBadge.classList.add('hidden');
    if (elements.btnCheckUpdate) elements.btnCheckUpdate.classList.remove('has-update');
}

/**
 * Show the update modal with version info.
 * @param {Object} data - Update check result
 */
function showUpdateModal(data) {
    const store = Alpine.store('dashboard');
    const el = (id) => document.getElementById(id);

    // Populate version info
    const currentVersion = el('update-current-version');
    const currentCommit = el('update-current-commit');
    const newVersion = el('update-new-version');
    const commitsBehind = el('update-commits-behind');

    if (currentVersion) currentVersion.textContent = `v${data.local_version}`;
    if (currentCommit) currentCommit.textContent = `(${data.local_commit})`;
    if (newVersion) {
        const ver = data.remote_version && data.remote_version !== 'unknown'
            ? `v${data.remote_version}` : data.remote_commit;
        newVersion.textContent = ver;
    }
    if (commitsBehind) commitsBehind.textContent = `+${data.commits_behind} commit(s)`;

    // Populate commit messages (toujours remplies, affichées seulement après clic "Détails")
    const changesList = el('update-changes-list');
    if (changesList) {
        changesList.innerHTML = '';
        (data.commit_messages || []).forEach(msg => {
            const li = document.createElement('li');
            li.textContent = msg;
            changesList.appendChild(li);
        });
    }

    // Populate files changed
    const filesList = el('update-files-list');
    const filesBlock = el('update-files-changed');
    if (filesList && filesBlock) {
        filesList.innerHTML = '';
        const files = data.files_changed || [];
        if (files.length > 0) {
            files.forEach(f => {
                const li = document.createElement('li');
                li.textContent = f;
                filesList.appendChild(li);
            });
            filesBlock.classList.remove('hidden');
        } else {
            filesBlock.classList.add('hidden');
        }
    }

    // Avertissement config utilisateur impactée
    const configWarning = el('update-config-warning');
    const configList = el('update-config-affected-list');
    const affected = data.config_files_affected || [];
    if (configWarning && configList) {
        configList.innerHTML = '';
        if (affected.length > 0) {
            affected.forEach(f => {
                const li = document.createElement('li');
                li.innerHTML = `<code>${f}</code>`;
                configList.appendChild(li);
            });
            configWarning.classList.remove('hidden');
        } else {
            configWarning.classList.add('hidden');
        }
    }

    // Détails dépliables : cachés par défaut, bouton "Voir les détails" toggle
    const details = el('update-details');
    if (details) details.classList.add('hidden');
    const btnDetails = el('btn-update-details');
    if (btnDetails) btnDetails.textContent = 'Voir les détails';

    // Reset state + show modal
    store.updateShowProgress = false;
    store.updateShowError = false;
    store.updateButtonsDisabled = false;
    store.updateModalVisible = true;

    // v5.12.0 : reset des boutons + panneau diff config (caché à l'ouverture)
    document.getElementById('btn-update-now')?.classList.remove('hidden');
    document.getElementById('btn-update-keep-config')?.classList.add('hidden');
    document.getElementById('btn-update-reset-config')?.classList.add('hidden');
    document.getElementById('update-config-diff-panel')?.classList.add('hidden');
}

/**
 * Toggle the details section (commits + files changed).
 */
function toggleUpdateDetails() {
    const details = document.getElementById('update-details');
    const btn = document.getElementById('btn-update-details');
    if (!details || !btn) return;
    const hidden = details.classList.toggle('hidden');
    btn.textContent = hidden ? 'Voir les détails' : 'Masquer les détails';
}

/**
 * Hide the update modal (dismiss until next page load).
 */
function hideUpdateModal() {
    Alpine.store('dashboard').updateModalVisible = false;
}

/**
 * Préparation MàJ (v5.12.0) — détecte un diff config.json avant de lancer.
 *
 * Si le `data/config.json` local diverge de `origin/main`, présente le diff
 * dans le panneau dédié et remplace le bouton "Mettre à jour" par 2 choix :
 *   - Garder ma config   → applyUpdate('keep')
 *   - Utiliser le dépôt → applyUpdate('reset')
 *
 * Sinon (pas de diff, ou erreur fetch), enchaîne directement sur applyUpdate('keep').
 */
async function prepareUpdate() {
    const store = Alpine.store('dashboard');
    store.updateButtonsDisabled = true;

    let diff = null;
    try {
        const response = await fetch('/api/health/update/config_diff/');
        if (response.ok) diff = await response.json();
    } catch (error) {
        console.warn('config_diff fetch exception:', error);
    }
    store.updateButtonsDisabled = false;

    const hasDiff = diff && diff.has_diff && Array.isArray(diff.diffs) && diff.diffs.length > 0;
    if (!hasDiff) {
        // Pas de divergence (ou endpoint en erreur) → flux simple, stratégie keep par défaut
        await applyUpdate('keep');
        return;
    }

    // Affiche le panneau diff + remplace les boutons
    renderConfigDiffPanel(diff.diffs);
    document.getElementById('btn-update-now')?.classList.add('hidden');
    document.getElementById('btn-update-keep-config')?.classList.remove('hidden');
    document.getElementById('btn-update-reset-config')?.classList.remove('hidden');
    log(`config.json diverge — ${diff.diffs.length} différence(s) à arbitrer`, 'warning');
}

/**
 * Render le panneau de diff config (liste clé/valeur avant→après).
 */
function renderConfigDiffPanel(diffs) {
    const panel = document.getElementById('update-config-diff-panel');
    const list = document.getElementById('update-config-diff-list');
    if (!panel || !list) return;
    list.innerHTML = '';
    diffs.forEach(d => {
        const li = document.createElement('li');
        const local = d.local === null ? '(absent)' : JSON.stringify(d.local);
        const upstream = d.upstream === null ? '(absent)' : JSON.stringify(d.upstream);
        const op = {added: '＋', removed: '－', modified: '⇄'}[d.op] || d.op;
        li.innerHTML = `<code>${d.path}</code> <em>${op}</em> ` +
                       `<span class="diff-local">${local}</span> ` +
                       `→ <span class="diff-upstream">${upstream}</span>`;
        list.appendChild(li);
    });
    panel.classList.remove('hidden');
}

/**
 * Apply the update.
 * Lance le script côté serveur (détaché) puis poll /api/health/update/status/
 * jusqu'à done=true. Recharge la page quand Django revient.
 *
 * @param {"keep"|"reset"} configStrategy - défaut "keep"
 */
async function applyUpdate(configStrategy = 'keep') {
    const store = Alpine.store('dashboard');

    store.updateShowProgress = true;
    store.updateShowError = false;
    store.updateButtonsDisabled = true;
    updateProgressUI({phase: 'starting', step: 0, total: 5, message: 'Lancement...'});
    log(`Mise a jour lancée (config_strategy=${configStrategy})`, 'info');

    try {
        const response = await fetch('/api/health/update/apply/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ config_strategy: configStrategy }),
        });

        const result = await response.json();
        if (!result.success) {
            showUpdateError(result.error || 'Erreur inconnue');
            log(`Erreur lancement MàJ : ${result.error}`, 'error');
            return;
        }
        log(`Script détaché : ${result.detach_info}`, 'success');
    } catch (error) {
        // Django ne répond plus = il est peut-être déjà en cours de restart
        // Le script écrit dans un fichier, on va poll quand même.
        log('Réponse API perdue — on poll le status tout de même', 'warning');
    }

    // Polling du status du script (survit aux restarts Django)
    await pollUpdateStatus();
}

/**
 * Poll /api/health/update/status/ toutes les 1s, MAX 4 minutes.
 *
 * Gère trois cas :
 *   - Status success=true, done=true  → reload page
 *   - Status success=false, done=true → afficher erreur
 *   - Fetch échoue (Django down pendant restart) → on continue de poll
 */
async function pollUpdateStatus() {
    const maxAttempts = 240;  // 240 * 1s = 4 min
    let consecutiveFailures = 0;
    let lastStatus = null;

    for (let attempt = 0; attempt < maxAttempts; attempt++) {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 2000);
            const response = await fetch('/api/health/update/status/', {
                signal: controller.signal
            });
            clearTimeout(timeoutId);

            if (response.ok) {
                const status = await response.json();
                consecutiveFailures = 0;
                lastStatus = status;
                updateProgressUI(status);

                if (status.done) {
                    if (status.success === true) {
                        log('Mise à jour terminée — rechargement...', 'success');
                        await sleep(1500);  // laisse Django finir son restart
                        window.location.reload();
                        return;
                    } else if (status.success === false) {
                        showUpdateError(status.error || status.message || 'Échec de la MàJ');
                        log(`Échec MàJ : ${status.error || status.message}`, 'error');
                        return;
                    }
                    // done=true mais success=null → état bizarre, idle
                    if (status.phase === 'idle') {
                        // Aucune MàJ en cours — cas limite après timeout ancien status
                        // On continue de poll un peu au cas où le script démarre tard
                    }
                }
            } else {
                consecutiveFailures += 1;
            }
        } catch (e) {
            // Django down (probablement restart en cours) — on continue
            consecutiveFailures += 1;
            updateProgressUI({
                phase: lastStatus?.phase || 'restart',
                step: lastStatus?.step || 5,
                total: 5,
                message: 'Redémarrage de Django...'
            });
        }
        await sleep(1000);
    }

    // Timeout : Django n'est pas revenu en 4 min
    showUpdateError('Timeout : Django ne répond plus après 4 minutes. '
        + 'Consultez logs/update.log et rechargez la page manuellement.');
}

const PHASE_LABELS = {
    starting: 'Démarrage',
    stop_services: 'Arrêt services',
    fetch: 'Récupération code',
    deps: 'Dépendances',
    services: 'Installation services',
    restart: 'Redémarrage',
    done: 'Terminé',
    error: 'Erreur',
    idle: 'Inactif',
};

/**
 * Met à jour la barre de progression et les libellés selon le status reçu.
 */
function updateProgressUI(status) {
    const phaseEl = document.getElementById('update-progress-phase');
    const stepEl = document.getElementById('update-progress-step');
    const textEl = document.getElementById('update-progress-text');
    const barEl = document.getElementById('update-progress-bar');

    const total = status.total || 5;
    const step = status.step || 0;
    const percent = Math.min(100, Math.round((step / total) * 100));

    if (phaseEl) phaseEl.textContent = PHASE_LABELS[status.phase] || status.phase || '--';
    if (stepEl) stepEl.textContent = `${step}/${total}`;
    if (textEl) textEl.textContent = status.message || '...';
    if (barEl) barEl.style.width = `${percent}%`;
}

/**
 * Show an error message in the update modal.
 */
function showUpdateError(message) {
    const store = Alpine.store('dashboard');
    store.updateShowProgress = false;
    store.updateShowError = true;
    store.updateButtonsDisabled = false;
    const errorText = document.getElementById('update-error-text');
    if (errorText) errorText.textContent = message;
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
    const btnLater = document.getElementById('btn-update-later');
    const btnNow = document.getElementById('btn-update-now');
    const btnDetails = document.getElementById('btn-update-details');
    const btnKeep = document.getElementById('btn-update-keep-config');
    const btnReset = document.getElementById('btn-update-reset-config');
    if (btnLater) btnLater.addEventListener('click', hideUpdateModal);
    // v5.12.0 : "Mettre à jour" passe par prepareUpdate() qui détecte un diff
    // config.json et bascule vers les 2 boutons keep/reset si nécessaire.
    if (btnNow) btnNow.addEventListener('click', () => prepareUpdate());
    if (btnKeep) btnKeep.addEventListener('click', () => applyUpdate('keep'));
    if (btnReset) btnReset.addEventListener('click', () => applyUpdate('reset'));
    if (btnDetails) btnDetails.addEventListener('click', toggleUpdateDetails);

    // Header update check button
    if (elements.btnCheckUpdate) {
        elements.btnCheckUpdate.addEventListener('click', manualCheckForUpdates);
    }
}

// Initialize update system after page load
document.addEventListener('DOMContentLoaded', () => {
    // Initialize update event listeners
    initUpdateListeners();

    // Check for updates after a short delay (don't block initial load)
    setTimeout(checkForUpdates, 3000);
});
