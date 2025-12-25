/**
 * DriftApp - Page Diagnostic Systeme
 *
 * Rafraichissement automatique des donnees systeme via l'API /api/health/diagnostic/
 */

// Configuration
const REFRESH_INTERVAL = 2000; // 2 secondes
const API_ENDPOINT = '/api/health/diagnostic/';

// Elements DOM (caches au chargement)
let elements = {};

// Timer de rafraichissement
let refreshTimer = null;

/**
 * Initialisation au chargement de la page
 */
document.addEventListener('DOMContentLoaded', () => {
    cacheElements();
    setupEventListeners();
    fetchDiagnostic();
    startAutoRefresh();
});

/**
 * Cache les references aux elements DOM
 */
function cacheElements() {
    elements = {
        // Global
        globalStatus: document.getElementById('global-status'),
        globalStatusDot: document.querySelector('#global-status .status-dot'),
        globalStatusText: document.querySelector('#global-status .status-text'),
        btnRefresh: document.getElementById('btn-refresh'),
        autoRefreshToggle: document.getElementById('auto-refresh-toggle'),
        lastUpdate: document.getElementById('last-update'),

        // Motor Service
        motorCard: document.getElementById('motor-card'),
        motorStatusBadge: document.getElementById('motor-status-badge'),
        motorStatus: document.getElementById('motor-status'),
        motorMode: document.getElementById('motor-mode'),
        motorPosition: document.getElementById('motor-position'),
        motorSimulation: document.getElementById('motor-simulation'),
        motorFileAge: document.getElementById('motor-file-age'),

        // Encoder Daemon
        encoderCard: document.getElementById('encoder-card'),
        encoderStatusBadge: document.getElementById('encoder-status-badge'),
        encoderStatus: document.getElementById('encoder-status'),
        encoderAngle: document.getElementById('encoder-angle'),
        encoderCalibrated: document.getElementById('encoder-calibrated'),
        encoderFileAge: document.getElementById('encoder-file-age'),

        // IPC Files
        ipcStatusFresh: document.getElementById('ipc-status-fresh'),
        ipcStatusContent: document.getElementById('ipc-status-content'),
        ipcEncoderFresh: document.getElementById('ipc-encoder-fresh'),
        ipcEncoderContent: document.getElementById('ipc-encoder-content'),
        ipcCommandFresh: document.getElementById('ipc-command-fresh'),
        ipcCommandContent: document.getElementById('ipc-command-content'),

        // Config
        siteName: document.getElementById('site-name'),
        siteLat: document.getElementById('site-lat'),
        siteLon: document.getElementById('site-lon'),
        siteAlt: document.getElementById('site-alt'),
        motorSteps: document.getElementById('motor-steps'),
        motorMicrosteps: document.getElementById('motor-microsteps'),
        motorGear: document.getElementById('motor-gear'),
        motorDelay: document.getElementById('motor-delay'),
        thresholdFeedback: document.getElementById('threshold-feedback'),
        thresholdLarge: document.getElementById('threshold-large'),
        thresholdProtection: document.getElementById('threshold-protection'),
        thresholdTolerance: document.getElementById('threshold-tolerance'),
        modesTbody: document.getElementById('modes-tbody'),
    };
}

/**
 * Configure les ecouteurs d'evenements
 */
function setupEventListeners() {
    elements.btnRefresh.addEventListener('click', () => {
        elements.btnRefresh.classList.add('spinning');
        fetchDiagnostic();
        setTimeout(() => elements.btnRefresh.classList.remove('spinning'), 500);
    });

    elements.autoRefreshToggle.addEventListener('change', (e) => {
        if (e.target.checked) {
            startAutoRefresh();
        } else {
            stopAutoRefresh();
        }
    });
}

/**
 * Demarre le rafraichissement automatique
 */
function startAutoRefresh() {
    if (refreshTimer) clearInterval(refreshTimer);
    refreshTimer = setInterval(fetchDiagnostic, REFRESH_INTERVAL);
}

/**
 * Arrete le rafraichissement automatique
 */
function stopAutoRefresh() {
    if (refreshTimer) {
        clearInterval(refreshTimer);
        refreshTimer = null;
    }
}

/**
 * Recupere les donnees de diagnostic depuis l'API
 */
async function fetchDiagnostic() {
    try {
        const response = await fetch(API_ENDPOINT);
        const data = await response.json();
        updateUI(data);
    } catch (error) {
        console.error('Erreur fetch diagnostic:', error);
        updateGlobalStatus(false, 'Erreur connexion');
    }
}

/**
 * Met a jour l'interface avec les donnees
 */
function updateUI(data) {
    // Status global
    updateGlobalStatus(data.overall_healthy, data.overall_healthy ? 'Systeme OK' : 'Probleme detecte');

    // Timestamp
    const timestamp = new Date(data.timestamp);
    elements.lastUpdate.textContent = `Derniere mise a jour: ${timestamp.toLocaleTimeString('fr-FR')}`;

    // Composants
    updateMotorService(data.components.motor_service);
    updateEncoderDaemon(data.components.encoder_daemon);

    // Fichiers IPC
    updateIpcFiles(data.ipc);

    // Configuration
    updateConfig(data.config);
}

/**
 * Met a jour le status global
 */
function updateGlobalStatus(healthy, text) {
    elements.globalStatusDot.className = 'status-dot ' + (healthy ? 'healthy' : 'unhealthy');
    elements.globalStatusText.textContent = text;
}

/**
 * Met a jour la section Motor Service
 */
function updateMotorService(motor) {
    const statusClass = motor.healthy ? 'healthy' : (motor.status === 'stale' ? 'stale' : 'unhealthy');

    elements.motorCard.className = 'component-card ' + statusClass;
    elements.motorStatusBadge.className = 'component-status ' + statusClass;
    elements.motorStatusBadge.textContent = motor.healthy ? 'OK' : motor.status.toUpperCase();

    elements.motorStatus.textContent = motor.status;

    if (motor.healthy && motor.details) {
        elements.motorMode.textContent = motor.details.mode || '--';
        elements.motorPosition.textContent = motor.details.position !== null
            ? motor.details.position.toFixed(1) + '°'
            : '--';
        elements.motorSimulation.textContent = motor.details.simulation ? 'Oui' : 'Non';
    } else {
        elements.motorMode.textContent = '--';
        elements.motorPosition.textContent = '--';
        elements.motorSimulation.textContent = '--';
    }

    elements.motorFileAge.textContent = motor.file.exists
        ? formatAge(motor.file.age_sec)
        : 'N/A';
}

/**
 * Met a jour la section Encoder Daemon
 */
function updateEncoderDaemon(encoder) {
    const statusClass = encoder.healthy ? 'healthy' : (encoder.status === 'stale' ? 'stale' : 'unhealthy');

    elements.encoderCard.className = 'component-card ' + statusClass;
    elements.encoderStatusBadge.className = 'component-status ' + statusClass;
    elements.encoderStatusBadge.textContent = encoder.healthy ? 'OK' : encoder.status.toUpperCase();

    elements.encoderStatus.textContent = encoder.status;

    if (encoder.healthy && encoder.details) {
        elements.encoderAngle.textContent = encoder.details.angle !== null
            ? encoder.details.angle.toFixed(1) + '°'
            : '--';
        elements.encoderCalibrated.textContent = encoder.details.calibrated ? 'Oui' : 'Non';
    } else {
        elements.encoderAngle.textContent = '--';
        elements.encoderCalibrated.textContent = '--';
    }

    elements.encoderFileAge.textContent = encoder.file.exists
        ? formatAge(encoder.file.age_sec)
        : 'N/A';
}

/**
 * Met a jour les fichiers IPC
 */
function updateIpcFiles(ipc) {
    // motor_status.json
    updateIpcCard(
        elements.ipcStatusFresh,
        elements.ipcStatusContent,
        ipc.contents.motor_status,
        ipc.freshness.status_file
    );

    // ems22_position.json
    updateIpcCard(
        elements.ipcEncoderFresh,
        elements.ipcEncoderContent,
        ipc.contents.encoder_position,
        ipc.freshness.encoder_file
    );

    // motor_command.json
    updateIpcCard(
        elements.ipcCommandFresh,
        elements.ipcCommandContent,
        ipc.contents.motor_command,
        ipc.freshness.command_file
    );
}

/**
 * Met a jour une carte IPC
 */
function updateIpcCard(freshEl, contentEl, content, freshness) {
    if (!freshness.exists) {
        freshEl.className = 'ipc-freshness missing';
        freshEl.textContent = 'Non trouve';
        contentEl.textContent = '(fichier non trouve)';
    } else if (!freshness.fresh) {
        freshEl.className = 'ipc-freshness stale';
        freshEl.textContent = formatAge(freshness.age_sec);
        contentEl.textContent = content.content
            ? JSON.stringify(content.content, null, 2)
            : content.empty
                ? '(aucune commande en attente)'
                : content.error || '(erreur lecture)';
    } else {
        freshEl.className = 'ipc-freshness fresh';
        freshEl.textContent = formatAge(freshness.age_sec);
        contentEl.textContent = content.content
            ? JSON.stringify(content.content, null, 2)
            : content.empty
                ? '(aucune commande en attente)'
                : content.error || '(vide)';
    }
}

/**
 * Met a jour la configuration
 */
function updateConfig(config) {
    if (config.error) {
        console.error('Erreur config:', config.error);
        return;
    }

    // Site
    if (config.site) {
        elements.siteName.textContent = config.site.nom || '--';
        elements.siteLat.textContent = config.site.latitude ? config.site.latitude + '°' : '--';
        elements.siteLon.textContent = config.site.longitude ? config.site.longitude + '°' : '--';
        elements.siteAlt.textContent = config.site.altitude ? config.site.altitude + 'm' : '--';
    }

    // Moteur
    if (config.moteur) {
        elements.motorSteps.textContent = config.moteur.steps_per_revolution || '--';
        elements.motorMicrosteps.textContent = config.moteur.microsteps || '--';
        elements.motorGear.textContent = config.moteur.gear_ratio ? config.moteur.gear_ratio + ':1' : '--';
        elements.motorDelay.textContent = config.moteur.motor_delay_base
            ? (config.moteur.motor_delay_base * 1000).toFixed(1) + 'ms'
            : '--';
    }

    // Seuils
    if (config.thresholds) {
        elements.thresholdFeedback.textContent = config.thresholds.feedback_min_deg
            ? config.thresholds.feedback_min_deg + '°' : '--';
        elements.thresholdLarge.textContent = config.thresholds.large_movement_deg
            ? config.thresholds.large_movement_deg + '°' : '--';
        elements.thresholdProtection.textContent = config.thresholds.feedback_protection_deg
            ? config.thresholds.feedback_protection_deg + '°' : '--';
        elements.thresholdTolerance.textContent = config.thresholds.default_tolerance_deg
            ? config.thresholds.default_tolerance_deg + '°' : '--';
    }

    // Modes adaptatifs
    if (config.adaptive_modes) {
        let html = '';
        for (const [name, mode] of Object.entries(config.adaptive_modes)) {
            html += `<tr>
                <td>${name}</td>
                <td>${mode.interval_sec}s</td>
                <td>${mode.threshold_deg}°</td>
                <td>${(mode.motor_delay * 1000).toFixed(2)}ms</td>
            </tr>`;
        }
        elements.modesTbody.innerHTML = html || '<tr><td colspan="4">--</td></tr>';
    }
}

/**
 * Formate un age en secondes en texte lisible
 */
function formatAge(seconds) {
    if (seconds === null || seconds === undefined) return '--';
    if (seconds < 1) return '<1s';
    if (seconds < 60) return Math.round(seconds) + 's';
    if (seconds < 3600) return Math.round(seconds / 60) + 'min';
    if (seconds < 86400) return Math.round(seconds / 3600) + 'h';
    return Math.round(seconds / 86400) + 'j';
}
