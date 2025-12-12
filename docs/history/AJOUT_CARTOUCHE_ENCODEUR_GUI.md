# 🎯 Ajout Cartouche Encodeur Compact dans le GUI

**Date** : 7 Décembre 2025
**Objectif** : Surveiller visuellement la calibration automatique de l'encodeur avec indicateur compact

---

## 📋 Résumé des Modifications

### 1. Démon Encodeur (`ems22d_calibrated.py`)

**Ajouts** :
- Flag `self.calibrated` initialisé à `False` au démarrage
- Passe à `True` lors du premier passage sur le switch (calibration à 45°)
- Publié dans le JSON `/dev/shm/ems22_position.json`

**Fichier JSON enrichi** :
```json
{
  "ts": 1733600234.567,
  "angle": 45.2,
  "raw": 512,
  "status": "OK",
  "calibrated": true
}
```

### 2. Widget GUI Compact (`gui/widgets/encoder_cartouche.py`)

**Caractéristiques** :
- Taille compacte : 110×40 pixels (environ moitié d'un cartouche standard)
- Format ultra-simple : **"ENC=xx.x°"** ou **"ENC=N/A"**
- Couleur de fond uniquement (pas de texte de statut)
- Mise à jour automatique toutes les 500ms

**Codes couleur** :
- ⚪ **Gris** : `ENC=N/A` - Démon inactif ou encodeur non trouvé
- 🟠 **Orange** : `ENC=123.5°` - Non calibré (avant passage switch)
- 🟢 **Vert** : `ENC=45.2°` - Calibré (après passage switch)
- 🔴 **Rouge** : `ENC=ERR` - Erreur démon

### 3. Intégration dans l'Interface (`gui/screens/main_screen.py`)

**Position** : Sur la **même ligne** que le champ Objet, **calé à droite**

```
┌────────────────────────────────────────────────────────┐
│ Objet: [Input M13................] RA/DEC: ... ENC=45.2°│
│                                                 ↑ Vert  │
├────────────────────────────────────────────────────────┤
│ [DÉMARRER]  [STOPPER]  [CONFIGURER]                   │
│ BANDEAU UNIFIÉ (Timer + Statuts)                      │
└────────────────────────────────────────────────────────┘
```

**Avantages de cette position** :
- ✅ Économise de l'espace vertical
- ✅ Toujours visible en haut de l'écran
- ✅ Proche du champ d'entrée pour cohérence visuelle
- ✅ Ne masque aucune information importante

---

## 🚀 Test et Validation

### 1. Redémarrer le Démon

```bash
# Copier le nouveau fichier démon
sudo cp /home/slenk/Dome_v4_5/ems22d_calibrated.py /home/slenk/Dome_v4_5/

# Redémarrer le service
sudo systemctl restart ems22d.service

# Vérifier le JSON
cat /dev/shm/ems22_position.json
# Devrait contenir : "calibrated": false (au démarrage)
```

### 2. Lancer l'Interface GUI

```bash
cd /home/slenk/Dome_v4_5
uv run main_gui.py
```

### 3. Vérifier l'Affichage

**Avant calibration** :
```
┌────────────────────────────────────┐
│ Objet: [...]  RA/DEC: ...  ENC=123.5°│
│                           (orange)   │
└────────────────────────────────────┘
```

**Après passage switch à 45°** :
```
┌────────────────────────────────────┐
│ Objet: [...]  RA/DEC: ...  ENC=45.0° │
│                           (vert)     │
└────────────────────────────────────┘
```

**Démon inactif** :
```
┌────────────────────────────────────┐
│ Objet: [...]  RA/DEC: ...  ENC=N/A   │
│                           (gris)     │
└────────────────────────────────────┘
```

---

## 🎨 Détails Visuels

### Taille et Proportions

- **Largeur** : 110 pixels
- **Hauteur** : 40 pixels
- **Référence** : ~50% de la hauteur d'un cartouche du bandeau unifié
- **Bordure** : Rayon de 8 pixels (coins arrondis)
- **Police** : 13sp, bold, centré

### Couleurs de Fond Exactes

| État | RGB | Hex | Apparence |
|------|-----|-----|-----------|
| **Inactif** | (0.3, 0.3, 0.3) | #4D4D4D | Gris neutre |
| **Non calibré** | (0.4, 0.3, 0.15) | #664D26 | Orange foncé |
| **Calibré** | (0.15, 0.35, 0.2) | #265933 | Vert foncé |
| **Erreur** | (0.4, 0.15, 0.15) | #662626 | Rouge foncé |

---

## 🔍 Surveillance en Temps Réel

### Test de Calibration

1. **Lancer le GUI**
2. **Observer** : Cartouche affiche angle courant (ex: `ENC=123.5°`) en orange
3. **Faire tourner** la coupole vers 45° azimut
4. **Au passage switch** :
   - Logs démon : `🔄 Microswitch activé → recalage à 45°`
   - Cartouche : `ENC=45.0°` (vert)
5. **Continuer à tourner** : Angle suit en temps réel (ex: `ENC=46.2°`)
6. **Statut reste vert** après calibration

### Logs Démon

```bash
tail -f /home/slenk/Dome_v4_5/logs/ems22d.log
```

**Logs attendus** :
```
[INFO] 🔄 Microswitch activé → recalage à 45°
[INFO]    → total_counts recalé à 4147
[INFO]    → angle affiché : 45°
```

### JSON Encodeur

```bash
watch -n 0.2 cat /dev/shm/ems22_position.json
```

**Évolution** :
```json
// Avant calibration
{"angle": 123.5, "calibrated": false}

// Passage switch
{"angle": 45.0, "calibrated": true}

// Après calibration
{"angle": 46.2, "calibrated": true}
```

---

## 🐛 Dépannage

### Cartouche affiche "ENC=N/A" (gris)

**Causes** :
1. Démon encodeur non lancé
2. Fichier `/dev/shm/ems22_position.json` absent

**Solution** :
```bash
# Vérifier démon
sudo systemctl status ems22d.service

# Si inactif
sudo systemctl start ems22d.service

# Vérifier JSON
cat /dev/shm/ems22_position.json
```

### Couleur reste orange après passage switch

**Diagnostic** :
```bash
# 1. Vérifier que le switch a bien été détecté
tail -50 logs/ems22d.log | grep "Microswitch"

# 2. Vérifier le flag dans le JSON
cat /dev/shm/ems22_position.json | grep calibrated
# Devrait afficher : "calibrated": true

# 3. Tester le switch directement
sudo python3 tests_sur_site/test_switch_direct.py
```

### Angle ne change pas

**Vérifications** :
```bash
# 1. Vérifier que le JSON se met à jour
watch -n 0.2 cat /dev/shm/ems22_position.json
# L'angle doit changer quand on bouge la coupole

# 2. Comparer avec boussole direct SPI
python tests_sur_site/ems22a_ring_gauge4_V2.py
```

---

## 📊 Comparaison Avant/Après

| Aspect | Avant | Après |
|--------|-------|-------|
| **Position** | Ligne dédiée sous boutons | Même ligne que champ Objet |
| **Taille** | 240×50px (large) | 110×40px (compact) |
| **Affichage** | "ENCODEUR / 45.2° / ✓ INITIALISÉ" | "ENC=45.2°" |
| **Statut texte** | Oui (séparé) | Non (couleur de fond) |
| **Espace vertical** | -50px | +0px (aucun espace utilisé) |
| **Lisibilité** | Très détaillé | Essentiel uniquement |

---

## 🎯 Avantages de la Version Compacte

✅ **Gain d'espace** : Économise 50 pixels de hauteur
✅ **Intégration naturelle** : S'intègre sur la ligne existante
✅ **Lecture rapide** : Format `ENC=xx.x°` immédiatement compréhensible
✅ **Couleur intuitive** : Gris/Orange/Vert = état immédiat
✅ **Toujours visible** : En haut de l'écran, jamais scrollé
✅ **Pas de distraction** : Compact mais informatif

---

## 📝 Notes de Développement

### Code Simplifié

Le widget hérite maintenant de `Label` au lieu de `BoxLayout`, ce qui simplifie considérablement le code :

**Avant** : 153 lignes (3 labels dans un layout)
**Après** : 102 lignes (1 label avec fond coloré)

### Mise à Jour Automatique

Le cartouche se met à jour **sans aucune intervention** :
- Timer Kivy : toutes les 500ms
- Lecture JSON encodeur
- Mise à jour texte + couleur

---

*Documentation mise à jour le 7 décembre 2025 - Version compacte*
