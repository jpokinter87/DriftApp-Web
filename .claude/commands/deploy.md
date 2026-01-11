---
description: Deploiement DriftApp sur Raspberry Pi
category: utilities-debugging
argument-hint: [optionnel] etape specifique (check, install, services, all)
---

# Deploiement DriftApp sur Raspberry Pi

Guide de deploiement complet pour production sur Raspberry Pi.

## Instructions

Tu vas deployer DriftApp sur Raspberry Pi : **$ARGUMENTS**

### Etape 1: Verification des Prerequis

```bash
echo "=== VERIFICATION PREREQUIS ==="

# 1. Detecter Raspberry Pi
echo -n "Raspberry Pi: "
if grep -q "Raspberry\|BCM" /proc/cpuinfo; then
    MODEL=$(cat /proc/device-tree/model 2>/dev/null | tr -d '\0')
    echo "OUI - $MODEL"
else
    echo "NON - Ce script est pour Raspberry Pi"
    exit 1
fi

# 2. Version Python
echo -n "Python: "
python3 --version

# 3. uv installe
echo -n "uv: "
uv --version 2>/dev/null || echo "NON INSTALLE - installer avec: curl -LsSf https://astral.sh/uv/install.sh | sh"

# 4. SPI active
echo -n "SPI: "
if ls /dev/spidev* 2>/dev/null; then
    echo "ACTIVE"
else
    echo "DESACTIVE - activer avec: sudo raspi-config → Interface Options → SPI"
fi

# 5. Groupes utilisateur
echo -n "Groupes: "
groups | grep -o "gpio\|spi" | tr '\n' ' '
echo ""
if ! groups | grep -q "gpio"; then
    echo "  ATTENTION: Ajouter au groupe gpio: sudo usermod -aG gpio $USER"
fi
if ! groups | grep -q "spi"; then
    echo "  ATTENTION: Ajouter au groupe spi: sudo usermod -aG spi $USER"
fi
```

### Etape 2: Installation des Dependances

```bash
echo "=== INSTALLATION DEPENDANCES ==="

# 1. Mise a jour systeme
sudo apt update && sudo apt upgrade -y

# 2. Paquets systeme requis
sudo apt install -y python3-dev python3-pip git

# 3. Dependances Python via uv
cd /home/$USER/Dome_web_v4_6  # Adapter le chemin
uv sync

# 4. Verifier installation
uv run python -c "import django; print(f'Django {django.VERSION}')"
uv run python -c "import astropy; print(f'Astropy OK')"
```

### Etape 3: Configuration

```bash
echo "=== CONFIGURATION ==="

# 1. Verifier config.json
if [ -f data/config.json ]; then
    echo "config.json existe"
    # Desactiver simulation pour production
    python3 -c "
import json
with open('data/config.json', 'r') as f:
    config = json.load(f)
if config.get('simulation', False):
    print('ATTENTION: Mode simulation active!')
    print('Pour production: mettre simulation: false')
else:
    print('Mode production OK')
"
else
    echo "ERREUR: data/config.json manquant"
    echo "Copier depuis: cp data/config.example.json data/config.json"
fi

# 2. Verifier abaque
if [ -f data/Loi_coupole.xlsx ]; then
    echo "Abaque present"
else
    echo "ATTENTION: data/Loi_coupole.xlsx manquant"
fi

# 3. Creer repertoire logs
mkdir -p logs
chmod 755 logs
```

### Etape 4: Installation des Services Systemd

```bash
echo "=== INSTALLATION SERVICES SYSTEMD ==="

# Chemin d'installation (adapter si necessaire)
INSTALL_DIR="$(pwd)"
echo "Repertoire: $INSTALL_DIR"

# 1. Adapter les fichiers de service
echo "Adaptation des chemins..."
sed -i "s|/home/slenk/Dome_v4_5|$INSTALL_DIR|g" ems22d.service
sed -i "s|/home/slenk/Dome_v4_5|$INSTALL_DIR|g" motor_service.service

# 2. Copier vers systemd
echo "Copie des services..."
sudo cp ems22d.service /etc/systemd/system/
sudo cp motor_service.service /etc/systemd/system/

# 3. Recharger systemd
sudo systemctl daemon-reload

# 4. Activer au demarrage
echo "Activation au demarrage..."
sudo systemctl enable ems22d.service
sudo systemctl enable motor_service.service

echo "Services installes"
```

### Etape 5: Demarrage des Services

```bash
echo "=== DEMARRAGE SERVICES ==="

# 1. Demarrer encoder daemon (doit etre premier)
echo "Demarrage ems22d..."
sudo systemctl start ems22d.service
sleep 2

# 2. Verifier encoder
if [ -f /dev/shm/ems22_position.json ]; then
    echo "Encoder daemon: OK"
    cat /dev/shm/ems22_position.json
else
    echo "ERREUR: Encoder daemon ne produit pas de donnees"
    sudo journalctl -u ems22d -n 20 --no-pager
    exit 1
fi

# 3. Demarrer motor service
echo "Demarrage motor_service..."
sudo systemctl start motor_service.service
sleep 2

# 4. Verifier motor service
if [ -f /dev/shm/motor_status.json ]; then
    echo "Motor service: OK"
    cat /dev/shm/motor_status.json | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Status: {d.get(\"status\")}')"
else
    echo "ERREUR: Motor service ne produit pas de donnees"
    sudo journalctl -u motor_service -n 20 --no-pager
    exit 1
fi
```

### Etape 6: Demarrage Django

```bash
echo "=== DEMARRAGE DJANGO ==="

# Option 1: Mode developpement (foreground)
cd web
uv run python manage.py runserver 0.0.0.0:8000

# Option 2: Mode production avec gunicorn (recommande)
# pip install gunicorn
# gunicorn --bind 0.0.0.0:8000 driftapp_web.wsgi:application
```

### Etape 7: Test Final

```bash
echo "=== TEST FINAL ==="

# 1. Test API health
echo -n "API Health: "
HEALTH=$(curl -s http://localhost:8000/api/health/)
echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); print('OK' if d.get('status')=='healthy' else 'ERREUR')"

# 2. Test encodeur via API
echo -n "Encodeur: "
curl -s http://localhost:8000/api/hardware/encoder/ | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'{d.get(\"angle\", \"N/A\")}°')"

# 3. Test moteur (JOG +1°)
echo "Test JOG +1°..."
curl -s -X POST http://localhost:8000/api/hardware/jog/ -H "Content-Type: application/json" -d '{"delta": 1.0}'
sleep 2
echo -n "Nouvelle position: "
curl -s http://localhost:8000/api/hardware/encoder/ | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'{d.get(\"angle\", \"N/A\")}°')"

echo ""
echo "=== DEPLOIEMENT TERMINE ==="
echo "Acces: http://$(hostname -I | awk '{print $1}'):8000"
```

### Commandes Utiles Post-Deploiement

```bash
# Voir les logs en temps reel
sudo journalctl -u motor_service -f

# Redemarrer un service
sudo systemctl restart motor_service

# Arreter tous les services
sudo systemctl stop motor_service ems22d

# Desactiver au demarrage
sudo systemctl disable motor_service ems22d

# Mise a jour du code
git pull
uv sync
sudo systemctl restart motor_service ems22d
```

### Troubleshooting

| Probleme | Solution |
|----------|----------|
| SPI non disponible | `sudo raspi-config` → Interface Options → SPI → Enable |
| Permission denied GPIO | `sudo usermod -aG gpio $USER` puis relogin |
| Encoder freeze | Verifier cablage SPI, redemarrer ems22d |
| Motor service crash | Voir logs: `journalctl -u motor_service -n 50` |
| Django 502 | Verifier que gunicorn/runserver est actif |

### Securite Production

Pour un deploiement securise :

```bash
# 1. Firewall (optionnel)
sudo ufw allow 8000/tcp
sudo ufw enable

# 2. HTTPS avec nginx (recommande)
# Installer nginx comme reverse proxy avec certificat SSL

# 3. Utilisateur dedie
sudo useradd -r -s /bin/false driftapp
sudo chown -R driftapp:driftapp /home/$USER/Dome_web_v4_6
```
