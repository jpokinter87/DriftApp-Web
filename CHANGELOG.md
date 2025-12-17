# 📜 Changelog DriftApp

Toutes les modifications notables de ce projet sont documentées dans ce fichier.

Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/).

---

## [4.4] - 2025-12-17

### 🔧 Corrigé
- **Saccades GOTO** : Les mouvements GOTO sont maintenant fluides
  - Rotation directe pour déplacements > 3° (sans feedback itératif)
  - Correction finale feedback (max 3 itérations) si erreur > 0.5°
  - JOG (boutons manuels) : Toujours rotation directe (fluidité maximale)

### 🗑️ Supprimé
- **Mode FAST_TRACK** : Redondant avec CONTINUOUS après calibration
  - CONTINUOUS utilisé pour tous les GOTO et tracking haute altitude

### ✏️ Modifié
- `motor_service.py` : Logique GOTO/JOG optimisée
- `config.json` : Version 2.2, CONTINUOUS.motor_delay = 0.00015s
- `adaptive_tracking.py` : Suppression TrackingMode.FAST_TRACK

### 📦 Ajouté
- Répertoire `tests/` avec scripts de diagnostic
- `CLAUDE.md` : Contexte mis à jour pour Claude AI

---

## [4.3] - 2025-12-09

### 🔧 Corrigé
- **Encodeur EMS22A** : Intégration daemon externe
- **Feedback controller** : Extraction dans module séparé

### ✏️ Modifié
- Architecture daemon encodeur (process séparé)
- Communication IPC via /dev/shm/

---

## [4.2] - 2025-11-16

### 🗑️ Supprimé
- **Mode CAUTIOUS** : Simplifié à 3 modes (NORMAL, CRITICAL, CONTINUOUS)

### ✏️ Modifié
- `adaptive_tracking.py` : Logique de sélection de mode simplifiée
- `config.json` : Version 2.1

---

## [4.1] - 2025-11-15

### 🔧 Corrigé
- **Rechargements config.json** : Passé de 7+ à 1 seul chargement
- **Injection dépendances** : Config passée aux modules au lieu de rechargement

### ✏️ Modifié
- `tracker.py` : Accepte motor_config, encoder_config en paramètres
- `adaptive_tracking.py` : Accepte adaptive_config en paramètre

---

## [4.0] - 2025-11-08

### 🔧 Corrigé
- **Décalage ×4** : MICROSTEPS intégré dans les calculs

### 📦 Ajouté
- Configuration MICROSTEPS dans config.json
- Calcul dynamique de steps_per_dome_revolution

---

## [3.2] - 2025-11-05

### 🔧 Corrigé
- **Vitesse insuffisante** : Limite délai passée de 1ms à 10µs

### 📦 Ajouté
- Mode FAST_TRACK pour GOTO rapides (~45°/min)

---

## [3.1] - 2025-11-01

### 📦 Ajouté
- **Système adaptatif** : 4 modes automatiques selon altitude/mouvement
- **Anticipation prédictive** : Calcul position future (5 minutes)
- **Zone critique** : Gestion spéciale proche zénith

---

## [3.0] - 2025-10-xx

### 📦 Ajouté
- Interface web Django
- Architecture 3 processus (Django, Motor Service, Daemon encodeur)
- Communication IPC via fichiers JSON en mémoire partagée

---

## [2.x] - 2025-xx-xx

### 📦 Ajouté
- Interface TUI (Textual)
- Méthode abaque pour correction parallaxe

---

## [1.x] - 2025-xx-xx

### 📦 Ajouté
- Contrôle moteur basique
- Calculs astronomiques
- Suivi d'objets célestes

---

## Types de changements

- 📦 **Ajouté** : Nouvelles fonctionnalités
- ✏️ **Modifié** : Changements de fonctionnalités existantes
- 🗑️ **Supprimé** : Fonctionnalités supprimées
- 🔧 **Corrigé** : Corrections de bugs
- 🔒 **Sécurité** : Corrections de vulnérabilités
