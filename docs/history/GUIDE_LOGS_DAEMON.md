# 📋 Guide des Logs du Daemon EMS22D

**Date** : 6 Décembre 2025
**Fichier** : `logs/ems22d.log`

---

## 📁 Emplacement des Logs

Les logs du daemon sont maintenant enregistrés dans :

```
/home/jp/PythonProject/Dome_v4_3/logs/ems22d.log
```

**Rotation automatique** :
- Taille max : **10 MB** par fichier
- Backups : **3 fichiers** conservés
- Fichiers : `ems22d.log`, `ems22d.log.1`, `ems22d.log.2`, `ems22d.log.3`

---

## 🔍 Commandes de Surveillance

### 1. Afficher les Logs en Temps Réel

```bash
# Suivre les logs en direct (comme tail -f)
tail -f logs/ems22d.log
```

**Utilisation** :
- Lancer cette commande **AVANT** de démarrer le daemon
- Observer les logs pendant les tests
- Ctrl+C pour arrêter

### 2. Afficher les Dernières Lignes

```bash
# Afficher les 50 dernières lignes
tail -n 50 logs/ems22d.log

# Afficher les 100 dernières lignes
tail -n 100 logs/ems22d.log
```

### 3. Rechercher un Événement Spécifique

```bash
# Chercher les calibrations switch
grep "Microswitch activé" logs/ems22d.log

# Chercher les erreurs SPI
grep "SPI error" logs/ems22d.log

# Chercher les warnings
grep "WARNING" logs/ems22d.log

# Chercher les logs d'une date précise (exemple : 6 décembre)
grep "2025-12-06" logs/ems22d.log
```

### 4. Afficher les Logs avec Couleurs (plus lisible)

```bash
# Installer ccze si pas déjà fait
sudo apt install ccze

# Afficher avec couleurs
tail -f logs/ems22d.log | ccze -A

# Ou analyser fichier complet
cat logs/ems22d.log | ccze -A | less -R
```

### 5. Nettoyer les Anciens Logs

```bash
# Supprimer TOUS les logs (attention !)
rm logs/ems22d.log*

# Ou simplement vider le fichier actuel
> logs/ems22d.log
```

---

## 📊 Exemple de Logs Attendus

### Démarrage du Daemon

```
[ems22d] 2025-12-06 15:30:12,345 INFO ======================================================================
[ems22d] 2025-12-06 15:30:12,346 INFO Daemon EMS22D avec Switch de Calibration - VERSION CORRIGÉE
[ems22d] 2025-12-06 15:30:12,347 INFO ======================================================================
[ems22d] 2025-12-06 15:30:12,348 INFO Port TCP : 5556
[ems22d] 2025-12-06 15:30:12,349 INFO CALIBRATION_FACTOR : 0.010851
[ems22d] 2025-12-06 15:30:12,350 INFO Switch GPIO : 27 (recalage à 45°)
[ems22d] 2025-12-06 15:30:12,351 INFO Méthode : INCRÉMENTALE (accumulation)
[ems22d] 2025-12-06 15:30:12,352 INFO ======================================================================
[ems22d] 2025-12-06 15:30:12,400 INFO Switch GPIO 27 configuré (pull-up) - état initial : 1
[ems22d] 2025-12-06 15:30:12,450 INFO SPI opened 0.0 @ 500000 Hz
[ems22d] 2025-12-06 15:30:12,500 INFO TCP en écoute 127.0.0.1:5556
```

**Vérifications** :
- ✅ `Switch GPIO 27 configuré - état initial : 1` → Switch correctement initialisé
- ✅ `SPI opened 0.0 @ 500000 Hz` → Encodeur connecté
- ✅ `TCP en écoute 127.0.0.1:5556` → Interface TCP prête

### Passage sur le Switch (Calibration)

```
[ems22d] 2025-12-06 15:35:42,123 INFO 🔄 Microswitch activé → recalage à 45°
[ems22d] 2025-12-06 15:35:42,124 INFO    → total_counts recalé à -11794
[ems22d] 2025-12-06 15:35:42,125 INFO    → angle affiché : 45°
```

**Vérification** :
- ✅ Ligne "🔄 Microswitch activé" → Switch détecté
- ✅ `total_counts recalé` → Recalibration effectuée
- ✅ `angle affiché : 45°` → Angle corrigé

### Erreurs SPI (si encodeur déconnecté)

```
[ems22d] 2025-12-06 15:40:10,456 WARNING SPI error: [Errno 121] Remote I/O error
[ems22d] 2025-12-06 15:40:10,500 WARNING SPI error: [Errno 121] Remote I/O error
[ems22d] 2025-12-06 15:40:10,550 WARNING Réinitialisation SPI…
[ems22d] 2025-12-06 15:40:11,000 INFO SPI opened 0.0 @ 500000 Hz
```

### Jump Aberrant (mouvement trop rapide détecté)

```
[ems22d] 2025-12-06 15:45:20,789 WARNING Jump aberrant détecté: 35.2° - ignoré
```

**Signification** : Mouvement > 30° détecté entre deux lectures → probablement bruit ou erreur, ignoré par filtre.

---

## 🧪 Test de Validation des Logs

### Procédure

```bash
# Terminal 1 : Suivre les logs
tail -f logs/ems22d.log

# Terminal 2 : Lancer le daemon
sudo python3 ems22d_calibrated.py
```

**Résultat attendu (Terminal 1)** :

Vous devriez voir **immédiatement** les logs de démarrage s'afficher dans le fichier logs/ems22d.log.

---

## 🔧 Intégration avec Test Switch

### Configuration Complète (3 Terminaux)

**Terminal 1 : Logs**
```bash
tail -f logs/ems22d.log
```

**Terminal 2 : Daemon**
```bash
sudo python3 ems22d_calibrated.py
```

**Terminal 3 : Boussole**
```bash
python3 boussole.py
```

**Test** : Bouger la coupole vers 45° et observer les 3 terminaux :
- **Terminal 1** : Log "🔄 Microswitch activé → recalage à 45°"
- **Terminal 2** : Affichage console identique (doublon)
- **Terminal 3** : Aiguille saute à 45°

---

## 📝 Cas d'Usage Pratiques

### 1. Debug en Temps Réel

```bash
# Lancer daemon en foreground (affichage console + fichier)
sudo python3 ems22d_calibrated.py

# Dans autre terminal, suivre aussi le fichier
tail -f logs/ems22d.log
```

### 2. Daemon en Background (Production)

```bash
# Lancer daemon en background
sudo python3 ems22d_calibrated.py &

# Suivre les logs (SEULE façon de voir ce qui se passe)
tail -f logs/ems22d.log

# Arrêter daemon
sudo pkill -f ems22d_calibrated
```

### 3. Analyse Post-Mortem

```bash
# Après un test, analyser les logs
cat logs/ems22d.log | grep "Microswitch"

# Ou extraire logs d'une session précise
grep "2025-12-06 15:3" logs/ems22d.log > test_switch_15h30.log
```

---

## ⚠️ Points Importants

1. **Fichier créé automatiquement** :
   - Le fichier `logs/ems22d.log` est créé au **premier démarrage** du daemon
   - Si absent avant, c'est normal

2. **Rotation automatique** :
   - Quand `ems22d.log` atteint 10 MB → renommé en `ems22d.log.1`
   - `ems22d.log.1` → `ems22d.log.2`
   - `ems22d.log.2` → `ems22d.log.3`
   - `ems22d.log.3` → supprimé
   - Nouveau `ems22d.log` créé

3. **Permissions** :
   - Daemon lancé avec `sudo` → fichier log appartient à **root**
   - Pour lire : `cat logs/ems22d.log` (pas besoin sudo)
   - Pour modifier/supprimer : `sudo rm logs/ems22d.log*`

4. **Double Affichage** :
   - Mode foreground : logs visibles **console + fichier**
   - Mode background : logs uniquement dans **fichier**

---

**Version** : 1.0
**Date** : 6 Décembre 2025
**Fichier** : `logs/ems22d.log`
