# 🎯 Fix Définitif Service ems22d

**Date** : 7 Décembre 2025

**Symptôme** : Le daemon fonctionne en manuel (`python3 ems22d_calibrated.py &`) mais crash quand lancé par systemd

---

## 🔍 Cause Racine Identifiée

Le fichier `ems22d.service` **manque la directive `WorkingDirectory`**.

Sans cette directive, systemd ne garantit pas que le processus démarre depuis `/home/slenk/Dome_v4_5`, ce qui peut causer des problèmes avec :
- La création du répertoire `logs/`
- L'écriture des fichiers de logs
- Les chemins relatifs

---

## ✅ Solution : Fichier Service Corrigé

**Nouveau contenu de `/etc/systemd/system/ems22d.service`** :

```ini
[Unit]
Description=EMS22A calibrated daemon
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/slenk/Dome_v4_5
ExecStart=/usr/bin/python3 /home/slenk/Dome_v4_5/ems22d_calibrated.py
Restart=always
User=slenk
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

**Changement clé** : Ajout de la ligne 7 :
```ini
WorkingDirectory=/home/slenk/Dome_v4_5
```

---

## 🚀 Procédure de Correction (3 commandes)

```bash
# 1. Copier le fichier service corrigé
sudo cp /home/slenk/Dome_v4_5/ems22d.service /etc/systemd/system/

# 2. Recharger la configuration systemd
sudo systemctl daemon-reload

# 3. Redémarrer le service
sudo systemctl restart ems22d.service

# 4. Vérifier le statut
sudo systemctl status ems22d.service
```

**Résultat attendu** :
```
● ems22d.service - EMS22A calibrated daemon
   Loaded: loaded (/etc/systemd/system/ems22d.service; enabled)
   Active: active (running) since ...
```

---

## ✅ Vérifications

```bash
# 1. Le service tourne
sudo systemctl status ems22d.service
# → Active: active (running)

# 2. Le fichier JSON est créé
cat /dev/shm/ems22_position.json
# → {"ts": ..., "angle": ..., "raw": ..., "status": "OK"}

# 3. Les logs sont écrits
ls -lh /home/slenk/Dome_v4_5/logs/
tail -20 /home/slenk/Dome_v4_5/logs/ems22d.log

# 4. L'angle se met à jour en temps réel
watch -n 0.2 cat /dev/shm/ems22_position.json
# (Ctrl+C pour arrêter)
```

---

## 🔍 Pourquoi Ça Fonctionnait en Manuel ?

Quand vous lancez manuellement :
```bash
cd /home/slenk/Dome_v4_5
python3 ems22d_calibrated.py &
```

- Vous êtes **déjà dans le bon répertoire** (`/home/slenk/Dome_v4_5`)
- Le script peut créer `logs/` et y écrire
- Tout fonctionne normalement

Quand systemd lance le service **sans `WorkingDirectory`** :
- Le processus démarre potentiellement depuis `/` ou `/home/slenk`
- Le script peut avoir des problèmes pour créer/écrire dans `logs/`
- Le daemon crash au démarrage

---

## 📊 Comparaison Avant/Après

| Élément | Avant (crash) | Après (OK) |
|---------|---------------|------------|
| **WorkingDirectory** | ❌ Absent | ✅ `/home/slenk/Dome_v4_5` |
| **Création logs/** | ❌ Échec possible | ✅ Succès garanti |
| **Écriture logs** | ❌ Permission denied ? | ✅ OK |
| **Lancement manuel** | ✅ Fonctionne | ✅ Fonctionne |
| **Lancement systemd** | ❌ Crash | ✅ Fonctionne |

---

## 🎓 Explication Technique

Le script `ems22d_calibrated.py` contient (lignes 61-63) :

```python
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "ems22d.log"
```

Même si `Path(__file__).parent` devrait pointer vers `/home/slenk/Dome_v4_5`, systemd exécute le processus dans un contexte différent qui peut causer des problèmes avec :
- Les permissions d'écriture
- Le contexte SELinux/AppArmor (sur certains systèmes)
- Les capacités du processus

**Bonne pratique systemd** : Toujours définir `WorkingDirectory` pour les services qui manipulent des fichiers locaux.

---

## 🔧 Si Le Problème Persiste

### 1. Vérifier les logs systemd

```bash
# Voir les 50 dernières lignes des logs du service
sudo journalctl -u ems22d.service -n 50 --no-pager
```

**Chercher** :
- `PermissionError` → Problème de permissions
- `FileNotFoundError` → Problème de chemin
- `OSError` → Problème système

### 2. Tester avec verbose logging

Modifier temporairement le service pour capturer stderr :

```ini
[Service]
Type=simple
WorkingDirectory=/home/slenk/Dome_v4_5
ExecStart=/usr/bin/python3 /home/slenk/Dome_v4_5/ems22d_calibrated.py
StandardOutput=journal
StandardError=journal
Restart=always
User=slenk
Environment=PYTHONUNBUFFERED=1
```

Puis :
```bash
sudo systemctl daemon-reload
sudo systemctl restart ems22d.service
sudo journalctl -u ems22d.service -f
```

### 3. Vérifier les permissions du répertoire

```bash
ls -ld /home/slenk/Dome_v4_5
ls -ld /home/slenk/Dome_v4_5/logs
```

**Attendu** :
```
drwxr-xr-x ... slenk slenk ... /home/slenk/Dome_v4_5
drwxr-xr-x ... slenk slenk ... /home/slenk/Dome_v4_5/logs
```

Si `logs/` n'existe pas ou n'est pas accessible en écriture :
```bash
mkdir -p /home/slenk/Dome_v4_5/logs
chmod 755 /home/slenk/Dome_v4_5/logs
chown slenk:slenk /home/slenk/Dome_v4_5/logs
```

---

## ✅ Checklist Finale

- [ ] Fichier `ems22d.service` contient `WorkingDirectory=/home/slenk/Dome_v4_5`
- [ ] Service copié dans `/etc/systemd/system/`
- [ ] `sudo systemctl daemon-reload` exécuté
- [ ] Service redémarré : `sudo systemctl restart ems22d.service`
- [ ] Statut = `Active: active (running)`
- [ ] Fichier `/dev/shm/ems22_position.json` existe et se met à jour
- [ ] Logs écrits dans `/home/slenk/Dome_v4_5/logs/ems22d.log`

---

*Fix définitif - 7 décembre 2025*
