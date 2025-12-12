# 🐛 Debug Switch dans Daemon - Mode Diagnostic

**Date** : 6 Décembre 2025
**Problème** : Test direct détecte le switch, mais daemon ne calibre pas

---

## 🔍 Symptômes

✅ **Test direct** (`test_switch_direct.py`) : Switch détecté, transition 1→0 visible
❌ **Daemon** (`ems22d_calibrated.py`) : Aucun log "🔄 Microswitch activé"

**Conclusion** : Hardware OK, mais daemon ne détecte pas la transition.

---

## 🧪 Logs de Debug Ajoutés

### Modification Appliquée

Ajout d'un log **à chaque transition** d'état du switch (ligne 197) :

```python
# DEBUG: Log les transitions pour diagnostiquer
if state != self.switch_last_state:
    logger.info(f"[DEBUG] Switch transition: {self.switch_last_state}→{state}")
```

**But** : Voir si le daemon lit le switch et détecte les changements d'état.

---

## 📋 Procédure de Test avec Debug

### Terminal 1 : Logs en Temps Réel

```bash
tail -f logs/ems22d.log
```

### Terminal 2 : Daemon

```bash
# Arrêter ancien daemon (important !)
sudo pkill -f ems22d_calibrated

# Lancer nouveau daemon avec logs debug
sudo python3 ems22d_calibrated.py
```

### Terminal 3 : Boussole (optionnel)

```bash
python3 boussole.py
```

---

## 🎯 Test

### Actions

1. **Observer le démarrage** (Terminal 1) :
   ```
   [ems22d] ... Switch GPIO 27 configuré (pull-up) - état initial : 1
   ```
   → **État initial doit être 1** (coupole PAS sur le switch)

2. **Bouger la coupole vers 45° physique**

3. **Observer les logs au passage du switch**

---

## 📊 Scénarios Possibles

### Scénario 1 : Aucune Transition Détectée ❌

**Logs observés** :
- Démarrage OK
- **AUCUN** log `[DEBUG] Switch transition: ...`
- Pas de "🔄 Microswitch activé"

**Diagnostic** :
Le daemon **ne détecte JAMAIS** de changement d'état du switch.

**Causes possibles** :
1. **Conflit GPIO** : Un autre processus utilise GPIO 27
2. **Permissions** : lgpio n'a pas accès au GPIO dans le daemon
3. **État figé** : `lgpio.gpio_read()` retourne toujours la même valeur

**Tests** :
```bash
# Vérifier qu'aucun autre processus n'utilise GPIO
sudo lsof | grep gpio

# Vérifier permissions lgpio
ls -l /dev/gpiochip*

# Tester lecture GPIO dans daemon
sudo python3 -c "
import lgpio
h = lgpio.gpiochip_open(0)
lgpio.gpio_claim_input(h, 27, lgpio.SET_PULL_UP)
print('État GPIO 27:', lgpio.gpio_read(h, 27))
lgpio.gpiochip_close(h)
"
```

---

### Scénario 2 : Transitions Détectées mais Pas de Calibration ⚠️

**Logs observés** :
```
[ems22d] ... [DEBUG] Switch transition: 1→0
[ems22d] ... [DEBUG] Switch transition: 0→1
```

**MAIS** :
- **AUCUN** log `🔄 Microswitch activé`

**Diagnostic** :
Le daemon **détecte les transitions**, mais la condition `if self.switch_last_state == 1 and state == 0:` n'est **jamais vraie**.

**Causes possibles** :
1. **Ordre des transitions inversé** : 0→1 au lieu de 1→0
   - Switch câblé en logique inversée (NO au lieu de NC ou vice versa)
2. **Bug logique** : `switch_last_state` pas mis à jour correctement
3. **Race condition** : État change trop vite

**Solution** :
Si transitions inversées (0→1 détectée), modifier la condition :

```python
# Au lieu de détecter 1→0, détecter 0→1
if self.switch_last_state == 0 and state == 1:
    logger.info(f"🔄 Microswitch activé → recalage à {SWITCH_CALIB_ANGLE}°")
```

---

### Scénario 3 : Calibration Détectée ✅

**Logs observés** :
```
[ems22d] ... [DEBUG] Switch transition: 1→0
[ems22d] ... 🔄 Microswitch activé → recalage à 45°
[ems22d] ...    → total_counts recalé à -11794
[ems22d] ...    → angle affiché : 45°
```

**Diagnostic** :
Tout fonctionne parfaitement ! Le problème venait probablement :
- D'un ancien daemon sans logs debug tournant en background
- D'un fichier log non surveillé

**Validation** :
- Vérifier que la boussole (Terminal 3) affiche bien 45°
- Continuer à bouger la coupole pour confirmer le tracking depuis 45°

---

## 🔧 Comparaison Test Direct vs Daemon

### Test Direct (`test_switch_direct.py`)

**Code** :
```python
h = lgpio.gpiochip_open(0)
lgpio.gpio_claim_input(h, 27, lgpio.SET_PULL_UP)
state = lgpio.gpio_read(h, 27)
```

**Fonctionne** : ✅ Détecte transition 1→0

### Daemon (`ems22d_calibrated.py`)

**Code (identique)** :
```python
self.hchip = lgpio.gpiochip_open(0)
lgpio.gpio_claim_input(self.hchip, 27, lgpio.SET_PULL_UP)
state = lgpio.gpio_read(self.hchip, 27)
```

**Fonctionne** : ❓ À confirmer avec logs debug

**Différences** :
- Test direct : Foreground, 20 Hz, script simple
- Daemon : Background possible, 50 Hz, classe complexe, SPI simultané

**Hypothèse** : Conflit SPI/GPIO ou timing différent.

---

## 📝 Checklist de Validation

Cocher au fur et à mesure :

- [ ] **1.** Test direct confirme détection switch (transition 1→0) ✅ (FAIT)
- [ ] **2.** Ancien daemon arrêté (`sudo pkill -f ems22d_calibrated`)
- [ ] **3.** Nouveau daemon lancé avec logs debug
- [ ] **4.** Log démarrage : "Switch GPIO 27 configuré - état initial : 1"
- [ ] **5.** Logs debug affichent `[DEBUG] Switch transition: ...` au passage
- [ ] **6.** Transition détectée est bien **1→0** (et pas 0→1)
- [ ] **7.** Log "🔄 Microswitch activé" apparaît
- [ ] **8.** Boussole affiche 45° au passage

---

## 🎯 Résultats Attendus

### Si AUCUNE Transition Détectée

→ **Problème d'accès GPIO dans le daemon**
→ Vérifier permissions, conflits, test Python direct

### Si Transitions Inversées (0→1)

→ **Problème de câblage ou logique inversée**
→ Modifier condition dans code (détecter 0→1 au lieu de 1→0)

### Si Transitions OK mais Pas de Calibration

→ **Bug dans la condition if**
→ Ajouter plus de logs pour voir valeurs exactes

### Si Tout Fonctionne

→ **Problème résolu !**
→ Retirer logs debug pour production

---

## 🔗 Fichiers Associés

- **Daemon** : `ems22d_calibrated.py` (lignes 187-217)
- **Test direct** : `tests_sur_site/test_switch_direct.py`
- **Logs** : `logs/ems22d.log`

---

**Version** : 1.0
**Date** : 6 Décembre 2025
**Statut** : Diagnostic en cours - Logs debug activés
