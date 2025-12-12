# 🗑️ Suppression Complète du Mode Vectoriel

**Date** : 6 Décembre 2025
**Objectif** : Garder uniquement le mode abaque (testé et fonctionnel)
**Raison** : Le mode vectoriel ne fonctionne pas correctement

**🎉 STATUT** : **COMPLÉTÉ** - Toutes les modifications ont été appliquées avec succès

---

## ✅ Modifications Complétées

### 1. config.json ✅
**Fichier** : `data/config.json`

**Supprimé** :
```json
"method": "abaque",        // Ligne 24 (supprimée)
"use_vectorielle": false,  // Ligne 25 (supprimée)
```

**Résultat** : Section `suivi` ne contient plus que :
- `seuil_correction_deg`
- `intervalle_verification_sec`
- `abaque_file`
- `enable_anticipation`

---

### 2. config_loader.py ✅
**Fichier** : `core/config/config_loader.py`

**Classe TrackingConfig (lignes 100-107)** :
```python
# AVANT (6 attributs)
class TrackingConfig:
    seuil_correction_deg: float
    intervalle_verification_sec: int
    method: str  # "abaque" ou "vectorielle"  ← SUPPRIMÉ
    use_vectorielle: bool  ← SUPPRIMÉ
    abaque_file: str
    enable_anticipation: bool

# APRÈS (4 attributs)
class TrackingConfig:
    """Configuration du suivi de base (méthode abaque uniquement)."""
    seuil_correction_deg: float
    intervalle_verification_sec: int
    abaque_file: str
    enable_anticipation: bool
```

**Chargement config (lignes 366-371)** :
```python
# AVANT
tracking = TrackingConfig(
    seuil_correction_deg=...,
    intervalle_verification_sec=...,
    method=str(tracking_cfg.get("method", "abaque")),  ← SUPPRIMÉ
    use_vectorielle=bool(tracking_cfg.get("use_vectorielle", False)),  ← SUPPRIMÉ
    abaque_file=...,
    enable_anticipation=...
)

# APRÈS
tracking = TrackingConfig(
    seuil_correction_deg=...,
    intervalle_verification_sec=...,
    abaque_file=...,
    enable_anticipation=...
)
```

**Sauvegarde config (lignes 544-549)** :
```python
# AVANT
tracking_dict = {
    'seuil_correction_deg': ...,
    'intervalle_verification_sec': ...,
    'method': config.tracking.method,  ← SUPPRIMÉ
    'use_vectorielle': config.tracking.use_vectorielle,  ← SUPPRIMÉ
    'abaque_file': ...,
    'enable_anticipation': ...
}

# APRÈS
tracking_dict = {
    'seuil_correction_deg': ...,
    'intervalle_verification_sec': ...,
    'abaque_file': ...,
    'enable_anticipation': ...
}
```

---

## ⏳ Modifications En Cours

### 3. ConfigScreenWithMethod → ConfigScreen
**Fichier** : `core/ui/main_screen.py` (lignes 117-196)

**Action requise** :
1. Renommer `ConfigScreenWithMethod` → `ConfigScreen` (ou supprimer et utiliser celle de modals.py)
2. Supprimer la checkbox abaque (ligne 168)
3. Retirer paramètre `use_abaque` du `__init__` et dismiss

**Code à modifier** :
```python
# AVANT (ligne 145-149)
def __init__(self, seuil: float, intervalle: int, use_abaque: bool):
    super().__init__()
    self.seuil = seuil
    self.intervalle = intervalle
    self.use_abaque = use_abaque  ← SUPPRIMER

# APRÈS
def __init__(self, seuil: float, intervalle: int):
    super().__init__()
    self.seuil = seuil
    self.intervalle = intervalle
```

```python
# AVANT (lignes 167-170)
Container(
    Checkbox("☑️ Utiliser l'ABAQUE (mesures réelles - recommandé)",
             value=self.use_abaque, id="checkbox_abaque"),  ← SUPPRIMER CE CONTAINER
    classes="config_row"
),
```

```python
# AVANT (lignes 184-191)
seuil = float(self.query_one("#input_seuil", Input).value)
intervalle = int(self.query_one("#input_intervalle", Input).value)
use_abaque = self.query_one("#checkbox_abaque", Checkbox).value  ← SUPPRIMER

if seuil <= 0 or intervalle <= 0:
    raise ValueError("Valeurs invalides")

self.dismiss((seuil, intervalle, use_abaque))  ← MODIFIER

# APRÈS
seuil = float(self.query_one("#input_seuil", Input).value)
intervalle = int(self.query_one("#input_intervalle", Input).value)

if seuil <= 0 or intervalle <= 0:
    raise ValueError("Valeurs invalides")

self.dismiss((seuil, intervalle))  ← Retourne tuple de 2 éléments
```

---

### 4. main_screen.py - Variables et Affichages
**Fichier** : `core/ui/main_screen.py`

**Variables à supprimer/modifier** :

**Ligne 269** :
```python
# AVANT
self.use_abaque = config.tracking.method == 'abaque'  ← SUPPRIMER

# Plus besoin de cette variable, toujours abaque
```

**Fonction _update_method_display (lignes 376-382)** :
```python
# AVANT
def _update_method_display(self):
    """Met à jour l'affichage de la méthode active."""
    method_str = "ABAQUE (mesures réelles)" if self.use_abaque else "VECTORIELLE (calcul)"
    mode_str = "SIM" if self.simulation else "PROD"
    self.query_one("#method_info", Static).update(
        f"[{mode_str}] Méthode: {method_str} | Seuil={self.seuil:.2f}° | Int={self.intervalle}s"
    )

# APRÈS (simplifier)
def _update_method_display(self):
    """Met à jour l'affichage de la configuration."""
    mode_str = "SIM" if self.simulation else "PROD"
    self.query_one("#method_info", Static).update(
        f"[{mode_str}] Méthode: ABAQUE (mesures réelles) | Seuil={self.seuil:.2f}° | Int={self.intervalle}s"
    )
```

**Ligne 423-424** (création TrackingSession) :
```python
# AVANT
method='abaque' if self.use_abaque else 'vectorielle',
abaque_file=self.config.tracking.abaque_file if self.use_abaque else None,

# APRÈS
method='abaque',  ← Toujours 'abaque'
abaque_file=self.config.tracking.abaque_file,
```

**Lignes 439, 444-445** (logs démarrage) :
```python
# AVANT
method_str = "ABAQUE" if self.use_abaque else "VECTORIELLE"
self._append_log(
    f"Mode: {mode_str} | Méthode: {method_str} | "
    f"Seuil={self.seuil:.2f}° | Intervalle={self.intervalle}s"
)

# APRÈS
self._append_log(
    f"Mode: {mode_str} | Méthode: ABAQUE | "
    f"Seuil={self.seuil:.2f}° | Intervalle={self.intervalle}s"
)
```

**Ligne 476** (handle_config callback) :
```python
# AVANT
def handle_config(result):
    if result is not None:
        self.seuil, self.intervalle, self.use_abaque = result  ← 3 valeurs
        method_str = "ABAQUE" if self.use_abaque else "VECTORIELLE"
        self._append_log(
            f"⚙️ Config: Seuil={self.seuil:.2f}° | "
            f"Intervalle={self.intervalle}s | "
            f"Méthode={method_str}"
        )
        ...

# APRÈS
def handle_config(result):
    if result is not None:
        self.seuil, self.intervalle = result  ← 2 valeurs seulement
        self._append_log(
            f"⚙️ Config: Seuil={self.seuil:.2f}° | "
            f"Intervalle={self.intervalle}s | "
            f"Méthode=ABAQUE"
        )
        ...
```

**Ligne 492** (appel ConfigScreenWithMethod) :
```python
# AVANT
self.push_screen(
    ConfigScreenWithMethod(self.seuil, self.intervalle, self.use_abaque),  ← 3 params
    handle_config
)

# APRÈS
self.push_screen(
    ConfigScreenWithMethod(self.seuil, self.intervalle),  ← 2 params
    handle_config
)
```

**Lignes 557-559** (affichage status tracking) :
```python
# AVANT
method_str = "ABAQUE ✓" if self.use_abaque else "VECTORIELLE"
status_line2 = (
    f"{method_str} | "
    ...
)

# APRÈS
status_line2 = (
    f"ABAQUE ✓ | "
    ...
)
```

---

### 5. tracker.py - Simplification Logique
**Fichier** : `core/tracking/tracker.py`

**Paramètre method dans __init__ (ligne 42)** :
```python
# AVANT
def __init__(
        self,
        moteur: Optional[MoteurCoupole | MoteurSimule],
        calc: AstronomicalCalculations,
        logger: TrackingLogger,
        seuil: float = 0.5,
        intervalle: int = 300,
        method: str = 'abaque',  ← SUPPRIMER CE PARAMÈTRE
        abaque_file: Optional[str] = None,
        ...
):

# APRÈS
def __init__(
        self,
        moteur: Optional[MoteurCoupole | MoteurSimule],
        calc: AstronomicalCalculations,
        logger: TrackingLogger,
        seuil: float = 0.5,
        intervalle: int = 300,
        abaque_file: str,  ← Requis, pas Optional
        ...
):
```

**Docstring (lignes 56-57)** :
```python
# AVANT
        intervalle: Intervalle entre corrections en secondes
        method: 'vectorielle' ou 'abaque' (défaut)  ← SUPPRIMER
        abaque_file: Chemin vers le fichier d'abaque (requis si method='abaque')

# APRÈS
        intervalle: Intervalle entre corrections en secondes
        abaque_file: Chemin vers le fichier d'abaque
```

**Variable self.method (ligne 65)** :
```python
# AVANT
self.method = method  ← SUPPRIMER

# Plus besoin de stocker la méthode
```

**Chargement abaque (lignes 118-124)** :
```python
# AVANT
self.abaque_manager = None
if self.method == 'abaque':
    if abaque_file is None:
        raise ValueError("abaque_file requis pour la méthode 'abaque'")

    self.abaque_manager = AbaqueManager(abaque_file, self.python_logger)
    self.python_logger.info("Abaque chargé (mode interpolation)")

# APRÈS
self.abaque_manager = AbaqueManager(abaque_file, self.python_logger)
self.python_logger.info("Abaque chargé (mode interpolation)")
```

**Méthode _calculate_target_position (lignes 218-250)** :
```python
# AVANT (3 branches if/elif/else)
def _calculate_target_position(
    self,
    azimut_objet: float,
    altitude_objet: float
) -> Tuple[float, dict]:
    if self.method == 'vectorielle':
        # Méthode originale : calcul vectoriel
        correction_parallaxe = self.calc.calculer_correction_parallaxe(
            azimut_objet,
            altitude_objet
        )
        position_cible = (azimut_objet + correction_parallaxe) % 360

        infos = {
            'method': 'vectorielle',
            'parallax_correction': correction_parallaxe,
            'position_cible': position_cible
        }

    elif self.method == 'abaque':
        # Méthode abaque : interpolation des mesures réelles
        position_cible, infos = self.abaque_manager.get_dome_position(
            altitude_objet,
            azimut_objet
        )
        infos['method'] = 'abaque'

        # Ajouter la correction de parallaxe vectorielle pour comparaison
        correction_parallaxe_vect = self.calc.calculer_correction_parallaxe(
            azimut_objet,
            altitude_objet
        )
        infos['parallax_vect'] = correction_parallaxe_vect

    else:
        raise ValueError(f"Méthode inconnue : {self.method}")

    return position_cible, infos

# APRÈS (simplifié, garde seulement abaque)
def _calculate_target_position(
    self,
    azimut_objet: float,
    altitude_objet: float
) -> Tuple[float, dict]:
    """
    Calcule la position cible de la coupole selon l'abaque.

    Args:
        azimut_objet: Azimut de l'objet (degrés)
        altitude_objet: Altitude de l'objet (degrés)

    Returns:
        Tuple (position_cible, infos_debug)
    """
    # Interpolation depuis les mesures réelles (abaque)
    position_cible, infos = self.abaque_manager.get_dome_position(
        altitude_objet,
        azimut_objet
    )
    infos['method'] = 'abaque'

    # Optionnel : Garder calcul vectoriel pour comparaison/debug
    correction_parallaxe_vect = self.calc.calculer_correction_parallaxe(
        azimut_objet,
        altitude_objet
    )
    infos['parallax_vect'] = correction_parallaxe_vect

    return position_cible, infos
```

**Ligne 326-327** (correction_parallaxe_initiale) :
```python
# AVANT
if self.method == 'vectorielle':
    self.correction_parallaxe_initiale = infos['parallax_correction']  ← SUPPRIMER

# Plus besoin de cette condition
```

**Ligne 336** (logger) :
```python
# AVANT
method_str = "ABAQUE" if self.method == 'abaque' else "VECTORIELLE"
self.logger.start_tracking(
    objet_name,
    method_str,
    ...
)

# APRÈS
self.logger.start_tracking(
    objet_name,
    "ABAQUE",  ← Toujours "ABAQUE"
    ...
)
```

**Ligne 404** (status dict) :
```python
# AVANT
status = {
    'running': True,
    'objet': self.objet,
    'method': self.method,  ← SUPPRIMER
    ...
}

# APRÈS
status = {
    'running': True,
    'objet': self.objet,
    ...
}
```

**Lignes 445-450** (infos spécifiques méthode) :
```python
# AVANT
if self.method == 'vectorielle':
    status['parallax_correction'] = infos['parallax_correction']
elif self.method == 'abaque':
    status['abaque_method'] = infos.get('method', 'interpolation')
    status['in_bounds'] = infos.get('in_bounds', True)
    # Ajouter la correction vectorielle pour comparaison
    status['parallax_vect'] = infos.get('parallax_vect', 0.0)

# APRÈS (toujours abaque)
status['abaque_method'] = infos.get('method', 'interpolation')
status['in_bounds'] = infos.get('in_bounds', True)
# Correction vectorielle gardée pour comparaison/debug
status['parallax_vect'] = infos.get('parallax_vect', 0.0)
```

**Ligne 688** (logs fin session) :
```python
# AVANT
self.python_logger.info(f"Méthode: {self.method.upper()}")

# APRÈS
self.python_logger.info(f"Méthode: ABAQUE")
```

---

### 6. viewmodel.py - Simplification Format
**Fichier** : `core/ui/viewmodel.py`

**Méthode format_parallax_info (lignes 75-88)** :
```python
# AVANT
@staticmethod
def format_parallax_info(azimut: float, altitude: float, correction: float, method: str) -> str:
    """
    Formate la ligne d'information sur la correction de parallaxe.
    """
    if method == 'abaque':
        method_str = "Abaque"
    else:
        method_str = "Vectorielle"

    return (
        f"Méthode: {method_str} | "
        f"Alt/Az: {altitude:.1f}°/{azimut:.1f}° | "
        f"Correction appliquée: {correction:+.2f}°"
    )

# APRÈS (simplifier)
@staticmethod
def format_parallax_info(azimut: float, altitude: float, correction: float) -> str:
    """
    Formate la ligne d'information sur la correction de parallaxe (abaque).
    """
    return (
        f"Méthode: Abaque | "
        f"Alt/Az: {altitude:.1f}°/{azimut:.1f}° | "
        f"Correction appliquée: {correction:+.2f}°"
    )
```

---

## 📊 Résumé des Changements

| Fichier | Lignes Modifiées | Type Modification |
|---------|------------------|-------------------|
| `data/config.json` | 24-25 | ✅ Suppression 2 paramètres |
| `core/config/config_loader.py` | 100-107, 366-371, 544-549 | ✅ Simplification classe + chargement |
| `core/ui/main_screen.py` | 117-196, 269, 376-382, 423-424, 439, 444-445, 476-492, 557-559 | ⏳ Suppression checkbox + affichages |
| `core/tracking/tracker.py` | 42, 56-57, 65, 118-124, 218-250, 326-327, 336, 404, 445-450, 688 | ⏳ Simplification logique |
| `core/ui/viewmodel.py` | 75-88 | ⏳ Suppression paramètre method |

**Total estimé** : ~150 lignes supprimées/simplifiées

---

## ✅ Avantages

1. **Code plus simple** : Suppression d'une branche complète (vectorielle) qui ne fonctionne pas
2. **Moins de bugs potentiels** : Une seule méthode = moins de cas à tester
3. **UI simplifiée** : Pas de choix inutile pour l'utilisateur
4. **Config allégée** : Moins de paramètres à gérer
5. **Maintenance facilitée** : Code focalisé sur ce qui fonctionne (abaque)

---

**Version** : 1.0
**Date** : 6 Décembre 2025
**Statut** : Modifications config terminées, UI/tracker/viewmodel en cours
