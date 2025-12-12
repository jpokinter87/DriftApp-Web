# ⚡ Fix Rapide Service ems22d

**Problème** : Le service crash au démarrage avec "status=1/FAILURE"

**Cause probable** : Modules Python `lgpio` et `spidev` manquants pour Python système

---

## 🎯 Diagnostic en 1 Commande

```bash
# Tester si les modules sont présents
/usr/bin/python3 -c "import lgpio; import spidev; print('✅ Modules OK')"
```

**Si erreur `ModuleNotFoundError`** → C'est bien ça !

---

## 🚀 Solution Rapide (30 secondes)

```bash
# 1. Installer les modules pour Python système
sudo pip3 install lgpio spidev

# 2. Redémarrer le service
sudo systemctl restart ems22d.service

# 3. Vérifier le statut
sudo systemctl status ems22d.service
```

**Statut attendu** : `Active: active (running)` (en vert)

---

## ✅ Vérification Finale

```bash
# Le fichier JSON doit exister et se mettre à jour
cat /dev/shm/ems22_position.json

# Surveiller les changements (Ctrl+C pour arrêter)
watch -n 0.2 cat /dev/shm/ems22_position.json

# Vérifier les logs
tail -f /home/slenk/Dome_v4_5/logs/ems22d.log
```

---

## 🔍 Si Ça Ne Marche Toujours Pas

### Voir l'erreur exacte :
```bash
# Arrêter le service
sudo systemctl stop ems22d.service

# Lancer manuellement (affiche l'erreur Python)
cd /home/slenk/Dome_v4_5
/usr/bin/python3 ems22d_calibrated.py
# Ctrl+C pour arrêter
```

### Consulter les guides complets :
- **DIAGNOSTIC_VRAI_PROBLEME.md** - Analyse complète
- **DIAGNOSTIC_SERVICE_DAEMON.md** - Autres erreurs possibles

---

## 📊 Pourquoi Ça Fonctionnait Avant ?

Dans `Dome_v4_3`, les modules `lgpio` et `spidev` étaient probablement installés **système-wide**.

En copiant vers `Dome_v4_5`, les fichiers Python ont été copiés mais **pas les modules Python installés**.

Le service utilise `/usr/bin/python3` (Python système), pas l'environnement virtuel `.venv`.

---

*Fix rapide - 7 décembre 2025 - Version 2.0*
