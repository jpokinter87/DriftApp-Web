---
description: Diagnostic complet du systeme DriftApp
category: utilities-debugging
argument-hint: [optionnel] composant specifique (motor, encoder, ipc, all)
---

# Diagnostic Systeme DriftApp

Effectue un diagnostic complet du systeme de controle de coupole.

## Instructions

Tu vas analyser l'etat du systeme DriftApp en suivant cette procedure : **$ARGUMENTS**

### 1. Detection de l'Environnement

Commence par determiner l'environnement d'execution :

```bash
# Verifier si on est sur Raspberry Pi
cat /proc/cpuinfo | grep -i "raspberry\|bcm" || echo "Pas un Raspberry Pi"

# Verifier si les services systemd existent
systemctl list-unit-files | grep -E "ems22d|motor_service" || echo "Services non installes"
```

### 2. Verification des Services

Si sur Raspberry Pi en production :

```bash
# Etat du daemon encodeur
sudo systemctl status ems22d.service --no-pager -l

# Etat du motor service
sudo systemctl status motor_service.service --no-pager -l
```

### 3. Verification des Fichiers IPC

Verifie l'existence et le contenu des fichiers IPC :

```bash
# Fichier encodeur
ls -la /dev/shm/ems22_position.json 2>/dev/null || echo "ABSENT"
cat /dev/shm/ems22_position.json 2>/dev/null || echo "Lecture impossible"

# Fichier status moteur
ls -la /dev/shm/motor_status.json 2>/dev/null || echo "ABSENT"
cat /dev/shm/motor_status.json 2>/dev/null || echo "Lecture impossible"

# Fichier commandes
ls -la /dev/shm/motor_command.json 2>/dev/null || echo "ABSENT (normal si aucune commande)"
```

### 4. Analyse de Fraicheur

Verifie si les donnees sont fraiches :

- **ems22_position.json** : Doit etre mis a jour toutes les ~20ms (50 Hz)
- **motor_status.json** : Doit etre mis a jour toutes les ~50ms (20 Hz)

Calcule l'age des fichiers et signale si > 1 seconde.

### 5. Verification de la Configuration

```bash
# Lire la config principale
cat data/config.json
```

Verifie :
- `simulation` : true/false selon environnement attendu
- `moteur.microsteps` : Doit correspondre au driver (4 par defaut)
- `site.latitude/longitude` : Coordonnees du site

### 6. Analyse des Logs Recents

```bash
# Logs Motor Service (derniers 50 lignes)
sudo journalctl -u motor_service -n 50 --no-pager 2>/dev/null || \
  tail -50 logs/motor_service*.log 2>/dev/null || \
  echo "Aucun log disponible"

# Logs Encoder Daemon
sudo journalctl -u ems22d -n 20 --no-pager 2>/dev/null || \
  echo "Logs encodeur non disponibles"
```

### 7. Test de Connectivite Django

```bash
# Verifier si Django repond
curl -s http://localhost:8000/api/health/ 2>/dev/null || echo "Django non accessible"
```

### 8. Resume du Diagnostic

Presente un resume clair avec des indicateurs :

```
=== DIAGNOSTIC DRIFTAPP ===

Environnement:
  [ ] Raspberry Pi detecte
  [ ] Mode simulation

Services:
  [OK/ERREUR] Encoder Daemon (ems22d)
  [OK/ERREUR] Motor Service

Fichiers IPC:
  [OK/ABSENT/STALE] ems22_position.json (age: Xs)
  [OK/ABSENT/STALE] motor_status.json (age: Xs)

Configuration:
  [OK/WARN] Microsteps: X
  [OK/WARN] Site: lat/lon

Django:
  [OK/ERREUR] API Health

Recommandations:
  - ...
```

### 9. Recommandations

Selon les problemes detectes, propose des solutions :

- **Encodeur absent** : `sudo systemctl start ems22d` ou verifier SPI
- **Motor Service arrete** : `sudo systemctl start motor_service`
- **Donnees perimees** : Redemarrer le service concerne
- **Config invalide** : Verifier `data/config.json`
- **Django inaccessible** : `cd web && python manage.py runserver 0.0.0.0:8000`

## Mode Simulation

Si aucun Raspberry Pi detecte, indique que le systeme fonctionne en mode simulation et que c'est normal pour le developpement.
