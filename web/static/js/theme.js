/**
 * Mode nuit rouge — choix du thème (Auto / Nuit / Jour), un réglage par écran.
 *
 * Chargé de façon bloquante dans <head> : data-theme est posé sur <html> avant
 * le premier rendu, sans flash de jour au chargement d'une page la nuit.
 * En Auto, nuit quand le Soleil est sous NIGHT_BELOW_DEG (fin du crépuscule
 * civil, même seuil que la fermeture du cimier), réévalué chaque minute.
 * Coordonnées du site : attributs data-site-lat / data-site-lon de <html>,
 * injectés depuis data/config.json (context processor site_coords).
 */
(function () {
    const STORAGE_KEY = 'driftapp-theme';
    const NIGHT_BELOW_DEG = -6;
    const RECHECK_MS = 60_000;
    const rad = Math.PI / 180;

    /**
     * Altitude géométrique du Soleil (degrés, sans réfraction), algorithme
     * simplifié de l'Almanach (~0.1° de 1950 à 2050). Suffisant pour un thème.
     */
    function sunAltitude(date, latDeg, lonDeg) {
        const d = date.getTime() / 86_400_000 + 2440587.5 - 2451545.0;
        const g = (357.529 + 0.98560028 * d) * rad;
        const q = 280.459 + 0.98564736 * d;
        const L = (q + 1.915 * Math.sin(g) + 0.020 * Math.sin(2 * g)) * rad;
        const e = (23.439 - 0.00000036 * d) * rad;
        const ra = Math.atan2(Math.cos(e) * Math.sin(L), Math.cos(L));
        const dec = Math.asin(Math.sin(e) * Math.sin(L));
        const gmstDeg = (18.697374558 + 24.06570982441908 * d) * 15;
        const ha = (gmstDeg + lonDeg) * rad - ra;
        const lat = latDeg * rad;
        const sinAlt = Math.sin(lat) * Math.sin(dec) + Math.cos(lat) * Math.cos(dec) * Math.cos(ha);
        return Math.asin(sinAlt) / rad;
    }

    if (typeof document === 'undefined') {
        module.exports = { sunAltitude };  // vérification node contre astropy
        return;
    }

    const root = document.documentElement;

    function readChoice() {
        try {
            return localStorage.getItem(STORAGE_KEY) || 'auto';
        } catch (e) {
            return 'auto';
        }
    }

    function resolve(choice) {
        if (choice === 'night' || choice === 'day') return choice;
        const lat = parseFloat(root.dataset.siteLat);
        const lon = parseFloat(root.dataset.siteLon);
        if (Number.isNaN(lat) || Number.isNaN(lon)) return 'day';
        return sunAltitude(new Date(), lat, lon) < NIGHT_BELOW_DEG ? 'night' : 'day';
    }

    function apply() {
        const choice = readChoice();
        root.dataset.theme = resolve(choice);
        document.querySelectorAll('[data-theme-choice]').forEach((btn) => {
            btn.setAttribute('aria-pressed', String(btn.dataset.themeChoice === choice));
        });
    }

    apply();
    setInterval(apply, RECHECK_MS);
    document.addEventListener('DOMContentLoaded', apply);
    document.addEventListener('click', (event) => {
        const btn = event.target.closest('[data-theme-choice]');
        if (!btn) return;
        try {
            localStorage.setItem(STORAGE_KEY, btn.dataset.themeChoice);
        } catch (e) {
            // Stockage indisponible : le choix vaut pour cette page seulement.
            root.dataset.theme = resolve(btn.dataset.themeChoice);
            btn.parentElement.querySelectorAll('[data-theme-choice]').forEach((b) => {
                b.setAttribute('aria-pressed', String(b === btn));
            });
            return;
        }
        apply();
    });
})();
