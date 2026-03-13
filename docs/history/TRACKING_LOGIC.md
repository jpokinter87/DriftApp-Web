# Logique complète du système de tracking DriftApp

## Vue d'ensemble

Le système suit automatiquement les objets célestes en compensant la rotation terrestre et la parallaxe instrumentale (tube décalé de 40cm dans une coupole de 120cm de rayon).

## Architecture à 3 processus

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Daemon EMS22A  │     │  Motor Service  │     │  Django Web     │
│  (ems22d.py)    │     │  (motor_svc.py) │     │  (manage.py)    │
│                 │     │                 │     │                 │
│  Lit encodeur   │────▶│  Contrôle       │◀────│  Interface      │
│  SPI @ 50Hz     │ JSON│  moteur + suivi │ IPC │  utilisateur    │
│                 │     │                 │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       │
        ▼                       ▼
/dev/shm/ems22_position.json   GPIO 17/18 → Driver DM556T → Moteur
```

## Démarrage du suivi (`TrackingSession.start()`)

```
1. Recherche objet (catalogue ou SIMBAD)
   └─▶ Obtient RA/DEC (J2000)

2. Calcul position initiale
   ├─▶ RA/DEC → Azimut/Altitude (coordonnées horizontales)
   └─▶ Azimut/Altitude → Position coupole (interpolation abaque)

3. Vérification GOTO initial (si encodeur calibré)
   ├─▶ Lit position réelle via daemon
   ├─▶ Compare avec position cible
   └─▶ Si delta > seuil → GOTO automatique en mode FAST_TRACK

4. Démarrage boucle de suivi
   └─▶ Programme prochaine correction (intervalle adaptatif)
```

## Boucle de correction (`check_and_correct()`)

Appelée périodiquement par le Motor Service :

```
┌─────────────────────────────────────────────────────────────────┐
│                    CHECK_AND_CORRECT                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. Vérifier si c'est le moment (next_correction_time)          │
│     └─▶ Si non → return (pas de correction)                     │
│                                                                 │
│  2. Calculer position actuelle de l'objet                       │
│     ├─▶ Étoiles: RA/DEC fixes → Azimut/Altitude (rotation Terre)│
│     └─▶ Planètes: Recalcul RA/DEC (mouvement propre)            │
│                                                                 │
│  3. Calculer position cible coupole (ABAQUE)                    │
│     └─▶ Interpolation bilinéaire depuis Loi_coupole.xlsx        │
│         (275 points mesurés sur site)                           │
│                                                                 │
│  4. Calculer delta (chemin le plus court)                       │
│     └─▶ verify_shortest_path() → évite les tours > 180°         │
│                                                                 │
│  5. Évaluer zone adaptative                                     │
│     └─▶ evaluate_tracking_zone() → choisit le mode              │
│                                                                 │
│  6. Si |delta| > seuil adaptatif                                │
│     └─▶ Appliquer correction avec feedback encodeur             │
│                                                                 │
│  7. Programmer prochaine vérification                           │
│     └─▶ now + intervalle adaptatif                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Système adaptatif (4 modes)

```
┌──────────────┬───────────┬─────────┬──────────────┬─────────────────────┐
│ Mode         │ Intervalle│ Seuil   │ Vitesse      │ Déclencheur         │
├──────────────┼───────────┼─────────┼──────────────┼─────────────────────┤
│ NORMAL       │ 60s       │ 0.5°    │ 0.002s/pas   │ Alt < 68°           │
│ CRITICAL     │ 15s       │ 0.25°   │ 0.00055s/pas │ 68° ≤ Alt < 75°     │
│ CONTINUOUS   │ 5s        │ 0.1°    │ 0.00012s/pas │ Alt ≥ 75° (zénith)  │
│ FAST_TRACK   │ 5s        │ 0.5°    │ 0.00015s/pas │ Delta > 30° (GOTO)  │
└──────────────┴───────────┴─────────┴──────────────┴─────────────────────┘
```

**Logique de sélection** (`evaluate_tracking_zone()`) :

```python
if abs(delta) > 30°:
    return FAST_TRACK      # Grand déplacement (GOTO, basculement méridien)
elif altitude >= 75°:
    return CONTINUOUS      # Proche zénith - mouvements rapides
elif altitude >= 68°:
    return CRITICAL        # Zone critique - surveillance accrue
else:
    return NORMAL          # Conditions standard
```

## Correction avec feedback (`FeedbackController`)

```
┌─────────────────────────────────────────────────────────────────┐
│              ROTATION_AVEC_FEEDBACK                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Position initiale ◀── Lire daemon encodeur                     │
│                                                                 │
│  BOUCLE (max 10 itérations):                                    │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  1. Lire position actuelle                              │    │
│  │  2. Calculer erreur = position_actuelle - angle_cible   │    │
│  │  3. Si |erreur| < tolérance → SUCCÈS, sortir            │    │
│  │  4. Si |erreur| > 20° et pas GOTO → ABANDON             │    │
│  │  5. Calculer steps = erreur × steps_per_revolution/360  │    │
│  │  6. Exécuter les pas (avec check stop tous les 500 pas) │    │
│  │  7. Pause 50ms stabilisation                            │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  Position finale ◀── Lire daemon encodeur                       │
│  Erreur finale = position_finale - angle_cible                  │
│  Succès si |erreur_finale| < tolérance (0.5°)                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Méthode Abaque (interpolation)

Le fichier `Loi_coupole.xlsx` contient 275 points mesurés sur site :

```
Altitude │ Azimut │ Position_Coupole
─────────┼────────┼─────────────────
30°      │ 0°     │ 358.2°
30°      │ 15°    │ 12.7°
...      │ ...    │ ...
85°      │ 345°   │ 340.1°
```

**Interpolation bilinéaire** :
```
                    Az1        Az2
                     │          │
            ┌────────┼──────────┼────────┐
       Alt1 │   P11  │    ●     │  P12   │
            │        │  (Az,Alt)│        │
            ├────────┼──────────┼────────┤
       Alt2 │   P21  │          │  P22   │
            └────────┴──────────┴────────┘

Position = interpolation(P11, P12, P21, P22, Az, Alt)
```

## Switch de calibration (45°)

```
┌─────────────────────────────────────────────────────────────────┐
│                 CALIBRATION AUTOMATIQUE                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Microswitch SS-5GL sur GPIO 27 à la position 45° azimut        │
│                                                                 │
│  Quand la coupole passe sur le switch :                         │
│  1. GPIO 27 passe de HIGH à LOW (falling edge)                  │
│  2. Daemon détecte la transition                                │
│  3. Recalage: total_counts ajusté pour angle = 45°              │
│  4. Flag calibrated = True                                      │
│                                                                 │
│  Impact sur le suivi :                                          │
│  • calibrated=True → GOTO initial automatique activé            │
│  • Position absolue connue → feedback précis                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Flux de données complet

```
                    OBJET CÉLESTE
                         │
                    RA/DEC (J2000)
                         │
                         ▼
              ┌──────────────────────┐
              │ Calcul astronomique  │
              │ (AstronomicalCalcs)  │
              └──────────────────────┘
                         │
                  Azimut/Altitude
                         │
                         ▼
              ┌──────────────────────┐
              │ Interpolation Abaque │
              │ (AbaqueManager)      │
              └──────────────────────┘
                         │
                Position cible coupole
                         │
                         ▼
              ┌──────────────────────┐
              │ Gestionnaire adaptatif│
              │ (AdaptiveTracking)   │
              └──────────────────────┘
                         │
              Mode + Paramètres (intervalle, seuil, vitesse)
                         │
                         ▼
              ┌──────────────────────┐
              │ Feedback Controller  │◀──── Position encodeur
              │ (boucle fermée)      │      (daemon EMS22A)
              └──────────────────────┘
                         │
                    Pulses GPIO
                         │
                         ▼
              ┌──────────────────────┐
              │ Driver DM556T        │
              │ → Moteur pas-à-pas   │
              │ → Courroie           │
              │ → Coupole (2230:1)   │
              └──────────────────────┘
```

## Paramètres critiques

```python
# Configuration moteur
MICROSTEPS = 4                    # Doit correspondre au driver DM556T
GEAR_RATIO = 2230                 # Réduction totale
STEPS_PER_REVOLUTION = 200        # Moteur NEMA
CORRECTION_FACTOR = 1.08849       # Ajustement empirique

# Calcul: steps par tour de coupole
STEPS_PER_DOME = 200 × 4 × 2230 × 1.08849 ≈ 1,941,866 pas/360°
                 ≈ 5,394 pas/degré

# Encodeur
CALIBRATION_FACTOR = 0.010851     # Rapport roue encodeur / coupole
# La roue encodeur fait ~92 tours par tour de coupole
```

## Fichiers clés

| Fichier | Rôle |
|---------|------|
| `core/tracking/tracker.py` | Session de suivi, GOTO initial, corrections |
| `core/tracking/adaptive_tracking.py` | Système adaptatif 4 modes |
| `core/tracking/abaque_manager.py` | Interpolation depuis mesures terrain |
| `core/hardware/moteur.py` | Contrôle moteur, wrapper feedback |
| `core/hardware/feedback_controller.py` | Boucle fermée avec encodeur |
| `services/motor_service.py` | Service IPC, commandes web |
| `ems22d_calibrated.py` | Daemon encodeur avec switch |
| `data/Loi_coupole.xlsx` | 275 points de mesure sur site |
| `data/config.json` | Configuration complète |