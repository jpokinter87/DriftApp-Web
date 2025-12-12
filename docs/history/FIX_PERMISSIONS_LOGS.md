# 🔧 Fix Permissions Logs - Solution Immédiate

**Date** : 7 Décembre 2025

**Erreur** :
```
PermissionError: [Errno 13] Permission denied: '/home/slenk/Dome_v4_5/logs/ems22d.log'
```

---

## 🎯 Cause

Le répertoire `logs/` ou le fichier `ems22d.log` appartient à **root** (créé lors d'un test avec `sudo`), et l'utilisateur `slenk` ne peut pas écrire dedans.

---

## ✅ Solution en 2 Commandes

```bash
# 1. Donner la propriété du répertoire logs à slenk
sudo chown -R slenk:slenk /home/slenk/Dome_v4_5/logs

# 2. Lancer le daemon
python3 /home/slenk/Dome_v4_5/ems22d_calibrated.py &
```

**IMPORTANT** : Ne plus utiliser `sudo python3` pour lancer le daemon !

---

## ✅ Pour le Service Systemd

```bash
# 1. Nettoyer les permissions
sudo chown -R slenk:slenk /home/slenk/Dome_v4_5/logs

# 2. Copier le fichier service corrigé (avec WorkingDirectory)
sudo cp /home/slenk/Dome_v4_5/ems22d.service /etc/systemd/system/

# 3. Recharger et redémarrer
sudo systemctl daemon-reload
sudo systemctl restart ems22d.service
sudo systemctl status ems22d.service
```

---

## 🔍 Vérification

```bash
# Vérifier les permissions du répertoire logs
ls -ld /home/slenk/Dome_v4_5/logs
# Devrait afficher : drwxr-xr-x ... slenk slenk ... /home/slenk/Dome_v4_5/logs

# Vérifier le contenu
ls -lh /home/slenk/Dome_v4_5/logs/
# Tous les fichiers doivent appartenir à slenk

# Si un fichier appartient encore à root
sudo chown slenk:slenk /home/slenk/Dome_v4_5/logs/ems22d.log*
```

---

## 📊 Explication Complète

### Ce qui s'est passé :

1. **Premier test** : Vous avez lancé avec `sudo python3 ems22d_calibrated.py`
   - Le daemon a créé `logs/` et `ems22d.log` appartenant à **root**

2. **Deuxième test** : Vous lancez sans `sudo` avec utilisateur `slenk`
   - Le script essaie d'écrire dans `logs/ems22d.log`
   - **Permission denied** car le fichier appartient à root

3. **Service systemd** : Configure `User=slenk`
   - Même problème : le fichier log appartient à root
   - Le service crash au démarrage

### Solution permanente :

- ✅ Le répertoire `logs/` doit appartenir à `slenk`
- ✅ Tous les fichiers dans `logs/` doivent appartenir à `slenk`
- ✅ Ne **jamais** lancer le daemon avec `sudo` (sauf pour le service systemd qui gère ça correctement)

---

## 🎓 Bonne Pratique

**Pour tester manuellement** :
```bash
# BON (sans sudo)
cd /home/slenk/Dome_v4_5
python3 ems22d_calibrated.py &

# MAUVAIS (crée des fichiers root)
sudo python3 ems22d_calibrated.py &
```

**Pour le service systemd** :
```bash
# Le service tourne avec User=slenk
# Les logs seront créés automatiquement avec le bon propriétaire
sudo systemctl start ems22d.service
```

---

## ✅ Checklist Finale

- [ ] `sudo chown -R slenk:slenk /home/slenk/Dome_v4_5/logs` exécuté
- [ ] Vérifier : `ls -ld /home/slenk/Dome_v4_5/logs` montre `slenk slenk`
- [ ] Fichier service contient `WorkingDirectory=/home/slenk/Dome_v4_5`
- [ ] Service redémarré : `sudo systemctl restart ems22d.service`
- [ ] Statut OK : `sudo systemctl status ems22d.service` → `active (running)`
- [ ] Fichier JSON créé : `cat /dev/shm/ems22_position.json`
- [ ] Logs écrits : `tail /home/slenk/Dome_v4_5/logs/ems22d.log`

---

*Fix permissions - 7 décembre 2025*
