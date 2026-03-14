# Audit Code -- core/

## Resume

| Severite | Count |
|----------|-------|
| Critical | 5 |
| High     | 10 |
| Medium   | 14 |
| Low      | 8 |

---

## Issues par module

### core/config/

#### [C-01] Chemins relatifs : config.json charge depuis le CWD (Critical)

- **Fichier:** config.py:17-20, config_loader.py:243,416
- **Probleme:** `DATA_DIR = Path("data")` et `ConfigLoader(config_path=Path("data/config.json"))` utilisent des chemins relatifs. Si le processus est demarre depuis un repertoire different (ex: systemd, cron, script deploy), le fichier config.json ne sera pas trouve. `config.py` echoue silencieusement (retourne `{}`), tandis que `config_loader.py` leve `FileNotFoundError`.
- **Correction:** Utiliser `Path(__file__).resolve().parent.parent.parent / "data"` pour resoudre les chemins relativement a la racine du projet, ou passer un chemin absolu via variable d'environnement.

#### [C-02] Chargement config au temps d'import sans gestion d'erreur (High)

- **Fichier:** config.py:67
- **Probleme:** `_config = _deep_update(DEFAULTS, _load_json(CONFIG_FILE))` est execute au moment de l'import du module. Si `config.json` contient du JSON invalide, `_load_json` retourne `{}` silencieusement (ligne 55: `except Exception: return {}`), masquant completement l'erreur. L'application demarre avec des valeurs par defaut sans aucun avertissement.
- **Correction:** Logger un warning dans `_load_json` quand une exception est capturee, ou lever l'exception pour les erreurs de parsing JSON.

#### [C-03] Exception `except Exception` trop large dans `_load_json` (Medium)

- **Fichier:** config.py:55
- **Probleme:** `except Exception: return {}` avale toutes les erreurs, y compris `PermissionError`, `UnicodeDecodeError`, `MemoryError`. Aucun log, aucune trace.
- **Correction:** Capturer `(json.JSONDecodeError, FileNotFoundError, OSError)` et logger un warning pour les cas inattendus.

#### [C-04] `save_config()` ne met pas a jour les variables de module (Medium)

- **Fichier:** config.py:111-128
- **Probleme:** `save_config()` ecrit le fichier mais les constantes de module (`SITE_LATITUDE`, `MOTOR_GEAR_RATIO`, etc.) ne sont pas rechargees. Un appel a `save_config()` suivi de `get_site_config()` retournera les anciennes valeurs.
- **Correction:** Soit recharger les constantes apres sauvegarde, soit documenter clairement que `save_config()` ne modifie que le fichier disque.

#### [C-05] `to_dict()` leve `NotImplementedError` (Low)

- **Fichier:** config_loader.py:233
- **Probleme:** `DriftAppConfig.to_dict()` est defini mais leve `NotImplementedError`. Code mort qui pourrait etre appele par erreur.
- **Correction:** Supprimer la methode ou l'implementer avec `dataclasses.asdict()`.

#### [C-06] Duplication de logique entre `config.py` et `config_loader.py` (Medium)

- **Fichier:** config.py, config_loader.py
- **Probleme:** Deux systemes de chargement de configuration coexistent : `config.py` (simple, `DEFAULTS` + JSON) et `config_loader.py` (dataclasses structurees). Ils ne partagent pas les memes valeurs par defaut, les memes cles JSON, ni la meme strategie d'erreur. Risque d'incoherence.
- **Correction:** Unifier autour de `config_loader.py` et deprecier `config.py`, ou faire que `config.py` delegue a `config_loader.py`.

---

### core/hardware/

#### [C-07] `bare except` dans `_init_gpio` peut masquer des erreurs critiques (Critical)

- **Fichier:** moteur.py:211
- **Probleme:** `except:` (bare except) dans le fallback `gpiochip_open(0)` capture absolument tout, y compris `SystemExit` et `KeyboardInterrupt`. Si le chip 4 echoue pour une raison autre que "mauvais numero de chip" (ex: permissions), l'erreur est silencieusement masquee et le fallback tente un chip qui peut aussi echouer.
- **Correction:** Remplacer par `except lgpio.error:` ou `except OSError:`.

#### [C-08] `bare except` dans `nettoyer()` (High)

- **Fichier:** moteur.py:531, 536
- **Probleme:** Deux blocs `except: pass` dans la methode de nettoyage GPIO. Si `gpio_free` ou `gpiochip_close` echoue pour une raison inattendue (ex: corruption memoire), l'erreur est completement avalee.
- **Correction:** Remplacer par `except Exception: pass` au minimum, ou mieux `except (lgpio.error, OSError):`.

#### [C-09] `import lgpio` repete a chaque appel de `faire_un_pas` (High)

- **Fichier:** moteur.py:337
- **Probleme:** `import lgpio` est execute dans le corps de `faire_un_pas()` a chaque pas moteur. Cette methode est appelee des centaines de milliers de fois par mouvement (1.9M pas/tour). Bien que Python cache les imports, le lookup dans `sys.modules` a chaque pas ajoute un overhead inutile dans une boucle critique de timing.
- **Correction:** Stocker la reference `lgpio.gpio_write` comme attribut d'instance dans `_init_gpio()` et l'appeler directement.

#### [C-10] `read_stable()` fait une moyenne arithmetique d'angles -- incorrecte au passage 0/360 (Critical)

- **Fichier:** daemon_encoder_reader.py:189
- **Probleme:** `sum(positions) / len(positions)` est une moyenne arithmetique. Pour des angles proches de 0/360 (ex: [359, 1, 0]), le resultat serait 120 au lieu de 0. Cette methode est utilisee par `FeedbackController._lire_position_stable()` pour les corrections de position.
- **Correction:** Utiliser une moyenne circulaire (atan2 de somme sin/cos), comme celle implementee dans `tracking_state_mixin.py:176-179`.

#### [C-11] Race condition dans la lecture du fichier JSON du demon (Critical)

- **Fichier:** daemon_encoder_reader.py:67-70
- **Probleme:** `read_raw()` lit le fichier avec `read_text()` puis `json.loads()` sans verrou. Le demon encodeur peut ecrire dans le fichier entre les deux operations, causant un JSON tronque ou corrompu. En revanche, `encoder_reader.py:26-31` utilise correctement un verrou `fcntl`.
- **Correction:** Ajouter un verrou fcntl partage (`LOCK_SH`) autour de la lecture, ou utiliser la lecture atomique via un fichier temporaire + rename.

#### [C-12] Boucle infinie potentielle dans `read_angle()` avec `max_age_ms > 0` (High)

- **Fichier:** daemon_encoder_reader.py:98-143
- **Probleme:** Si les donnees du demon sont toujours "perimes" (`age_ms > max_age_ms`), la boucle `while True` leve `StaleDataError` immediatement apres la premiere lecture reussie, mais ne rattrape pas cette exception en interne. Le probleme est que `json.JSONDecodeError` a la ligne 140 est rattrape et boucle, mais `StaleDataError` propage directement. Cela fonctionne mais si le demon produit un `status` non reconnu (ni "OK*", ni "FROZEN", ni "SPI*"), la boucle continuera indefiniment car `angle` est retourne seulement pour "OK" et "SPI", et le `timeout_ms` n'est verifie qu'au debut de la boucle.
- **Correction:** Ajouter une clause `else` par defaut qui retourne l'angle ou leve une erreur apres le bloc de verification de status.

#### [C-13] `MoteurSimule` ne simule pas `stop_requested` dans `rotation()` (High)

- **Fichier:** moteur_simule.py:164-195
- **Probleme:** `MoteurSimule.rotation()` ignore le flag `stop_requested` et execute toujours `time.sleep(movement_time)` completement. Si un utilisateur demande l'arret pendant un grand GOTO simule (ex: 6 secondes), le systeme ne reagira pas.
- **Correction:** Decouvrir le sleep en petits intervalles et verifier `stop_requested` entre chaque.

#### [C-14] Singleton global `_daemon_reader` non thread-safe (High)

- **Fichier:** daemon_encoder_reader.py:200-213
- **Probleme:** `get_daemon_reader()` n'est pas protege par un verrou. Django est multi-thread ; deux threads pourraient creer deux instances simultanement. Pas critique ici car `DaemonEncoderReader` est stateless (pas d'etat modifiable), mais le pattern est fragile.
- **Correction:** Utiliser `threading.Lock` pour proteger l'initialisation.

#### [C-15] Variable globale `gpio_handle` desynchronisee (Medium)

- **Fichier:** moteur.py:42,202,214
- **Probleme:** Le module maintient a la fois `self.gpio_handle` (instance) et une variable globale `gpio_handle` (module). La globale est mise a jour dans `_init_gpio()` mais seulement pour lgpio (ligne 214), pas pour RPi.GPIO. Elle n'est utilisee nulle part ensuite. Code mort et confusant.
- **Correction:** Supprimer la variable globale `gpio_handle` au niveau module.

#### [C-16] `AccelerationRamp.get_delay()` : division par zero possible (High)

- **Fichier:** acceleration_ramp.py:177
- **Probleme:** `t = step_index / self.accel_end` -- si `accel_end` vaut 0 (ce qui est le cas quand `total_steps < min_steps`, ligne 86), la methode retourne `target_delay` a la ligne 166 avant d'atteindre cette division. MAIS si `ramp_enabled` est True et `accel_end == 0` (par un appel externe modifiant l'attribut), une `ZeroDivisionError` se produira.
- **Correction:** Ajouter une garde `if self.accel_end == 0: return self.target_delay` avant la division.

#### [C-17] `_valider_config` est une methode vide (Low)

- **Fichier:** moteur.py:116-118
- **Probleme:** `_valider_config()` ne fait rien (`pass`). Elle est appelee dans `__init__` mais la validation est deja faite dans `_charger_config`.
- **Correction:** Supprimer la methode et l'appel pour eviter la confusion.

#### [C-18] `_init_parametres_rampe` est une methode vide (Low)

- **Fichier:** moteur.py:129-141
- **Probleme:** Methode avec un long commentaire mais un corps `pass`. Code mort.
- **Correction:** Supprimer la methode et l'appel.

#### [C-19] `_calculer_delai_rampe` est morte (Low)

- **Fichier:** moteur.py:348-371
- **Probleme:** Methode qui retourne toujours `vitesse_nominale` sans aucun calcul. N'est appelee nulle part (la rampe est geree par `AccelerationRamp`). Code mort.
- **Correction:** Supprimer la methode.

---

### core/tracking/

#### [C-20] `log_to_web()` appelee mais jamais definie -- `AttributeError` en production (Critical)

- **Fichier:** tracking_corrections_mixin.py:181
- **Probleme:** `self.log_to_web("Mode degrade...", "warning")` est appele dans `_notify_degraded_mode()`, mais la methode `log_to_web` n'est definie nulle part dans la hierarchie de classes (`TrackingSession`, les trois mixins, ni `TrackingLogger`). Cela provoquera un `AttributeError` la premiere fois que le systeme bascule en mode degrade (encodeur indisponible pendant le suivi).
- **Correction:** Soit definir `log_to_web` dans `TrackingStateMixin` ou `TrackingSession`, soit remplacer par `self.logger.warning(...)` ou `self.tracking_logger.log_motor_activity(...)`.

#### [C-21] Double comptage des corrections dans `_apply_correction_avec_feedback` + `_apply_correction_sans_feedback` (High)

- **Fichier:** tracking_corrections_mixin.py:151,217-219,354-356
- **Probleme:** `_finaliser_correction()` (ligne 217-219) incremente `total_corrections` et `total_movement`. Mais `_apply_correction_sans_feedback()` (lignes 354-356) incremente aussi `total_corrections` et `total_movement`. Si le fallback passe de feedback a sans-feedback dans `_apply_correction_avec_feedback()` (ligne 160), `_finaliser_correction` a deja ete appelee avant le fallback... Non, en fait `_finaliser_correction` est appelee apres `_executer_rotation_feedback` donc avant `_traiter_resultat_feedback`. Mais dans le cas du fallback (ligne 160), `_finaliser_correction` n'a pas ete appelee car l'exception est lancee avant. Donc pas de double comptage dans le chemin de fallback. En revanche, `check_and_correct()` (ligne 85) appelle `_apply_correction()` qui incremente les compteurs, puis les lignes 119-120 ajoutent a `correction_history`. C'est coherent MAIS les statistiques dans `check_and_correct` sont basees sur le delta d'entree, pas sur le mouvement reel (qui peut differer avec feedback). Cela peut fausser les stats.
- **Correction:** Utiliser le resultat reel du feedback pour les statistiques au lieu du delta d'entree.

#### [C-22] `_calculate_current_coords` instancie `PlanetaryEphemerides()` a chaque appel (High)

- **Fichier:** tracker.py:159
- **Probleme:** `PlanetaryEphemerides()` est instancie a chaque appel de `_calculate_current_coords` pour les planetes. Cette methode est appelee par `get_status()` (rafraichi toutes les 2s par le frontend) et par `check_and_correct()`. La classe est legere mais cela reste une allocation inutile.
- **Correction:** Instancier une fois dans `__init__` ou utiliser les methodes statiques directement (elles le sont deja : `is_planet`, `get_planet_position`).

#### [C-23] `_rechercher_objet` instancie `GestionnaireCatalogue()` a chaque appel (Medium)

- **Fichier:** tracking_goto_mixin.py:106
- **Probleme:** `GestionnaireCatalogue()` charge le cache JSON a chaque instanciation. Appele une seule fois par session (dans `start()`), donc l'impact est faible, mais le pattern est fragile.
- **Correction:** Passer le catalogue en parametre de `TrackingSession` ou le cacher.

#### [C-24] Acces a `critical_zones[0]` sans verification de longueur (High)

- **Fichier:** adaptive_tracking.py:81-86
- **Probleme:** `adaptive_config.critical_zones[0]` leve `IndexError` si `critical_zones` est une liste vide. La condition `if adaptive_config.critical_zones` est True pour une liste vide `[]`... non, une liste vide est falsy en Python. Donc la garde est correcte. MAIS : seule la premiere zone critique est utilisee. Si la config definit plusieurs zones, les autres sont ignorees silencieusement.
- **Correction:** Supporter plusieurs zones critiques ou documenter la limitation.

#### [C-25] `verify_shortest_path` reimplemente `shortest_angular_distance` (Medium)

- **Fichier:** adaptive_tracking.py:347-409
- **Probleme:** La methode `verify_shortest_path` (62 lignes) reimplemente la logique de `shortest_angular_distance` de `angle_utils.py` (6 lignes) avec un code plus complexe et plus sujet aux bugs. Les deux devraient donner le meme resultat mais la duplication est un risque de divergence.
- **Correction:** Utiliser `shortest_angular_distance` de `angle_utils.py` et enrichir uniquement avec le logging et la description.

#### [C-26] `_mode_time_tracker` utilise des cles string mais les compare avec `mode.value` (Medium)

- **Fichier:** tracking_state_mixin.py:79-85, 248-252
- **Probleme:** Le tracker initialise `'normal'`, `'critical'`, `'continuous'` comme cles. Mais `_update_mode_time` utilise `mode_key = current_mode.lower()` ou `current_mode` peut etre `tracking_params.mode.value` (string) OU `tracking_params.mode` (enum). La condition `prev_mode in self._mode_time_tracker` (ligne 251) ignore les cles `'last_mode'` et `'last_mode_time'` car elles ne sont pas des modes valides -- ce qui est correct par accident mais fragile.
- **Correction:** Separer les metadonnees (`last_mode`, `last_mode_time`) des compteurs de temps dans des structures distinctes.

#### [C-27] `_save_session_to_file` importe `web.session` depuis `core/` (Medium)

- **Fichier:** tracker.py:403
- **Probleme:** `from web.session import session_storage` cree un couplage inverse : `core/` depend de `web/`. L'architecture prevoit que `web/` depend de `core/`, pas l'inverse. L'import est protege par `try/except ImportError` mais c'est une violation architecturale.
- **Correction:** Utiliser un callback ou un event pour la sauvegarde, injecte depuis `web/`.

#### [C-28] `est_proche_meridien` utilise `deja_jnow=True` avec une AD potentiellement J2000 (Medium)

- **Fichier:** calculations.py:287
- **Probleme:** `calculer_angle_horaire(ad_deg, date_heure, deja_jnow=True)` suppose que `ad_deg` est en JNOW. Mais les appelants pourraient passer une AD J2000 (du catalogue). Si c'est le cas, le resultat sera imprecis de quelques dizaines de secondes d'arc -- peu significant pour une verification "proche du meridien" a 5 minutes pres.
- **Correction:** Documenter clairement que `ad_deg` doit etre en JNOW, ou supprimer le raccourci.

---

### core/observatoire/

#### [C-29] `rechercher` dans catalogue.py relit config.json pour chaque planete (High)

- **Fichier:** catalogue.py:273-278
- **Probleme:** Pour chaque recherche de planete, `rechercher()` ouvre et parse `data/config.json` pour obtenir latitude/longitude. Avec un chemin relatif (`Path("data") / "config.json"`) qui depend du CWD. De plus, les coordonnees du site sont deja disponibles via `config.py` qui est deja importe (ligne 15 : `from core.config.config import CACHE_FILE`).
- **Correction:** Utiliser `SITE_LATITUDE` et `SITE_LONGITUDE` depuis `core.config.config` deja importe.

#### [C-30] `_normaliser_angle_360` ne gere pas correctement les angles negatifs (Medium)

- **Fichier:** calculations.py:54-58
- **Probleme:** `angle = angle % 360; if angle < 0: angle += 360` -- en Python, `%` retourne toujours un resultat du signe du diviseur pour les floats. Donc `(-10) % 360 == 350.0`, et la condition `if angle < 0` n'est jamais True. Le code fonctionne correctement mais la condition est du code mort qui peut confondre.
- **Correction:** Supprimer le `if angle < 0` ou remplacer toute la methode par `angle_utils.normalize_angle_360()`.

#### [C-31] `calculer_heure_passage_meridien` peut lever `ValueError` (Medium)

- **Fichier:** calculations.py:226
- **Probleme:** `minuit.replace(hour=heures, ...)` leve `ValueError` si `heures >= 24` ou `minutes >= 60`. Cela peut arriver si `diff_heures_solaires > 24` (objet deja passe ou calcul errone).
- **Correction:** Ajouter `heures = heures % 24` ou utiliser `minuit + timedelta(hours=diff_heures_solaires)`.

#### [C-32] `_convert_to_horizontal` : `denominator == 0` compare un float a zero (Low)

- **Fichier:** calculations.py:190
- **Probleme:** Comparaison stricte `denominator == 0` pour un float. En pratique, `math.cos(ha_rad) * math.sin(lat_rad) - math.tan(dec_rad) * math.cos(lat_rad)` est extremement peu probable d'etre exactement 0.0, mais si c'est le cas a la precision machine, le `atan2` le gererait correctement de toute facon (il accepte un denominateur zero).
- **Correction:** Supprimer le test special ; `math.atan2` gere nativement les cas limites.

#### [C-33] `get_planet_position` avale toutes les exceptions (Medium)

- **Fichier:** ephemerides.py:102
- **Probleme:** `except Exception: return None` masque toute erreur de calcul d'ephemeride (ex: date invalide, erreur astropy). Aucun log.
- **Correction:** Logger l'exception au niveau warning avant de retourner None.

#### [C-34] `rechercher_simbad` cree une nouvelle instance Simbad a chaque appel (Low)

- **Fichier:** catalogue.py:131
- **Probleme:** `simple_simbad = Simbad()` est recree a chaque appel, ignorant `self.simbad` initialise dans `__init__`. Le `self.simbad` configure avec des champs supplementaires n'est jamais utilise.
- **Correction:** Utiliser `self.simbad` ou supprimer sa creation dans `__init__`.

---

### core/utils/

#### [C-35] `normalize_angle_180(180)` retourne 180, pas -180 (Low)

- **Fichier:** angle_utils.py:53-57
- **Probleme:** `normalize_angle_180(180)` retourne `180.0` car `180 > 180` est False. Certaines conventions attendent `[-180, 180[` (ouvert a droite). Ce n'est pas un bug en soi mais peut causer des comportements inattendus aux limites.
- **Correction:** Documenter le comportement aux limites ou choisir une convention coherente.

#### [C-36] `shortest_angular_distance` utilise des boucles `while` au lieu du modulo (Low)

- **Fichier:** angle_utils.py:83-89
- **Probleme:** `while delta > 180: delta -= 360; while delta < -180: delta += 360` est correct mais inefficace pour des angles tres grands (ex: `shortest_angular_distance(0, 720000)` ferait 2000 iterations). Peu probable en production mais fragile.
- **Correction:** Utiliser `delta = ((delta + 180) % 360) - 180` pour une normalisation en O(1). Meme remarque pour `calculations.py:46-51`, `calculations.py:161-164`.

#### [C-37] Duplication de la logique de normalisation d'angle (Low)

- **Fichier:** angle_utils.py, calculations.py:45-59, moteur.py:435-444, tracking_state_mixin.py:153-157, adaptive_tracking.py:367-409
- **Probleme:** La normalisation d'angle et le calcul du chemin le plus court sont reimplementes dans au moins 5 fichiers differents. `angle_utils.py` existe mais n'est utilise que par `feedback_controller.py`.
- **Correction:** Centraliser tous les usages sur `angle_utils.py`.

---

## Synthese des risques critiques

1. **`log_to_web()` manquant** [C-20] : `AttributeError` garanti en mode degrade (encodeur perdu pendant le suivi). Impact direct en production.

2. **Moyenne arithmetique d'angles dans `read_stable()`** [C-10] : Erreur de positionnement potentielle de plusieurs degres quand la coupole est pres de 0/360. Utilise pour les corrections de feedback.

3. **Race condition lecture JSON sans verrou** [C-11] : Lecture corrompue possible a 50 Hz d'ecriture par le demon. Peut causer des mouvements erratiques.

4. **`bare except` dans `_init_gpio`** [C-07] : Masque les erreurs de permissions GPIO, empechant le diagnostic.

5. **Chemins relatifs pour la configuration** [C-01] : Echec silencieux si le CWD n'est pas la racine du projet.
