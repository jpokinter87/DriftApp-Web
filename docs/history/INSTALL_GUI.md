# Installation Interface Graphique (Kivy)

Guide rapide pour installer et tester l'interface graphique tactile.

## ⚠️ MISES À JOUR

### Version 3.4 - 7 décembre 2025 ⭐ ACTUELLE

**TIMER PARFAIT 360° + RÉINITIALISATION INTERVALLE**

✅ **Timer position 12h** : Arc démarre exactement à 12h avec angle 360° (pattern: 90°→15h, 180°→18h, 270°→21h, 360°→24h=12h)
✅ **Timer réinitialisé** : Quand l'intervalle change dans config, le timer se réinitialise immédiatement à la nouvelle valeur
✅ **Arc proportionnel** : L'arc parcourt toujours 100% du cercle quelle que soit la valeur de l'intervalle (15s, 30s, 60s...)
✅ **Focus persistant** : Le focus revient sur le champ Objet après validation du popup config

### Version 3.3 - 7 décembre 2025

**CORRECTIONS TIMER 270° + FOCUS VIA CALLBACK** (timer à 9h au lieu de 12h)

✅ **Focus via callback** : Le focus est restauré dans le callback de validation (popup se ferme correctement)
✅ **Popup fonctionnel** : Le popup se ferme normalement après validation ou annulation
❌ **Timer à 270°** : Arc démarrait à 9h au lieu de 12h - angle encore incorrect

### Version 3.2 - 7 décembre 2025

**PERFECTION TIMER + FOCUS PERSISTANT** (PROBLÈMES : popup bloqué, timer à 18h)

❌ **Timer à 180°** : Arc démarrait à 18h au lieu de 12h - angle incorrect
❌ **Focus via on_dismiss** : Le popup ne se fermait plus - événement bloquant
✅ **Intention correcte** : Focus persistant sur champ Objet après config

### Version 3.1 - 7 décembre 2025

**CORRECTIONS FINALES : ANGLE TIMER + FOCUS AUTOMATIQUE**

✅ **Timer corrigé** : Arc démarre à 90° (tentative, mais démarrait encore à 15h au lieu de 12h)
✅ **Focus popup config** : Utilise événement `on_open` pour focus fiable sur premier champ
✅ **Focus au démarrage** : Le champ Objet reçoit automatiquement le focus au lancement de l'application
✅ **Expérience clavier complète** : L'application peut être utilisée entièrement au clavier dès le démarrage

### Version 3.0 - 7 décembre 2025

**LAYOUT 50/50 : TIMER GAUCHE + CARTOUCHES 2 COLONNES DROITE**

✅ **Bandeau unifié** : UnifiedBanner fusionne InfoBanner et StatusBanner en un seul widget
✅ **Layout 50/50** : Timer+MODE à gauche (50%), tous les cartouches à droite (50%)
✅ **Hauteur optimale** : 240px pour lisibilité maximale du timer et des cartouches
✅ **Timer agrandi** : Occupe 75% de la hauteur gauche, police 24sp, rayon max (marge 2px)
✅ **Arc corrigé** : Timer démarre à 90° (12h) avec correction +45° pour bug Kivy, se vide dans le sens anti-horaire
✅ **2 colonnes droite** : (SEUIL/AZ/ALT/ENCOD.) et (INTERVALLE/COUPOLE/POSITION)
✅ **CORRECTIONS en bas** : Cartouche sur toute la largeur sous les 2 colonnes avec espacement
✅ **MODE sous timer** : Cartouche MODE en dessous du timer à gauche (25% hauteur)
✅ **MODE CONTINU rouge vif** : Couleur (0.9, 0.15, 0.15, 0.9) pour attirer l'attention de l'utilisateur
✅ **Layout cartouches horizontal** : Label+icône à gauche (50%), valeur à droite (50%)
✅ **Alignement texte** : Labels justifiés à gauche, valeurs justifiées à droite
✅ **Auto-focus popup config** : Focus automatique sur le premier champ pour utilisation clavier seul

### Version 2.9 - 7 décembre 2025

**LAYOUT OPTIMISÉ 70/30 + TIMER PLEINE HAUTEUR** (OBSOLÈTE - superposition cartouches)

✅ **Timer pleine hauteur** : Occupe 70% de l'écran sur toute la hauteur pour maximum de lisibilité
✅ **Arc démarre en haut** : Timer commence à 90° (12h) et progresse dans le sens anti-horaire
✅ **Cartouches empilés** : Tous les cartouches (SEUIL, INTERVALLE, AZ/ALT, COUPOLE, ENCODEUR, MODE, POSITION, CORRECTIONS) en colonne verticale à droite (30%)
✅ **Cartouches compacts** : Police 7sp/9sp, hauteur 16px, layout horizontal label|valeur
✅ **Espacement optimisé** : Spacer 70% pour alignement parfait timer/cartouches

### Version 2.8 - 7 décembre 2025

**OPTIMISATION ESPACE + TIMER ADAPTATIF + NAVIGATION CLAVIER**

✅ **Timer agrandi** : Occupe 45% de l'espace pour meilleure lisibilité, adaptatif selon intervalle (15s=360°)
✅ **Header compact** : Police réduite (13sp) et hauteur 30px pour libérer de l'espace
✅ **Zone RA/DEC intégrée** : Affichage compact à droite du champ objet (plus de bandeau)
✅ **Suppression TEMPS** : Cartouche redondant avec timer circulaire supprimé
✅ **Navigation clavier** : Tab pour naviguer entre champs config, Entrée pour valider
✅ **Layout optimisé** : Maximisation de l'espace logs, interface épurée

### Version 2.7 - 7 décembre 2025

**AMBIANCE OBSERVATOIRE + TIMER CIRCULAIRE + MODE DYNAMIQUE**

✅ **Couleurs atténuées** : Boutons en tons foncés (vert, rouge, bleu) pour préserver la vision nocturne
✅ **Timer circulaire** : Widget graphique avec arc de progression et temps au centre
✅ **Bandeau simplifié** : Suppression de "MÉTHODE", focus sur SEUIL et INTERVALLE à droite
✅ **Mode dynamique** : Fond du cartouche MODE change de couleur (vert=NORMAL, orange=CRITICAL, rouge=CONTINU)
✅ **Layout optimisé** : Timer à gauche, config à droite, espace harmonieux

### Version 2.6 - 7 décembre 2025

**ICÔNES PNG + LOGS TEMPS RÉEL FIXÉS**

✅ **Icônes PNG réelles** : play.png, stop.png, settings.png (plus de symboles unicode)
✅ **Widget IconButton** : Bouton personnalisé avec Image PNG + effets complets
✅ **Logs temps réel** : texture_update() forcée + debug console
✅ **Print debug** : Tous les logs s'affichent aussi en console pour vérification

### Version 2.5 - 7 décembre 2025

**INTERFACE GRAPHIQUE COMPLÈTE & FONCTIONNELLE**

✅ **Logs de tracking visibles** : Auto-scroll vers le bas, tous les logs s'affichent correctement
✅ **Popup configuration parfait** : Titre bien espacé, boutons avec effets hover/press
✅ **Icônes sur boutons** : ▶ DÉMARRER, ■ STOPPER, ⚙ CONFIGURER
✅ **Bandeau info graphique** : 3 sections colorées (Méthode, Seuil, Intervalle)
✅ **Design moderne complet** : Effets hover, press, ombres, bordures arrondies
✅ **Réservé texte pour logs** : Seule la zone de logs utilise du texte

### Version 2.4 - 7 décembre 2025

**DESIGN MODERNE & RÉACTIF**

✅ **Boutons interactifs** : Effets hover (+20% luminosité) + press (anim 95%)
✅ **Bordures très arrondies** : radius=18 pour boutons, 12-15 pour zones
✅ **Ombre portée** : Shadow subtile sur tous les boutons
✅ **Input moderne** : Fond arrondi radius=12, curseur vert
✅ **Animations fluides** : 50ms pour feedback immédiat

### Versions précédentes

- **v2.2** : Popup config + bandeau objet + touche Entrée
- **v2.1** : Tracking réel fonctionnel
- **v2.0** : Interface fidèle TUI
- **v1.0** : Version initiale (obsolète)

## Installation en 3 étapes

### 1. Installer Kivy

**Méthode 1 : Installation automatique (recommandée)**
```bash
cd /home/jp/PythonProject/Dome_v4_3

# Avec uv (installe automatiquement les dépendances GUI)
uv sync --extra gui

# OU avec pip
pip install -e ".[gui]"
```

**Méthode 2 : Installation manuelle**
```bash
# Si vous préférez installer manuellement
uv pip install "kivy[base]>=2.3.0"

# OU avec pip
pip install "kivy[base]>=2.3.0"
```

### 2. Tester l'interface

```bash
# Lancer l'interface graphique
uv run main_gui.py

# OU
python main_gui.py
```

### 3. Vérifier le daemon encodeur (nécessaire pour la boussole)

```bash
# Le daemon doit tourner pour afficher la position
cat /dev/shm/ems22_position.json

# Si vide, démarrer le daemon :
sudo python3 ems22d_calibrated.py &
```

## Premiers pas & Test des effets

### Test des boutons modernes avec icônes PNG
1. **Icônes** : Vérifiez que les icônes PNG s'affichent (▶ play, ■ stop, ⚙ settings)
2. **Survol** : Passez la souris sur "DÉMARRER" → couleur s'éclaircit (+20%)
3. **Clic** : Cliquez sur le bouton → réduction 95% + anim fluide
4. **Release** : Relâchez → retour à la taille normale

### Test du popup configuration
1. Cliquez **⚙ CONFIGURER** (ou appuyez sur **c**)
2. **Focus automatique** : Le curseur est déjà dans le champ SEUIL, prêt à taper
3. Tapez une valeur, appuyez sur **Tab** → passe au champ INTERVALLE
4. Appuyez sur **Entrée** → valide directement (pas besoin de cliquer Valider)
5. Popup se ferme → bandeau graphique se met à jour

### Test du bandeau unifié (layout 50/50)
1. Observez le bandeau sous les boutons
2. **Partie GAUCHE (50%)** :
   - **TIMER circulaire** (haut) : affiche le compte à rebours avec arc de progression
   - **Arc démarre exactement à 12h** (position haute) et se vide dans le sens anti-horaire
   - Arc tourne comme une horloge inversée (anti-horaire)
   - Couleur change selon progression : vert (>50%), orange (>25%), rouge (<25%)
   - **MODE** (bas) : affiche NORMAL/CRITICAL/CONTINU avec fond coloré
3. **Partie DROITE (50%)** :
   - **Colonne 1** : SEUIL, AZ/ALT, ENCODEUR
   - **Colonne 2** : INTERVALLE, COUPOLE, POSITION
   - **CORRECTIONS** : en bas sur toute la largeur
4. Changez la config → SEUIL et INTERVALLE se mettent à jour dynamiquement
5. Lors du tracking, tous les cartouches s'actualisent en temps réel

### Test du focus automatique et persistant
1. Lancez l'application : `uv run main_gui.py`
2. **Le curseur est déjà dans le champ Objet** - pas besoin de cliquer
3. Tapez directement "M13" et appuyez sur **Entrée** → recherche l'objet
4. Appuyez sur **c** pour ouvrir la configuration → popup s'ouvre avec focus sur SEUIL
5. Modifiez les valeurs, validez avec **Entrée** → popup se ferme
6. **Le focus revient automatiquement sur le champ Objet** - vous pouvez retaper directement
7. **Expérience clavier 100%** : Aucun clic souris nécessaire, navigation fluide

### Test du timer et changement d'intervalle
1. Au démarrage, le timer affiche **60s** (valeur par défaut) et l'arc fait le tour complet
2. **Vérifiez position 12h** : L'arc doit démarrer exactement en haut (comme 12h sur une horloge)
3. Appuyez sur **c** → changez INTERVALLE à **30s** → validez
4. **Timer se réinitialise** : Le timer affiche maintenant **30s** et l'arc fait toujours le tour complet (100%)
5. Changez à nouveau l'intervalle à **15s** → timer affiche **15s** avec arc complet
6. **Proportionnalité** : Quel que soit l'intervalle (15s, 30s, 60s), l'arc parcourt 100% du cercle

### Test des logs de tracking
1. Dans le champ "Objet" (focus automatique au démarrage)
2. Tapez "M101" et appuyez sur **Entrée**
3. Bandeau d'info objet apparaît en haut (RA, DEC)
4. **Logs s'affichent en bas** : "Objet trouvé : M101", etc.
5. Auto-scroll : Les nouveaux logs apparaissent automatiquement

## Retour à l'interface TUI

L'interface Textual (terminal) reste **inchangée** :

```bash
python main.py  # Interface TUI (comme avant)
```

## Problèmes courants

### Kivy ne démarre pas

```bash
# Vérifier l'installation
python -c "import kivy; print(kivy.__version__)"

# Réinstaller si nécessaire
uv pip install --force-reinstall "kivy[base]"
```

### La boussole ne bouge pas

```bash
# Vérifier que le daemon tourne
ps aux | grep ems22d

# Vérifier le fichier JSON
cat /dev/shm/ems22_position.json
# Devrait afficher : {"ts": ..., "angle": ..., "raw": ..., "status": "OK"}

# Si vide ou absent, démarrer le daemon
sudo python3 ems22d_calibrated.py &
```

### Écran noir / interface vide

```bash
# Mode debug
export KIVY_LOG_LEVEL=debug
python main_gui.py

# Vérifier les logs dans la console
```

## Ajout permanent à pyproject.toml (optionnel)

Si vous voulez rendre Kivy permanent dans les dépendances :

```bash
# Éditer pyproject.toml et ajouter à la section dependencies :
"kivy[base]>=2.3.0",

# Puis synchroniser
uv sync
```

## Développement futur

Voir `gui/README.md` pour :
- Structure des fichiers
- Ajout de nouveaux écrans
- Création de widgets personnalisés
- Configuration écran tactile avancée