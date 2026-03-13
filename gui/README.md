# Interface Graphique Kivy pour DriftApp

Interface tactile moderne pour Raspberry Pi 5 avec écran tactile.

## Architecture

Cette interface GUI est **complètement indépendante** de l'interface Textual (TUI) :

- **TUI (Textual)** : `main.py` → `core/ui/` (INCHANGÉ)
- **GUI (Kivy)** : `main_gui.py` → `gui/` (NOUVEAU)
- **Code métier partagé** : `core/` (tracking, hardware, config, etc.)

## Installation

### 1. Installer Kivy

```bash
# Avec uv (recommandé)
uv pip install "kivy[base]>=2.3.0"

# OU avec pip standard
pip install "kivy[base]>=2.3.0"
```

### 2. Configuration pour écran tactile

Pour Raspberry Pi avec écran tactile officiel :

```bash
# Éditer ~/.kivy/config.ini (ou laisser Kivy le créer au premier lancement)
# La configuration auto devrait fonctionner directement
```

## Lancement

### Mode GUI (Kivy)

```bash
# Avec uv
uv run main_gui.py

# OU standard Python
python main_gui.py
```

### Mode TUI (Textual) - inchangé

```bash
uv run main.py
# ou
python main.py
```

## Fonctionnalités actuelles

### ✅ Implémenté (6 déc 2025 - Version 2.2)

**Interface COMPLÈTE et FONCTIONNELLE** : Équivalent total du TUI

#### Interface et contrôles
- **Statut matériel** : Affichage PRODUCTION/SIMULATION + plateforme
- **Bandeau objet** : Apparaît après recherche réussie (nom, type, RA, DEC)
- **Champ de saisie** : TextInput libre + touche Entrée pour démarrer
- **3 boutons action** : ▶ Démarrer | ⏹ Stopper | ⚙ Configurer (tous fonctionnels)
- **Ligne info** : Méthode ABAQUE | Seuil | Intervalle (mise à jour dynamique)
- **2 lignes statut** : Az/Alt objet + Position coupole + Mode + Corrections
- **Zone de logs** : Scrollable avec messages colorés (markup Kivy)
- **Raccourcis clavier** : d/s/c/q (comme TUI)

#### Fonctionnalités métier
- **Recherche objet** : Cache local + SIMBAD en ligne (GestionnaireCatalogue)
- **Tracking réel** : TrackingSession avec méthode abaque
- **Modes adaptatifs** : NORMAL 🟢 / CRITICAL 🟠 / CONTINUOUS 🔴
- **Timers Kivy** : Mise à jour 1s + corrections adaptatives
- **Encodeur daemon** : Lecture position temps réel
- **Popup config** : Modification seuil/intervalle en temps réel

#### Widgets
- **ConfigPopup** : Modal de configuration avec validation
- **CompassWidget** : Boussole temps réel (écran statut)
- **Thème sombre** : Adapté observatoire nocturne

### 🚧 À implémenter

- **Écran de tracking** : Suivi actif d'un objet avec corrections
- **Saisie manuelle** : Position Az/Alt avec clavier tactile
- **Graphiques temps réel** : Historique des positions, erreurs
- **Configuration** : Paramètres adaptatifs, seuils, méthode (vectorielle/abaque)
- **Labels cardinaux** : N/E/S/W sur la boussole

## Structure des fichiers

```
gui/
├── README.md           # Ce fichier
├── __init__.py
├── app.py              # Application Kivy principale
├── screens/            # Écrans de l'interface
│   ├── __init__.py
│   ├── main_screen.py  # Sélection d'objets
│   └── status_screen.py # Boussole + statut
└── widgets/            # Widgets réutilisables
    ├── __init__.py
    └── compass.py      # Widget boussole temps réel
```

## Développement

### Ajouter un nouvel écran

1. Créer le fichier dans `gui/screens/my_screen.py`
2. Hériter de `kivy.uix.screenmanager.Screen`
3. Ajouter dans `gui/app.py` : `sm.add_widget(MyScreen(name='my_screen'))`

### Ajouter un widget

1. Créer le fichier dans `gui/widgets/my_widget.py`
2. Hériter de `kivy.uix.widget.Widget` (ou autre)
3. Utiliser dans les écrans : `from gui.widgets.my_widget import MyWidget`

## Retour à l'interface TUI

Aucune modification n'a été apportée aux fichiers existants. Pour revenir à l'interface Textual :

```bash
python main.py  # Fonctionne exactement comme avant
```

## Debugging

### Mode fenêtré (développement)

Éditer `gui/app.py` ligne 31 :

```python
Config.set('graphics', 'fullscreen', '0')  # Mode fenêtré
Config.set('graphics', 'width', '800')
Config.set('graphics', 'height', '600')
```

### Logs Kivy

Les logs Kivy s'affichent dans la console au lancement. Pour plus de détails :

```bash
export KIVY_LOG_LEVEL=debug
python main_gui.py
```

## Compatibilité

- **Raspberry Pi 4/5** : Testé et optimisé
- **Écran tactile** : Support natif Kivy
- **Résolution** : Adaptatif (responsive)
- **Python** : ≥ 3.12 (comme le reste du projet)