# Analyse des bugs terrain - 7 et 8 décembre 2025

## Résumé des incidents

### Incident 1 : 7/12 18h17 - M31 rotation continue
- **Symptôme** : La coupole était relancée toutes les 5-6s dans une rotation continue
- **Durée avant arrêt manuel** : > 45° de déplacement
- **Objet** : M31 à altitude 78.3° (mode CONTINUOUS activé)

### Incident 2 : 7/12 19h09 - M31 après passage switch
- Fonctionnement amélioré après passage par le switch de calibration (45°)

### Incident 3 : 8/12 10h27-10h31 - M13 écran figé
- **Symptôme** : Écran figé après plusieurs corrections en mode CRITICAL
- **Reprise** : Après quelques minutes
- **Observation** : Coupole déplacée de beaucoup dans le sens anti-horaire

### Incident 4 : 8/12 - M13 passage switch
- **Symptôme** : Passage sur switch mais encodeur non remis à 45°
- **Suite** : Rotation continue dans le sens anti-horaire > 90°

## Analyse des logs

### Log 7/12 19h09 (driftapp_20251207_190930.log)
```
19:14:09 | CHANGEMENT DE MODE: normal → continuous
         | Raisons: Proche zénith (78.6°)
         | - Intervalle: 5s
         | - Seuil: 0.10°
         | - Délai moteur: 0.00012s

19:14:09 | Correction: +1.37° | Mode: CONTINUOUS
19:14:15 | Correction: +0.14° | Mode: CONTINUOUS
19:14:20 | Correction: +0.12° | Mode: CONTINUOUS
19:14:25 | Correction: +0.12° | Mode: CONTINUOUS
... (correction toutes les 5s avec ~0.12° à chaque fois)
```

### Observations critiques

1. **Mode CONTINUOUS trop agressif**
   - Intervalle : 5s (correction toutes les 5 secondes !)
   - Seuil : 0.1° (quasiment toujours déclenché)
   - Motor delay : 0.00012s (vitesse ~45°/min, trop rapide pour le moteur)

2. **Erreurs de logging répétées**
   ```
   TypeError: not all arguments converted during string formatting
   File "tracker.py", line 448, in check_and_correct
       self.python_logger.info(azimut, altitude, delta)
   ```
   Cette erreur (maintenant corrigée dans la version actuelle) polluait les logs.

3. **Encodeur non calibré au démarrage**
   - `Position: 360.0°` au démarrage = non calibré
   - Mode relatif utilisé, mais offset peut dériver

## Causes racines identifiées

### Cause 1 : Paramètres mode CONTINUOUS inadaptés (PRINCIPALE)
```json
"continuous": {
  "interval_sec": 5,       // Trop fréquent
  "threshold_deg": 0.1,    // Trop sensible
  "motor_delay": 0.00012   // Trop rapide - moteur "hurle"
}
```

Problèmes :
- **Intervalle 5s** : Pour un objet se déplaçant de ~0.12°/5s, le seuil de 0.1° est quasi-toujours dépassé
- **Motor delay 0.00012s** : 8333 pas/seconde, bien au-delà des capacités du moteur stepper
- Le moteur "hurle sans tourner" = décrochage des pas (perte de couple)

### Cause 2 : Timer Kivy non adaptatif
Le timer `_corr_timer` est créé avec un intervalle fixe au démarrage :
```python
self._corr_timer = Clock.schedule_interval(self._do_correction, self.intervalle)
```
Il ne s'adapte pas quand le mode change de NORMAL (60s) à CONTINUOUS (5s).

### Cause 3 : Appels bloquants dans le thread UI
`rotation_avec_feedback_daemon()` est appelé depuis `_do_correction()` qui tourne dans le thread principal Kivy. Une correction de plusieurs secondes bloque toute l'interface.

### Cause 4 : Switch de calibration non fonctionnel
Le switch GPIO 27 ne recalibre pas toujours l'encodeur à 45° quand la coupole passe dessus. Voir les analyses précédentes dans `ANALYSE_SWITCH_NON_FONCTIONNEL.md`.

## Corrections appliquées

### 1. Modification config.json - Paramètres adaptatifs moins agressifs

**AVANT :**
```json
"critical": {
  "interval_sec": 15,
  "threshold_deg": 0.25,
  "motor_delay": 0.00055
},
"continuous": {
  "interval_sec": 5,
  "threshold_deg": 0.1,
  "motor_delay": 0.00012
}
```

**APRÈS :**
```json
"critical": {
  "interval_sec": 30,
  "threshold_deg": 0.35,
  "motor_delay": 0.0008
},
"continuous": {
  "interval_sec": 30,
  "threshold_deg": 0.3,
  "motor_delay": 0.0006
}
```

**Justification :**
- **Intervalle 30s** : Suffisant pour rattraper n'importe quel mouvement (30-60°/heure max proche zénith)
- **Seuil 0.3°** : Évite les micro-corrections incessantes tout en restant précis
- **Motor delay 0.0006s** : Vitesse ~15°/min, compatible avec les capacités du moteur

## Recommandations pour tests futurs

### Test 1 : Vérifier le switch de calibration
```bash
sudo pkill -f ems22d_calibrated
sudo python3 tests_sur_site/test_switch_direct.py
# Bouger la coupole vers 45° et observer les transitions
```

### Test 2 : Observer le comportement en mode CRITICAL/CONTINUOUS
Viser un objet à haute altitude (>70°) et observer :
- Le moteur ne devrait plus "hurler"
- Les corrections espacées de 30s
- Corrections de ~0.3-0.5° par cycle (pas des micro-mouvements de 0.1°)

### Test 3 : Comportement à long terme
- Lancer un suivi de 30+ minutes sur M13 ou M31
- Vérifier que le suivi reste stable
- Observer le nombre total de corrections (devrait être ~60-120/heure max)

## Historique des versions

| Version | Date | État |
|---------|------|------|
| Dome_v4_3 actuelle | 8/12/2025 | Corrigée (ce document) |
| Dome_v4_3-suivi_parfait | 8/12 14h13 | Sauvegarde pré-correction (identique) |
| Dome_v4_5 | 7/12 | Sur le Pi (mêmes bugs) |

## Fichiers modifiés

- `data/config.json` : Paramètres adaptive_tracking modes critical et continuous