# 🔧 Diagnostic et Correction Service ems22d

**Date** : 7 Décembre 2025
**Problème** : Service ems22d crash au démarrage (code=exited, status=1/FAILURE)

---

## 🚨 Symptômes

```
Active: failed (Result: exit-code)
Process: ExecStart=/usr/bin/python3 /home/slenk/Dome_v4_5/ems22d_calibrated.py (code=exited, status=1/FAILURE)
Duration: 60ms
ems22d.service: Start request repeated too quickly
```

Le daemon crash **immédiatement** (60ms) → Problème de permissions SPI/GPIO

---

## ✅ Solution Complète

### Étape 1 : Vérifier les Logs d'Erreur

```bash
# Voir les logs du service (montre l'erreur Python exacte)
sudo journalctl -u ems22d.service -n 50 --no-pager
```

**Erreur attendue** : `PermissionError` ou `OSError` lié à `/dev/spidev0.0` ou `/dev/gpiochip0`

---

### Étape 2 : Ajouter l'Utilisateur aux Groupes Nécessaires

```bash
# Ajouter slenk aux groupes spi, gpio, dialout
sudo usermod -a -G spi,gpio,dialout slenk

# Vérifier les groupes
groups slenk
# Devrait afficher : slenk ... spi gpio dialout ...
```

⚠️ **IMPORTANT** : Il faut se **déconnecter/reconnecter** pour que les groupes soient actifs !

```bash
# Déconnexion
exit

# Puis se reconnecter via SSH
```

---

### Étape 3 : Mettre à Jour le Fichier Service

```bash
# Copier le nouveau fichier service
sudo cp /home/slenk/Dome_v4_5/ems22d.service /etc/systemd/system/

# Vérifier le contenu
cat /etc/systemd/system/ems22d.service
```

**Contenu attendu** :
```ini
[Unit]
Description=EMS22A calibrated daemon
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /home/slenk/Dome_v4_5/ems22d_calibrated.py
Restart=always
User=slenk
# Ajouter les groupes nécessaires pour SPI et GPIO
SupplementaryGroups=spi gpio dialout
# Variables d'environnement
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

---

### Étape 4 : Recharger et Redémarrer le Service

```bash
# Recharger la configuration systemd
sudo systemctl daemon-reload

# Activer le service (démarrage automatique au boot)
sudo systemctl enable ems22d.service

# Démarrer le service
sudo systemctl start ems22d.service

# Vérifier le statut
sudo systemctl status ems22d.service
```

**Statut attendu (OK)** :
```
● ems22d.service - EMS22A calibrated daemon
   Loaded: loaded (/etc/systemd/system/ems22d.service; enabled)
   Active: active (running) since ...
   Main PID: 1234 (python3)
```

---

### Étape 5 : Vérifier le Fonctionnement

```bash
# 1. Vérifier que le fichier JSON est créé et mis à jour
cat /dev/shm/ems22_position.json
# Devrait afficher : {"ts": 1733587234.5, "angle": 123.45, "raw": 512, "status": "OK"}

# 2. Surveiller les mises à jour (Ctrl+C pour arrêter)
watch -n 0.2 cat /dev/shm/ems22_position.json
# L'angle doit changer quand on bouge la coupole manuellement

# 3. Vérifier les logs du daemon
tail -f /home/slenk/Dome_v4_5/logs/ems22d.log
```

**Logs attendus** :
```
[INFO] ems22d_calibrated démarré - Méthode INCRÉMENTALE
[INFO] Switch GPIO 27 configuré - état initial : 1
[INFO] Lecture encodeur OK - Angle : 123.45°
```

---

## 🔍 Diagnostic Approfondi

### Si le service crash toujours

```bash
# 1. Tester le script manuellement (montre l'erreur Python complète)
cd /home/slenk/Dome_v4_5
sudo python3 ems22d_calibrated.py
# Ctrl+C pour arrêter après quelques secondes si OK
```

**Erreurs possibles** :

#### A) ImportError: No module named 'spidev'
```bash
# Installer spidev
pip3 install spidev
# OU avec uv
cd /home/slenk/Dome_v4_5
uv pip install spidev
```

#### B) ImportError: No module named 'lgpio'
```bash
# Installer lgpio
pip3 install lgpio
# OU avec uv
uv pip install lgpio
```

#### C) PermissionError: [Errno 13] Permission denied: '/dev/spidev0.0'
```bash
# Vérifier les permissions du device SPI
ls -l /dev/spidev0.0
# Devrait afficher : crw-rw---- 1 root spi ...

# Si pas dans le groupe spi :
sudo usermod -a -G spi slenk
# Puis déconnexion/reconnexion
```

#### D) PermissionError: [Errno 13] Permission denied: '/dev/gpiochip0'
```bash
# Vérifier les permissions GPIO
ls -l /dev/gpiochip0
# Devrait afficher : crw-rw---- 1 root gpio ...

# Si pas dans le groupe gpio :
sudo usermod -a -G gpio slenk
# Puis déconnexion/reconnexion
```

---

### Vérifier les Permissions des Devices

```bash
# 1. SPI disponible ?
ls -l /dev/spidev*
# Devrait afficher :
# crw-rw---- 1 root spi ... /dev/spidev0.0
# crw-rw---- 1 root spi ... /dev/spidev0.1

# 2. GPIO disponible ?
ls -l /dev/gpiochip*
# Devrait afficher :
# crw-rw---- 1 root gpio ... /dev/gpiochip0

# 3. Utilisateur dans les bons groupes ?
groups slenk
# Doit inclure : spi gpio dialout
```

---

## 🎯 Checklist Complète

- [ ] Utilisateur `slenk` dans les groupes `spi`, `gpio`, `dialout`
- [ ] Déconnexion/reconnexion effectuée après ajout aux groupes
- [ ] Fichier `/etc/systemd/system/ems22d.service` mis à jour avec `SupplementaryGroups=spi gpio dialout`
- [ ] `sudo systemctl daemon-reload` exécuté
- [ ] SPI activé (`ls /dev/spidev*` retourne des devices)
- [ ] Dépendances Python installées (`spidev`, `lgpio`)
- [ ] Service démarré : `sudo systemctl start ems22d.service`
- [ ] Fichier `/dev/shm/ems22_position.json` créé et mis à jour
- [ ] Logs daemon dans `/home/slenk/Dome_v4_5/logs/ems22d.log` sans erreur

---

## 🚀 Alternative : Exécuter en Root (Non Recommandée)

Si les solutions ci-dessus ne fonctionnent pas, dernière option :

```ini
# /etc/systemd/system/ems22d.service
[Unit]
Description=EMS22A calibrated daemon
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /home/slenk/Dome_v4_5/ems22d_calibrated.py
Restart=always
User=root  # ⚠️ Exécution en root
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl restart ems22d.service
```

⚠️ **Risque de sécurité** : Le daemon tourne avec tous les privilèges root

---

## 📞 Support

Si le problème persiste après toutes ces étapes, envoyer :

1. **Logs systemd** :
```bash
sudo journalctl -u ems22d.service -n 100 --no-pager > /tmp/ems22d_systemd_logs.txt
```

2. **Logs daemon** :
```bash
cat /home/slenk/Dome_v4_5/logs/ems22d.log > /tmp/ems22d_daemon_logs.txt
```

3. **Permissions** :
```bash
ls -l /dev/spidev* /dev/gpiochip* > /tmp/permissions.txt
groups slenk >> /tmp/permissions.txt
```

4. **Test manuel** :
```bash
cd /home/slenk/Dome_v4_5
sudo python3 ems22d_calibrated.py 2>&1 | head -50 > /tmp/manual_test.txt
# Ctrl+C après 5 secondes
```

Envoyer les 4 fichiers `/tmp/ems22d_*.txt`, `/tmp/permissions.txt`, `/tmp/manual_test.txt`

---

*Document créé le 7 décembre 2025 - Version 1.0*
