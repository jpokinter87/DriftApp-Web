# Phase 2: Refactoring - Context

**Gathered:** 2026-01-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Appliquer les corrections identifiées par le code review Phase 1 sans régression. Inclut:
- 15 bare exceptions à corriger dans core/ avec exceptions spécifiques
- 52 exceptions intentionnelles à documenter proprement
- Duplication IPC paths (6x) et angle normalization (25+)
- Pattern command registry pour OCP dans command_handlers

Exclut: type hints (94% acceptable), complexité CC=18 hardware (légitime), autres patterns DRY.

</domain>

<decisions>
## Implementation Decisions

### Hiérarchie des exceptions
- Fichier unique: `core/exceptions.py` pour toutes les exceptions custom
- Granularité par composant: MotorError, EncoderError, AbaqueError, IPCError (~4-5 classes)
- Attributs contextuels: `raise MotorError('timeout', pin=17, delay=0.002)` pour debug
- 52 exceptions intentionnelles: convertir en logging explicite + continue (pas de # noqa)

### Stratégie DRY
- IPC paths: centraliser dans `core/config/config.py` (IPC_MOTOR_COMMAND, etc.)
- Angle normalization: utiliser `normalize_angle_360()` existant de `core.utils.angle_utils`
- Périmètre: IPC + angles seulement, autres patterns DRY peuvent attendre
- Nouveaux modules: autorisés si améliore la séparation des responsabilités

### Gestion des régressions
- Commits atomiques: 1 commit par type de correction (exceptions, IPC paths, angles, command registry)
- Tests après chaque commit: détecter les régressions immédiatement
- Si test échoue: fix immédiat dans un commit supplémentaire, ne pas laisser de tests rouges
- Tests supplémentaires: ajouter des tests pour les nouvelles exceptions custom

### Périmètre des corrections
- Exceptions: 15 à corriger + 52 à documenter proprement
- DRY: IPC paths + angles (les 2 plus impactés)
- SOLID: inclure command registry pattern pour OCP
- Type hints: non (94% docstrings acceptable)
- Complexité CC=18: ne pas toucher (légitime pour hardware formatting)
- CHANGELOG: nouveau fichier `.planning/phases/02-refactoring/CHANGELOG.md`

### Claude's Discretion
- Structure interne des classes d'exception (héritage commun ou non)
- Ordre des corrections dans les plans
- Découpage exact des commits si besoin de granularité

</decisions>

<specifics>
## Specific Ideas

- Les exceptions doivent avoir des attributs contextuels pour faciliter le debug (pin, delay, etc.)
- Le code review a identifié que CC=18 est légitime pour les fonctions de formatage hardware
- Le pattern command registry a été recommandé dans le rapport SOLID

</specifics>

<deferred>
## Deferred Ideas

- Type hints pour les 76 fonctions — peut-être Phase ultérieure si besoin
- Autres patterns DRY (GPIO setup, logging) — pas critique pour cette phase
- Refactoring complexité hardware — explicitement exclu (légitime)

</deferred>

---

*Phase: 02-refactoring*
*Context gathered: 2026-01-25*
