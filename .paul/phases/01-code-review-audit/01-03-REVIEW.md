# Code Review Report — 01-03: Services & Web

**Date:** 2026-03-13
**Scope:** services/motor_service.py, web/hardware/, web/tracking/, web/driftapp_web/
**Fichiers analysés:** 8/8

---

## Résumé

| Sévérité | Nombre |
|----------|--------|
| CRITIQUE | 2 |
| HAUT | 5 |
| MOYEN | 8 |
| BAS | 5 |
| **Total** | **20** |

---

## CRITIQUE

### C-05: Django SECRET_KEY en dur et DEBUG=True
- **Fichier:** `web/driftapp_web/settings.py:19,22`
- **Type:** sécurité
- **Description:** `SECRET_KEY = 'django-insecure-driftapp-dev-key-change-in-production'` et `DEBUG = True` sont en dur. Même si l'application tourne en réseau local, le SECRET_KEY permet de signer les sessions/cookies. `ALLOWED_HOSTS = ['*']` (ligne 25) rend le serveur accessible à tout le réseau. En combinaison avec DEBUG=True, les pages d'erreur exposent le code source et la configuration.
- **Recommandation:** Charger SECRET_KEY depuis une variable d'environnement ou un fichier `.env`. Configurer `DEBUG = os.environ.get('DEBUG', 'False') == 'True'`. Restreindre ALLOWED_HOSTS aux IP du réseau local.

### C-06: `MotorServiceClient` dupliqué dans 2 fichiers
- **Fichier:** `web/hardware/views.py:14-54`, `web/tracking/views.py:17-60`
- **Type:** duplication, bug-risk
- **Description:** Deux classes `MotorServiceClient` identiques existent dans `hardware/views.py` et `tracking/views.py`, chacune avec sa propre instance globale `motor_client`. Elles partagent le même fichier IPC mais tout changement dans l'une ne sera pas reflété dans l'autre. Risque de divergence lors de la maintenance.
- **Recommandation:** Extraire `MotorServiceClient` dans un module partagé (`web/common/ipc_client.py` ou similaire) et importer une seule instance.

---

## HAUT

### H-15: `motor_service.py` — `_load_parking_config` accède à `raw_config` inexistant
- **Fichier:** `services/motor_service.py:376-386`
- **Type:** bug
- **Description:** `_load_parking_config()` vérifie `hasattr(self.config, 'raw_config')` puis `self.config.raw_config['parking']`. Mais `DriftAppConfig` (config_loader.py) ne stocke pas le JSON brut dans un attribut `raw_config`. Ce code ne fonctionne donc jamais et tombe toujours dans le fallback `DEFAULT_PARKING_CONFIG`. La configuration parking de `config.json` est ignorée.
- **Recommandation:** Ajouter un attribut `raw_config` à `DriftAppConfig` dans config_loader.py, ou créer un `ParkingConfig` dataclass propre.

### H-16: `motor_service.py` — `calculate_sunset()` est une approximation incorrecte
- **Fichier:** `services/motor_service.py:175-203`
- **Type:** bug
- **Description:** `calculate_sunset()` calcule le coucher en prenant "le lever + 2× le temps entre lever et midi". Cette approximation est mathématiquement incorrecte (le midi solaire n'est pas à 12h00 locale, et la durée du jour n'est pas symétrique autour de 12h). L'erreur peut atteindre 30-60 minutes.
- **Recommandation:** Implémenter le calcul correct du coucher (même algo que le lever mais avec `-ha` au lieu de `+ha`), ou utiliser Astropy si disponible.

### H-17: `motor_service.py` — `calculate_sunrise()` timezone en dur pour la France
- **Fichier:** `services/motor_service.py:164-172`
- **Type:** bug-risk
- **Description:** Le décalage horaire est codé en dur : `+1h` en hiver (CET), `+2h` si mois entre 3 et 10 (CEST). Cela est approximatif : le changement d'heure ne se fait pas le 1er mars/1er octobre. De plus, si le projet est utilisé à un autre fuseau, c'est faux.
- **Recommandation:** Utiliser la config `tz_offset` de `config.json` ou le module `zoneinfo`/`pytz` avec le fuseau `"Europe/Paris"`.

### H-18: `motor_service.py` — ~900 lignes, God Class
- **Fichier:** `services/motor_service.py`
- **Type:** design
- **Description:** `MotorService` est une classe monolithique de ~900 lignes qui gère : IPC, GOTO, JOG, tracking, parking, calibration, sunrise, mouvement continu, status, et plus. Cela rend le code difficile à tester et à maintenir.
- **Recommandation:** Extraire les responsabilités en modules : `ParkingManager`, `TrackingManager`, `IPCHandler`. Le motor_service deviendrait un orchestrateur léger.

### H-19: API views — aucune validation de type sur `speed`
- **Fichier:** `web/hardware/views.py:89-92`
- **Type:** bug, sécurité
- **Description:** `GotoView` et `JogView` font `float(speed)` sans try/except. Si un utilisateur envoie `speed: "abc"`, le serveur crash avec un ValueError non géré (erreur 500). De plus, aucune borne n'est vérifiée — un `speed: 0` causerait une division par zéro dans le moteur.
- **Recommandation:** Valider le type et les bornes de `speed` (ex: 0.00001 ≤ speed ≤ 0.01). Utiliser des serializers DRF pour la validation.

---

## MOYEN

### M-23: `motor_service.py` — `_julian_date` dupliquée (3ème copie)
- **Fichier:** `services/motor_service.py:91-98` (dans `calculate_sunrise`)
- **Type:** duplication
- **Description:** Troisième implémentation du jour Julien (après `calculations.py` et `ephemerides.py`).

### M-24: `motor_service.py` — `write_status()` utilise écriture atomique mais `read_command()` non
- **Fichier:** `services/motor_service.py:686-704`
- **Type:** incohérence
- **Description:** `write_status()` fait correctement tmp+rename pour l'atomicité, mais `read_command()` lit directement sans protection. Si Django écrit pendant que motor_service lit, le JSON peut être tronqué.
- **Recommandation:** Utiliser le même pattern tmp+rename côté Django (dans `MotorServiceClient.send_command`).

### M-25: `motor_service.py` — `handle_continuous()` utilise un thread sans protection
- **Fichier:** `services/motor_service.py` (handle_continuous)
- **Type:** bug-risk
- **Description:** Le mouvement continu utilise un thread séparé (`self.continuous_thread`). Si deux commandes `continuous` arrivent rapidement, le deuxième thread pourrait démarrer avant que le premier ne s'arrête, créant des conflits GPIO.
- **Recommandation:** Vérifier et terminer le thread existant avant d'en créer un nouveau, avec un lock.

### M-26: `ParkView` — position parking en dur à 44.0
- **Fichier:** `web/hardware/views.py:276`
- **Type:** incohérence
- **Description:** Le message de réponse dit `'target': 44.0` en dur alors que la position parking devrait venir de la configuration.
- **Recommandation:** Lire la position depuis la config ou ne pas inclure de target dans la réponse (le motor_service gère la logique).

### M-27: `ObjectListView` appelle `get_objets_disponibles()` potentiellement inexistant
- **Fichier:** `web/tracking/views.py:148`
- **Type:** bug
- **Description:** `catalogue.get_objets_disponibles()` est appelé mais cette méthode n'existe pas dans `GestionnaireCatalogue`. Cela crasherait avec `AttributeError`.
- **Recommandation:** Vérifier si la méthode existe. Si non, soit l'ajouter, soit retourner `catalogue.objets` directement.

### M-28: `settings.py` — log file path non garanti
- **Fichier:** `web/driftapp_web/settings.py:134`
- **Type:** bug-risk
- **Description:** `'filename': PROJECT_ROOT / 'logs' / 'django.log'` — si le répertoire `logs/` n'existe pas au démarrage de Django, le FileHandler échoue silencieusement.
- **Recommandation:** Créer le répertoire dans settings.py ou utiliser `os.makedirs(logs_dir, exist_ok=True)`.

### M-29: `settings.py` — pas de CSRF exemption pour l'API REST
- **Fichier:** `web/driftapp_web/settings.py:46`
- **Type:** design
- **Description:** `CsrfViewMiddleware` est actif mais les vues API utilisent `APIView` sans `@csrf_exempt`. DRF désactive le CSRF par défaut pour les SessionAuthentication non utilisées, mais ce serait plus propre avec une configuration explicite.
- **Recommandation:** Soit expliciter `CSRF_TRUSTED_ORIGINS`, soit retirer `CsrfViewMiddleware` si l'API n'utilise pas de sessions.

### M-30: `motor_service.py` — `sys.path.insert(0, ...)` manipulation de path
- **Fichier:** `services/motor_service.py:34`
- **Type:** design
- **Description:** `sys.path.insert(0, str(Path(__file__).parent.parent))` est nécessaire car le service tourne comme script indépendant. C'est un pattern fragile — si le service est déplacé, il casse. Même chose dans `settings.py:16`.
- **Recommandation:** Acceptable pour l'architecture actuelle (multi-process sans package installé). À améliorer avec un `pyproject.toml` et installation en mode `pip install -e .` dans la Phase 4 (CI/CD).

---

## BAS

### L-17: `motor_service.py` — `import math` mais aussi des calculs en ligne
- **Fichier:** `services/motor_service.py`
- **Type:** style
- **Description:** Calculs astronomiques (sunrise/sunset) mélangés avec la logique de service moteur. Ces fonctions devraient être dans `calculations.py`.

### L-18: `GotoView`, `JogView`, etc. — code boilerplate répétitif
- **Fichier:** `web/hardware/views.py`
- **Type:** style
- **Description:** Pattern identique dans toutes les vues : valider → send_command → Response. Pourrait être factorisé avec une vue de base.

### L-19: Emoji dans les logs motor_service.py
- **Fichier:** `services/motor_service.py` (multiples)
- **Type:** style (cohérent avec L-01, L-10)

### L-20: `web/tracking/views.py` — `ObjectSearchView` min query length = 1
- **Fichier:** `web/tracking/views.py:166`
- **Type:** design
- **Description:** `len(query) < 1` — une recherche d'un seul caractère risque de retourner trop de résultats ou de faire un appel SIMBAD inutile.
- **Recommandation:** Augmenter le minimum à 2 caractères.

### L-21: `web/driftapp_web/urls.py` — admin inclus sans usage
- **Fichier:** `web/driftapp_web/urls.py:9`
- **Type:** code-mort
- **Description:** `path('admin/', admin.site.urls)` est inclus mais il n'y a aucun modèle Django (pas de migrations, pas de User). L'admin est inutile et expose une surface d'attaque potentielle.
- **Recommandation:** Retirer ou commenter tant qu'il n'y a pas de modèles.

---

## Observations transversales

### Architecture IPC
L'architecture à 3 processus (daemon encodeur + motor_service + Django) est solide. L'écriture atomique du status (tmp+rename) est bonne pratique. L'absence de cette atomicité côté commande (Django → motor_service) est un risque mineur.

### Motor Service monolithique
Avec ~900 lignes, `motor_service.py` est le fichier le plus complexe du projet. Il mélange trop de responsabilités. Le refactoring de la Phase 2 devrait prioritiser sa décomposition.

### Sécurité Web
Pour un usage en réseau local d'observatoire, les risques sont limités. Mais `DEBUG=True` + `ALLOWED_HOSTS=['*']` + admin exposé + pas de validation des inputs représentent des vulnérabilités si le réseau est compromis.

---

*Rapport généré : 2026-03-13*
*Reviewer : Claude (revue automatisée)*
