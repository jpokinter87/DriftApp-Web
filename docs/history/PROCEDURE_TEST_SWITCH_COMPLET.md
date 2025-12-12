# ✅ Procédure de Test Complet du Switch avec Daemon

**Date** : 6 Décembre 2025
**Objectif** : Vérifier que le daemon calibre bien l'angle à 45° au passage du switch

---

## 📋 Étapes du Test

### 1️⃣ Arrêter le Test Direct

Si `test_switch_direct.py` tourne encore :

```bash
# Ctrl+C pour arrêter le test direct
# OU
sudo pkill -f test_switch_direct
```

---

### 2️⃣ Lancer le Daemon en Foreground avec Logs Visibles

**Terminal 1** :

```bash
# Arrêter l'ancien daemon si tourne en background
sudo pkill -f ems22d_calibrated

# Lancer daemon en foreground (logs visibles)
sudo python3 ems22d_calibrated.py
```

**Résultat attendu au démarrage** :

```
[ems22d] ... ======================================================================
[ems22d] ... Daemon EMS22D avec Switch de Calibration - VERSION CORRIGÉE
[ems22d] ... ======================================================================
[ems22d] ... Port TCP : 5556
[ems22d] ... CALIBRATION_FACTOR : 0.010851
[ems22d] ... Switch GPIO : 27 (recalage à 45°)
[ems22d] ... Méthode : INCRÉMENTALE (accumulation)
[ems22d] ... ======================================================================
[ems22d] ... Switch GPIO 27 configuré (pull-up) - état initial : 1
[ems22d] ... SPI opened 0.0 @ 500000 Hz
```

**IMPORTANT** : Vérifier la ligne `Switch GPIO 27 configuré - état initial : X`
- Si **état initial : 1** → Coupole PAS sur le switch (normal)
- Si **état initial : 0** → Coupole DÉJÀ sur le switch (attention au démarrage)

---

### 3️⃣ Lancer la Boussole

**Terminal 2** :

```bash
python3 boussole.py
```

La boussole devrait afficher l'**angle actuel** (probablement incorrect car non calibré).

---

### 4️⃣ Faire Passer la Coupole sur le Switch

**Actions** :
1. **Bouger la coupole** vers la position 45° physique
2. **Observer attentivement** les deux terminaux pendant le passage

---

### 5️⃣ Résultats Attendus au Passage du Switch

#### **Terminal 1 (Daemon)** :

```
[ems22d] 2025-12-06 14:30:45,123 INFO 🔄 Microswitch activé → recalage à 45°
[ems22d] 2025-12-06 14:30:45,124 INFO    → total_counts recalé à -11794
[ems22d] 2025-12-06 14:30:45,125 INFO    → angle affiché : 45°
```

**Si ces logs n'apparaissent PAS** → Le daemon ne détecte pas le switch (bug logique)

#### **Terminal 2 (Boussole)** :

L'aiguille devrait :
1. **Sauter instantanément à 45°** au moment du passage
2. **Continuer à suivre** la coupole depuis cette position calibrée

---

## 🐛 Diagnostic en Cas de Problème

### Problème 1 : Aucun Log "Microswitch activé"

**Cause possible** :
- Le daemon détecte le switch mais la logique `process_switch()` ne se déclenche pas

**Actions** :
```bash
# Vérifier que la logique switch est bien appelée
grep -n "process_switch" ems22d_calibrated.py

# Résultat attendu :
# 162:    def process_switch(self, angle):
# 307:                angle = self.process_switch(angle)
```

Si ligne 307 manquante → Bug dans le code !

### Problème 2 : Log Apparaît Mais Boussole Ne Bouge Pas

**Cause possible** :
- Daemon calibre correctement
- Mais boussole ne lit pas les nouvelles données

**Test** :
```bash
# Pendant que daemon tourne, surveiller JSON
watch -n 0.5 cat /dev/shm/ems22_position.json

# Devrait afficher angle proche de 45° après passage switch
```

Si JSON correct mais boussole figée → Revoir bug boussole (déjà corrigé normalement)

### Problème 3 : Log Apparaît Plusieurs Fois

**Cause possible** :
- Switch mécanique "rebondit" (plusieurs transitions rapides)
- Daemon calibre plusieurs fois de suite

**Solution** :
- Ajouter un délai anti-rebond dans `process_switch()`
- Ignorer transitions < 0.5s après dernière calibration

---

## 📊 Checklist de Validation

Cocher les étapes au fur et à mesure :

- [ ] **1.** Test direct confirme détection GPIO (transition 1→0) ✅ (FAIT)
- [ ] **2.** Daemon démarre avec log "Switch GPIO 27 configuré"
- [ ] **3.** Boussole affiche l'angle actuel (incorrect)
- [ ] **4.** Au passage switch : Log "🔄 Microswitch activé" apparaît
- [ ] **5.** Au passage switch : Boussole saute instantanément à 45°
- [ ] **6.** Après passage : Boussole continue de suivre la coupole
- [ ] **7.** Vérifier JSON : `cat /dev/shm/ems22_position.json` montre angle ~45°

---

## 🎯 Résultat Final Attendu

Si **TOUTES** les étapes fonctionnent :

✅ **Switch hardware** : OK (détection GPIO)
✅ **Switch daemon** : OK (calibration à 45°)
✅ **Boussole** : OK (affichage synchronisé)
✅ **Système complet** : FONCTIONNEL

Le système est alors prêt pour l'intégration dans DriftApp (tracking avec recalage automatique).

---

**Version** : 1.0
**Date** : 6 Décembre 2025
**Statut** : Procédure de validation terrain
