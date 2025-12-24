# Plan d'Analyse et Refactoring - DriftApp-Web

**Date**: 24 décembre 2025
**Branche**: `claude/code-analysis-refactor-1ujcU`
**Analysé par**: Claude Code

---

## Résumé Exécutif

Analyse approfondie du codebase DriftApp-Web (~7,500 lignes de code production + ~2,000 lignes de tests). Le code est globalement bien structuré avec une architecture IPC 3-processus solide. Cependant, plusieurs bugs potentiels et opportunités de refactoring ont été identifiés.

---

## 1. BUGS CRITIQUES IDENTIFIÉS

### 1.1 État Global Partagé dans `moteur_simule.py` (Ligne 19)

**Fichier**: `core/hardware/moteur_simule.py:19`

```python
# Variable globale pour partager la position entre instances (singleton pattern)
_simulated_position = 0.0
```

**Problème**: La variable globale `_simulated_position` est partagée entre TOUTES les instances de `MoteurSimule`. Cela casse l'isolation des tests si plusieurs instances sont créées en parallèle.

**Impact**:
- Tests qui peuvent s'influencer mutuellement
- Comportement non déterministe en tests parallèles
- Difficile à reproduire (race condition)

**Solution recommandée**:
```python
class MoteurSimule:
    _instances_positions = {}  # Dict[id, position] pour isolation

    def __init__(self, config_moteur=None):
        self._instance_id = id(self)
        MoteurSimule._instances_positions[self._instance_id] = 0.0
```

---

### 1.2 Absence de Verrou IPC dans `ipc_manager.py` (Lignes 52-68)

**Fichier**: `services/ipc_manager.py:52-68`

```python
def read_command(self) -> Optional[Dict[str, Any]]:
    if not COMMAND_FILE.exists():
        return None
    try:
        text = COMMAND_FILE.read_text()  # RISQUE: lecture non atomique
```

**Problème**: La lecture de commande n'est PAS thread-safe. Django peut écrire pendant que Motor Service lit, causant une lecture de JSON partiel.

**Impact**:
- `JSONDecodeError` sporadique en production
- Commandes perdues si le timing est mauvais
- Difficile à reproduire (race condition)

**Solution recommandée**:
```python
import fcntl

def read_command(self) -> Optional[Dict[str, Any]]:
    if not COMMAND_FILE.exists():
        return None
    try:
        with open(COMMAND_FILE, 'r') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)  # Verrou partagé
            try:
                text = f.read()
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
```

---

### 1.3 Double Instance de DaemonEncoderReader

**Fichiers**:
- `core/hardware/moteur.py:161` - Instance globale `_daemon_reader`
- `services/motor_service.py` - Crée sa propre instance

**Problème**: Deux lecteurs indépendants du daemon peuvent avoir des états différents (cache, timeout settings).

**Impact**:
- Incohérence potentielle des lectures de position
- Configuration non synchronisée si modifiée à runtime

**Solution recommandée**: Injection de dépendance - passer une instance unique à tous les composants.

---

### 1.4 Gestion d'Exception Trop Large dans `tracker.py` (Lignes 767-770)

**Fichier**: `core/tracking/tracker.py:767-770`

```python
except Exception as e:
    self.python_logger.error(f"Erreur correction feedback: {e}")
    self.python_logger.error("Traceback:", exc_info=True)
    self._apply_correction_sans_feedback(delta_deg, motor_delay)
```

**Problème**: Capture toutes les exceptions et bascule silencieusement vers le mode sans feedback. Peut masquer des erreurs graves (ex: calibration perdue, encodeur défaillant).

**Impact**:
- Erreurs critiques masquées
- L'utilisateur ne sait pas que le système est dégradé
- Debug difficile en production

**Solution recommandée**:
```python
except (RuntimeError, IOError) as e:
    # Erreurs de communication - fallback légitime
    self.python_logger.warning(f"Fallback sans feedback: {e}")
    self._apply_correction_sans_feedback(delta_deg, motor_delay)
except Exception as e:
    # Erreur inattendue - ne pas masquer
    self.python_logger.error(f"Erreur critique feedback: {e}", exc_info=True)
    raise
```

---

## 2. BUGS MODÉRÉS IDENTIFIÉS

### 2.1 Constantes Magiques Dispersées

**Locations**:
- `services/command_handlers.py:29` - `SEUIL_FEEDBACK_DEG = 3.0`
- `core/tracking/tracker.py:543` - `LARGE_MOVEMENT_THRESHOLD = 30.0`
- `core/hardware/feedback_controller.py:267` - Seuil `20.0°` hardcodé

**Problème**: Même concept (seuil de mouvement) avec différentes valeurs dans différents fichiers.

**Solution**: Centraliser dans `data/config.json` ou créer `core/constants.py`.

---

### 2.2 Pas de Timeout Global sur GOTO Initial

**Fichier**: `core/tracking/tracker.py:456`

```python
result = self.moteur.rotation_avec_feedback(
    angle_cible=position_cible,
    # ...
    max_iterations=10,  # Peut durer 10 × temps_par_iteration
)
```

**Problème**: Si l'encodeur renvoie des valeurs erratiques, la boucle peut tourner pendant les 10 itérations complètes.

**Solution**: Ajouter un `max_duration` en plus de `max_iterations`.

---

### 2.3 Position 0° Assumée au Démarrage

**Fichier**: `core/tracking/tracker.py:399`

```python
def _setup_initial_position(self, azimut: float, altitude: float,
                             position_cible: float):
    # ...
    self.position_relative = position_cible
```

**Problème**: Le commentaire dit "User centered manually" mais aucune vérification. Si l'utilisateur n'a pas centré, toutes les corrections seront erronées.

**Solution**: Ajouter une vérification UI ou un warning explicite.

---

### 2.4 Statut Non Remis à 'idle' en Cas d'Erreur Handler

**Fichier**: `services/command_handlers.py:106-109`

```python
except Exception as e:
    logger.error(f"Erreur GOTO: {e}")
    current_status['status'] = 'error'
    current_status['error'] = str(e)
```

**Problème**: Le statut reste 'error' indéfiniment. Pas de recovery automatique.

**Solution**: Ajouter un mécanisme de timeout qui remet 'idle' après X secondes.

---

## 3. OPPORTUNITÉS DE REFACTORING

### 3.1 Extraction de Configuration Motor (PRIORITÉ: HAUTE)

**Problème**: Logique de parsing config dupliquée entre `moteur.py` et `moteur_simule.py`.

**Fichiers concernés**:
- `core/hardware/moteur.py:225-243`
- `core/hardware/moteur_simule.py:39-57`

**Refactoring proposé**:
```python
# core/hardware/motor_config_parser.py
class MotorConfigParser:
    @staticmethod
    def parse(config_moteur) -> MotorParams:
        if hasattr(config_moteur, 'gpio_pins'):
            return MotorParams.from_dataclass(config_moteur)
        else:
            return MotorParams.from_dict(config_moteur)
```

---

### 3.2 Unification de la Détection Encodeur (PRIORITÉ: HAUTE)

**Problème**: 3 patterns différents pour détecter si l'encodeur est disponible.

**Fichiers concernés**:
- `core/tracking/tracker.py:97` - `MoteurCoupole.get_daemon_angle()`
- `core/tracking/tracker.py:320-365` - `_check_initial_goto()`
- `services/motor_service.py:88` - `daemon_reader.is_available()`

**Refactoring proposé**:
```python
# core/hardware/hardware_detector.py
class HardwareDetector:
    @staticmethod
    def check_encoder_daemon() -> tuple[bool, str, Optional[float]]:
        """
        Returns: (available, error_message, current_angle)
        Centralise TOUTE la logique de détection encodeur.
        """
```

---

### 3.3 Simplification de la Logique de Lissage (PRIORITÉ: MOYENNE)

**Fichier**: `core/tracking/tracker.py:608-660`

**Problème**: La méthode `_smooth_position_cible()` utilise des seuils arbitraires (10°, 5 échantillons) sans documentation du pourquoi.

**Refactoring proposé**:
- Documenter le raisonnement derrière les paramètres
- Considérer un filtre de Kalman pour plus de robustesse
- Ou au minimum, externaliser les constantes

---

### 3.4 Standardisation du Logging (PRIORITÉ: MOYENNE)

**Problème**: Mix de `print()`, `self.logger`, et `self.python_logger` dans le code.

**Refactoring proposé**:
- Utiliser `logging.getLogger(__name__)` partout
- Supprimer tous les `print()` de production

---

### 3.5 Tests d'Intégration Manquants (PRIORITÉ: HAUTE)

**Problème**: Pas de tests end-to-end couvrant le flux Django → IPC → Motor Service → Tracker.

**Refactoring proposé**:
```python
# tests/test_integration.py
class TestIntegrationFlow:
    def test_goto_command_flow(self):
        """Test complet: Django envoie GOTO, Motor Service exécute, statut retourné."""

    def test_tracking_start_stop_flow(self):
        """Test complet: Démarrage/arrêt suivi via IPC."""
```

---

## 4. PLAN D'IMPLÉMENTATION PRIORISÉ

### Phase 1: Corrections Critiques (Immédiat) ✅ TERMINÉE

| # | Tâche | Fichier | Statut |
|---|-------|---------|--------|
| 1.1 | Isoler état MoteurSimule | `moteur_simule.py` | ✅ Terminé |
| 1.2 | Ajouter verrou fcntl à IPC | `ipc_manager.py` | ✅ Terminé |
| 1.3 | Unifier DaemonEncoderReader | `moteur.py`, `motor_service.py` | ✅ Terminé |
| 1.4 | Spécifier exceptions feedback | `tracker.py` | ✅ Terminé |

### Phase 2: Consolidation (Court terme) ✅ TERMINÉE

| # | Tâche | Fichier | Statut |
|---|-------|---------|--------|
| 2.1 | Centraliser constantes | `config.json`, `config_loader.py` | ✅ c0285d2 |
| 2.2 | Extraire MotorConfigParser | `motor_config_parser.py` | ✅ c76a5f9 |
| 2.3 | Ajouter timeout global GOTO | `feedback_controller.py` | ✅ e2fd4ac |
| 2.4 | Recovery automatique erreur | `motor_service.py`, `command_handlers.py` | ✅ a9c568a |

### Phase 3: Tests & Documentation (Moyen terme)

| # | Tâche | Fichier | Statut |
|---|-------|---------|--------|
| 3.1 | Tests d'intégration IPC | `tests/test_integration.py` | ✅ 05a067b |
| 3.2 | Documenter algorithme lissage | `tracker.py` | ✅ 90cbbf4 |
| 3.3 | Standardiser logging | tous | ✅ Terminé |

---

## 5. RISQUES ET MITIGATIONS

| Risque | Probabilité | Impact | Mitigation |
|--------|-------------|--------|------------|
| Race condition IPC | Moyenne | Haut | Phase 1.1 - Verrou fcntl |
| Tests non isolés | Basse | Moyen | Phase 1.2 - État isolé |
| Erreurs masquées | Moyenne | Haut | Phase 1.4 - Exceptions spécifiques |
| Régression | Basse | Moyen | Exécuter suite tests après chaque changement |

---

## 6. VALIDATION

Après chaque phase:
1. Exécuter `uv run pytest -v` (tous les tests)
2. Test manuel sur Raspberry Pi si disponible
3. Vérifier les logs pour erreurs/warnings

---

## Approbation

Ce plan est soumis pour validation. Merci de confirmer:
- [ ] Priorités acceptées
- [ ] Ordre d'implémentation OK
- [ ] Questions/clarifications

---

*Document généré automatiquement par Claude Code le 24/12/2025*
