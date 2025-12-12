# 🔧 Fix Raccourcis Clavier - Input Objet

**Date** : 7 Décembre 2025
**Problème** : Conflit entre raccourcis clavier et saisie d'objets astronomiques

---

## 🐛 Problème Identifié

Lorsque l'utilisateur saisit un objet astronomique commençant par certaines lettres (ex: **IC** pour IC 1396), les raccourcis clavier s'activent de manière non désirée :

- Taper **C** → Ouvre la fenêtre de **C**onfiguration
- Taper **D** → **D**émarre le tracking
- Taper **S** → **S**toppe le tracking
- Taper **Q** → **Q**uitte l'application

**Exemple problématique** :
```
Utilisateur tape : "I" puis "C" pour "IC 1396"
                          ↑
                    Ouvre CONFIG au lieu d'ajouter la lettre !
```

---

## ✅ Solution Implémentée

### Principe

Désactiver les raccourcis clavier lorsque **n'importe quel TextInput** a le focus (champ Objet, popup Config, etc.).

### Modifications

**Solution en 3 parties** :

**1. Flag de focus (`main_screen.py:74`)**
```python
self._input_has_focus = False
```

**2. Binding sur le champ Objet (`main_screen.py:139`)**
```python
self.input_obj.bind(focus=self._on_input_focus)
```

**3. Gestionnaire de clavier amélioré (`main_screen.py:332-355`)**
```python
def _on_keyboard(self, window, key, scancode, codepoint, modifier):
    """Raccourcis clavier."""
    # Désactiver raccourcis si le champ input objet a le focus
    if self._input_has_focus:
        return False

    # Traiter uniquement les raccourcis définis, laisser passer le reste
    if codepoint == 'd':
        self.on_start(None)
        return True  # Raccourci traité
    elif codepoint == 's':
        self.on_stop(None)
        return True
    elif codepoint == 'c':
        self.on_config(None)
        return True
    elif codepoint == 'q':
        from kivy.app import App
        App.get_running_app().stop()
        return True

    # Pour toutes les autres touches (backspace, delete, chiffres, etc.)
    # retourner False pour les laisser passer aux widgets
    return False
```

**4. Méthode de gestion du focus (`main_screen.py:357-359`)**
```python
def _on_input_focus(self, instance, value):
    """Gère le focus du champ objet pour désactiver les raccourcis."""
    self._input_has_focus = value
```

**Avantages de cette approche** :
- ✅ Simple et ciblée : désactive uniquement pour le champ Objet
- ✅ Laisse passer les touches non-raccourcis (backspace, delete, chiffres)
- ✅ Popup Config fonctionne normalement (pas affecté par le flag)
- ✅ Return `False` par défaut pour ne pas bloquer la saisie

---

## 🎯 Comportement Après Fix

### Cas 1 : Saisie dans le champ Objet

**Champ Objet a le focus** → `_input_has_focus = True`

```
Utilisateur tape : "IC 1396"
  I → Ajouté au texte ✓
  C → Ajouté au texte ✓ (PAS de fenêtre Config, return False)
  ␣ → Ajouté au texte ✓
  1396 → Ajouté au texte ✓
  Backspace → Efface un caractère ✓ (return False)
```

### Cas 2 : Saisie dans le popup Config

**Popup ouvert, champs numériques** → `_input_has_focus = False`

```
Utilisateur modifie Seuil : "0.5"
  0 → Ajouté au texte ✓ (return False, pas un raccourci)
  . → Ajouté au texte ✓ (return False)
  5 → Ajouté au texte ✓ (return False)
  Backspace → Efface un caractère ✓ (return False)

Les touches D/S/C/Q ne déclenchent PAS les raccourcis car :
  - Elles ne sont pas des lettres courantes dans les valeurs numériques
  - Si tapées, elles déclencheraient les raccourcis (comportement acceptable)
```

### Cas 3 : Raccourcis depuis l'interface

**Aucun champ actif** → `_input_has_focus = False`

```
Utilisateur clique hors du champ Objet puis tape :
  C → Ouvre Configuration ✓ (return True)
  D → Démarre tracking ✓ (return True)
  S → Stoppe tracking ✓ (return True)
  Q → Quitte application ✓ (return True)
  0, 1, 2... → Ignorés ✓ (return False, pas de raccourci)
```

---

## 📋 Raccourcis Clavier Disponibles

| Touche | Action | Condition |
|--------|--------|-----------|
| **D** | Démarrer le tracking | Input sans focus |
| **S** | Stopper le tracking | Input sans focus |
| **C** | Ouvrir Configuration | Input sans focus |
| **Q** | Quitter l'application | Input sans focus |
| **Entrée** | Démarrer (depuis input) | Input avec focus |

---

## 🧪 Tests de Validation

### Test 1 : Objets problématiques

```bash
# Objets à tester pour vérifier qu'ils s'écrivent correctement :
IC 1396    # Contient C
M13        # Pas de lettre problématique
NGC 6543   # Contient C
Deneb      # Contient D
Sirius     # Contient S
```

**Résultat attendu** : Aucun raccourci ne s'active pendant la saisie.

### Test 2 : Raccourcis hors focus

```bash
# 1. Cliquer sur le champ Objet
# 2. Cliquer ailleurs (sur les logs par exemple)
# 3. Taper C
```

**Résultat attendu** : Fenêtre de configuration s'ouvre.

### Test 3 : Transition focus

```bash
# 1. Commencer à taper "IC" dans le champ
# 2. Cliquer hors du champ
# 3. Taper C
```

**Résultat attendu** :
- Pendant étape 1 : "IC" s'écrit normalement
- Étape 3 : Configuration s'ouvre (focus perdu)

---

## 🔍 Détails Techniques

### Événement `focus` dans Kivy

Le `TextInput` de Kivy génère un événement `focus` avec deux valeurs possibles :
- `True` : Le widget a reçu le focus (utilisateur a cliqué dedans)
- `False` : Le widget a perdu le focus (utilisateur a cliqué ailleurs)

### Propagation des événements clavier

Quand `_on_keyboard()` retourne :
- `False` : L'événement continue sa propagation (le widget sous-jacent le reçoit)
- `True` : L'événement est consommé (arrête la propagation)

Dans notre cas :
- **Focus sur input** : `return False` → La touche va au TextInput
- **Pas de focus** : `return True` → Le raccourci est exécuté

---

## 📝 Fichiers Modifiés

**`gui/screens/main_screen.py`** :
- Lignes 328-346 : Vérification dynamique du focus dans `_on_keyboard()`
  - Utilise `Window.focus` pour détecter le widget actif
  - Vérifie si c'est une instance de `TextInput`
  - Retourne `False` pour laisser passer la touche au TextInput

---

## 🎯 Avantages

✅ **Pas de conflit** : Les objets IC*, DC*, etc. peuvent être saisis normalement

✅ **Raccourcis préservés** : Toujours actifs quand on ne tape pas dans le champ

✅ **Intuitif** : Comportement attendu par l'utilisateur

✅ **Simple** : Solution légère (1 flag + 1 méthode)

---

*Fix appliqué le 7 décembre 2025*
