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

### 3. `calibration_vitesse_max.py`

**Objectif** : Trouver la vitesse maximale atteignable sans saccades.

**Prérequis** :
- Motor Service **patché** avec commande `test_speed`
- Ou utiliser le Motor Service modifié (motor_service_with_test_speed.py)

**Usage** :
```bash
# 1. Patcher le Motor Service (temporairement)
cp services/motor_service.py services/motor_service.py.backup
cp motor_service_with_test_speed.py services/motor_service.py
sudo ./start_web.sh restart

# 2. Lancer la calibration
python3 tests/calibration_vitesse_max.py

# 3. Restaurer le Motor Service original
cp services/motor_service.py.backup services/motor_service.py
sudo ./start_web.sh restart
```

**Ce qu'il teste** :
- Vitesses de 0.55ms à 0.12ms
- Observation utilisateur (1-5)
- Identification vitesse max fluide

**Résultat** :
- Rapport dans `logs/calibration_vitesse_YYYYMMDD_HHMMSS.txt`
- Recommandation pour config.json

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

| Délai | Résultat typique |
|-------|------------------|
| 0.55 ms | ✅ Fluide |
| 0.30 ms | ✅ Fluide |
| 0.15 ms | ✅/⚠️ Limite |
| 0.12 ms | ❌ Saccadé |

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

Les scripts génèrent des rapports dans `logs/` :

```
logs/
├── diagnostic_moteur_YYYYMMDD_HHMMSS.txt
├── calibration_vitesse_YYYYMMDD_HHMMSS.txt
└── motor_service.log
```

---

## ⚠️ Notes importantes

1. **TEST A** nécessite d'arrêter tous les services (conflit GPIO)
2. **TEST B** et **Calibration** nécessitent Motor Service actif
3. **Calibration** nécessite le patch `test_speed` (temporaire)
4. Toujours créer un backup avant modification

---

**Dernière mise à jour** : 17 décembre 2025
