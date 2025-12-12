# 🎯 Diagnostic : Le Vrai Problème du Service ems22d

**Date** : 7 Décembre 2025
**Contexte** : Le daemon fonctionnait dans Dome_v4_3, crash dans Dome_v4_5

---

## 🔍 Analyse du Crash

Le service crash **immédiatement** (60ms) **AVANT** même d'essayer d'accéder au SPI.

### Ce n'est PAS un problème de permissions !

**Preuve** :
- Le daemon fonctionnait avant dans Dome_v4_3 avec le même utilisateur `slenk`
- Les permissions SPI/GPIO n'ont pas changé
- Un crash à 60ms = erreur Python **avant** le code principal

---

## ⚡ La Vraie Cause : Modules Python Manquants

Le script `ems22d_calibrated.py` utilise :
```python
import lgpio      # Ligne 27
import spidev     # Ligne 30
```

Le service utilise :
```ini
ExecStart=/usr/bin/python3 /home/slenk/Dome_v4_5/ems22d_calibrated.py
```

**Problème** : `/usr/bin/python3` = **Python système** (pas environnement virtuel)

Si `lgpio` et `spidev` ont été installés avec `uv` dans Dome_v4_3, ils sont dans un **venv** que le service systemd ne voit pas !

---

## ✅ Solution 1 : Installer les Modules pour Python Système

```bash
# Installer lgpio et spidev pour le Python système
sudo apt update
sudo apt install -y python3-lgpio python3-spidev

# OU avec pip système (si les paquets Debian n'existent pas)
sudo pip3 install lgpio spidev
```

**Puis redémarrer le service** :
```bash
sudo systemctl restart ems22d.service
sudo systemctl status ems22d.service
```

---

## ✅ Solution 2 : Utiliser l'Environnement Virtuel dans le Service

Modifier le service pour utiliser le Python du venv :

```ini
[Unit]
Description=EMS22A calibrated daemon
After=network.target

[Service]
Type=simple
# Utiliser le Python de l'environnement virtuel
ExecStart=/home/slenk/Dome_v4_5/.venv/bin/python /home/slenk/Dome_v4_5/ems22d_calibrated.py
Restart=always
User=slenk
WorkingDirectory=/home/slenk/Dome_v4_5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

**Puis** :
```bash
# Installer les dépendances dans le venv
cd /home/slenk/Dome_v4_5
uv sync  # ou : source .venv/bin/activate && pip install -r requirements.txt

# Recharger le service
sudo cp ems22d.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart ems22d.service
```

---

## 🔎 Diagnostic Rapide : Voir l'Erreur Exacte

Pour confirmer que c'est bien un problème d'import :

```bash
# Tester manuellement avec le Python système
/usr/bin/python3 -c "import lgpio; import spidev; print('OK')"
```

**Si erreur `ModuleNotFoundError`** → C'est bien ça !

```bash
# Installer les modules manquants
sudo pip3 install lgpio spidev
```

---

## 🎯 Vérification Logs Systemd

Pour voir l'erreur Python exacte :

```bash
sudo journalctl -u ems22d.service -n 50 --no-pager
```

**Erreur attendue** :
```
ModuleNotFoundError: No module named 'lgpio'
```
OU
```
ModuleNotFoundError: No module named 'spidev'
```

---

## 📊 Comparaison Dome_v4_3 vs Dome_v4_5

| Élément | Dome_v4_3 (fonctionnel) | Dome_v4_5 (crash) |
|---------|-------------------------|-------------------|
| **Script Python** | `/home/slenk/Dome_v4_3/ems22d_calibrated.py` | `/home/slenk/Dome_v4_5/ems22d_calibrated.py` |
| **Modules Python** | lgpio, spidev installés (venv ou système) | ❌ Modules manquants ? |
| **Environnement virtuel** | `.venv` avec dépendances | `.venv` pas synchronisé ? |
| **Python utilisé par service** | `/usr/bin/python3` (système) | `/usr/bin/python3` (système) |

**Conclusion** : Les modules étaient installés **système-wide** dans Dome_v4_3, mais pas dans le nouveau serveur ou pas transférés

---

## 🚀 Fix Rapide (30 secondes)

```bash
# 1. Installer les modules manquants
sudo pip3 install lgpio spidev

# 2. Redémarrer le service
sudo systemctl restart ems22d.service

# 3. Vérifier
sudo systemctl status ems22d.service
cat /dev/shm/ems22_position.json
```

**Statut attendu** : `Active: active (running)`

---

## 🔧 Alternative : Debug Mode

Si vous voulez être sûr du problème :

```bash
# Arrêter le service
sudo systemctl stop ems22d.service

# Lancer manuellement (montre l'erreur Python exacte)
cd /home/slenk/Dome_v4_5
/usr/bin/python3 ems22d_calibrated.py

# L'erreur s'affichera en clair :
# - ImportError → modules manquants
# - PermissionError → problème SPI/GPIO (peu probable)
# - OSError → autre problème
```

Ctrl+C pour arrêter une fois le problème identifié

---

## 📌 Résumé

**Problème** : `ModuleNotFoundError` au démarrage (lgpio ou spidev manquant)

**Cause** : Les modules Python ne sont pas installés pour `/usr/bin/python3` (Python système)

**Solution rapide** :
```bash
sudo pip3 install lgpio spidev
sudo systemctl restart ems22d.service
```

**Solution propre** : Utiliser le venv dans le service (voir Solution 2)

---

*Diagnostic mis à jour - 7 décembre 2025*
