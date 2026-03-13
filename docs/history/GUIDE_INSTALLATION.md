# Guide d'Installation et d'Utilisation - DriftApp v4.3 Web

## Vue d'ensemble

Cette version ajoute une interface web en plus de l'interface TUI existante.

**Architecture des processus :**
```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Django Web     │────▶│  Motor Service  │────▶│ Encoder Daemon  │
│  (Port 8000)    │ IPC │  (GPIO/Simul)   │ SPI │ (ems22d)        │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

---

## 0. Mise à Jour Rapide du Daemon Encodeur (Service Systemd)

Si le daemon encodeur tourne déjà comme service systemd (`ems22d.service`), voici comment le mettre à jour après modification de `ems22d_calibrated.py` :

### Commande rapide (une seule ligne)
```bash
sudo systemctl restart ems22d
```

### Commande détaillée avec vérification
```bash
# 1. Arrêter le service
sudo systemctl stop ems22d

# 2. Vérifier qu'il est bien arrêté
sudo systemctl status ems22d

# 3. Redémarrer le service (charge automatiquement le nouveau code)
sudo systemctl start ems22d

# 4. Vérifier le démarrage et les logs
sudo systemctl status ems22d
journalctl -u ems22d -f    # Logs en temps réel (Ctrl+C pour quitter)
```

### Si le chemin du fichier a changé
```bash
# Éditer le fichier service
sudo nano /etc/systemd/system/ems22d.service

# Modifier les lignes WorkingDirectory et ExecStart:
# WorkingDirectory=/home/slenk/Dome_v4_3
# ExecStart=/usr/bin/python3 /home/slenk/Dome_v4_3/ems22d_calibrated.py

# Recharger la configuration systemd
sudo systemctl daemon-reload

# Redémarrer le service
sudo systemctl restart ems22d
```

### Vérifier que le nouveau code est actif
```bash
# Voir le dernier fichier log créé (horodaté par session)
ls -lt /home/slenk/Dome_v4_3/logs/ems22d_*.log | head -1

# Suivre les logs en direct
tail -f /home/slenk/Dome_v4_3/logs/ems22d_*.log
```

---

## 1. Installation sur le Raspberry Pi

### 1.1 Cloner sans supprimer l'ancienne version

```bash
# Garder l'ancienne version intacte
cd /home/pi/PythonProject
mv Dome_v4_3 Dome_v4_3_backup    # Optionnel: renommer l'ancienne

# Cloner la nouvelle version (ou copier via USB/SCP)
# Option A: Depuis Git
git clone <url_du_repo> Dome_v4_3

# Option B: Copie depuis PC (depuis le PC)
scp -r /home/jp/PythonProject/Dome_v4_3 pi@raspberrypi:/home/pi/PythonProject/
```

### 1.2 Installer les dépendances avec uv

```bash
cd /home/pi/PythonProject/Dome_v4_3

# Si uv n'est pas installé
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc

# Créer l'environnement et installer les dépendances
uv sync

```
---

## 2. Démarrage des Services

### 2.1 Mode Production (Raspberry Pi)

```bash
cd /home/pi/PythonProject/Dome_v4_3

# Démarrer TOUS les services (nécessite sudo pour GPIO)
sudo ./start_web.sh

# Vérifier l'état
./start_web.sh status

# Arrêter tous les services
sudo ./start_web.sh stop

# Redémarrer
sudo ./start_web.sh restart
```

**Ce que fait `start_web.sh` :**
1. Lance le daemon encodeur (`ems22d_calibrated.py`)
2. Lance le Motor Service (`services/motor_service.py`)
3. Lance Django (`web/manage.py runserver`)

### 2.2 Mode Développement (PC - Simulation)

```bash
cd /home/jp/PythonProject/Dome_v4_3

# Pas besoin de sudo (mode simulation)
./start_dev.sh

# État des services
./start_dev.sh status

# Arrêter
./start_dev.sh stop
```

**Différence dev/prod :**
- `start_web.sh` : Nécessite sudo, lance le daemon encodeur (GPIO réel)
- `start_dev.sh` : Pas de sudo, mode simulation automatique

---

## 3. Accès à l'Interface Web

### 3.1 Ouvrir le navigateur

Une fois les services démarrés, ouvrir un navigateur web (Firefox, Chrome, etc.) :

| Depuis | URL | Exemple |
|--------|-----|---------|
| **Raspberry Pi** (local) | http://localhost:8000 | Directement sur le Pi |
| **PC/Tablette** (réseau) | http://raspberrypi.local:8000 | Si mDNS fonctionne |
| **PC/Tablette** (IP directe) | http://IP_DU_PI:8000 | http://192.168.1.42:8000 |

### 3.2 Trouver l'adresse IP du Raspberry Pi

```bash
# Sur le Raspberry Pi, exécuter :
hostname -I
# Exemple de résultat : 192.168.1.42

# Ou plus détaillé :
ip addr show wlan0 | grep inet
```

### 3.3 Ouvrir automatiquement le navigateur (sur le Pi)

```bash
# Ouvrir Firefox avec l'interface
firefox http://localhost:8000 &

# Ou Chromium
chromium-browser http://localhost:8000 &

# Mode kiosk (plein écran, sans barre d'adresse)
chromium-browser --kiosk http://localhost:8000 &
```

### 3.4 Accès depuis un smartphone/tablette

1. Connecter le téléphone au même réseau WiFi que le Pi
2. Ouvrir le navigateur du téléphone
3. Entrer : `http://IP_DU_PI:8000` (ex: `http://192.168.1.42:8000`)

### 3.5 Vérifier que l'interface répond

```bash
# Test rapide depuis le terminal
curl -s http://localhost:8000/api/hardware/status/ | head -5

# Doit afficher du JSON avec "status", "position", etc.
```

---

## 4. Commandes Utiles

### 4.1 Gestion des processus

```bash
# Voir les processus DriftApp
ps aux | grep -E "(motor_service|ems22d|manage.py)"

# Arrêter proprement tout
./start_web.sh stop   # ou start_dev.sh stop

# Arrêt forcé (si nécessaire)
sudo pkill -f motor_service.py
sudo pkill -f ems22d_calibrated
pkill -f "manage.py runserver"

# Vérifier les ports utilisés
ss -tlnp | grep 8000
```

### 4.2 Logs

```bash
# Motor Service
tail -f logs/motor_service.log

# Daemon Encodeur (un fichier par session)
ls -lt logs/ems22d_*.log | head -5     # Derniers fichiers
tail -f logs/ems22d_*.log              # Dernier fichier

# Django (dans le terminal ou)
# Les erreurs Django apparaissent dans le terminal de start_web.sh
```

### 4.3 Fichiers IPC (mémoire partagée)

```bash
# Position encodeur
cat /dev/shm/ems22_position.json | python3 -m json.tool

# État Motor Service
cat /dev/shm/motor_status.json | python3 -m json.tool

# Commandes envoyées au Motor Service
cat /dev/shm/motor_command.json | python3 -m json.tool
```

---

## 5. Dépannage

### 5.1 Le daemon encodeur ne démarre pas

```bash
# Vérifier si déjà en cours
pgrep -f ems22d_calibrated

# Vérifier les permissions SPI
ls -la /dev/spidev*

# Tester manuellement
sudo python3 ems22d_calibrated.py
```

### 5.2 L'interface web ne répond pas

```bash
# Vérifier Django
curl http://localhost:8000/api/hardware/status/

# Vérifier Motor Service
cat /dev/shm/motor_status.json

# Redémarrer Django seul
pkill -f "manage.py runserver"
cd web && python3 manage.py runserver 0.0.0.0:8000 &
```

### 5.3 Le moteur ne bouge pas

```bash
# Vérifier le Motor Service
./start_web.sh status

# Vérifier les logs
tail -20 logs/motor_service.log

# Vérifier si en mode simulation
grep simulation /dev/shm/motor_status.json
```

---

## 6. Revenir à l'Ancienne Version

```bash
# Arrêter les services actuels
./start_web.sh stop

# Restaurer l'ancienne version
cd /home/pi/PythonProject
mv Dome_v4_3 Dome_v4_3_new
mv Dome_v4_3_backup Dome_v4_3

# Relancer l'ancienne version
cd Dome_v4_3
source .venv/bin/activate
# ... utiliser l'interface TUI ou Kivy
```

---

## 7. Résumé des Commandes

| Action | Commande |
|--------|----------|
| **Démarrer (Pi)** | `sudo ./start_web.sh` |
| **Démarrer (PC)** | `./start_dev.sh` |
| **Arrêter** | `./start_web.sh stop` |
| **État** | `./start_web.sh status` |
| **Logs Motor** | `tail -f logs/motor_service.log` |
| **Logs Encoder** | `tail -f logs/ems22d_*.log` |
| **Position** | `cat /dev/shm/motor_status.json` |

---

## 8. Structure des Fichiers Importants

```
Dome_v4_3/
├── start_web.sh          # Script démarrage PRODUCTION
├── start_dev.sh          # Script démarrage DEV/SIMULATION
├── ems22d_calibrated.py  # Daemon encodeur
├── services/
│   └── motor_service.py  # Service contrôle moteur
├── web/
│   ├── manage.py         # Django
│   ├── templates/
│   │   └── dashboard.html
│   └── static/
│       ├── js/dashboard.js
│       └── css/dashboard.css
├── logs/
│   ├── motor_service.log
│   └── ems22d_YYYYMMDD_HHMMSS.log  # Un par session
└── core/                 # Logique métier (partagée)
```
