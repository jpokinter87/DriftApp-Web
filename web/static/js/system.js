/**
 * DriftApp - Page Diagnostic Systeme
 *
 * Rafraichissement automatique des donnees systeme via l'API /api/health/diagnostic/
 * Alpine.store('system') pour status global, auto-refresh et badges composants
 */

// Configuration
const REFRESH_INTERVAL = 2000; // 2 secondes
const API_ENDPOINT = '/api/health/diagnostic/';

// Timer de rafraichissement
let refreshTimer = null;

// Elements DOM (caches au chargement — uniquement ceux non geres par Alpine)
let elements = {};

/**
 * Alpine.js store — pont entre vanilla JS et couche reactive
 */
document.addEventListener('alpine:init', () => {
    Alpine.store('system', {
        // Global status
        globalHealthy: null,
        globalStatusText: 'Chargement...',
        // Auto-refresh
        autoRefresh: true,
        // Motor Service badge
        motor: { badgeText: '--', badgeClass: '', cardClass: '' },
        // Encoder Daemon badge
        encoder: { badgeText: '--', badgeClass: '', cardClass: '' },
    });
});

/**
 * Initialisation au chargement de la page
 */
document.addEventListener('DOMContentLoaded', () => {
    cacheElements();
    setupEventListeners();
    fetchDiagnostic();
    startAutoRefresh();

    // Watch Alpine store autoRefresh pour sync avec polling
    const checkAutoRefresh = () => {
        try {
            const store = Alpine.store('system');
            if (store.autoRefresh && !refreshTimer) {
                startAutoRefresh();
            } else if (!store.autoRefresh && refreshTimer) {
                stopAutoRefresh();
            }
        } catch (e) { /* Alpine pas encore pret */ }
    };
    setInterval(checkAutoRefresh, 500);
});

/**
 * Cache les references aux elements DOM (uniquement ceux non geres par Alpine)
 */
function cacheElements() {
    elements = {
        // Global (refresh button only — status gere par Alpine)
        btnRefresh: document.getElementById('btn-refresh'),
        lastUpdate: document.getElementById('last-update'),

        // Motor Service (detail values — badge gere par Alpine)
        motorStatus: document.getElementById('motor-status'),
        motorMode: document.getElementById('motor-mode'),
        motorPosition: document.getElementById('motor-position'),
        motorSimulation: document.getElementById('motor-simulation'),
        motorFileAge: document.getElementById('motor-file-age'),

        // Encoder Daemon (detail values — badge gere par Alpine)
        encoderStatus: document.getElementById('encoder-status'),
        encoderAngle: document.getElementById('encoder-angle'),
        encoderCalibrated: document.getElementById('encoder-calibrated'),
        encoderFileAge: document.getElementById('encoder-file-age'),

        // IPC Files (restent en vanilla JS)
        ipcStatusFresh: document.getElementById('ipc-status-fresh'),
        ipcStatusContent: document.getElementById('ipc-status-content'),
        ipcEncoderFresh: document.getElementById('ipc-encoder-fresh'),
        ipcEncoderContent: document.getElementById('ipc-encoder-content'),
        ipcCommandFresh: document.getElementById('ipc-command-fresh'),
        ipcCommandContent: document.getElementById('ipc-command-content'),

        // Config (restent en vanilla JS)
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
    // Refresh button (Alpine x-model gere le toggle auto-refresh)
    elements.btnRefresh.addEventListener('click', () => {
        elements.btnRefresh.classList.add('spinning');
        fetchDiagnostic();
        setTimeout(() => elements.btnRefresh.classList.remove('spinning'), 500);
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
    // Status global (Alpine store)
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
 * Met a jour le status global (via Alpine store)
 */
function updateGlobalStatus(healthy, text) {
    const store = Alpine.store('system');
    store.globalHealthy = healthy;
    store.globalStatusText = text;
}

/**
 * Met a jour la section Motor Service
 */
function updateMotorService(motor) {
    // Badge et card border via Alpine store
    const store = Alpine.store('system');
    const badgeClass = motor.healthy ? 'sys-badge-ok' : (motor.status === 'stale' ? 'sys-badge-stale' : 'sys-badge-error');
    const cardClass = motor.healthy ? 'sys-card-healthy' : (motor.status === 'stale' ? 'sys-card-stale' : 'sys-card-unhealthy');
    store.motor = {
        badgeText: motor.healthy ? 'OK' : motor.status.toUpperCase(),
        badgeClass: badgeClass,
        cardClass: cardClass
    };

    // Detail values via getElementById (simple text updates)
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
    // Badge et card border via Alpine store
    const store = Alpine.store('system');
    const badgeClass = encoder.healthy ? 'sys-badge-ok' : (encoder.status === 'stale' ? 'sys-badge-stale' : 'sys-badge-error');
    const cardClass = encoder.healthy ? 'sys-card-healthy' : (encoder.status === 'stale' ? 'sys-card-stale' : 'sys-card-unhealthy');
    store.encoder = {
        badgeText: encoder.healthy ? 'OK' : encoder.status.toUpperCase(),
        badgeClass: badgeClass,
        cardClass: cardClass
    };

    // Detail values via getElementById
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
    updateIpcCard(
        elements.ipcStatusFresh,
        elements.ipcStatusContent,
        ipc.contents.motor_status,
        ipc.freshness.status_file
    );

    updateIpcCard(
        elements.ipcEncoderFresh,
        elements.ipcEncoderContent,
        ipc.contents.encoder_position,
        ipc.freshness.encoder_file
    );

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
        freshEl.className = 'ipc-fresh ipc-fresh-missing';
        freshEl.textContent = 'Non trouve';
        contentEl.textContent = '(fichier non trouve)';
    } else if (!freshness.fresh) {
        freshEl.className = 'ipc-fresh ipc-fresh-stale';
        freshEl.textContent = formatAge(freshness.age_sec);
        contentEl.textContent = content.content
            ? JSON.stringify(content.content, null, 2)
            : content.empty
                ? '(aucune commande en attente)'
                : content.error || '(erreur lecture)';
    } else {
        freshEl.className = 'ipc-fresh ipc-fresh-ok';
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

    if (config.site) {
        elements.siteName.textContent = config.site.nom || '--';
        elements.siteLat.textContent = config.site.latitude ? config.site.latitude + '°' : '--';
        elements.siteLon.textContent = config.site.longitude ? config.site.longitude + '°' : '--';
        elements.siteAlt.textContent = config.site.altitude ? config.site.altitude + 'm' : '--';
    }

    if (config.moteur) {
        elements.motorSteps.textContent = config.moteur.steps_per_revolution || '--';
        elements.motorMicrosteps.textContent = config.moteur.microsteps || '--';
        elements.motorGear.textContent = config.moteur.gear_ratio ? config.moteur.gear_ratio + ':1' : '--';
        elements.motorDelay.textContent = config.moteur.motor_delay_base
            ? (config.moteur.motor_delay_base * 1000).toFixed(1) + 'ms'
            : '--';
    }

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

    if (config.adaptive_modes) {
        let html = '';
        for (const [name, mode] of Object.entries(config.adaptive_modes)) {
            html += `<tr class="border-b border-obs-border/50">
                <td class="py-1 pr-2 text-obs-text">${name}</td>
                <td class="py-1 pr-2">${mode.interval_sec}s</td>
                <td class="py-1 pr-2">${mode.threshold_deg}°</td>
                <td class="py-1">${(mode.motor_delay * 1000).toFixed(2)}ms</td>
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
