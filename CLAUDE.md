# 🤖 CLAUDE.md - Contexte pour Claude AI

> **Dernière mise à jour** : 17 décembre 2025  
> **Version DriftApp** : 4.4  
> **Statut** : Production - Correction saccades GOTO

---

## 📋 Vue d'ensemble du projet

**DriftApp** est une application de contrôle de coupole astronomique pour l'Observatoire Ubik (France). Elle gère le suivi automatique d'objets célestes en synchronisant la rotation de la coupole avec le mouvement apparent du ciel.

### Architecture technique

```
DriftApp v4.4/
├── core/
│   ├── config/
│   │   └── config_loader.py      # Chargement configuration centralisée
│   ├── hardware/
│   │   ├── moteur.py             # Contrôle moteur pas-à-pas + DaemonEncoderReader
│   │   ├── moteur_simule.py      # Simulation pour développement
│   │   ├── feedback_controller.py # Boucle fermée encodeur
│   │   └── hardware_detector.py  # Détection auto Raspberry Pi
│   ├── tracking/
│   │   ├── tracker.py            # Session de suivi principal
│   │   ├── adaptive_tracking.py  # Modes adaptatifs (3 modes)
│   │   ├── abaque_manager.py     # Interpolation loi de coupole
│   │   └── tracking_logger.py    # Logs de suivi
│   ├── observatoire/
│   │   └── calculs astronomiques
│   └── utils/
│       └── angle_utils.py        # shortest_angular_distance, etc.
├── services/
│   └── motor_service.py          # Service IPC pour Django (v4.4)
├── web/                          # Interface Django
├── data/
│   ├── config.json               # Configuration centralisée (v2.2)
│   └── Loi_coupole.xlsx          # Abaque de correction
├── logs/                         # Fichiers de log
└── tests/                        # Scripts de test et diagnostic
```

### Matériel

| Composant | Modèle | Caractéristiques |
|-----------|--------|------------------|
| SBC | Raspberry Pi 4 | 4GB RAM, Raspbian |
| Moteur | Pas-à-pas NEMA | 200 steps/rev |
| Driver | DM556T | Microsteps: 4 |
| Encodeur | EMS22A | Magnétique, 10 bits (1024 positions) |
| Réduction | Engrenages | Ratio 2230:1 |

---

## 🔧 Historique des problèmes et solutions

### Problème 1 : Zone critique Eltanin (1er novembre 2025)
**Symptôme** : Perte de l'objet près du zénith  
**Cause** : Mouvement trop rapide de la coupole en haute altitude  
**Solution** : Système adaptatif à 4 modes (puis 3 modes)  
**Statut** : ✅ Résolu

### Problème 2 : Vitesse insuffisante (5 novembre 2025)
**Symptôme** : Moteur trop lent pour suivre les objets rapides  
**Cause** : Limite de délai à 1ms  
**Solution** : Passage à délai minimum 10µs  
**Statut** : ✅ Résolu

### Problème 3 : Décalage ×4 (8 novembre 2025)
**Symptôme** : Mouvement 4× plus court que demandé  
**Cause** : MICROSTEPS non pris en compte  
**Solution** : Intégration dans config.json et calculs  
**Statut** : ✅ Résolu

### Problème 4 : Saccades moteur GOTO (décembre 2025)
**Symptôme** : Claquements audibles lors des GOTO manuels et automatiques  
**Cause** : Boucle feedback avec pauses de 130ms entre itérations  
**Solution** : GOTO sans feedback pour grands déplacements (> 3°)  
**Statut** : ✅ Résolu (v4.4)

---

## 🎯 Solution v4.4 - Correction des saccades

### Diagnostic effectué (16-17 décembre 2025)

| Test | Résultat | Conclusion |
|------|----------|------------|
| TEST A (boucle isolée) | 0.01% outliers | Boucle moteur parfaite |
| TEST B (Motor Service) | Fluide | Motor Service OK |
| Calibration vitesse | 0.15ms = max fluide | FAST_TRACK trop rapide |
| Production (GOTO) | Saccadé | Feedback = cause |

### Cause identifiée

Le `FeedbackController.rotation_avec_feedback()` introduit des pauses :
- `_lire_position_stable()` : 80ms (50ms stabilisation + 3×10ms échantillons)
- `time.sleep(0.05)` : 50ms entre itérations
- **Total : ~130ms de pause entre chaque micro-correction**

Pour un GOTO de 90°, le mouvement est découpé en plusieurs itérations avec ces pauses, créant les saccades audibles.

### Solution implémentée

```python
# motor_service.py v4.4
def handle_goto(self, angle, speed):
    delta = shortest_angular_distance(current_pos, angle)
    
    if abs(delta) > 3.0:  # SEUIL_FEEDBACK_DEG
        # GRAND DÉPLACEMENT : Rotation directe (fluide)
        self.moteur.rotation(delta, vitesse=speed)
        
        # Correction finale si nécessaire (max 3 itérations)
        if abs(erreur) > 0.5:
            self.feedback_controller.rotation_avec_feedback(
                angle_cible=angle, max_iterations=3
            )
    else:
        # PETIT DÉPLACEMENT : Feedback classique
        self.feedback_controller.rotation_avec_feedback(angle_cible=angle)

def handle_jog(self, delta, speed):
    # Boutons manuels : TOUJOURS rotation directe (fluidité)
    self.moteur.rotation(delta, vitesse=speed)
```

### Modifications apportées

| Fichier | Modification |
|---------|--------------|
| `motor_service.py` | GOTO optimisé, JOG sans feedback |
| `config.json` | Suppression FAST_TRACK, CONTINUOUS=0.00015s |
| `adaptive_tracking.py` | Suppression TrackingMode.FAST_TRACK |

---

## ⚙️ Configuration actuelle (config.json v2.2)

### Modes de vitesse

| Mode | Délai | Vitesse | Usage |
|------|-------|---------|-------|
| NORMAL | 2.0 ms | ~5°/min | Tracking altitude < 68° |
| CRITICAL | 1.0 ms | ~9°/min | Tracking 68° ≤ altitude < 75° |
| CONTINUOUS | 0.15 ms | ~41°/min | Tracking altitude ≥ 75° + GOTO |

### Seuils

```json
{
  "adaptive_tracking": {
    "altitudes": {
      "critical": 68.0,
      "zenith": 75.0
    },
    "movements": {
      "critical": 30.0,
      "extreme": 50.0,
      "min_for_continuous": 1.0
    }
  }
}
```

---

## 🧪 Tests disponibles

### Scripts de diagnostic (répertoire `tests/`)

| Script | Usage |
|--------|-------|
| `diagnostic_moteur_complet.py` | TEST A - Boucle moteur isolée |
| `test_motor_service_seul.py` | TEST B - Motor Service via IPC |
| `calibration_vitesse_max.py` | Trouver vitesse max fluide |

### Exécution

```bash
# TEST A - Mode isolé (sudo requis)
sudo python3 tests/diagnostic_moteur_complet.py

# TEST B - Via Motor Service (services actifs)
python3 tests/test_motor_service_seul.py

# Calibration vitesse
python3 tests/calibration_vitesse_max.py
```

---

## 📊 Métriques de performance

### Tracking

- Corrections < 5° typiquement
- Précision finale : < 0.5°
- Modes adaptatifs fonctionnels

### GOTO (v4.4)

- Mouvement fluide (pas de saccades)
- Erreur résiduelle < 0.5° après correction finale
- Temps GOTO 90° : ~2-3 secondes

---

## 🔄 Procédure de mise à jour

```bash
# Sauvegarde
mkdir -p backups/v4.3
cp services/motor_service.py backups/v4.3/
cp data/config.json backups/v4.3/
cp core/tracking/adaptive_tracking.py backups/v4.3/

# Mise à jour
cp nouveaux_fichiers/* emplacements_respectifs/

# Redémarrage
sudo ./start_web.sh restart
```

---

## 📝 Notes pour Claude

### Quand l'utilisateur parle de...

| Sujet | Contexte |
|-------|----------|
| "Saccades" | Problème résolu en v4.4, vérifier version déployée |
| "FAST_TRACK" | Supprimé, remplacé par CONTINUOUS |
| "Feedback" | Utilisé pour tracking et petits GOTO (≤ 3°) |
| "Calibration" | Script dans tests/, nécessite patch Motor Service |
| "Encodeur EMS22A" | Daemon externe, lit /dev/shm/ems22_position.json |

### Architecture IPC

```
Django (8000) ─── /dev/shm/motor_command.json ───► Motor Service
                                                        │
Motor Service ─── /dev/shm/motor_status.json ───► Django
                                                        │
Daemon encodeur ─ /dev/shm/ems22_position.json ─► Motor Service
```

### Fichiers critiques

- `/dev/shm/motor_command.json` : Commandes (goto, jog, stop, tracking_start...)
- `/dev/shm/motor_status.json` : État (position, status, tracking_info...)
- `/dev/shm/ems22_position.json` : Position encodeur (angle, calibrated, status)

---

## 🚀 Prochaines améliorations possibles

1. **Optimisation feedback** : Réduire les pauses de `read_stable()` (50ms → 20ms)
2. **Interface web** : Afficher le mode de vitesse en cours
3. **Logs structurés** : Format JSON pour analyse automatique
4. **Tests automatisés** : CI/CD avec pytest

---

**Fin du contexte CLAUDE.md**
