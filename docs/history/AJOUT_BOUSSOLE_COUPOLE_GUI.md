# 🧭 Ajout Boussole Coupole dans le Bandeau Unifié

**Date** : 7 Décembre 2025
**Objectif** : Visualisation graphique en temps réel de la position actuelle de la coupole et de sa position cible

---

## 📋 Résumé des Modifications

### 1. Nouveau Widget Boussole (`gui/widgets/dome_compass.py`)

**Caractéristiques** :
- Widget circulaire affichant la coupole vue de dessus
- **Arc rouge** : Position actuelle avec ouverture réaliste (70cm sur périmètre π×200cm ≈ 40°)
- **Flèche bleue** : Position cible (où la coupole devrait pointer)
- **Marqueurs cardinaux** : N, E, S, W
- **Triangle rouge** : Indicateur au centre de l'ouverture

**Dimensions** :
- 180×180 pixels
- Même taille que le timer circulaire

**Angles astronomiques** :
- 0° = Nord (haut)
- Sens horaire (90° = Est, 180° = Sud, 270° = Ouest)
- Conversion automatique vers coordonnées Kivy

### 2. Nouveau Layout du Bandeau Unifié (`gui/widgets/unified_banner.py`)

**Ancienne disposition (50/50)** :
```
┌─────────────────────┬─────────────────────┐
│  TIMER + MODE       │  CARTOUCHES (2 col) │
│       (50%)         │       (50%)         │
└─────────────────────┴─────────────────────┘
```

**Nouvelle disposition (35/30/35)** :
```
┌───────────────┬─────────────┬───────────────┐
│  TIMER + MODE │  BOUSSOLE   │  CARTOUCHES   │
│     (35%)     │  COUPOLE    │   (2 col)     │
│               │   (30%)     │     (35%)     │
└───────────────┴─────────────┴───────────────┘
```

**Sections** :
1. **Gauche (35%)** : Timer circulaire + MODE (réduit de 50% → 35%)
2. **Centre (30%)** : Boussole coupole + Label angle
3. **Droite (35%)** : Cartouches en 2 colonnes + CORRECTIONS (réduit de 50% → 35%)

### 3. Intégration dans l'Écran Principal (`gui/screens/main_screen.py`)

**Mise à jour automatique** :
- Méthode `_update_status()` appelée toutes les secondes pendant le tracking
- Récupère position actuelle depuis daemon encodeur via `MoteurCoupole.get_daemon_angle()`
- Récupère position cible depuis `status['position_cible']`
- Appelle `unified_banner.update_dome_positions(position_actuelle, position_cible)`

---

## 🎨 Détails Visuels

### Codes Couleur de la Boussole

| Élément | Couleur | Signification |
|---------|---------|---------------|
| **Cercle de fond** | Gris foncé (0.25, 0.27, 0.3) | Coupole vue de dessus |
| **Arc rouge épais** | Rouge vif (0.9, 0.2, 0.2) | Position actuelle (largeur 8px) |
| **Triangle rouge** | Rouge clair (1, 0.3, 0.3) | Indicateur centre ouverture |
| **Flèche bleue** | Bleu clair (0.3, 0.6, 1) | Ligne position cible |
| **Tête flèche bleue** | Bleu foncé (0.2, 0.5, 0.9) | Triangle direction cible |
| **Marqueurs cardinaux** | Gris (0.5, 0.5, 0.5, 0.8) | N, E, S, W |

### Ouverture de la Coupole

**Calcul de l'arc rouge** :
- Diamètre coupole : 200 cm
- Périmètre coupole : π × 200 cm = 628.3 cm
- Largeur ouverture : 70 cm
- Pourcentage : 70/628.3 = 11.14%
- Angle d'arc : 360° × 0.1114 = **40.1°**

L'arc rouge s'étend donc de **-20°** à **+20°** autour de la position actuelle (centre de l'arc = centre de l'ouverture), simulant visuellement la largeur réelle de la trappe.

---

## 🚀 Utilisation

### Lancement du GUI

```bash
cd /home/jp/PythonProject/Dome_v4_3
uv run main_gui.py
```

### Vérification Visuelle

1. **Au démarrage** (sans tracking actif) :
   - Boussole affiche position 0° (arc rouge vers le haut)
   - Flèche bleue également à 0°
   - Label sous la boussole : "0.0°"

2. **Pendant le tracking** :
   - **Arc rouge** : Suit la position réelle de la coupole (lecture encodeur)
   - **Flèche bleue** : Pointe vers la position calculée nécessaire pour l'objet
   - **Label angle** : Affiche la position actuelle en degrés

3. **En cas de désynchronisation** :
   - Si arc rouge ≠ flèche bleue → correction nécessaire
   - Le système lancera automatiquement une correction
   - Après correction : arc rouge se rapproche de la flèche bleue

---

## 🔍 Surveillance en Temps Réel

### Scénarios d'Utilisation

**Tracking M13 (23h30 → Az 45°)** :
1. Démarrer tracking → Flèche bleue pointe vers 45° (Est)
2. Coupole tourne → Arc rouge se déplace progressivement
3. Arc rouge atteint 45° → Alignement parfait
4. Objet dérive → Flèche bleue bouge lentement vers 46°
5. Système détecte écart → Correction automatique
6. Arc rouge suit la flèche bleue

**Passage au méridien** :
- Flèche bleue traverse le Nord (0°/360°)
- Arc rouge suit en continu
- Pas de saut visuel (gestion wrapping 0°/360°)

**Calibration encodeur** :
- Coupole passe le switch à 45°
- Arc rouge se recale instantanément sur 45°
- Flèche bleue reste sur position cible calculée

---

## 📊 Avantages de la Boussole

✅ **Visualisation intuitive** : Comprendre immédiatement où pointe la coupole
✅ **Diagnostic rapide** : Voir si coupole suit correctement l'objet
✅ **Ouverture réaliste** : Arc de 40° simule la vraie largeur de la trappe (70cm)
✅ **Double information** : Position actuelle (rouge) + cible (bleu)
✅ **Temps réel** : Mise à jour synchronisée avec le tracking (1 Hz)
✅ **Repères cardinaux** : Orientation immédiate (N/E/S/W)

---

## 🐛 Dépannage

### La boussole ne se met pas à jour

**Causes possibles** :
1. Tracking non démarré → La boussole est mise à jour uniquement pendant le tracking
2. Daemon encodeur inactif → Arc rouge reste à 0°, vérifier `/dev/shm/ems22_position.json`

**Solution** :
```bash
# Vérifier démon encodeur
sudo systemctl status ems22d.service

# Vérifier JSON temps réel
watch -n 0.2 cat /dev/shm/ems22_position.json

# Redémarrer si nécessaire
sudo systemctl restart ems22d.service
```

### Arc rouge et flèche bleue confondus

**C'est normal** si :
- Tracking vient de démarrer ET correction vient d'être appliquée
- Objet à faible dérive (étoile proche équateur céleste)

**Vérifier** :
- Si après 60s ils divergent → dérive normale de l'objet
- Si restent alignés longtemps → vérifier que l'objet bouge (`Az` et `Alt` doivent changer dans les cartouches)

### Flèche bleue fait des sauts

**Causes** :
- Mode CONTINUOUS activé (haute altitude > 75°) → corrections fréquentes normales
- Objet près du zénith → Azimut change rapidement

**Comportement normal** :
- En mode CONTINUOUS, position cible recalculée toutes les 5s
- Flèche bleue ajuste sa direction en conséquence

---

## 📝 Code Technique

### Méthode de Mise à Jour (main_screen.py:486-490)

```python
# Mettre à jour la boussole coupole
self.unified_banner.update_dome_positions(
    position_actuelle=position if position is not None else 0,
    position_cible=float(status['position_cible'])
)
```

### Dessin de l'Ouverture (dome_compass.py:100-128)

```python
def _draw_dome_opening(self, cx, cy, radius, angle_center):
    # Largeur de l'ouverture : 70cm sur périmètre π×200cm
    # Angle = (70 / (π × 200)) × 360° ≈ 40.1°
    import math
    opening_angle = (70.0 / (math.pi * 200.0)) * 360.0  # ≈ 40.1°
    half_opening = opening_angle / 2

    # Angles de début et fin (en degrés astro)
    start_angle_astro = angle_center - half_opening
    end_angle_astro = angle_center + half_opening

    # Conversion en angles Kivy (inverser l'ordre pour sens anti-horaire Kivy)
    start_angle_kivy = 90 - end_angle_astro
    end_angle_kivy = 90 - start_angle_astro

    # Dessiner l'arc rouge
    Color(0.9, 0.2, 0.2, 1)  # Rouge vif
    Line(
        circle=(cx, cy, radius - 2, start_angle_kivy, end_angle_kivy),
        width=4
    )
```

### Conversion Angles Astronomiques → Kivy

```python
# Angles astronomiques : 0° = Nord (haut), sens horaire
# Angles Kivy : 0° = Est (droite), sens anti-horaire
angle_kivy = 90 - angle_astro
```

---

## 📋 Fichiers Modifiés

1. ✅ **gui/widgets/dome_compass.py** - Nouveau widget boussole (223 lignes)
2. ✅ **gui/widgets/unified_banner.py** - Layout modifié + méthode `update_dome_positions()`
3. ✅ **gui/screens/main_screen.py** - Ajout appel mise à jour boussole dans `_update_status()`

---

## 🎯 Prochaines Améliorations Possibles

- [ ] Afficher l'écart angulaire (Δ) entre position actuelle et cible
- [ ] Colorer l'arc rouge selon l'écart (vert si < 1°, orange si 1-3°, rouge si > 3°)
- [ ] Animation lors des corrections (transition fluide de l'arc)
- [ ] Indicateur de sens de rotation (CW/CCW)

---

*Documentation créée le 7 décembre 2025*
