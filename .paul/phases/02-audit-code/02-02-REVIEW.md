# Audit Code — services/

## Resume

| Severite | Count |
|----------|-------|
| Critical | 2 |
| High     | 5 |
| Medium   | 6 |
| Low      | 4 |

---

## Issues par module

### services/motor_service.py

#### [S-01] Thread safety : `current_status` partage entre thread principal et thread continu (Critical)
- **Fichier:** motor_service.py:460-494, command_handlers.py:348-387
- **Probleme:** Le dictionnaire `self.current_status` est mutable et partage entre le thread principal (boucle `run()`) et le thread du `ContinuousHandler._movement_loop()`. Le thread continu modifie `current_status['position']` (ligne 366/376 de command_handlers.py) et appelle `self.status_callback(current_status)` (ligne 378) pendant que le thread principal lit et ecrit les memes cles (lignes 473-479 de motor_service.py). Les dictionnaires Python sont thread-safe pour les operations atomiques (get/set d'une cle), mais les sequences lecture-modification-ecriture ne le sont pas. Par exemple, le thread continu met `status='idle'` (ligne 386) pendant que le thread principal verifie `tracking_handler.is_active` puis modifie `status['position']` (lignes 479-480).
- **Risque:** Etat incoherent visible par le frontend (position d'un mode melangee avec le statut d'un autre), ou perte de mise a jour de position.
- **Correction:** Proteger `current_status` avec un `threading.Lock` pour toute sequence lecture-modification-ecriture, ou utiliser une copie par thread et fusionner de maniere atomique.

#### [S-02] Le GOTO et le JOG bloquent la boucle principale 20 Hz (Critical)
- **Fichier:** motor_service.py:466-468, command_handlers.py:121-172, 258-298
- **Probleme:** `process_command()` appelle `self.goto_handler.execute()` et `self.jog_handler.execute()` de maniere synchrone dans la boucle principale. Ces handlers appellent `self.moteur.rotation(delta, vitesse=speed)` (command_handlers.py:181) et `self.feedback_controller.rotation_avec_feedback()` (ligne 191/218) qui sont des appels bloquants — le moteur tourne pas a pas avec un sleep entre chaque pas. Un GOTO de 180 degres avec une reduction de 2230:1 et 800 pas/tour implique ~990 000 pas, ce qui bloque la boucle pendant potentiellement des minutes.
- **Consequences:** (1) Le watchdog systemd ne recoit plus de WATCHDOG=1 pendant le GOTO — si le GOTO dure > 20 secondes (WatchdogSec=30 minus marge), systemd tue et redemarre le service. (2) Aucune commande STOP ne peut etre traitee pendant un GOTO (la boucle est bloquee). (3) La position n'est pas mise a jour pour le frontend. Le seul mecanisme d'arret est `moteur.request_stop()` via signal, pas via commande IPC.
- **Correction:** Executer les commandes GOTO/JOG dans un thread dedie (comme `ContinuousHandler` le fait deja), avec envoi de watchdog heartbeat depuis la boucle principale restee libre. Alternativement, fragmenter le GOTO en micro-steps traites a chaque iteration de la boucle.

#### [S-03] Watchdog systemd : intervalle de 10s avec WatchdogSec=30 est a la limite (High)
- **Fichier:** motor_service.py:169, motor_service.service:14
- **Probleme:** `WATCHDOG_INTERVAL = 10.0` et `WatchdogSec=30`. La recommandation systemd est d'envoyer le heartbeat a `WatchdogSec/2` soit toutes les 15 secondes. Avec 10s c'est correct en theorie, mais combine avec [S-02] (GOTO bloquant), le service peut facilement depasser 30s sans heartbeat. De plus, le commentaire ligne 169 dit "doit etre < WatchdogSec/2" ce qui est respecte, mais cela suppose que la boucle n'est jamais bloquee.
- **Correction:** Resoudre [S-02] pour garantir que le heartbeat est envoye meme pendant un GOTO. Considerer aussi reduire WATCHDOG_INTERVAL a 5s pour plus de marge.

#### [S-04] `error_timestamp` absent pour certains chemins d'erreur (Medium)
- **Fichier:** command_handlers.py:488-496, motor_service.py:339-362
- **Probleme:** Le `TrackingHandler.start()` met `current_status['status'] = 'error'` (ligne 492) mais ne met PAS `error_timestamp` dans le `except Exception`. Le mecanisme `_check_error_recovery()` dans motor_service.py (ligne 349-350) teste `error_timestamp` et retourne si `None`, ce qui signifie que l'etat 'error' ne sera JAMAIS auto-recupere si l'erreur vient du tracking start.
- **Correction:** Ajouter `current_status['error_timestamp'] = time.time()` dans le bloc except de `TrackingHandler.start()` (ligne 492), et aussi dans le bloc `else` du `if success:` (ligne 488).

#### [S-05] Fuite memoire potentielle : `tracking_info` et `session_data` jamais nettoyes (Medium)
- **Fichier:** command_handlers.py:542-559
- **Probleme:** Chaque appel a `TrackingHandler.update()` ajoute `tracking_info` et `session_data` dans `current_status`. Le `session_data` (ligne 559) est un objet potentiellement volumineux (historique complet de session) qui est stocke dans le dictionnaire et serialise en JSON a chaque ecriture IPC. Sur une session de suivi longue (plusieurs heures), `session_data` peut accumuler des milliers d'entrees de corrections.
- **Correction:** Limiter la taille de `session_data` avant serialisation, ou le servir via un endpoint API dedie plutot que dans le fichier IPC de status (qui est lu/ecrit a 20 Hz).

#### [S-06] Le `cleanup()` ne fait pas `self.running = False` (Low)
- **Fichier:** motor_service.py:498-515
- **Probleme:** `cleanup()` ne positionne pas `self.running = False`. Si `cleanup()` est appele directement (pas depuis `run()`), et qu'un autre thread reference `self.running`, il pourrait voir un etat incoherent. Actuellement non critique car `cleanup()` est toujours appele en fin de `run()`.
- **Correction:** Ajouter `self.running = False` au debut de `cleanup()`.

---

### services/command_handlers.py

#### [S-07] Race condition : `ContinuousHandler` modifie `current_status` depuis un thread daemon (High)
- **Fichier:** command_handlers.py:348-387
- **Probleme:** Le thread daemon (`_movement_loop`) modifie `current_status['position']` (lignes 365, 376) et `current_status['status']` (ligne 386) sans aucune synchronisation. Le thread principal peut lire ces valeurs au meme moment dans `motor_service.py:472-480`. Le fait que le thread soit `daemon=True` (ligne 332) signifie aussi qu'il sera tue brutalement a la fin du processus, potentiellement au milieu d'une ecriture IPC.
- **Correction:** Utiliser un `threading.Lock` pour proteger les acces a `current_status`, ou passer par une queue thread-safe pour communiquer les mises a jour de position vers le thread principal.

#### [S-08] `ContinuousHandler.start()` ne verifie pas l'etat actuel (High)
- **Fichier:** command_handlers.py:314-333, motor_service.py:410-414
- **Probleme:** Dans `motor_service.py:412-413`, un `handle_stop()` est appele avant `continuous_handler.start()` seulement si le tracking est actif. Mais si un GOTO est en cours (bloquant dans le thread principal — cf. [S-02]), la commande `continuous` ne sera de toute facon pas traitee. Si un mouvement continu est deja actif, `self.stop()` est bien appele (ligne 318), mais il n'y a pas de verification que le thread precedent est effectivement arrete avant d'en lancer un nouveau (`thread.join(timeout=2.0)` pourrait echouer silencieusement a ligne 340).
- **Correction:** Verifier que `self.thread is None` apres le `stop()` et logger un warning si le thread precedent n'a pas pu etre arrete.

#### [S-09] GOTO sans validation d'angle (High)
- **Fichier:** command_handlers.py:121-172, motor_service.py:393-398
- **Probleme:** L'angle recu depuis l'IPC (`command.get('angle', 0)`) n'est jamais valide. Un angle negatif, superieur a 360, NaN, ou non-numerique serait passe directement a `shortest_angular_distance()` puis au moteur. Si Django envoie une valeur corrompue (ou si le JSON est altere), le moteur pourrait recevoir une commande aberrante.
- **Correction:** Valider l'angle : verifier qu'il est un nombre fini entre 0 et 360 (ou le normaliser avec `normalize_360()`). Meme chose pour `delta` du JOG et `speed`.

#### [S-10] Le callback `on_goto_info` capture `current_status` par reference (Medium)
- **Fichier:** command_handlers.py:435-443
- **Probleme:** La closure `on_goto_info` capture `current_status` par reference et le modifie (ligne 437-438). Ce callback sera appele depuis `TrackingSession.start()` qui est synchrone dans le meme thread, donc pas de race condition ici. Cependant, si `TrackingSession` changeait pour etre asynchrone, cela deviendrait problematique. C'est un couplage implicite fragile.
- **Correction:** Documenter clairement que ce callback doit etre appele dans le meme thread, ou utiliser un mecanisme plus explicite.

#### [S-11] `TrackingHandler.update()` avale les exceptions silencieusement (Medium)
- **Fichier:** command_handlers.py:565-566
- **Probleme:** Le `except Exception as e` (ligne 565) ne fait que logger l'erreur. Le suivi reste marque comme `active = True` meme si `check_and_correct()` ou `get_status()` leve une exception repetee. Cela signifie que le tracking peut etre dans un etat zombie — marque actif mais ne faisant plus de corrections.
- **Correction:** Ajouter un compteur d'erreurs consecutives. Apres N erreurs (par ex. 5), arreter automatiquement le suivi et notifier le frontend.

#### [S-12] `_get_rotate_log_func()` : import circulaire differe fragile (Low)
- **Fichier:** command_handlers.py:31-39
- **Probleme:** L'import differe de `rotate_log_for_tracking` depuis `services.motor_service` est un pattern fragile. Si le module est restructure ou si `motor_service.py` change de nom, l'import echouera silencieusement (capture par `try/except` ligne 416-418). Le cache global `_rotate_log_func` n'est jamais invalide.
- **Correction:** Injecter la fonction de rotation de log via le constructeur de `TrackingHandler` au lieu d'utiliser un import circulaire.

---

### services/ipc_manager.py

#### [S-13] Ecriture du status : le verrou est sur le fichier `.tmp`, pas sur le fichier final (High)
- **Fichier:** ipc_manager.py:126-141, web/common/ipc_client.py:54-59
- **Probleme:** `write_status()` verrouille `motor_status.json.tmp` avec LOCK_EX (ligne 132), puis ecrit, unlock, et renomme vers `motor_status.json` (ligne 141). Le lecteur cote Django (`ipc_client.py:54-59`) prend un verrou LOCK_SH sur `motor_status.json`. Or le verrou est sur des fichiers differents — le verrou sur `.tmp` ne bloque pas la lecture de `.json`. Le rename atomique POSIX est cense garantir que le lecteur voit soit l'ancien fichier complet soit le nouveau, ce qui est correct sur /dev/shm (tmpfs). Cependant, si le lecteur ouvre le fichier, puis le rename a lieu, le lecteur lit toujours l'ancien contenu (l'ancien inode) — pas de corruption, mais le verrou LOCK_SH est inutile car il ne protege contre rien.
- **Correction:** Le rename atomique est suffisant sur Linux/tmpfs. Retirer le verrou LOCK_SH cote lecteur (ipc_client.py) car il n'apporte aucune protection reelle et ajoute un overhead inutile. Alternativement, verrouiller un fichier sentinel commun (`motor_status.lock`).

#### [S-14] `read_command()` : TOCTOU entre `exists()` et `open()` (Medium)
- **Fichier:** ipc_manager.py:79-112
- **Probleme:** La verification `if not COMMAND_FILE.exists()` (ligne 79) suivie de `open(COMMAND_FILE, 'r')` (ligne 83) est sujette a une race condition TOCTOU (time-of-check-time-of-use). Le fichier pourrait etre supprime entre les deux appels. En pratique, le fichier n'est jamais supprime (il est vide ou rempli), donc le risque est quasi-nul. C'est neanmoins un anti-pattern.
- **Correction:** Utiliser un `try/except FileNotFoundError` autour du `open()` au lieu de tester `exists()` avant.

#### [S-15] `clear_command()` devrait utiliser `truncate()` au lieu de `write('')` (Low)
- **Fichier:** ipc_manager.py:154-157
- **Probleme:** `f.write('')` ecrit zero octets mais ne tronque pas le fichier si le mode 'w' n'a pas deja tronque. Avec `open(..., 'w')`, le fichier est bien tronque a l'ouverture, donc le code fonctionne. Mais c'est un `write('')` semantiquement vide — inutile puisque le `open('w')` a deja tronque.
- **Correction:** Retirer le `f.write('')` qui ne fait rien, ou utiliser `COMMAND_FILE.write_text('')` pour plus de clarte (mais garder le verrou).

#### [S-16] `fsync()` sur `/dev/shm` est un no-op couteux (Low)
- **Fichier:** ipc_manager.py:136
- **Probleme:** `os.fsync(f.fileno())` sur `/dev/shm` (tmpfs) est inutile car tmpfs est en memoire — il n'y a pas de disque vers lequel forcer l'ecriture. Le syscall est quand meme effectue, ajoutant un overhead a chaque ecriture de status (potentiellement 20 fois par seconde si le tracking est actif).
- **Correction:** Retirer le `fsync()` pour `/dev/shm` ou le conditionner au type de filesystem.

---

### services/simulation.py

#### [S-17] Pas de simulation du delai de rotation (Medium)
- **Fichier:** simulation.py:42-44
- **Probleme:** `read_angle()` retourne instantanement `get_simulated_position()`. Sur le vrai hardware, `read_angle(timeout_ms=200)` peut prendre jusqu'a 200ms et bloque. En simulation, il retourne instantanement, ce qui change le timing de la boucle principale et des handlers. Les tests de performance ou de timing ne sont pas representatifs.
- **Correction:** Ajouter un `time.sleep(0.001)` minimal pour simuler la latence I2C/SPI de l'encodeur reel, ou rendre le delai configurable.

#### [S-18] `read_angle()` ignore le parametre `timeout_ms` (Low)
- **Fichier:** simulation.py:42
- **Probleme:** Le parametre `timeout_ms` est accepte mais completement ignore. Si du code depend du timeout pour detecter un encodeur absent (par exemple lever `RuntimeError` apres timeout), ce comportement ne sera jamais teste en simulation.
- **Correction:** Documenter explicitement que le timeout est ignore en simulation, ou simuler des echecs aleatoires/configurables pour tester la resilience.

---

## Synthese et recommandations prioritaires

### Actions immediates (Critical)

1. **[S-02] Deplacer GOTO/JOG dans un thread dedie** — C'est le probleme le plus grave. Un GOTO long bloque la boucle principale, empechant la reception de commandes STOP et l'envoi du watchdog. Sur le vrai materiel avec la reduction 2230:1, un GOTO de 180 degres prend plusieurs minutes. Systemd tuera le service apres 30 secondes. Le ContinuousHandler montre deja le pattern correct avec un thread dedie.

2. **[S-01]/[S-07] Proteger `current_status` avec un Lock** — Le partage non-synchronise du dictionnaire entre le thread principal et le thread continu est un bug de concurrence reel.

### Actions a court terme (High)

3. **[S-09] Valider les entrees** avant de les passer au moteur.
4. **[S-13] Simplifier la strategie de verrouillage IPC** — Les verrous actuels n'apportent pas la protection attendue.
5. **[S-03]/[S-08] Durcir la robustesse** du watchdog et des transitions de mouvement continu.

### Actions a moyen terme (Medium)

6. **[S-04] Harmoniser `error_timestamp`** sur tous les chemins d'erreur.
7. **[S-05] Limiter `session_data`** dans le fichier IPC de status.
8. **[S-11] Ajouter un mecanisme de detection de tracking zombie.**
9. **[S-10] Refactorer l'injection de callback** pour le GOTO tracking.

### Note positive

Le code est bien structure et lisible. La separation en handlers (GOTO, JOG, Continuous, Tracking) est propre. Le pattern write-tmp-then-rename pour l'IPC est correct. La gestion des signaux (SIGTERM/SIGINT) et le cleanup au demarrage sont de bonnes pratiques. Le systeme de logs avec rotation par session de suivi est bien pense.
