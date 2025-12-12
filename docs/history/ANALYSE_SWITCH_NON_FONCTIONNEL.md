# 🐛 Switch de Calibration Non Fonctionnel

**Date** : 6 Décembre 2025
**Problème** : Le switch ne calibre pas la position à 45° lors du passage de la coupole
**Vidéo** : `WhatsApp Video 2025-12-06 at 14.08.41.mp4` (passage switch à -4s)

---

## 📋 Résumé

**Symptôme observé** :
- La coupole se déplace et passe sur le microswitch (4 secondes avant la fin de la vidéo)
- L'angle affiché est incorrect (position non calibrée)
- **L'angle ne passe PAS à 45°** au moment du passage
- Pas de logs disponibles pour confirmer la détection

**Questions clés** :
1. ✅ Le daemon `ems22d_calibrated.py` contient-il la logique du switch ? → OUI (vérifié)
2. ❓ Le daemon a-t-il été **redémarré** après ajout de la logique switch ?
3. ❓ Le GPIO 27 est-il **physiquement connecté** au switch ?
4. ❓ Le switch fonctionne-t-il **électriquement** ?
5. ❓ Y a-t-il un **bug dans la logique** de détection ?

---

## 🔍 Analyse du Code Actuel

### Vérification : Logique Switch Présente

✅ Le fichier `ems22d_calibrated.py` contient bien la logique du switch :

```python
# Ligne 47 : Configuration
SWITCH_GPIO = 27
SWITCH_CALIB_ANGLE = 45

# Ligne 80-84 : Initialisation dans __init__
self.hchip = lgpio.gpiochip_open(0)
lgpio.gpio_claim_input(self.hchip, SWITCH_GPIO, lgpio.SET_PULL_UP)
self.switch_last_state = lgpio.gpio_read(self.hchip, SWITCH_GPIO)
logger.info(f"Switch GPIO {SWITCH_GPIO} configuré - état initial : {self.switch_last_state}")

# Ligne 161-191 : Fonction de détection
def process_switch(self, angle):
    state = self.read_switch()

    if self.switch_last_state == 1 and state == 0:
        logger.info(f"🔄 Microswitch activé → recalage à {SWITCH_CALIB_ANGLE}°")

        # Recalcul total_counts
        target_wheel_deg = SWITCH_CALIB_ANGLE / (CALIBRATION_FACTOR * ROTATION_SIGN)
        self.total_counts = int((target_wheel_deg / 360.0) * COUNTS_PER_REV)

        logger.info(f"   → total_counts recalé à {self.total_counts}")
        logger.info(f"   → angle affiché : {SWITCH_CALIB_ANGLE}°")

        angle = SWITCH_CALIB_ANGLE

    self.switch_last_state = state
    return angle

# Ligne 306 : Appel dans la boucle principale
angle = self.process_switch(angle)
```

**Conclusion** : La logique est présente et semble correcte.

---

## 🧪 Hypothèses et Tests

### Hypothèse 1 : Daemon Non Redémarré ⚠️

**Problème possible** :
Le daemon a été modifié pour ajouter le switch, mais **n'a pas été redémarré**.

**Impact** :
- L'ancienne version (sans switch) continue de tourner
- Le switch est physiquement activé mais ignoré
- Pas de log "Microswitch activé"

**Test** :
```bash
# 1. Vérifier quel processus tourne
ps aux | grep ems22d

# 2. Arrêter et relancer
sudo pkill -f ems22d_calibrated
sudo python3 ems22d_calibrated.py &

# 3. Vérifier les logs au démarrage
tail -f /var/log/syslog | grep ems22d

# Résultat attendu au démarrage :
# [ems22d] ... Switch GPIO 27 configuré - état initial : X
```

**Si ce log n'apparaît PAS** → Le daemon n'a pas la logique switch

---

### Hypothèse 2 : GPIO Non Connecté 🔌

**Problème possible** :
Le microswitch n'est pas physiquement connecté au GPIO 27, ou mal câblé.

**Impact** :
- `lgpio.gpio_read()` retourne toujours 1 (pull-up)
- Jamais de transition 1→0 détectée
- `process_switch()` ne se déclenche jamais

**Test** :
```bash
# Test direct du GPIO avec script fourni
sudo python3 tests_sur_site/test_switch_direct.py

# Actions à faire pendant le test :
# 1. Bouger la coupole vers 45°
# 2. Observer si transition 1→0 s'affiche au passage

# Résultat attendu quand coupole passe sur switch :
# [HH:MM:SS] Transition #001 : 1→0 | 🔴 PRESSÉ
#              ✅ Front DESCENDANT détecté
```

**Si AUCUNE transition** → Problème de câblage :
- Vérifier connexion GPIO 27 au signal switch
- Vérifier GND commun entre switch et Pi
- Vérifier que le switch SS-5GL fonctionne (test continuité multimètre)

---

### Hypothèse 3 : Switch Trop Rapide ⏱️

**Problème possible** :
Le switch est activé et relâché **entre deux lectures** du daemon (intervalle 20ms à 50Hz).

**Impact** :
La transition 1→0→1 se fait en < 20ms → daemon la rate complètement

**Solution** :
Si le test direct détecte les transitions mais pas le daemon, c'est probablement ce problème.
Le switch mécanique devrait rester fermé suffisamment longtemps (>20ms) pour être détecté.

---

### Hypothèse 4 : Logs Non Surveillés 📋

**Problème possible** :
Le switch **fonctionne** mais les logs ne sont pas surveillés/enregistrés.

**Impact** :
- Calibration se fait correctement
- Mais impossible de le vérifier sans logs

**Test** :
```bash
# Lancer daemon en foreground avec logs visibles
sudo python3 ems22d_calibrated.py

# Puis faire passer coupole sur switch et observer

# Résultat attendu :
# [ems22d] ... 🔄 Microswitch activé → recalage à 45°
# [ems22d] ...    → total_counts recalé à -11794
# [ems22d] ...    → angle affiché : 45°
```

---

## 📊 Arbre de Décision pour Diagnostic

```
Switch ne fonctionne pas
├─ 1. Lancer test_switch_direct.py
│  ├─ Détecte transitions 1→0 au passage ?
│  │  ├─ OUI → GPIO connecté OK
│  │  │  └─ 2. Vérifier logs daemon pendant passage
│  │  │     ├─ "Microswitch activé" apparaît ?
│  │  │     │  ├─ OUI → Switch fonctionne ! (vérifier boussole)
│  │  │     │  └─ NON → Daemon sans logique switch ou pas redémarré
│  │  │     │     └─ Redémarrer daemon
│  │  └─ NON → GPIO non connecté
│  │     └─ Vérifier câblage :
│  │        - GPIO 27 → Signal switch
│  │        - GND → GND switch
│  │        - Continuité switch (multimètre)
```

---

## ✅ Procédure de Validation Complète

### Étape 1 : Vérifier Configuration Daemon

```bash
# 1. Arrêter daemon actuel
sudo pkill -f ems22d_calibrated

# 2. Vérifier que le code contient bien la logique switch
grep -n "SWITCH_GPIO" ems22d_calibrated.py
grep -n "process_switch" ems22d_calibrated.py

# Résultat attendu :
# 47:SWITCH_GPIO = 27
# 161:    def process_switch(self, angle):
# 306:                angle = self.process_switch(angle)
```

### Étape 2 : Test GPIO Isolé

```bash
# Lancer test direct (sans daemon)
sudo python3 tests_sur_site/test_switch_direct.py

# Pendant le test :
# - Bouger coupole vers position 45°
# - Observer affichage quand passe sur switch

# Résultat attendu :
# [HH:MM:SS] Transition #001 : 1→0 | 🔴 PRESSÉ
#              ✅ Front DESCENDANT détecté

# Si RIEN ne s'affiche → Problème câblage
```

### Étape 3 : Redémarrer Daemon avec Logs

```bash
# Lancer daemon en foreground avec logs visibles
sudo python3 ems22d_calibrated.py

# Observer au démarrage :
# [ems22d] ... Switch GPIO 27 configuré - état initial : X
# [ems22d] ... Daemon EMS22D avec Switch de Calibration

# Si ces logs n'apparaissent PAS → Mauvais fichier !
```

### Étape 4 : Test Complet avec Boussole

```bash
# Terminal 1 : Daemon avec logs
sudo python3 ems22d_calibrated.py

# Terminal 2 : Boussole
python3 boussole.py

# Actions :
# 1. Observer angle initial (incorrect car non calibré)
# 2. Bouger coupole vers 45° physique
# 3. Au passage du switch, observer :
#    - Terminal 1 : "🔄 Microswitch activé → recalage à 45°"
#    - Terminal 2 : Aiguille saute instantanément à 45°
# 4. Continuer à bouger la coupole
# 5. Vérifier que tracking continue depuis 45° calibré
```

---

## 🔧 Corrections Suggérées

### Correction Appliquée : État Initial du Switch

**Fichier** : `ems22d_calibrated.py` lignes 80-84

**Modification** : Lire l'état réel au démarrage au lieu de forcer à 1

```python
# Gestion du switch
self.hchip = lgpio.gpiochip_open(0)
lgpio.gpio_claim_input(self.hchip, SWITCH_GPIO, lgpio.SET_PULL_UP)
# Lire l'état réel au démarrage (évite calibration fantôme)
self.switch_last_state = lgpio.gpio_read(self.hchip, SWITCH_GPIO)
logger.info(f"Switch GPIO {SWITCH_GPIO} configuré - état initial : {self.switch_last_state}")
```

**Bénéfice** : Évite calibration intempestive si daemon démarre avec coupole déjà sur switch.

---

## 📝 Checklist Utilisateur

Avant de contacter le support, vérifier :

- [ ] Le daemon `ems22d_calibrated.py` a été **redémarré** après modification
- [ ] Les logs au démarrage montrent "Switch GPIO 27 configuré - état initial : X"
- [ ] Le test `test_switch_direct.py` détecte les transitions 1→0
- [ ] Le câblage GPIO 27 → Switch signal est correct
- [ ] Le GND est commun entre switch et Raspberry Pi
- [ ] Le switch SS-5GL fonctionne (test continuité)
- [ ] Les logs du daemon sont surveillés pendant test
- [ ] La boussole affiche bien les données du daemon (fichier JSON)

---

## 🔗 Fichiers de Test

**Script de test GPIO** :
```bash
sudo python3 tests_sur_site/test_switch_direct.py
```

**Relancer daemon avec logs** :
```bash
sudo pkill -f ems22d_calibrated
sudo python3 ems22d_calibrated.py
```

**Surveiller logs système** :
```bash
tail -f /var/log/syslog | grep ems22d
```

---

**Version** : 1.0
**Date** : 6 Décembre 2025
**Statut** : Diagnostic - Tests terrain requis
