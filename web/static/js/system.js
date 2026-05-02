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
        // Cimier — Automatisation (v6.0 Phase 4 sub-plan 04-02).
        // Hydraté par fetchCimierAutomation toutes les REFRESH_INTERVAL.
        cimierAutomation: {
            mode: null,                    // 'manual' | 'semi' | 'full' | null (config.json)
            serviceMode: null,             // mode chargé en mémoire par cimier_service
            serviceRunning: false,         // true si cimier_service vivant (last_update < 90s)
            applyPending: false,           // true si mode != serviceMode ET service vivant
            modeLabel: '--',
            // ISO bruts conservés pour tick local 1s (recalcul du Restant entre fetches).
            nextOpenIso: null,
            nextCloseIso: null,
            nextOpenLabel: '--',           // 'HH:MM' local ou '--'
            nextOpenRemaining: '--',       // 'Xh Ymin' ou '--'
            nextCloseLabel: '--',
            nextCloseRemaining: '--',
            lastEventLabel: '--',          // 'HH:MM:SS' local ou '--'
            lastEventMessage: '--',        // message court ou '--'
        },
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
    // Tick local 1s pour décrémenter le « Restant » des cards Cimier — Automatisation
    // sans attendre le prochain fetch (qui peut être lent / throttlé en arrière-plan).
    setInterval(recomputeAutomationLabels, 1000);

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
        thresholdGemDelay: document.getElementById('threshold-gem-delay'),
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
    // Fetch parallèle de l'état automation cimier (vue 04-01).
    fetchCimierAutomation();
}

/**
 * Récupère l'état automation cimier depuis /api/cimier/automation/
 * et hydrate Alpine.store('system').cimierAutomation. (v6.0 Phase 4 sub-plan 04-02)
 */
async function fetchCimierAutomation() {
    const store = Alpine.store('system');
    try {
        const response = await fetch('/api/cimier/automation/');
        if (!response.ok) {
            // Service indisponible — fallback sans spammer les logs.
            store.cimierAutomation.mode = 'unknown';
            store.cimierAutomation.modeLabel = 'Service indisponible';
            store.cimierAutomation.nextOpenLabel = '--';
            store.cimierAutomation.nextOpenRemaining = '--';
            store.cimierAutomation.nextCloseLabel = '--';
            store.cimierAutomation.nextCloseRemaining = '--';
            return;
        }
        const data = await response.json();
        const labels = { manual: 'Manuel', semi: 'Semi-auto', full: 'Full auto' };
        const mode = data.mode || 'unknown';
        const serviceMode = data.service_mode || mode;
        const serviceRunning = !!data.service_running;
        const applyPending = !!(data.mode_apply_pending ?? data.restart_required);
        store.cimierAutomation.mode = mode;
        store.cimierAutomation.serviceMode = serviceMode;
        store.cimierAutomation.serviceRunning = serviceRunning;
        store.cimierAutomation.applyPending = applyPending;
        // ISO bruts conservés pour tick local (cf. recomputeAutomationRemaining).
        store.cimierAutomation.nextOpenIso = data.next_open_at || null;
        store.cimierAutomation.nextCloseIso = data.next_close_at || null;
        // Badge contextualisé selon vivacité service + apply_pending.
        if (!serviceRunning) {
            store.cimierAutomation.modeLabel = `${labels[mode] || mode} ⊘ service arrêté`;
        } else if (applyPending) {
            store.cimierAutomation.modeLabel = `${labels[mode] || mode} ⏳ application…`;
        } else {
            store.cimierAutomation.modeLabel = labels[mode] || '--';
        }

        const openLabel = formatTriggerLabel(data.next_open_at);
        const closeLabel = formatTriggerLabel(data.next_close_at);

        // Message contextuel selon mode (au lieu de '--' partout en mode manual/semi).
        // Fix smoke 2026-05-02 : cards "vides" quand mode=manual.
        // Délègue le formatage absolute/relative au tick local pour avoir un
        // affichage à jour entre les fetches (un fetch toutes les 2s ne suffit
        // pas si le browser throttle setInterval ou si le backend est lent).
        recomputeAutomationLabels();

        // lastEventLabel/Message : pas d'agrégation cross-page (Alpine stores
        // scoped par page — décision plan 04-02). On laisse '--' tant que pas
        // d'endpoint Django dédié /api/cimier/timeline/.
    } catch (error) {
        console.error('Erreur fetch cimier automation:', error);
        store.cimierAutomation.mode = 'unknown';
        store.cimierAutomation.modeLabel = 'Erreur connexion';
    }
}

/**
 * Recalcule les libellés absolute (HH:MM) + relative (Xh Ymin) pour next_open
 * et next_close à partir des ISO bruts stockés dans le store.
 *
 * Appelé :
 *   1. Après chaque fetchCimierAutomation (hydratation immédiate).
 *   2. Tick local 1s (pour faire décrémenter le Restant entre fetches sans
 *      attendre la prochaine requête backend).
 *
 * Fix UX 2026-05-02 : Restant figé à 4min même 10min plus tard — cause :
 * formatTriggerLabel n'était calculé qu'au fetch (2s) et le browser throttle
 * setInterval quand l'onglet est en arrière-plan. Tick local visible élimine
 * cette dérive.
 */
function recomputeAutomationLabels() {
    const store = Alpine.store('system');
    const auto = store.cimierAutomation;
    if (!auto) return;

    const mode = auto.mode || 'unknown';
    const openLabel = formatTriggerLabel(auto.nextOpenIso);
    const closeLabel = formatTriggerLabel(auto.nextCloseIso);

    if (mode === 'manual') {
        auto.nextOpenLabel = '— (mode manuel)';
        auto.nextOpenRemaining = 'Aucun trigger automatique';
        auto.nextCloseLabel = '— (mode manuel)';
        auto.nextCloseRemaining = 'Aucun trigger automatique';
    } else if (mode === 'semi') {
        auto.nextOpenLabel = '— (semi : manuel)';
        auto.nextOpenRemaining = 'Démarrage manuel utilisateur';
        auto.nextCloseLabel = closeLabel.absolute;
        auto.nextCloseRemaining = closeLabel.relative !== '--'
            ? closeLabel.relative
            : 'Calcul des éphémérides…';
    } else if (mode === 'full') {
        auto.nextOpenLabel = openLabel.absolute;
        auto.nextOpenRemaining = openLabel.relative !== '--'
            ? openLabel.relative
            : 'Calcul des éphémérides…';
        auto.nextCloseLabel = closeLabel.absolute;
        auto.nextCloseRemaining = closeLabel.relative !== '--'
            ? closeLabel.relative
            : 'Calcul des éphémérides…';
    } else {
        auto.nextOpenLabel = '--';
        auto.nextOpenRemaining = '--';
        auto.nextCloseLabel = '--';
        auto.nextCloseRemaining = '--';
    }
}

/**
 * Formate un instant ISO 8601 UTC en {absolute: 'HH:MM' local, relative: 'Xh Ymin'}.
 * Retourne {absolute: '--', relative: '--'} si null/invalide/passé.
 */
function formatTriggerLabel(isoUtc) {
    if (!isoUtc) return { absolute: '--', relative: '--' };
    const ms = Date.parse(isoUtc);
    if (!Number.isFinite(ms)) return { absolute: '--', relative: '--' };
    const dt = new Date(ms);
    const absolute = dt.toLocaleTimeString('fr-FR', {
        hour: '2-digit', minute: '2-digit', hour12: false
    });
    const remainingMs = ms - Date.now();
    if (remainingMs <= 0) return { absolute, relative: '--' };
    const totalMin = Math.floor(remainingMs / 60000);
    const hours = Math.floor(totalMin / 60);
    const minutes = totalMin % 60;
    const relative = hours > 0
        ? `${hours}h ${minutes.toString().padStart(2, '0')}min`
        : `${minutes}min`;
    return { absolute, relative };
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
        const spr = config.moteur.steps_per_revolution || 0;
        const ms = config.moteur.microsteps || 1;
        elements.motorSteps.textContent = spr ? (spr * ms) : '--';
        elements.motorMicrosteps.textContent = ms || '--';
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
    if (config.meridien) {
        const delay = config.meridien.gem_delay_minutes;
        elements.thresholdGemDelay.textContent = (delay !== undefined && delay !== null)
            ? delay + ' min' : '0 min';
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
