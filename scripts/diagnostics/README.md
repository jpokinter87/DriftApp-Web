# 🧪 Tests et Diagnostics DriftApp

Ce répertoire contient les scripts de test et de diagnostic pour DriftApp.

## 📋 Scripts disponibles

### 1. `diagnostic_moteur_complet.py` (TEST A)

**Objectif** : Tester la boucle moteur en isolation totale.

**Prérequis** :
- Services DriftApp arrêtés (`sudo ./start_web.sh stop`)
- Privilèges root (accès GPIO)

**Usage** :
```bash
sudo python3 tests/diagnostic_moteur_complet.py
```

**Ce qu'il teste** :
- Boucle moteur pure (faire_un_pas)
- Timing des pulses GPIO
- Régularité des délais
- Détection d'outliers

**Résultat attendu** :
- < 0.1% outliers = boucle moteur parfaite
- Overhead constant = normal (limitation Python/OS)

---

### 2. `test_motor_service_seul.py` (TEST B)

**Objectif** : Tester le Motor Service via IPC, sans Django.

**Prérequis** :
- Motor Service actif (`sudo ./start_web.sh start`)

**Usage** :
```bash
python3 tests/test_motor_service_seul.py
```

**Ce qu'il teste** :
- Communication IPC (/dev/shm/motor_command.json)
- Exécution des commandes GOTO
- Fluidité du mouvement

**Résultat attendu** :
- Mouvement fluide
- Observation moyenne ≤ 2

---

### 3. `calibration_vitesse_encodeur.py`

**Objectif** : trouver la vitesse maximale du moteur en mesurant, à chaque palier,
la vitesse réelle de la coupole lue sur l'encodeur (décrochage = la coupole ne suit
plus la vitesse demandée).

**Usage** (ne modifie ni la config ni les services) :
```bash
python3 scripts/diagnostics/calibration_vitesse_encodeur.py --dry-run
python3 scripts/diagnostics/calibration_vitesse_encodeur.py
python3 scripts/diagnostics/calibration_vitesse_encodeur.py --depuis 130
```

**Résultat** : rapport `logs/diagnostics/calibration_vitesse_YYYYMMDD_HHMMSS.json`
avec la valeur recommandée pour `motor_driver.fast_delay_us`.

---

### 4. `pluie_manual.py`

**Objectif** : valider sur le terrain le capteur de pluie MH-RD lu par le Shelly Plus Uni (192.168.1.87), avec signal lumineux et sonore — l'écran d'exploitation est à l'intérieur de la coupole, le capteur dehors.

**Prérequis** : aucun. Python 3 stdlib pure, aucune dépendance, aucune configuration. Se lance depuis n'importe quelle machine du réseau local — de préférence le portable emporté à côté du capteur.

**Récupérer le script sur le portable** (une seule fois) :

```bash
scp slenk@<ip-du-pi>:~/DriftApp/scripts/diagnostics/pluie_manual.py .
```

Le fichier est autonome : rien d'autre à copier. Les commandes ci-dessous sont écrites depuis la racine du dépôt (cas d'un lancement sur le Pi) ; une fois le fichier copié seul sur le portable, remplacer `scripts/diagnostics/pluie_manual.py` par `pluie_manual.py`.

**Marche à suivre**

1. **Avant de sortir**, vérifier que le son fonctionne sur cette machine :

   ```bash
   python3 scripts/diagnostics/pluie_manual.py monitor --demo
   ```

   Trois signaux doivent être audibles : montant (sec → pluie), descendant (pluie → sec), trois coups graves (Shelly injoignable). Le programme annonce au démarrage lequel il utilise. S'il affiche `son : BEL terminal`, le bip dépend de l'émulateur : monter le volume, ou changer de machine. `Ctrl-C` pour sortir.

2. **Identifier l'entrée et la polarité** — la commande du verre d'eau :

   ```bash
   python3 scripts/diagnostics/pluie_manual.py read
   ```

   Arroser la plaque, relancer. L'entrée dont l'état change est celle du capteur. Si l'interprétation est à l'envers (`PLUIE` affiché alors que la plaque est sèche), ajouter `--invert` à toutes les commandes suivantes.

3. **Régler le trimpot** du module : le tourner dans le sens des aiguilles d'une montre augmente la sensibilité. Chercher le point où quelques gouttes suffisent à faire basculer, sans que la rosée du matin déclenche.

4. **Campagne de mesure** — c'est elle qui donne le temps de séchage :

   ```bash
   python3 scripts/diagnostics/pluie_manual.py monitor
   ```

   Arroser franchement, **noter l'heure du dernier arrosage**, puis laisser tourner sans y toucher jusqu'au retour au vert. `Ctrl-C` affiche le résumé : la durée de l'épisode PLUIE le plus long est le temps de séchage recherché.

**Ce qu'il faut nous renvoyer**

Le fichier `pluie_test_<horodatage>.log` créé dans le répertoire d'où la commande a été lancée : il contient toutes les transitions horodatées **et** le résumé final. Ne pas rediriger la sortie de l'écran vers un fichier (`> sortie.txt`) : elle est pleine de codes d'affichage et illisible — c'est le `.log` qui fait foi.

Y joindre les réponses à deux questions : quelle entrée (`id=0` ou `id=1`) porte le capteur, et `--invert` a-t-il été nécessaire.

Si le résumé affiche une ligne `⚠ ... épisode(s) INJOIGNABLE`, c'est que la liaison avec le Shelly a été perdue en cours de route : le temps de séchage annoncé est peut-être sous-estimé, le signaler.

**Options** : `--host` (IP du Shelly), `--input {0,1,both}`, `--interval` (secondes entre deux lectures), `--timeout` (timeout HTTP), `--invert`, `--no-sound`, `--log CHEMIN`, `--no-log`, `--demo`.

**Note** : ce script ne pilote rien et ne décide rien — il lit et il affiche. Le capteur n'est pas encore branché à l'automatisation du cimier.

---

## 📊 Interprétation des résultats

### TEST A : Boucle moteur

| Outliers | Interprétation |
|----------|----------------|
| < 0.1% | ✅ Parfait |
| 0.1-1% | ⚠️ Acceptable |
| > 1% | ❌ Problème timing |

### TEST B : Motor Service

| Observation moyenne | Interprétation |
|---------------------|----------------|
| 1-2 | ✅ Fluide |
| 2-3 | ⚠️ Micro-hésitations |
| 3-4 | ❌ Saccades |
| 4-5 | ❌ Très saccadé |

### Calibration vitesse

Validé terrain le 27/09/2026 : tous les paliers tenus jusqu'à 124 µs/pas
(~90°/min à l'encodeur). Le rapport JSON donne la limite mesurée et la valeur
recommandée.

---

## 🔧 Diagnostic rapide

### Symptôme : Saccades lors des GOTO

1. **Vérifier la version** : DriftApp v4.4+ résout ce problème
2. **Si < v4.4** : Le feedback cause les saccades (pauses de 130ms)
3. **Solution** : Mettre à jour vers v4.4

### Symptôme : Moteur ne tourne pas

1. Vérifier GPIO avec `gpio readall`
2. Vérifier alimentation driver
3. Tester avec `diagnostic_moteur_complet.py`

### Symptôme : Position incorrecte

1. Vérifier calibration encodeur
2. Vérifier `/dev/shm/ems22_position.json`
3. Vérifier `calibration_factor` dans config.json

---

## 📁 Fichiers générés

Les scripts génèrent leurs rapports dans `logs/diagnostics/` (depuis la 6.22 ;
les rapports plus anciens sont restés à la racine de `logs/`) :

```
logs/
├── diagnostics/
│   ├── diagnostic_moteur_YYYYMMDD_HHMMSS.txt
│   ├── calibration_vitesse_YYYYMMDD_HHMMSS.json
│   └── hardware_detection.txt
├── moteur/      motor_service_*.log (un par démarrage et par session de suivi)
├── encodeur/    ems22d_*.log
├── cimier/      cimier_service.log
├── web/         django_*.log
└── update.log, update_status.json, restart*.json   (mises à jour : restent à la racine)
```

---

## ⚠️ Notes importantes

1. **TEST A** nécessite d'arrêter tous les services (conflit GPIO)
2. **TEST B** et **Calibration** nécessitent Motor Service actif
3. **Calibration** nécessite le patch `test_speed` (temporaire)
4. Toujours créer un backup avant modification

---

**Dernière mise à jour** : 17 décembre 2025
