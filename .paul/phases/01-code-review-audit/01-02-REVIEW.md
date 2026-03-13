# Code Review Report — 01-02: Tracking & Observatoire

**Date:** 2026-03-13
**Scope:** core/tracking/, core/observatoire/
**Fichiers analysés:** 8/8 (tracker.py, adaptive_tracking.py, abaque_manager.py, tracking_logger.py, calculations.py, ephemerides.py, catalogue.py, __init__.py)

---

## Résumé

| Sévérité | Nombre |
|----------|--------|
| CRITIQUE | 2 |
| HAUT | 6 |
| MOYEN | 10 |
| BAS | 7 |
| **Total** | **25** |

---

## CRITIQUE

### C-03: Référence morte à FAST_TRACK dans tracker.py
- **Fichier:** `core/tracking/tracker.py:558-566`
- **Type:** code-mort, incohérence
- **Description:** `MODE_ICONS` contient encore `'fast_track': '🟣'` et `LARGE_MOVEMENT_THRESHOLD = 30.0` avec commentaire "au-delà, on utilise FAST_TRACK". FAST_TRACK a été supprimé en v4.4. Ces références mortes pourraient induire en erreur un développeur et masquent le fait que CONTINUOUS gère maintenant les grands déplacements.
- **Recommandation:** Supprimer l'entrée `fast_track` de `MODE_ICONS` et mettre à jour le commentaire de `LARGE_MOVEMENT_THRESHOLD`.

### C-04: `catalogue.py` charge config.json avec chemin relatif dans `rechercher()`
- **Fichier:** `core/observatoire/catalogue.py:267-268`
- **Type:** bug, sécurité
- **Description:** `rechercher()` ouvre directement `Path("data") / "config.json"` avec un chemin relatif. Cela échoue si le working directory n'est pas la racine du projet (ex: lancé depuis `web/` par Django, ou depuis `tests/`). De plus, le catalogue importe `CACHE_FILE` depuis `core.config.config` (l'ancien système de config — voir finding C-01), créant une dépendance sur le système deprecated.
- **Recommandation:** Utiliser `load_config()` de `config_loader.py` pour obtenir latitude/longitude. Ou au minimum utiliser `PROJECT_ROOT` de `config.py` pour construire un chemin absolu.

---

## HAUT

### H-09: `tracker.py` appelle `MoteurCoupole.get_daemon_angle()` statiquement en mode simulation
- **Fichier:** `core/tracking/tracker.py:91,314,328,434,457,510`
- **Type:** bug
- **Description:** Plusieurs méthodes (`_init_encoder`, `_check_initial_goto`, `_execute_initial_goto`) appellent `MoteurCoupole.get_daemon_angle()` et `MoteurCoupole.get_daemon_status()` comme méthodes statiques. En mode simulation (pas de Raspberry Pi), `MoteurCoupole` ne peut pas être instancié (pas de GPIO), donc ces appels statiques accèdent au vrai daemon `/dev/shm/` qui n'existe pas. Cela génère des `RuntimeError` silencieusement catchées, mais le GOTO initial et la synchronisation encodeur ne fonctionnent jamais en simulation.
- **Recommandation:** Utiliser `self.moteur.get_daemon_angle()` au lieu de `MoteurCoupole.get_daemon_angle()`, car `MoteurSimule` implémente ces méthodes et retourne des positions simulées.

### H-10: `_smooth_position_cible` importe `math` à chaque appel
- **Fichier:** `core/tracking/tracker.py:676`
- **Type:** performance
- **Description:** `import math` est à l'intérieur de la méthode `_smooth_position_cible()`, appelée à chaque `get_status()` (toutes les 1-2 secondes via l'API web). Bien que Python cache les imports, c'est un anti-pattern. L'import devrait être au niveau du module.
- **Recommandation:** Déplacer `import math` en tête de fichier (il est déjà utilisé dans d'autres modules du projet).

### H-11: `verify_shortest_path()` duplique `shortest_angular_distance()`
- **Fichier:** `core/tracking/adaptive_tracking.py:330-389`
- **Type:** duplication, bug-risk
- **Description:** `verify_shortest_path()` réimplémente le calcul du chemin le plus court en ~60 lignes, alors que `shortest_angular_distance()` de `angle_utils.py` fait exactement la même chose en 10 lignes. La version dans adaptive_tracking est plus complexe et produit le même résultat. Deux implémentations = risque de divergence.
- **Recommandation:** Remplacer par un appel à `shortest_angular_distance()` + construction du string de description.

### H-12: `abaque_manager.py` — `get_val()` utilise `list.index()` O(n)
- **Fichier:** `core/tracking/abaque_manager.py:192-193`
- **Type:** performance
- **Description:** `get_val()` dans `_interpolate_circular()` fait `list(data['az_astre']).index(azimut)` pour trouver l'indice. `list.index()` est O(n) et convertit à chaque appel. Avec ~275 points et 4 appels par interpolation, c'est ~1100 recherches linéaires par correction. Pour le tracking (1 appel/60s), c'est acceptable. Mais pour le statut (1 appel/s), ça s'accumule.
- **Recommandation:** Pré-construire un dictionnaire `{azimut: index}` par altitude lors du chargement.

### H-13: `abaque_manager.py` — extrapolation silencieuse hors bornes
- **Fichier:** `core/tracking/abaque_manager.py:242-249`
- **Type:** bug-risk
- **Description:** Quand l'altitude ou l'azimut est hors des bornes de l'abaque, `_interpolate_circular()` clamp silencieusement aux bornes (via `max(0, min(i_alt, ...))` lignes 183-184). Le flag `in_bounds` est calculé mais pas utilisé pour avertir. Si l'objet est à une altitude plus basse que la plus petite mesure, les résultats sont extrapolés sans avertissement.
- **Recommandation:** Logger un warning quand `in_bounds` est False. Considérer un fallback plus explicite.

### H-14: `catalogue.py` — résultat `rechercher()` incohérent pour les planètes
- **Fichier:** `core/observatoire/catalogue.py:280-285`
- **Type:** bug
- **Description:** Pour les planètes, `rechercher()` retourne `{"name": ..., "ra_deg": ..., "dec_deg": ..., "type": "planet"}`. Mais pour les objets SIMBAD, il retourne `{"nom": ..., "ra_deg": ..., "dec_deg": ..., "type": "Unknown"}`. Clés différentes : `"name"` vs `"nom"`, `"planet"` vs `"Unknown"`. Le `tracker.py` vérifie `result.get('is_planet', False)` (ligne 364) qui n'existe jamais dans le résultat planète — donc `is_planet` est toujours False et les planètes sont traitées comme des étoiles fixes.
- **Recommandation:** Normaliser la structure de retour. Ajouter `"is_planet": True` dans le résultat planète.

---

## MOYEN

### M-13: `PlanetaryEphemerides` instanciée à chaque calcul de coords
- **Fichier:** `core/tracking/tracker.py:184`
- **Type:** performance
- **Description:** `_calculate_current_coords()` crée une nouvelle instance `PlanetaryEphemerides()` à chaque appel. Cette méthode est appelée à chaque correction et chaque status. `PlanetaryEphemerides` est stateless — une seule instance suffit.
- **Recommandation:** Créer l'instance une fois dans `__init__` ou utiliser les méthodes statiques directement.

### M-14: `_julian_date()` dupliquée dans `ephemerides.py` et `calculations.py`
- **Fichier:** `core/observatoire/ephemerides.py:142-156`, `core/observatoire/calculations.py:113-123`
- **Type:** duplication
- **Description:** La même fonction de calcul du jour Julien existe dans les deux modules, avec des noms légèrement différents (`_julian_date` vs `_calculate_julian_day`). Code identique.
- **Recommandation:** Extraire dans `angle_utils.py` ou un module `astro_utils.py` partagé.

### M-15: `calculations.py` — `_normaliser_angle_180/360` dupliquent `angle_utils.py`
- **Fichier:** `core/observatoire/calculations.py:44-59`
- **Type:** duplication
- **Description:** Méthodes statiques identiques à `normalize_angle_180/360` de `angle_utils.py`. Utilisées uniquement en interne par `calculations.py`.
- **Recommandation:** Remplacer par des imports de `angle_utils.py`.

### M-16: `calculations.py` — `_add_time_component()` jamais appelée
- **Fichier:** `core/observatoire/calculations.py:137-141`
- **Type:** code-mort
- **Description:** Méthode statique qui n'est appelée nulle part dans le code.
- **Recommandation:** Supprimer.

### M-17: `calculations.py` — `est_proche_meridien()` utilise `deja_jnow=True` sur coords J2000
- **Fichier:** `core/observatoire/calculations.py:287`
- **Type:** bug
- **Description:** `est_proche_meridien()` reçoit `ad_deg` et appelle `calculer_angle_horaire(ad_deg, ..., deja_jnow=True)`. Mais le paramètre `ad_deg` est probablement en J2000 (venant du catalogue). En passant `deja_jnow=True`, la conversion de précession est sautée, ce qui introduit une erreur de ~1° (50 arcsec/an × années depuis 2000).
- **Recommandation:** Passer `deja_jnow=False` ou documenter que l'appelant doit passer des coordonnées JNOW.

### M-18: `_apply_correction_sans_feedback()` n'utilise pas `motor_delay` du paramètre
- **Fichier:** `core/tracking/tracker.py:883-922`
- **Type:** incohérence
- **Description:** La méthode reçoit `motor_delay` et l'utilise correctement, mais le commentaire dit "ancienne méthode" et la boucle fait `faire_un_pas(delai=motor_delay)` pas par pas au lieu d'utiliser `self.moteur.rotation()` qui est plus efficace et gère déjà la direction.
- **Recommandation:** Simplifier en utilisant `self.moteur.rotation(delta_deg, vitesse=motor_delay)`.

### M-19: `adaptive_tracking.py` — `_get_continuous_params_from_config` est `@staticmethod` inutilement
- **Fichier:** `core/tracking/adaptive_tracking.py:141-158`
- **Type:** design
- **Description:** La méthode statique est wrappée par `_get_continuous_params()` qui passe `self.adaptive_config`. Pas de raison d'avoir une méthode statique ici.
- **Recommandation:** Convertir en méthode d'instance simple.

### M-20: `tracker.py` — `drift_tracking['corrections_log']` grandit sans limite
- **Fichier:** `core/tracking/tracker.py:749-755`
- **Type:** memory-leak
- **Description:** Chaque correction append un dict dans `corrections_log`. Pour une session de 8h avec corrections toutes les 30s, ça fait ~960 entrées. Pas critique, mais dans un environnement Raspberry Pi à mémoire limitée, c'est à surveiller.
- **Recommandation:** Limiter à N dernières entrées avec un `deque(maxlen=100)` ou vider périodiquement.

### M-21: `tracking_logger.py` — seuil zénith en dur à 85°
- **Fichier:** `core/tracking/tracking_logger.py:69`
- **Type:** incohérence
- **Description:** `log_zenith()` utilise un seuil codé en dur à 85° alors que la config utilise 75° pour le zenith. Le logger ne signalera donc jamais l'approche du zénith entre 75° et 85°.
- **Recommandation:** Utiliser le seuil de configuration ou au moins le même 75°.

### M-22: `catalogue.py` — recherche SIMBAD reconfigurée à chaque appel
- **Fichier:** `core/observatoire/catalogue.py:108-123`
- **Type:** performance
- **Description:** `rechercher_simbad()` crée une nouvelle instance `Simbad()` à chaque appel au lieu d'utiliser `self.simbad` (déjà prévu dans `__init__` ligne 50).
- **Recommandation:** Utiliser la configuration lazy prévue dans `__init__`.

---

## BAS

### L-10: Emoji dans les messages de log de tracker.py et adaptive_tracking.py
- **Fichier:** `core/tracking/tracker.py` (multiples), `core/tracking/adaptive_tracking.py:273,382-387`
- **Type:** style
- **Description:** Même problème que L-01 — emoji dans les logs pouvant poser problème sur Pi.

### L-11: `tracking_logger.py` — logger nommé `"CoupoleUPAN.Tracking"`
- **Fichier:** `core/tracking/tracking_logger.py:12`
- **Type:** style
- **Description:** Nom de logger incohérent avec le reste du projet (pas de namespace `core.tracking`). "CoupoleUPAN" semble être un ancien nom de projet.
- **Recommandation:** Renommer en `"core.tracking.logger"` pour cohérence.

### L-12: `ephemerides.py` — `_simple_planet_position()` très imprécise
- **Fichier:** `core/observatoire/ephemerides.py:106-140`
- **Type:** documentation
- **Description:** Le fallback sans Astropy donne des résultats très approximatifs (commentaire "ATTENTION: très imprécis" ligne 134). C'est documenté mais pourrait surprendre si Astropy n'est pas installé en production.
- **Recommandation:** Logger un warning visible si le fallback est utilisé (pas juste dans le test `__main__`).

### L-13: `calculations.py` — `calculer_coords_horizontales_coupole()` retourne toujours 0.0 comme correction
- **Fichier:** `core/observatoire/calculations.py:229-251`
- **Type:** code-mort
- **Description:** Méthode qui wrape `calculer_coords_horizontales()` et ajoute `0.0`. Si rien n'utilise cette méthode ou le 3ème élément du tuple, c'est du code mort.
- **Recommandation:** Vérifier les usages. Si uniquement `calculer_coords_horizontales()` est utilisé, supprimer cette méthode.

### L-14: `abaque_manager.py` — `export_to_json()` jamais utilisé en production
- **Fichier:** `core/tracking/abaque_manager.py:319-353`
- **Type:** code-mort probable
- **Description:** Utilitaire d'export qui n'est probablement appelé que manuellement. Pas critique mais ajoute du code à maintenir.

### L-15: `catalogue.py` — lignes vides multiples et indentation incohérente
- **Fichier:** `core/observatoire/catalogue.py` (multiples)
- **Type:** style
- **Description:** Lignes vides excessives (117-118, 125-126, 144, 198, 217, 227), indentation de docstrings incohérente (lignes 87-106).

### L-16: `adaptive_tracking.py` — code de test `__main__` avec 496 lignes
- **Fichier:** `core/tracking/adaptive_tracking.py:443-496`
- **Type:** style
- **Description:** Le bloc `if __name__ == "__main__"` est utile pour le diagnostic mais devrait idéalement être dans `tests/`.

---

## Observations transversales

### Duplication de code
Pattern systématique de fonctions réimplémentées plutôt qu'importées :
- `shortest_angular_distance` dupliqué dans `verify_shortest_path`
- `normalize_angle_180/360` dupliqué dans `calculations.py`
- `_julian_date` dupliqué dans `calculations.py` et `ephemerides.py`

### Simulation
Le tracker utilise `MoteurCoupole` statiquement (H-09), rendant la simulation incomplète. Le GOTO initial et la calibration encodeur ne fonctionnent jamais en mode simulation.

### Configuration
Le catalogue dépend de `config.py` (ancien système) via `CACHE_FILE`, ajoutant une dépendance au problème C-01 identifié dans le rapport 01-01.

---

*Rapport généré : 2026-03-13*
*Reviewer : Claude (revue automatisée)*
