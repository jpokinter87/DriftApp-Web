# Milestones

Completed milestone log for this project.

| Milestone | Completed | Duration | Stats |
|-----------|-----------|----------|-------|
| v5.0 Interface Moderne | 2026-02-22 | 1 day | 5 phases, 11 plans |
| v5.1 Synchronisation & Qualité | 2026-03-14 | 1 day | 6 phases, 11 plans |

---

## v5.1 Synchronisation & Qualité

**Completed:** 2026-03-14
**Duration:** 1 day

### Stats

| Metric | Value |
|--------|-------|
| Phases | 6 |
| Plans | 11 |
| Files modified | ~35 (22 core/services sync + 11 refactoring + 4 tests créés) |
| Tests | 407 → 746 (+339 tests, 0 échecs) |
| Issues corrigées | 38 (5C + 16H + 14M + 3 acceptées) |

### Key Accomplishments

- core/ et services/ synchronisés byte-for-byte avec la production DriftApp_v4_6 (22 fichiers)
- Audit code complet : 54 issues identifiées (7C, 15H, 20M, 12L) dans core/ et services/
- 27 issues corrigées dans core/ : moyenne circulaire, verrou fcntl, chemins absolus, code mort supprimé, angle_utils centralisé
- 11 issues corrigées dans services/ : thread safety (status_lock), validation entrées, IPC simplifié, zombie detection
- Suite de tests passée de 407 à 693 tests (8 fichiers réparés, alignés sur API production)
- Couverture étendue : 3 nouveaux fichiers tests (health, session views, session storage) → 738 tests
- Validation cross-couche : 8 tests Django ↔ IPC ↔ MotorService → 746 tests verts
- Simulation réaliste avec délais I2C calibrés sur matériel EMS22A

### Key Decisions

- Source de vérité : DriftApp_v4_6 (production Pi) pour sync
- Corriger les tests pour refléter l'API production, pas l'inverse
- Thread safety limité à ContinuousHandler (seul handler multi-thread)
- Pas de threading GOTO/JOG (trop risqué pour refactoring, milestone dédié futur)
- Centralisation angle_utils pour toute normalisation/distance angulaire
- APIRequestFactory pour contourner dispatch Django dans les mocks
- Patch double IPC pour tests cross-couche (ipc_manager + Django settings)

---

## v5.0 Interface Moderne

**Completed:** 2026-02-22
**Duration:** 1 day (single session)

### Stats

| Metric | Value |
|--------|-------|
| Phases | 5 |
| Plans | 11 |
| Files created | 4 |
| Files modified | 10 |
| Files deleted | 2 (system.css, session.css) |
| CSS lines removed | ~1,189 |

### Key Accomplishments

- Tailwind CSS v4 integrated via standalone CLI (no Node.js) with Alpine.js CDN
- Base template Django (base.html) with header, nav, footer and 6 blocks
- 38 reusable component classes in @layer components (32KB compiled)
- Dashboard redesigned: 2-column layout, star field SVG, glow effects, fire gradients
- Alpine.store bridge pattern on all 3 pages (dashboard, system, session)
- GOTO and Update modals migrated to Alpine.js x-show reactivity
- System page: cards, IPC monitoring, badges, auto-refresh toggle
- Session page: selector, Chart.js themed, stats cards, history panel
- CSS legacy cleaned: system.css and session.css deleted, shared styles factorized
- Responsive mobile-first + accessibility (aria, focus-visible, prefers-reduced-motion)

### Key Decisions

- Tailwind v4 CSS-based config (@theme) instead of tailwind.config.js
- Standalone CLI instead of npm (Raspberry Pi simplicity)
- Fonts: JetBrains Mono (display) + IBM Plex Sans (body)
- Random star field (500 pts) SVG — more convincing than constellations
- Alpine.store bridge: Alpine for UI reactivity, vanilla JS for canvas/polling/API
- x-cloak to prevent content flash on load
- Pages secondaires: inline CSS for shared styles (dashboard.css not loaded)
- Mobile-first grid (grid-cols-1 lg:grid-cols-[350px_1fr])
- prefers-reduced-motion global for vestibular accessibility
- focus-visible amber outline matching observatory theme

---
