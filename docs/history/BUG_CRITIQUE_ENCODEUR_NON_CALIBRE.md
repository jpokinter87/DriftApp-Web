# 🔴 BUG CRITIQUE : Mouvement Infini avec Encodeur Non Calibré

**Date** : 7 Décembre 2025
**Gravité** : CRITIQUE - Mouvement infini, arrêt impossible
**Contexte** : Suivi lancé sur M13 sans calibration préalable de l'encodeur

---

## 📋 Symptômes Observés

1. ❌ **Divergence encodeur/correction** : Encodeur à 0.1° alors qu'une correction de 0.56° venait d'être appliquée
2. ❌ **Mouvement infini** : Coupole continue de tourner indéfiniment
3. ❌ **Bouton STOP ne répond pas** : Impossible d'arrêter le suivi via l'interface
4. ❌ **Arrêt forcé nécessaire** : Utilisateur contraint de tuer le processus

---

## 🔍 Analyse des Logs (driftapp_20251207_181738.log)

### Séquence Problématique

**Initialisation** :
```
Ligne 44-45 : Encodeur actif - Position: 0.1°
Ligne 55    : SYNC: Coupole=110.5° | Encodeur=0.1° | Offset=110.5°
```
⚠️ **Encodeur non calibré** : reste à 0.1° (pas passé par switch 45°)

**Première Correction (18:19:06)** :
```
Ligne 112 : Rotation avec feedback: 0.1° → 0.8°
Ligne 113 : ⚠️ Rotation feedback imprécise: 0.1° → 359.8° (erreur: +0.98°, 10/10 iter)
```
❌ **Échec** : 10 itérations sans atteindre la cible (33.9s)

**Deuxième Correction (18:19:40)** :
```
Ligne 157 : Rotation avec feedback: 359.8° → 1.3°
Ligne 158 : ⚠️ Rotation feedback imprécise: 359.8° → 0.1° (erreur: +1.20°, 10/10 iter)
```
❌ **Échec** : 10 itérations sans atteindre la cible (51.4s)

**Troisième Correction (18:20:32)** :
```
Ligne 202 : Rotation avec feedback: 0.1° → 2.0°
Ligne 203 : ⚠️ Rotation feedback imprécise: 0.1° → 359.9° (erreur: +2.07°, 10/10 iter)
```
❌ **Échec** : 10 itérations sans atteindre la cible (76.9s)

---

## 🎯 Cause Racine

### Problème 1 : Encodeur Non Calibré

L'encodeur retourne une valeur **fixe ~0.1°** car :
- Pas de passage par le switch de calibration (45°)
- Lecture brute de l'encodeur sans référence absolue
- `total_counts` non initialisé correctement dans le daemon

**Conséquence** : La boucle de feedback pense que la coupole ne bouge jamais.

### Problème 2 : Boucle de Feedback Sans Échappatoire

Dans `core/hardware/moteur_feedback.py` :
```python
for iteration in range(max_iterations):
    # Moteur tourne
    # Encodeur lit toujours 0.1° (valeur fixe)
    # Calcul erreur : cible - 0.1° = toujours > tolérance
    # Continue... 10 fois
    time.sleep(0.5)  # ← Bloque le thread pendant 5s au total

# Après 10 itérations : abandonne avec WARNING
# MAIS le système continue et lance une nouvelle correction !
```

**Conséquence** :
- Chaque correction prend 30-76 secondes (10 itérations × délais)
- Le système voit toujours un écart (encodeur fixe à 0.1°)
- Lance immédiatement une nouvelle correction
- **Boucle infinie**

### Problème 3 : Bouton STOP Bloqué

Pendant les `time.sleep()` de la boucle feedback, le thread GUI est probablement bloqué ou les événements Kivy ne sont pas traités.

**Hypothèse** :
- `_do_correction()` est appelé dans le thread GUI
- Les `time.sleep()` bloquent le traitement des événements
- Le clic sur STOP n'est jamais traité

---

## 🛠️ Solutions Proposées

### Solution 1 : Détection Encodeur Non Calibré (PRIORITAIRE)

**Vérifier avant le suivi si l'encodeur est calibré** :

```python
# Dans tracker.py, méthode start()
if self.moteur.encodeur_enabled:
    encoder_data = self.moteur.get_daemon_status()
    if encoder_data and not encoder_data.get('calibrated', False):
        raise RuntimeError(
            "⚠️ ENCODEUR NON CALIBRÉ\n"
            "Veuillez faire passer la coupole par le switch (45°) "
            "avant de lancer le suivi."
        )
```

**Message dans l'interface** :
```
❌ Impossible de démarrer le suivi
L'encodeur n'est pas calibré.

Action requise :
1. Faire tourner manuellement la coupole
2. Passer par la position 45° (switch)
3. Attendre la calibration automatique
4. Relancer le suivi
```

### Solution 2 : Limite de Corrections Consécutives Échouées

**Arrêter après 3 corrections échouées consécutives** :

```python
# Dans tracker.py
self.failed_corrections_count = 0

def check_and_correct(self):
    correction_applied, log_msg = self._apply_correction()

    if not correction_applied:
        self.failed_corrections_count += 1

        if self.failed_corrections_count >= 3:
            self.stop()
            raise RuntimeError(
                "⚠️ SUIVI ARRÊTÉ : 3 corrections consécutives ont échoué.\n"
                "Vérifiez l'encodeur et la calibration."
            )
    else:
        self.failed_corrections_count = 0  # Reset si succès
```

### Solution 3 : Fix Erreur de Logging

**Ligne 448 de tracker.py** :
```python
# AVANT (ERREUR)
self.python_logger.info(azimut, altitude, delta)

# APRÈS (CORRECT)
self.python_logger.info(f"Correction Az={azimut:.2f}° Alt={altitude:.2f}° Delta={delta:.2f}°")
```

### Solution 4 : Arrêt Non Bloquant

**Utiliser un flag pour arrêter la boucle feedback** :

```python
# Dans moteur_feedback.py
def rotate_with_daemon_feedback(self, target_angle, ...):
    for iteration in range(max_iterations):
        if self.stop_requested:  # ← Nouveau flag
            logger.info("Arrêt demandé, abandon de la correction")
            break

        # ... rotation ...
        time.sleep(check_interval)

# Méthode pour arrêter
def request_stop(self):
    self.stop_requested = True
```

**Dans main_screen.py, bouton STOP** :
```python
def on_stop(self, instance):
    if self.tracking_session:
        self.tracking_session.moteur.request_stop()
        self.tracking_session.stop()
```

---

## 🧪 Tests de Validation

### Test 1 : Démarrage sans calibration

```bash
# 1. Lancer le daemon encodeur (sans passer par 45°)
sudo systemctl restart ems22d.service

# 2. Vérifier que calibrated=false
cat /dev/shm/ems22_position.json
# Doit montrer: "calibrated": false

# 3. Lancer le GUI et essayer de démarrer un suivi
uv run main_gui.py

# Résultat attendu :
# ❌ Message d'erreur : "Encodeur non calibré"
# ✅ Suivi ne démarre pas
```

### Test 2 : Corrections échouées multiples

```bash
# Simuler un encodeur bloqué dans le daemon (pour test)
# Forcer calibrated=true mais angle fixe

# Résultat attendu :
# ⚠️ Après 3 corrections échouées : arrêt automatique
# ✅ Message : "3 corrections consécutives ont échoué"
```

### Test 3 : Arrêt pendant correction

```bash
# 1. Lancer un suivi
# 2. Pendant une correction en cours (feedback loop), cliquer STOP

# Résultat attendu :
# ✅ Arrêt immédiat (< 1s)
# ✅ Moteur s'arrête
# ✅ Logs : "Arrêt demandé, abandon de la correction"
```

---

## 📊 Impact

**Avant fix** :
- ❌ Mouvement infini possible
- ❌ Arrêt impossible
- ❌ Risque mécanique (forcer le moteur)
- ❌ Expérience utilisateur catastrophique

**Après fix** :
- ✅ Impossible de démarrer sans calibration
- ✅ Arrêt automatique après 3 échecs
- ✅ Bouton STOP réactif
- ✅ Sécurité matérielle garantie

---

## 🎯 Priorités de Développement

1. **URGENT** : Détection encodeur non calibré avant démarrage
2. **URGENT** : Limite corrections consécutives échouées
3. **HAUTE** : Fix erreur de logging (évite spam logs)
4. **HAUTE** : Arrêt non bloquant de la boucle feedback
5. **MOYENNE** : Tests automatisés pour ces scénarios

---

## 📝 Fichiers à Modifier

1. **`core/tracking/tracker.py`** :
   - Ligne ~150 : Vérification calibration au démarrage
   - Ligne 448 : Fix format logging
   - Ajout compteur échecs consécutifs

2. **`core/hardware/moteur_feedback.py`** :
   - Ajout flag `stop_requested`
   - Vérification flag dans boucle feedback
   - Méthode `request_stop()`

3. **`gui/screens/main_screen.py`** :
   - Bouton STOP : appel `request_stop()` avant `stop()`
   - Gestion exception au démarrage (encodeur non calibré)

4. **`ems22d_calibrated.py`** (daemon) :
   - S'assurer que `calibrated` est correctement publié dans JSON

---

*Analyse créée le 7 décembre 2025 - BUG CRITIQUE à corriger en priorité*
