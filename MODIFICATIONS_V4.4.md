# 🔧 MODIFICATIONS DRIFTAPP v4.4 - Correction des saccades GOTO

## Date: 17 décembre 2025

## 📋 Résumé des modifications

Suite aux diagnostics de calibration, les saccades lors des GOTO ont été identifiées comme provenant des pauses de la boucle de feedback (~130ms entre chaque itération).

### Solution implémentée:
- **GOTO grands déplacements (> 3°)**: Rotation directe fluide + correction finale feedback
- **GOTO petits déplacements (≤ 3°)**: Feedback classique (précision)
- **JOG (boutons manuels)**: Rotation directe sans feedback (fluidité maximale)
- **Tracking**: Feedback conservé (corrections < 5°)
- **Suppression FAST_TRACK**: Redondant avec CONTINUOUS après calibration

---

## 📁 Fichiers à déployer

### 1. `motor_service.py`
**Emplacement**: `~/Dome_v4_6/services/motor_service.py`

**Modifications**:
- `handle_goto()`: Logique optimisée selon le seuil de 3°
- `handle_jog()`: Rotation directe sans feedback
- `_get_goto_speed()`: Utilise CONTINUOUS (plus rapide vitesse fluide)
- Ajout de la constante `SEUIL_FEEDBACK_DEG = 3.0`

### 2. `config.json`
**Emplacement**: `~/Dome_v4_6/data/config.json`

**Modifications**:
- Suppression du mode `fast_track`
- `continuous.motor_delay`: 0.00015s (calibré le 17/12/2025)
- Mise à jour version: 2.2

### 3. `adaptive_tracking.py`
**Emplacement**: `~/Dome_v4_6/core/tracking/adaptive_tracking.py`

**Modifications**:
- Suppression de `TrackingMode.FAST_TRACK`
- Suppression de `_get_fast_track_params()`
- Mise à jour des commentaires

---

## 🚀 Procédure de déploiement

```bash
# 1. Créer une sauvegarde
cd ~/Dome_v4_6
mkdir -p backups/v4.3
cp services/motor_service.py backups/v4.3/
cp data/config.json backups/v4.3/
cp core/tracking/adaptive_tracking.py backups/v4.3/

# 2. Arrêter les services
sudo ./start_web.sh stop

# 3. Copier les nouveaux fichiers
cp /chemin/vers/motor_service.py services/
cp /chemin/vers/config.json data/
cp /chemin/vers/adaptive_tracking.py core/tracking/

# 4. Redémarrer les services
sudo ./start_web.sh start

# 5. Tester
# - GOTO manuel de 90° → doit être fluide
# - Boutons +10°, -10° → doit être fluide
# - Tracking d'un objet → doit fonctionner normalement
```

---

## 🔍 Détails techniques

### Logique GOTO optimisée (motor_service.py)

```python
def handle_goto(self, angle: float, speed: Optional[float] = None):
    delta = shortest_angular_distance(current_pos, angle)
    
    if abs(delta) > 3.0:
        # GRAND DÉPLACEMENT
        # 1. Rotation directe (fluide)
        self.moteur.rotation(delta, vitesse=speed)
        
        # 2. Correction finale si erreur > 0.5°
        if abs(erreur) > 0.5:
            self.feedback_controller.rotation_avec_feedback(
                angle_cible=angle,
                max_iterations=3  # Max 3 corrections fines
            )
    else:
        # PETIT DÉPLACEMENT - Feedback classique
        self.feedback_controller.rotation_avec_feedback(angle_cible=angle)
```

### Logique JOG optimisée (motor_service.py)

```python
def handle_jog(self, delta: float, speed: Optional[float] = None):
    # Rotation directe sans feedback (fluidité maximale)
    self.moteur.rotation(delta, vitesse=speed)
    
    # Lire position finale depuis encodeur
    self.current_status['position'] = self.daemon_reader.read_angle()
```

### Vitesses configurées (config.json)

| Mode | Délai | Vitesse | Usage |
|------|-------|---------|-------|
| NORMAL | 2.0 ms | ~5°/min | Tracking standard |
| CRITICAL | 1.0 ms | ~9°/min | Tracking rapproché |
| CONTINUOUS | 0.15 ms | ~41°/min | Tracking continu + GOTO |

---

## ⚠️ Points d'attention

1. **Seuil de 3°**: Modifiable via `SEUIL_FEEDBACK_DEG` en haut de motor_service.py
2. **Tolérance finale**: 0.5° (configurable dans handle_goto)
3. **Max iterations correction finale**: 3 (suffisant pour < 1° d'erreur résiduelle)

---

## 🔄 Rollback si nécessaire

```bash
cd ~/Dome_v4_6
sudo ./start_web.sh stop
cp backups/v4.3/motor_service.py services/
cp backups/v4.3/config.json data/
cp backups/v4.3/adaptive_tracking.py core/tracking/
sudo ./start_web.sh start
```

---

## ✅ Tests de validation

1. **GOTO 90°**: Mouvement fluide, pas de saccades audibles
2. **GOTO 2°**: Mouvement avec feedback (quelques micro-corrections)
3. **Bouton +10°**: Mouvement fluide et rapide
4. **Bouton +1°**: Mouvement fluide et rapide
5. **Tracking**: Corrections toutes les 30-60s, mouvement fluide
6. **Position finale**: Erreur < 0.5° après GOTO

---

## 📊 Résultats attendus

| Opération | Avant v4.4 | Après v4.4 |
|-----------|------------|------------|
| GOTO 90° | Saccadé (feedback) | Fluide + correction finale |
| JOG +10° | Saccadé (feedback) | Fluide |
| Tracking | OK | OK (inchangé) |
| Précision finale | ~0.3° | ~0.5° (acceptable) |
