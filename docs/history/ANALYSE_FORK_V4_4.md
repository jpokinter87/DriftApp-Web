# 📊 Analyse Comparative : Dome v4.3 vs v4.4 (Fork)

**Date** : 6 Décembre 2025
**Objectif** : Identifier évolutions et régressions pour fusion sélective

---

## 📋 RÉSUMÉ EXÉCUTIF

| Catégorie | Nombre | Recommandation |
|-----------|--------|----------------|
| **Évolutions** (à garder) | 5 | Cherry-pick depuis v4.4 |
| **Régressions** (à rejeter) | 5 | GARDER v4.3 (corrections critiques) |
| **Neutre** (à décider) | 4 | Décision utilisateur |
| **Total différences** | 14 | |

### ⚠️ ALERTE CRITIQUE

**Version 4.3 = VERSION DE RÉFÉRENCE CORRECTE**

La v4.3 contient des **corrections critiques** effectuées du 5 au 6 décembre 2025 :
- ✅ Méthode incrémentale du daemon encodeur (correction majeure)
- ✅ Facteur de calibration corrigé (0.010851 au lieu de 0.031354)
- ✅ Infrastructure feedback en boucle fermée fonctionnelle
- ✅ Logs avec rotation automatique
- ✅ Support calibration switch avec logs debug

**La v4.4 est une version ANTÉRIEURE (novembre 2025)** qui contient les bugs corrigés en v4.3.

---

## 🔴 RÉGRESSIONS CRITIQUES (V4.4) - À REJETER

### 1. Facteur de Calibration Incorrect ❌

**Fichier** : `data/config.json`

| Version | Valeur | Statut |
|---------|--------|--------|
| **v4.3** | `0.010851` | ✅ CORRECT (corrigé 5 déc) |
| **v4.4** | `0.031354` | ❌ INCORRECT (ancien bug) |

**Impact** : Erreur de position ×2.89 (daemon affiche 89° au lieu de 31°)

**Explication** :
- V4.3 : `0.01077 / 0.9925 = 0.010851` (cohérent script SPI direct)
- V4.4 : Valeur mesurée en novembre AVANT correction méthode incrémentale

**Décision** : **GARDER v4.3**

---

### 2. Méthode de Calcul du Daemon Encodeur ❌

**Fichier** : `ems22d_calibrated.py`

| Aspect | v4.3 | v4.4 |
|--------|------|------|
| Méthode | INCRÉMENTALE (accumulation) | ABSOLUE (conversion directe) |
| Calibration factor | 0.010851 | 0.031354 |
| Port TCP | 5556 (évite conflit) | 5555 (ancien) |
| Logs | RotatingFileHandler → logs/ems22d.log | basicConfig (stdout) |
| Filtre anti-saut | 30° (assoupli) | 5° (trop strict) |
| Switch support | Complet avec logs debug | Présent mais sans debug |

**Impact** : Daemon v4.4 **ne peut pas suivre les mouvements** de la coupole (bug majeur corrigé en v4.3)

**Explication** :
- Méthode absolue : Convertit raw (0-1023) → angle directement
- **Problème** : L'encodeur fait ~92 tours par rotation coupole → impossible de savoir quel "tour" on est
- Méthode incrémentale : Accumule les changements → suit les mouvements correctement

**Décision** : **GARDER v4.3** (correction critique du 5 décembre)

---

### 3. Suppression Infrastructure Feedback Boucle Fermée ❌

**Fichiers** :
- v4.3 : `core/hardware/moteur_feedback.py` (425 lignes)
- v4.4 : Supprimé, remplacé par `encoder_reader.py` (38 lignes)

**Ce qui est perdu en v4.4** :
- `rotation_avec_feedback_daemon()` : Correction itérative de l'erreur
- `_lire_position_daemon_stable()` : Moyennage pour stabilité mécanique
- Gestion transitions 0°/360° dans calcul delta
- Logs détaillés des corrections
- Fallback open-loop si daemon indisponible

**Ce que fait encoder_reader.py** :
- Juste une fonction de LECTURE (38 lignes)
- Pas de boucle fermée, pas de corrections

**Impact** : **Perte complète du système de feedback** → tracking open-loop seulement

**Décision** : **GARDER moteur_feedback.py de v4.3** (infrastructure essentielle)

---

### 4. Désactivation Feedback dans tracker.py ❌

**Fichier** : `core/tracking/tracker.py`

| Ligne | v4.3 | v4.4 |
|-------|------|------|
| 18 | `from core.hardware.moteur_feedback import ajouter_methode_feedback_daemon` | ❌ Supprimé |
| 67-69 | Initialisation feedback sur moteur | ❌ Supprimé |
| 16 | - | `from core.hardware.encoder_reader import read_encoder_daemon` |

**Impact** : La méthode `rotation_avec_feedback_daemon()` n'est jamais ajoutée au moteur → feedback impossible

**Décision** : **GARDER v4.3** (activation feedback)

---

### 5. Suppression Variables Anti-Oscillation ❌

**Fichier** : `core/tracking/tracker.py` (lignes 142-149 en v4.3)

**Supprimé en v4.4** :
```python
self.correction_history = deque(maxlen=10)
self.oscillation_count = 0
self.consecutive_errors = 0
self.max_consecutive_errors = 5
```

**Impact** : Perte infrastructure de détection d'oscillations (même si non utilisée actuellement)

**Décision** : **GARDER v4.3** (infrastructure de sécurité)

---

## 🟢 ÉVOLUTIONS INTÉRESSANTES (V4.4) - À CHERRY-PICK

### 1. Module encoder_reader.py ✅

**Fichier** : `core/hardware/encoder_reader.py` (nouveau, 38 lignes)

**Fonctionnalité** :
```python
def read_encoder_daemon(max_age_seconds=1.0) -> tuple[float, bool, float]:
    """
    Lit position encodeur depuis daemon avec validation âge données
    Returns: (angle, status_ok, timestamp)
    """
```

**Avantages** :
- ✅ Point d'accès centralisé pour lecture daemon
- ✅ Validation fraîcheur données (max_age_seconds)
- ✅ Retour tuple standardisé (angle, status, timestamp)
- ✅ Améliore séparation des responsabilités

**Utilisation complémentaire** : Peut être utilisé **AVEC** moteur_feedback.py (non exclusif)

**Décision** : **AJOUTER à v4.3** (complément, pas remplacement)

---

### 2. TrackingViewModel (Pattern MVVM) ✅

**Fichier** : `core/ui/viewmodel.py` (nouveau, ~100 lignes)

**Fonctionnalité** :
```python
class TrackingViewModel:
    def format_status_for_ui(self, status: TrackingStatus) -> dict:
        """Formate données pour affichage UI avec couleurs/icônes"""
```

**Avantages** :
- ✅ Sépare logique formatage de logique UI
- ✅ Suit pattern MVVM (Model-View-ViewModel)
- ✅ Améliore testabilité
- ✅ Gestion couleurs centralisée (#c07a6a pour rouge, etc.)
- ✅ Gestion valeurs nulles ("---" si inactif)

**Décision** : **AJOUTER à v4.3** (amélioration architecture)

---

### 3. Annotations de Type améliorées ✅

**Fichier** : `core/tracking/tracker.py` (ligne 35)

**Changement** :
```python
# v4.3
moteur,  # Pas de type

# v4.4
moteur: Optional[MoteurCoupole|MoteurSimule],  # Type union Python 3.10+
```

**Avantages** :
- ✅ Meilleure complétion IDE
- ✅ Documentation explicite (moteur réel ou simulé)
- ✅ Détection erreurs type statique

**Décision** : **AJOUTER à v4.3** (clarté code)

---

### 4. Extraction Méthode _calculate_current_coords() ✅

**Fichier** : `core/tracking/tracker.py` (lignes 128-146 en v4.4)

**Changement** :
- v4.3 : Logique calcul coordonnées embarquée dans `_calculate_target_position()`
- v4.4 : Extraite dans méthode dédiée

**Avantages** :
- ✅ Séparation responsabilités (calcul coords vs calcul position cible)
- ✅ Réutilisabilité
- ✅ Facilite tests unitaires
- ✅ Gestion centralisée planètes vs étoiles fixes

**Décision** : **AJOUTER à v4.3** (refactoring qualité)

---

### 5. Nettoyage Code Mort (abaque_manager.py) ✅

**Fichier** : `core/tracking/abaque_manager.py`

**Supprimé en v4.4** :
- ~40 lignes de code commenté (tentative scipy RegularGridInterpolator)
- Variables inutilisées
- Imports scipy (non fonctionnels)

**Avantages** :
- ✅ Code plus lisible
- ✅ Retire confusion (quelle méthode est utilisée ?)
- ✅ Garde l'implémentation manuelle qui fonctionne

**Décision** : **APPLIQUER nettoyage à v4.3** (maintenance)

---

## 🔵 CHANGEMENTS NEUTRES - DÉCISION UTILISATEUR

### 1. Renommage DriftApp → DomeApp

**Fichiers** :
- `core/config/config_loader.py` : classe `DriftAppConfig` → `DomeAppConfig`
- `core/ui/main_screen.py` : classe `DriftApp` → `DomeApp`
- `main.py` : import correspondant

**Analyse** :
- **DriftApp** (v4.3) : Nom spécifique du projet
- **DomeApp** (v4.4) : Nom générique "contrôleur de coupole"

**Question** : Quel est le nom officiel du projet ?

**Décision** : **À DÉCIDER** (cohérence branding)

---

### 2. Suppression dome_control.py et predictive_anticipation.py

**Fichiers supprimés en v4.4** :
- `core/tracking/dome_control.py` (99 lignes)
- `core/tracking/predictive_anticipation.py` (400+ lignes)

**Analyse** :
- Code actuellement **non utilisé** dans les deux versions (commenté ligne 106-113 tracker.py)
- Fournit modes tracking alternatifs (relatif, anticipation)
- Documenté dans architecture

**Question** : Ces modes seront-ils utilisés à l'avenir ?

**Décision** : **À DÉCIDER** (conserver si utile futur)

---

### 3. Fichier documentation.txt

**Fichier** : `documentation.txt` (nouveau en v4.4)

**Contenu** : Documentation état projet novembre 2025

**Problème** : Documentation **OBSOLÈTE** (référence bugs corrigés depuis)

**v4.3 a** : `CONTEXT.md` et `CLAUDE.md` **à jour** (décembre 2025)

**Décision** : **IGNORER** (v4.3 mieux documenté)

---

## 🎯 PLAN D'ACTION RECOMMANDÉ

### Phase 1 : Préservation Base v4.3 ✅

**Base** : Version 4.3 (contient toutes les corrections critiques)

**À CONSERVER** :
- ✅ `ems22d_calibrated.py` (méthode incrémentale + logs + switch debug)
- ✅ `data/config.json` avec calibration_factor 0.010851
- ✅ `core/hardware/moteur_feedback.py` (boucle fermée)
- ✅ `core/tracking/tracker.py` avec initialisation feedback (lignes 18, 67-69)
- ✅ Variables anti-oscillation (lignes 142-149)
- ✅ `CONTEXT.md` et `CLAUDE.md` à jour

---

### Phase 2 : Cherry-Pick Améliorations v4.4

#### Étape 1 : Ajouter encoder_reader.py
```bash
# Copier le fichier (complément, pas remplacement)
cp Dome_v4_4/core/hardware/encoder_reader.py Dome_v4_3/core/hardware/
```

**Utilisation** : Peut être appelé depuis moteur_feedback.py pour lecture daemon sécurisée

---

#### Étape 2 : Ajouter TrackingViewModel
```bash
# Copier le nouveau module
cp Dome_v4_4/core/ui/viewmodel.py Dome_v4_3/core/ui/

# Modifier main_screen.py pour l'utiliser
# (à faire manuellement avec imports et intégration)
```

---

#### Étape 3 : Améliorer Type Annotations

**Fichier** : `core/tracking/tracker.py` ligne 35

**Changement** :
```python
# Avant
moteur,

# Après (v4.4)
moteur: Optional[MoteurCoupole|MoteurSimule],
```

---

#### Étape 4 : Extraire _calculate_current_coords()

**Fichier** : `core/tracking/tracker.py`

**Action** : Copier méthode lignes 128-146 de v4.4 et l'utiliser dans v4.3

---

#### Étape 5 : Nettoyer abaque_manager.py

**Fichier** : `core/tracking/abaque_manager.py`

**Action** : Retirer code commenté scipy (lignes ~162-197 en v4.3)

---

### Phase 3 : Décisions Branding

**Question 1** : Garder "DriftApp" ou passer à "DomeApp" ?

Si changement souhaité :
```bash
# Renommer partout (classes + imports)
# DriftAppConfig → DomeAppConfig
# DriftApp → DomeApp
```

**Question 2** : Conserver predictive_anticipation.py et dome_control.py ?

Si oui : Ne rien faire (déjà en v4.3)
Si non : Supprimer (comme v4.4)

---

## 📊 TABLEAU DE SYNTHÈSE

| Composant | v4.3 | v4.4 | Recommandation |
|-----------|------|------|----------------|
| **CRITIQUE** | | | |
| Daemon encodeur | Incrémental ✅ | Absolu ❌ | **GARDER v4.3** |
| Calibration factor | 0.010851 ✅ | 0.031354 ❌ | **GARDER v4.3** |
| Feedback boucle fermée | moteur_feedback.py ✅ | Supprimé ❌ | **GARDER v4.3** |
| **AMÉLIORATIONS** | | | |
| encoder_reader.py | Absent | Présent ✅ | **AJOUTER de v4.4** |
| TrackingViewModel | Absent | Présent ✅ | **AJOUTER de v4.4** |
| Type annotations | Partielles | Complètes ✅ | **AJOUTER de v4.4** |
| Code cleanup | - | Meilleur ✅ | **APPLIQUER v4.4** |
| **BRANDING** | | | |
| Nom classes | DriftApp | DomeApp | **À DÉCIDER** |

---

## ⚠️ RISQUES SI FUSION COMPLÈTE V4.4

**NE PAS fusionner v4.4 intégralement** car :

1. ❌ **Perte corrections critiques** (daemon incrémental, calibration_factor)
2. ❌ **Régression feedback** (système boucle fermée supprimé)
3. ❌ **Erreurs positionnement** (×2.89 sur angle affiché)
4. ❌ **Perte logs daemon** (rotation automatique, fichier structuré)
5. ❌ **Perte debug switch** (logs transitions détaillées)

**Résultat** : Retour à état novembre 2025 avec bugs connus

---

## ✅ RÉSULTAT ATTENDU APRÈS CHERRY-PICK

**Version hybride optimale** :

| Aspect | Source |
|--------|--------|
| Daemon encodeur (incrémental) | v4.3 ✅ |
| Calibration factor (0.010851) | v4.3 ✅ |
| Feedback boucle fermée | v4.3 ✅ |
| Logs daemon (rotation) | v4.3 ✅ |
| Switch debug | v4.3 ✅ |
| encoder_reader.py (centralisé) | v4.4 ✅ |
| TrackingViewModel (MVVM) | v4.4 ✅ |
| Type annotations | v4.4 ✅ |
| Code cleanup | v4.4 ✅ |

**Avantages** :
- ✅ Garde toutes les corrections critiques
- ✅ Ajoute améliorations architecturales
- ✅ Meilleure séparation responsabilités (encoder_reader + moteur_feedback)
- ✅ Code plus maintenable (type hints, ViewModel, cleanup)

---

**Version** : 1.0
**Date** : 6 Décembre 2025
**Conclusion** : **Base v4.3 + Cherry-pick sélectif v4.4**
