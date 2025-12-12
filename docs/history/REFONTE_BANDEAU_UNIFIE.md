# 🎨 Refonte du Bandeau Unifié - Décembre 2025

**Date** : 7 Décembre 2025
**Objectif** : Optimiser l'affichage et regrouper les informations liées à la coupole

---

## 📋 Modifications Appliquées

### 1. ✅ Correction Position Boussole

**Problème** : L'arc rouge restait bloqué à 0° alors que COUPOLE affichait 33.9°

**Cause** : Utilisation de `get_daemon_angle()` (encodeur) au lieu de `session.position_relative`

**Solution** :
```python
# main_screen.py:489-491
self.unified_banner.update_dome_positions(
    position_actuelle=float(session.position_relative % 360),  # Position calculée
    position_cible=float(status['position_cible'])
)
```

### 2. ✅ Regroupement Informations Coupole au Centre

**Avant** :
- COUPOLE et POSITION dispersés dans colonnes droites
- CORRECTIONS en bas de la section droite

**Après** :
- Boussole graphique au centre
- COUPOLE et POSITION alignés sous la boussole
- CORRECTIONS sous COUPOLE/POSITION (même hauteur que MODE)

### 3. ✅ Suppression Cartouche ENCODEUR

**Raison** : Déjà affiché en haut à droite dans le cartouche compact `ENC=xx.x°`

### 4. ✅ Séparation AZ/ALT en Deux Cartouches

**Avant** : Un seul cartouche `AZ/ALT: 45.2° / 30.1°`

**Après** :
- Cartouche `AZIMUT: 45.2°`
- Cartouche `ALTITUDE: 30.1°`

Plus lisible et cohérent avec le reste du design.

### 5. ✅ Uniformisation Hauteurs Cartouches

Tous les cartouches MODE, COUPOLE, POSITION, CORRECTIONS ont maintenant la même hauteur pour un design harmonieux.

---

## 🎨 Nouveau Layout

```
┌────────────────────────────────────────────────────────────────┐
│                    PRODUCTION | RPi 5                          │
├────────────────────────────────────────────────────────────────┤
│  Objet: [M13...........]  RA/DEC: 16h 41m...  ENC=45.2° ✓     │
├────────────────────────────────────────────────────────────────┤
│  [DÉMARRER]    [STOPPER]    [CONFIGURER]                      │
├────────────────────────────────────────────────────────────────┤
│ ┌─────────────┬──────────────────┬───────────────────────┐    │
│ │   GAUCHE    │     CENTRE       │       DROITE          │    │
│ │    (35%)    │      (30%)       │       (35%)           │    │
│ ├─────────────┼──────────────────┼───────────────────────┤    │
│ │             │                  │                       │    │
│ │   TIMER     │    BOUSSOLE      │  SEUIL   │ INTERVALLE│    │
│ │    [◷]      │      [🧭]        │  0.50°   │    60s    │    │
│ │             │                  │──────────┼───────────│    │
│ │             │  ┌──────┬──────┐ │ AZIMUT   │ ALTITUDE  │    │
│ │    MODE     │  │COUPO.│POSIT.│ │  45.2°   │   30.1°   │    │
│ │   NORMAL    │  │ 34°  │ 34°  │ ├──────────┴───────────┤    │
│ │             │  └──────┴──────┘ │    CORRECTIONS        │    │
│ │             │                  │    3 (1.2° total)     │    │
│ └─────────────┴──────────────────┴───────────────────────┘    │
│                                                                │
│ LOGS                                                           │
└────────────────────────────────────────────────────────────────┘
```

---

## 📊 Comparaison Avant/Après

| Aspect | Avant | Après |
|--------|-------|-------|
| **Boussole position** | Bloquée à 0° | Suit `session.position_relative` ✓ |
| **COUPOLE/POSITION** | Colonne droite | Sous boussole (centre) |
| **CORRECTIONS** | Bas droite | Sous COUPOLE/POSITION (centre) |
| **ENCODEUR** | Colonne droite | Supprimé (déjà en haut) |
| **AZ/ALT** | Un seul cartouche | Deux cartouches séparés |
| **Hauteur cartouches** | Variables | Uniformisée |

---

## 🔧 Détails Techniques

### Section Gauche (35%)

**Contenu** :
- Timer circulaire (75% hauteur)
- MODE (25% hauteur)

**Inchangé par rapport à la version précédente.**

### Section Centre (30%)

**Structure verticale** :
```
75% : Boussole (DomeCompass widget)
25% : COUPOLE + POSITION (en ligne)
```

**Cartouches COUPOLE et POSITION** :
- Même style que MODE (vertical, titre + valeur)
- Taille de police réduite (9sp titre, 12sp valeur)
- Couleurs distinctes (vert pour COUPOLE, bleu pour POSITION)
- Affichés côte à côte sous la boussole

### Section Droite (35%)

**Structure verticale** :
```
33% : SEUIL | INTERVALLE (en ligne)
33% : AZIMUT | ALTITUDE (en ligne)
34% : CORRECTIONS (toute la largeur)
```

**Ligne 1** : SEUIL et INTERVALLE côte à côte
**Ligne 2** : AZIMUT et ALTITUDE côte à côte (nouveaux cartouches séparés)
**Ligne 3** : CORRECTIONS sur toute la largeur

---

## 📝 Fichiers Modifiés

### 1. `gui/widgets/unified_banner.py`

**Méthodes ajoutées** :
- `_create_azimut_cartouche()` - Cartouche AZIMUT seul
- `_create_altitude_cartouche()` - Cartouche ALTITUDE seul
- `_create_corrections_cartouche_center()` - CORRECTIONS au centre

**Méthodes modifiées** :
- `_create_center_section()` - Ajout COUPOLE/POSITION/CORRECTIONS
- `_create_right_section()` - Suppression ENCODEUR/COUPOLE/POSITION, séparation AZ/ALT
- `update_status()` - Utilise nouveaux labels (`azimut_label`, `altitude_label`, etc.)

**Méthodes supprimées** :
- `_create_azalt_cartouche()` (remplacée par azimut + altitude)
- `_create_encodeur_cartouche()` (encodeur affiché en haut)
- `_create_coupole_cartouche()` (déplacée au centre)
- `_create_position_cartouche()` (déplacée au centre)

### 2. `gui/screens/main_screen.py`

**Ligne 489-491** - Correction mise à jour boussole :
```python
self.unified_banner.update_dome_positions(
    position_actuelle=float(session.position_relative % 360),  # ← CORRIGÉ
    position_cible=float(status['position_cible'])
)
```

### 3. `gui/widgets/dome_compass.py`

**Ligne 119-123** - Correction angles pour Line.circle() :
```python
# Line.circle() : 0°/360° = haut (12h), sens horaire
start_angle_kivy = start_angle_astro if start_angle_astro >= 0 else start_angle_astro + 360
end_angle_kivy = end_angle_astro if end_angle_astro >= 0 else end_angle_astro + 360
```

---

## 🎯 Avantages de la Refonte

✅ **Regroupement logique** : Toutes les infos coupole au centre (boussole, angles, corrections)

✅ **Lecture intuitive** : Arc rouge (actuel) et flèche bleue (cible) alignés visuellement

✅ **Pas de doublon** : ENCODEUR supprimé du bandeau (déjà en haut)

✅ **Meilleure lisibilité** : AZ et ALT séparés, valeurs plus grandes

✅ **Design uniforme** : Tous les cartouches ont la même hauteur

✅ **Espace optimisé** : Suppression espaces inutiles, meilleure densité d'information

---

## 🐛 Corrections Futures Possibles

- [ ] Ajouter icônes pour AZIMUT et ALTITUDE (boussole, montagne)
- [ ] Animer la transition de l'arc rouge lors des corrections
- [ ] Afficher l'écart (Δ) entre COUPOLE et POSITION avec code couleur

---

*Documentation créée le 7 décembre 2025*
