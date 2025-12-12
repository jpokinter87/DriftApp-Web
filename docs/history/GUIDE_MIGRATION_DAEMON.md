# Migration vers Architecture Démon Encodeur

## Résumé

Le démon isole la lecture SPI de l'encodeur pour éviter les interférences avec le moteur.

## Installation

### 1. Arrêter le programme principal
```bash
# Si DriftApp tourne, l'arrêter (Ctrl+C)
```

### 2. Lancer le démon encodeur
```bash
# Rendre exécutable et lancer en arrière-plan
chmod +x ems22d_calibrated.py
sudo python3 ems22d_calibrated.py &

# Vérifier qu'il fonctionne
cat /dev/shm/ems22_position.json
# Devrait afficher: {"ts": ..., "angle": ..., "raw": ..., "status": "OK"}
```

### 3. Configuration systemd (optionnel, pour démarrage automatique)
```bash
# Créer le service
sudo nano /etc/systemd/system/ems22-daemon.service
```

Contenu:
```ini
[Unit]
Description=EMS22A Encoder Daemon
After=network.target

[Service]
Type=simple
User=pi
ExecStart=/usr/bin/python3 /home/pi/DriftApp/ems22d_calibrated.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
# Activer et démarrer
sudo systemctl daemon-reload
sudo systemctl enable ems22-daemon
sudo systemctl start ems22-daemon
sudo systemctl status ems22-daemon
```

## Fichiers à remplacer

1. **moteur.py** → moteur_daemon.py
2. **moteur_feedback.py** → moteur_feedback_daemon.py  
3. **tracker.py** → Ajouter patch au début

## Modifications du code

### Dans main.py
```python
# Au début, après les imports
from core.tracking.tracker_daemon import patch_tracker_for_daemon
patch_tracker_for_daemon()

# Le reste du code reste identique
```

### Dans main_screen.py (si nécessaire)
```python
# Pour lire la position
from core.hardware.moteur import MoteurCoupole
try:
    position = MoteurCoupole.get_daemon_angle()
    self.status_label.update(f"Position: {position:.1f}°")
except RuntimeError:
    self.status_label.update("Encodeur: N/A")
```

## Vérification

```bash
# Test rapide
python3 -c "
from moteur_daemon import MoteurCoupole
try:
    pos = MoteurCoupole.get_daemon_angle()
    print(f'✅ Position: {pos:.1f}°')
except Exception as e:
    print(f'❌ Erreur: {e}')
"
```

## Avantages

- **Isolation SPI** : Plus d'interférences pendant les mouvements
- **Stabilité** : Le démon continue même si le programme principal crash
- **Performance** : Lecture à 50 Hz indépendamment du programme
- **Simplicité** : Une seule source de vérité dans `/dev/shm`

## Dépannage

### Le démon ne démarre pas
```bash
# Vérifier SPI activé
ls /dev/spidev*
# Si vide: sudo raspi-config → Interface Options → SPI → Enable

# Tester SPI directement
python3 -c "import spidev; s=spidev.SpiDev(); s.open(0,0); print('OK')"
```

### Position aberrante
```bash
# Tuer et relancer le démon
sudo pkill -f ems22d_calibrated
sudo uv run ems22d_calibrated.py &
```

### Performances
```bash
# Surveiller le démon
tail -f /dev/shm/ems22_position.json
# La valeur "ts" (timestamp) doit changer ~50 fois/seconde
```

## Retour en arrière

Si besoin de revenir à l'ancienne architecture:
1. Arrêter le démon: `sudo systemctl stop ems22-daemon`
2. Restaurer les fichiers originaux
3. Redémarrer DriftApp

## Notes

- Les modules `encoder_manager.py` et `encoder_singleton.py` ne sont plus nécessaires
- Le démon consomme < 5% CPU sur un Pi 4
- Le fichier JSON est en RAM (/dev/shm), pas d'usure SD
