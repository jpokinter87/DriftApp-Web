
# 🔧 Diagnostic : Switch Détecté mais Pas de Recalage

**Date** : 6 décembre 2025
**Contexte** : Le test `test_gpio27_lgpio.py` montre que le switch fonctionne, mais le daemon ne recalibre pas

---

## ✅ Ce Qui Fonctionne

### Test GPIO 27 Direct (19:14:41)
```
État initial GPIO 27 : 1
État 1 = Switch OUVERT (repos, coupole PAS à 45°)

[19:14:41] Transition #001 : 1→0
           FRONT DESCENDANT (1-0) - C'EST CE QUE LE DAEMON CHERCHE!
[19:14:41] Transition #002 : 0→1
           Front montant (0-1) - Ignoré par daemon
```

**Conclusion** : ✅ Hardware OK, ✅ lgpio OK, ✅ Front 1→0 détecté correctement

---

## ❌ Ce Qui Ne Fonctionne PAS

Le daemon ne recalibre PAS à 45° malgré le passage sur le switch.

---

## 🔍 Diagnostic Probable

### Hypothèse #1 : DAEMON ANCIENNE VERSION (99% probable)

Le daemon actuellement en cours d'exécution sur le Raspberry Pi est **l'ancienne version** qui N'A PAS :
- Les logs debug aux lignes 197-198
- La configuration RotatingFileHandler pour écrire dans `logs/ems22d.log`

**Pourquoi cette hypothèse** :
1. Le fichier `ems22d_calibrated.py` a été modifié récemment pour ajouter les logs debug
2. Le daemon n'a probablement **PAS été redémarré** après la modification
3. Le processus en mémoire utilise encore l'ancienne version du code

### Hypothèse #2 : Condition Switch Jamais Satisfaite (1% probable)

La variable `self.switch_last_state` pourrait avoir un problème d'initialisation.

---

## 🛠️ Plan de Correction

### ÉTAPE 1 : Vérifier la Version du Daemon en Cours

```bash
# Afficher les processus Python actifs
ps aux | grep ems22

# Résultat attendu :
# root     12345  0.5  0.2  python3 ems22d_calibrated.py
#                             ^^^^^^ noter le PID
```

### ÉTAPE 2 : Arrêter l'Ancien Daemon

```bash
# Arrêter tous les processus ems22d
sudo pkill -f ems22d_calibrated

# OU avec le PID spécifique
sudo kill 12345

# Vérifier qu'il est bien arrêté
ps aux | grep ems22
# Doit afficher seulement la ligne du grep lui-même
```

### ÉTAPE 3 : Redémarrer le Nouveau Daemon

```bash
# IMPORTANT : Se placer dans le bon répertoire
cd /home/jp/PythonProject/Dome_v4_3

# Lancer le daemon avec sudo (requis pour SPI et GPIO)
sudo python3 ems22d_calibrated.py &

# Vérifier qu'il démarre correctement
tail -f logs/ems22d.log
```

**Messages attendus au démarrage** :
```
[ems22d] 2025-12-06 19:30:00 INFO EMS22A daemon démarré (méthode INCRÉMENTALE)
[ems22d] 2025-12-06 19:30:00 INFO SPI initialisé : bus=0, device=0, speed=500kHz
[ems22d] 2025-12-06 19:30:00 INFO Switch GPIO 27 configuré - état initial : 1
[ems22d] 2025-12-06 19:30:00 INFO Serveur TCP démarré sur port 5556
[ems22d] 2025-12-06 19:30:00 INFO Polling démarré à 50 Hz
```

### ÉTAPE 4 : Tester le Switch avec Logs Actifs

1. **Garder le terminal avec tail -f actif** :
   ```bash
   tail -f logs/ems22d.log
   ```

2. **Bouger la coupole lentement vers le switch (position 45°)**

3. **Messages attendus quand le switch est activé** :
   ```
   [ems22d] 2025-12-06 19:31:00 INFO [DEBUG] Switch transition: 1→0
   [ems22d] 2025-12-06 19:31:00 INFO 🔄 Microswitch activé → recalage à 45°
   [ems22d] 2025-12-06 19:31:00 INFO    → total_counts recalé à 3796
   [ems22d] 2025-12-06 19:31:00 INFO    → angle affiché : 45°
   ```

4. **Vérifier la position publiée** :
   ```bash
   cat /dev/shm/ems22_position.json
   ```

   **Résultat attendu** :
   ```json
   {
     "ts": 1733511060.123,
     "angle": 45.0,
     "raw": 512,
     "status": "OK"
   }
   ```

---

## 🎯 Résolution Attendue

Si la correction fonctionne :
- ✅ Logs `[DEBUG] Switch transition: 1→0` apparaissent
- ✅ Message `🔄 Microswitch activé → recalage à 45°` apparaît
- ✅ L'angle dans le JSON passe brutalement à 45.0°
- ✅ Les lectures suivantes continuent depuis 45° (pas de saut)

Si ça ne fonctionne toujours pas après le redémarrage :
- Vérifier l'initialisation de `self.switch_last_state` dans `__init__`
- Ajouter plus de logs pour tracer l'état du switch à chaque itération

---

## 📋 Checklist de Vérification

- [ ] Ancien daemon arrêté (`ps aux | grep ems22` ne montre rien)
- [ ] Nouveau daemon démarré (`tail -f logs/ems22d.log` montre le démarrage)
- [ ] Message "Switch GPIO 27 configuré - état initial : X" apparaît
- [ ] Coupole bougée vers le switch (45°)
- [ ] Log `[DEBUG] Switch transition: 1→0` apparaît
- [ ] Log `🔄 Microswitch activé → recalage à 45°` apparaît
- [ ] JSON publié contient `"angle": 45.0`
- [ ] Boussole GUI (si lancée) affiche instantanément 45°

---

## 📝 Notes pour le Debug Futur

Si le problème persiste même après redémarrage :

1. **Ajouter un log permanent du polling switch** (toutes les secondes) :
   ```python
   # Dans la boucle principale, ajouter :
   if iteration_count % 50 == 0:  # Une fois par seconde
       state = self.read_switch()
       logger.info(f"[POLL] Switch state: {state} (last: {self.switch_last_state})")
   ```

2. **Vérifier l'initialisation dans __init__** :
   ```python
   def __init__(self):
       ...
       # Ligne 118-122 : Vérifier que self.switch_last_state est bien initialisé
       self.switch_last_state = self.read_switch()
       logger.info(f"Switch initial state: {self.switch_last_state}")
   ```

3. **Test en foreground** (pas en arrière-plan) pour voir tous les logs en direct :
   ```bash
   sudo python3 ems22d_calibrated.py
   # (sans le &, les logs apparaissent directement dans le terminal)
   ```
