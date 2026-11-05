/**
 * Frise de nuit — restitution graphique d'une nuit d'observation.
 *
 * Quatre lignes sur un axe horaire commun (midi → midi) :
 *   1. Pluie     — bande = pluie, hachures = capteur injoignable
 *   2. Cimier    — bande = ouvert, marqueurs verticaux aux décisions
 *   3. Suivi     — bandes des sessions, étiquetées du nom d'objet
 *   4. Batteries — tension relevée toutes les 5 min (6.31.0), fonds ambre et
 *      rouge sous les seuils, trait coupé quand le boîtier est hors tension
 *
 * SVG inline, sans dépendance. Aucune information ne dépend d'un survol :
 * l'écran de l'observatoire est tactile.
 */

const FRIEZE = {
    rowHeight: 30,
    rowGap: 14,
    marginLeft: 74,
    marginRight: 14,
    // Laisse la place au repère « maintenant » posé au-dessus de la 1re ligne.
    marginTop: 22,
    axisHeight: 22,
    colors: {
        wet: '#4aa3ff',
        dry: 'rgba(255,255,255,0.05)',
        unreachable: '#ffa502',
        cimierOpen: '#00d26a',
        tracking: '#d4a055',
        closeMarker: '#ff4757',
        wouldCloseMarker: '#ffa502',
        axis: 'rgba(255,255,255,0.25)',
        text: '#9aa0a6',
        future: 'rgba(0,0,0,0.45)',
        nowLine: 'rgba(255,255,255,0.45)',
        label: '#1b1b1b',
        voltLine: '#e8e6e3',
        voltWarnBand: 'rgba(255,165,2,0.16)',
        voltBadBand: 'rgba(255,71,87,0.20)',
    },
};

// Couleurs du thème actif : variables --frieze-* de theme.css (nom en kebab-case),
// relues à chaque rendu ; à défaut, les valeurs ci-dessus.
function applyThemeColors() {
    const cs = getComputedStyle(document.documentElement);
    for (const key of Object.keys(FRIEZE.colors)) {
        const name = '--frieze-' + key.replace(/[A-Z]/g, (c) => '-' + c.toLowerCase());
        const value = cs.getPropertyValue(name).trim();
        if (value) FRIEZE.colors[key] = value;
    }
}

const ROWS = [
    { key: 'rain', label: 'Pluie' },
    { key: 'cimier', label: 'Cimier' },
    { key: 'tracking', label: 'Suivi' },
    // Plus haute : une tension se lit sur un axe, pas sur une bande.
    { key: 'battery', label: 'Batteries', height: 64 },
];

const rowHeightOf = (index) => ROWS[index].height || FRIEZE.rowHeight;

// Deux relevés séparés de plus que ça = trou (boîtier hors tension, service
// arrêté) : le trait est coupé plutôt que d'inventer une droite.
const VOLT_GAP_MS = 15 * 60 * 1000;

function parseIso(value) {
    const ms = Date.parse(value);
    return Number.isFinite(ms) ? ms : null;
}

/**
 * Convertit la liste d'événements en segments d'état continus.
 * Un état vaut jusqu'au prochain événement du même type, ou jusqu'à la fin.
 */
function toSegments(events, predicate, valueOf, startMs, endMs) {
    const points = events
        .filter(predicate)
        .map((e) => ({ ts: parseIso(e.ts), value: valueOf(e) }))
        .filter((p) => p.ts !== null)
        .sort((a, b) => a.ts - b.ts);

    const segments = [];
    for (let i = 0; i < points.length; i += 1) {
        const from = Math.max(points[i].ts, startMs);
        const to = i + 1 < points.length ? Math.min(points[i + 1].ts, endMs) : endMs;
        if (to > from) segments.push({ from, to, value: points[i].value });
    }
    return segments;
}

function svgEl(name, attrs) {
    const el = document.createElementNS('http://www.w3.org/2000/svg', name);
    Object.entries(attrs || {}).forEach(([k, v]) => el.setAttribute(k, String(v)));
    return el;
}

/**
 * Dessine la frise dans le conteneur fourni.
 * @param {HTMLElement} container
 * @param {Object} data - payload de GET /api/session/night/
 */
function renderNightFrieze(container, data) {
    applyThemeColors();
    container.innerHTML = '';
    if (!data || !data.night) {
        const empty = document.createElement('div');
        empty.className = 'text-xs text-obs-text-muted italic text-center py-6';
        empty.textContent = 'Aucune nuit enregistrée pour l\'instant.';
        container.appendChild(empty);
        return;
    }

    const startMs = parseIso(data.night_start);
    const endMs = parseIso(data.night_end);
    if (startMs === null || endMs === null || endMs <= startMs) return;

    // Borne de restitution : un état connu vaut jusqu'au suivant, mais pas
    // au-delà de l'instant présent. Sans ça, la nuit en cours affichait le
    // dernier état jusqu'à midi le lendemain — de la pluie dans l'avenir
    // (terrain 16/08/2026). L'heure vient du serveur, qui horodate les
    // événements ; la tablette de l'observatoire n'est pas l'autorité.
    const nowMs = parseIso(data.now);
    const knownEnd = Math.min(endMs, Math.max(nowMs === null ? endMs : nowMs, startMs));
    const nightInProgress = knownEnd < endMs;

    const width = Math.max(container.clientWidth || 720, 480);
    const plotWidth = width - FRIEZE.marginLeft - FRIEZE.marginRight;
    const xOf = (ms) =>
        FRIEZE.marginLeft +
        ((Math.min(Math.max(ms, startMs), endMs) - startMs) / (endMs - startMs)) * plotWidth;
    const yOf = (rowIndex) => {
        let y = FRIEZE.marginTop;
        for (let i = 0; i < rowIndex; i += 1) y += rowHeightOf(i) + FRIEZE.rowGap;
        return y;
    };
    const axisY = yOf(ROWS.length);
    const height = axisY + FRIEZE.axisHeight;

    const svg = svgEl('svg', {
        width: '100%',
        height,
        viewBox: `0 0 ${width} ${height}`,
        role: 'img',
        'aria-label': `Frise de la nuit du ${data.night}`,
    });

    // Hachures pour « capteur injoignable ».
    const defs = svgEl('defs', {});
    const pattern = svgEl('pattern', {
        id: 'frieze-hatch',
        width: 6,
        height: 6,
        patternUnits: 'userSpaceOnUse',
        patternTransform: 'rotate(45)',
    });
    pattern.appendChild(svgEl('rect', { width: 6, height: 6, fill: 'rgba(255,165,2,0.12)' }));
    pattern.appendChild(svgEl('rect', { width: 2, height: 6, fill: FRIEZE.colors.unreachable }));
    defs.appendChild(pattern);
    svg.appendChild(defs);

    // Libellés et fonds de ligne.
    ROWS.forEach((row, index) => {
        const y = yOf(index);
        svg.appendChild(
            svgEl('rect', {
                x: FRIEZE.marginLeft,
                y,
                width: plotWidth,
                height: rowHeightOf(index),
                fill: FRIEZE.colors.dry,
                rx: 3,
            })
        );
        const label = svgEl('text', {
            x: FRIEZE.marginLeft - 10,
            y: y + rowHeightOf(index) / 2 + 4,
            'text-anchor': 'end',
            fill: FRIEZE.colors.text,
            'font-size': 11,
            'font-family': 'monospace',
        });
        label.textContent = row.label;
        svg.appendChild(label);
    });

    const events = Array.isArray(data.events) ? data.events : [];

    // Ligne 1 — pluie.
    toSegments(
        events,
        (e) => e.event === 'rain',
        (e) => e.state,
        startMs,
        knownEnd
    ).forEach((seg) => {
        if (seg.value === 'dry') return;
        svg.appendChild(
            svgEl('rect', {
                x: xOf(seg.from),
                y: yOf(0),
                width: Math.max(xOf(seg.to) - xOf(seg.from), 1),
                height: FRIEZE.rowHeight,
                fill: seg.value === 'wet' ? FRIEZE.colors.wet : 'url(#frieze-hatch)',
                rx: 3,
            })
        );
    });

    // Ligne 2 — cimier ouvert, d'un cycle `open` réussi au `close` suivant.
    toSegments(
        events,
        (e) => e.event === 'cimier' && (e.action === 'open' || e.action === 'close'),
        (e) => e.action,
        startMs,
        knownEnd
    ).forEach((seg) => {
        if (seg.value !== 'open') return;
        svg.appendChild(
            svgEl('rect', {
                x: xOf(seg.from),
                y: yOf(1),
                width: Math.max(xOf(seg.to) - xOf(seg.from), 1),
                height: FRIEZE.rowHeight,
                fill: FRIEZE.colors.cimierOpen,
                opacity: 0.55,
                rx: 3,
            })
        );
    });

    // Marqueurs de décision sur la ligne cimier.
    events
        .filter((e) => e.event === 'decision')
        .forEach((e) => {
            const ts = parseIso(e.ts);
            if (ts === null) return;
            const isReal = e.action === 'close';
            svg.appendChild(
                svgEl('line', {
                    x1: xOf(ts),
                    x2: xOf(ts),
                    y1: yOf(1) - 5,
                    y2: yOf(1) + FRIEZE.rowHeight + 5,
                    stroke: isReal ? FRIEZE.colors.closeMarker : FRIEZE.colors.wouldCloseMarker,
                    'stroke-width': 2,
                    'stroke-dasharray': isReal ? '' : '3 3',
                })
            );
        });

    // Ligne 3 — sessions de suivi.
    (data.tracking || []).forEach((session) => {
        const from = parseIso(session.start_time);
        if (from === null) return;
        // Session encore en cours : elle court jusqu'à maintenant, pas
        // jusqu'à la fin de la nuit.
        const to = parseIso(session.end_time) || knownEnd;
        const x = xOf(from);
        const w = Math.max(xOf(to) - x, 2);
        svg.appendChild(
            svgEl('rect', {
                x,
                y: yOf(2),
                width: w,
                height: FRIEZE.rowHeight,
                fill: FRIEZE.colors.tracking,
                opacity: 0.5,
                rx: 3,
            })
        );
        if (w > 48 && session.object_name) {
            const name = svgEl('text', {
                x: x + 6,
                y: yOf(2) + FRIEZE.rowHeight / 2 + 4,
                fill: FRIEZE.colors.label,
                'font-size': 10,
                'font-family': 'monospace',
            });
            name.textContent = session.object_name;
            svg.appendChild(name);
        }
    });

    // Ligne 4 — tension des batteries.
    drawBatteryRow(svg, events, data.battery_thresholds, {
        top: yOf(3),
        height: rowHeightOf(3),
        left: FRIEZE.marginLeft,
        width: plotWidth,
        xOf,
        startMs,
        knownEnd,
    });

    // Nuit en cours : voiler ce qui n'a pas encore eu lieu et marquer
    // l'instant présent. Le repère est étiqueté en clair — l'écran de
    // l'observatoire est tactile, rien ne doit dépendre d'un survol.
    if (nightInProgress) {
        const nowX = xOf(knownEnd);
        const rowsTop = yOf(0);
        const rowsBottom = yOf(ROWS.length - 1) + rowHeightOf(ROWS.length - 1);
        svg.appendChild(
            svgEl('rect', {
                x: nowX,
                y: rowsTop,
                width: FRIEZE.marginLeft + plotWidth - nowX,
                height: rowsBottom - rowsTop,
                fill: FRIEZE.colors.future,
            })
        );
        svg.appendChild(
            svgEl('line', {
                x1: nowX,
                x2: nowX,
                y1: rowsTop - 6,
                y2: rowsBottom + 4,
                stroke: FRIEZE.colors.nowLine,
                'stroke-width': 1,
            })
        );
        // Ancrage à droite du trait, sauf trop près du bord où le libellé
        // sortirait du cadre.
        const labelFits = FRIEZE.marginLeft + plotWidth - nowX > 70;
        const nowLabel = svgEl('text', {
            x: labelFits ? nowX + 5 : nowX - 5,
            y: rowsTop - 9,
            'text-anchor': labelFits ? 'start' : 'end',
            fill: FRIEZE.colors.text,
            'font-size': 9,
            'font-family': 'monospace',
        });
        nowLabel.textContent = 'maintenant';
        svg.appendChild(nowLabel);
    }

    // Axe horaire : une graduation toutes les 2 h.
    svg.appendChild(
        svgEl('line', {
            x1: FRIEZE.marginLeft,
            x2: FRIEZE.marginLeft + plotWidth,
            y1: axisY,
            y2: axisY,
            stroke: FRIEZE.colors.axis,
        })
    );
    for (let hour = 0; hour <= 24; hour += 2) {
        const ts = startMs + hour * 3600 * 1000;
        if (ts > endMs) break;
        const x = xOf(ts);
        svg.appendChild(
            svgEl('line', { x1: x, x2: x, y1: axisY, y2: axisY + 4, stroke: FRIEZE.colors.axis })
        );
        const tick = svgEl('text', {
            x,
            y: axisY + 16,
            'text-anchor': 'middle',
            fill: FRIEZE.colors.text,
            'font-size': 10,
            'font-family': 'monospace',
        });
        tick.textContent = String((12 + hour) % 24).padStart(2, '0') + 'h';
        svg.appendChild(tick);
    }

    container.appendChild(svg);
}

function formatVolts(v) {
    return v.toFixed(2).replace('.', ',') + ' V';
}

/**
 * Ligne « Batteries » : tension sur une échelle verticale propre à la ligne.
 * Fonds ambre / rouge sous les seuils (le niveau se lit sans légende), trait
 * coupé sur les trous, dernière valeur et minimum de la nuit écrits en clair.
 */
function drawBatteryRow(svg, events, thresholds, box) {
    const goodV = thresholds?.good_v ?? 12.4;
    const lowV = thresholds?.low_v ?? 12.0;
    const points = events
        .filter((e) => e.event === 'voltages')
        .map((e) => ({ ts: parseIso(e.ts), v: typeof e.battery === 'number' ? e.battery : null }))
        .filter((p) => p.ts !== null && p.ts >= box.startMs && p.ts <= box.knownEnd)
        .sort((a, b) => a.ts - b.ts);
    const values = points.filter((p) => p.v !== null).map((p) => p.v);

    const text = (x, y, content, anchor, size = 10) => {
        const el = svgEl('text', {
            x,
            y,
            'text-anchor': anchor,
            fill: FRIEZE.colors.text,
            'font-size': size,
            'font-family': 'monospace',
        });
        el.textContent = content;
        svg.appendChild(el);
    };

    if (values.length === 0) {
        text(box.left + 8, box.top + box.height / 2 + 4, 'aucun relevé', 'start');
        return;
    }

    // Échelle : englobe les seuils et les mesures, avec un peu d'air.
    const vMin = Math.min(lowV - 0.3, ...values) - 0.05;
    const vMax = Math.max(goodV + 0.4, ...values) + 0.05;
    const pad = 4;
    const yOfV = (v) =>
        box.top + pad + ((vMax - v) / (vMax - vMin)) * (box.height - 2 * pad);
    const band = (from, to, fill) => {
        const y1 = yOfV(Math.min(to, vMax));
        const y2 = yOfV(Math.max(from, vMin));
        if (y2 > y1) {
            svg.appendChild(svgEl('rect', { x: box.left, y: y1, width: box.width, height: y2 - y1, fill }));
        }
    };
    band(lowV, goodV, FRIEZE.colors.voltWarnBand);
    band(vMin, lowV, FRIEZE.colors.voltBadBand);

    // Trait coupé aux trous (mesure absente ou relevés trop espacés).
    let path = '';
    let prev = null;
    points.forEach((p) => {
        if (p.v === null) {
            prev = null;
            return;
        }
        const cmd = prev && p.ts - prev.ts <= VOLT_GAP_MS ? 'L' : 'M';
        path += `${cmd}${box.xOf(p.ts).toFixed(1)},${yOfV(p.v).toFixed(1)} `;
        prev = p;
    });
    svg.appendChild(
        svgEl('path', {
            d: path.trim(),
            fill: 'none',
            stroke: FRIEZE.colors.voltLine,
            'stroke-width': 2,
            'stroke-linejoin': 'round',
            'stroke-linecap': 'round',
        })
    );

    // Relevé isolé (entouré de trous) : un point, sinon il serait invisible.
    points.forEach((p, i) => {
        if (p.v === null) return;
        const near = (q) => q && q.v !== null && Math.abs(q.ts - p.ts) <= VOLT_GAP_MS;
        if (!near(points[i - 1]) && !near(points[i + 1])) {
            svg.appendChild(
                svgEl('circle', { cx: box.xOf(p.ts), cy: yOfV(p.v), r: 2.5, fill: FRIEZE.colors.voltLine })
            );
        }
    });

    // Valeurs des seuils au bord gauche des bandes, puis dernière valeur et
    // minimum de la nuit en haut à gauche : à droite, le voile « maintenant »
    // de la nuit en cours les masquerait.
    const fmt = (v) => v.toFixed(1).replace('.', ',');
    text(box.left + 4, yOfV(goodV) + 9, fmt(goodV), 'start', 9);
    text(box.left + 4, yOfV(lowV) + 9, fmt(lowV), 'start', 9);
    const last = [...points].reverse().find((p) => p.v !== null);
    const minV = Math.min(...values);
    text(box.left + 6, box.top + 12, `dernière ${formatVolts(last.v)} · min ${formatVolts(minV)}`, 'start');
}

window.renderNightFrieze = renderNightFrieze;
