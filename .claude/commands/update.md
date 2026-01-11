---
description: Mise a jour du systeme DriftApp
category: utilities-debugging
argument-hint: [optionnel] mode (check, apply, rollback)
---

# Mise a Jour DriftApp

Verifie et applique les mises a jour du systeme.

## Instructions

Tu vas gerer les mises a jour : **$ARGUMENTS**

### 1. Verification des Mises a Jour Disponibles

```bash
echo "=== VERIFICATION MISES A JOUR ==="

# Aller dans le repertoire du projet
cd /home/$USER/Dome_web_v4_6 2>/dev/null || cd "$(dirname "$(pwd)")"

# Sauvegarder la branche actuelle
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
echo "Branche actuelle: $CURRENT_BRANCH"

# Recuperer les mises a jour du remote
echo "Recuperation des informations remote..."
git fetch origin --quiet

# Comparer avec le remote
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/$CURRENT_BRANCH 2>/dev/null || echo "N/A")

echo "Commit local:  ${LOCAL:0:8}"
echo "Commit remote: ${REMOTE:0:8}"

if [ "$LOCAL" = "$REMOTE" ]; then
    echo ""
    echo "[OK] Le systeme est a jour!"
else
    # Compter les commits de retard
    BEHIND=$(git rev-list HEAD..origin/$CURRENT_BRANCH --count 2>/dev/null || echo "?")
    echo ""
    echo "[!] $BEHIND commit(s) disponible(s)"
    echo ""
    echo "=== CHANGEMENTS DISPONIBLES ==="
    git log HEAD..origin/$CURRENT_BRANCH --oneline --no-decorate 2>/dev/null | head -10
fi
```

### 2. Verification des Changements Locaux

Avant de mettre a jour, verifier s'il y a des modifications locales :

```bash
echo "=== CHANGEMENTS LOCAUX ==="

# Fichiers modifies
MODIFIED=$(git status --porcelain | grep -c "^ M\| M " || echo "0")
UNTRACKED=$(git status --porcelain | grep -c "^??" || echo "0")

echo "Fichiers modifies: $MODIFIED"
echo "Fichiers non suivis: $UNTRACKED"

if [ "$MODIFIED" -gt 0 ]; then
    echo ""
    echo "Fichiers modifies:"
    git status --porcelain | grep "^ M\| M "
    echo ""
    echo "ATTENTION: Des fichiers locaux ont ete modifies."
    echo "Options:"
    echo "  1. git stash    # Sauvegarder temporairement"
    echo "  2. git checkout -- <fichier>  # Annuler les changements"
    echo "  3. git commit   # Commiter les changements"
fi
```

### 3. Application de la Mise a Jour

```bash
echo "=== APPLICATION MISE A JOUR ==="

# Verifier les pre-requis
if [ "$MODIFIED" -gt 0 ]; then
    echo "ERREUR: Resoudre les changements locaux d'abord"
    exit 1
fi

# Sauvegarder l'etat actuel (pour rollback)
ROLLBACK_COMMIT=$(git rev-parse HEAD)
echo "Point de rollback: $ROLLBACK_COMMIT"
echo "$ROLLBACK_COMMIT" > .last_update_rollback

# Arreter les services
echo "Arret des services..."
sudo systemctl stop motor_service 2>/dev/null || true
sudo systemctl stop ems22d 2>/dev/null || true
sleep 2

# Appliquer la mise a jour
echo "Telechargement des mises a jour..."
git pull origin $CURRENT_BRANCH

# Mettre a jour les dependances
echo "Mise a jour des dependances..."
uv sync

# Migrations Django (si necessaire)
echo "Verification des migrations..."
cd web
uv run python manage.py migrate --check 2>/dev/null || uv run python manage.py migrate
cd ..

# Redemarrer les services
echo "Redemarrage des services..."
sudo systemctl start ems22d
sleep 2
sudo systemctl start motor_service
sleep 2

# Verification
echo ""
echo "=== VERIFICATION ==="
echo -n "ems22d: "
systemctl is-active ems22d
echo -n "motor_service: "
systemctl is-active motor_service

# Test API
echo -n "API Health: "
curl -s http://localhost:8000/api/health/ | python3 -c "import sys,json; d=json.load(sys.stdin); print('OK' if d.get('status')=='healthy' else 'ERREUR')" 2>/dev/null || echo "Non accessible"

echo ""
echo "=== MISE A JOUR TERMINEE ==="
echo "Nouveau commit: $(git rev-parse --short HEAD)"
```

### 4. Rollback en Cas de Probleme

```bash
echo "=== ROLLBACK ==="

# Lire le point de rollback
if [ -f .last_update_rollback ]; then
    ROLLBACK_COMMIT=$(cat .last_update_rollback)
    echo "Retour au commit: $ROLLBACK_COMMIT"
else
    echo "ERREUR: Pas de point de rollback enregistre"
    echo "Utiliser: git log --oneline | head -10"
    echo "Puis: git checkout <commit>"
    exit 1
fi

# Arreter les services
echo "Arret des services..."
sudo systemctl stop motor_service 2>/dev/null || true
sudo systemctl stop ems22d 2>/dev/null || true

# Rollback
echo "Rollback..."
git checkout $ROLLBACK_COMMIT

# Reinstaller dependances
echo "Reinstallation dependances..."
uv sync

# Redemarrer
echo "Redemarrage..."
sudo systemctl start ems22d
sleep 2
sudo systemctl start motor_service

echo ""
echo "=== ROLLBACK TERMINE ==="
echo "Commit actuel: $(git rev-parse --short HEAD)"
```

### 5. Mise a Jour via Interface Web

L'interface web propose aussi une mise a jour :

1. Aller sur `/api/health/system/`
2. Si mise a jour disponible, un bandeau s'affiche
3. Cliquer sur "Mettre a jour"
4. Attendre la reconnexion automatique

### 6. Script de Mise a Jour Automatique

Pour les mises a jour automatiques (cron) :

```bash
#!/bin/bash
# update_driftapp.sh

cd /home/$USER/Dome_web_v4_6

# Log
LOG="/var/log/driftapp_update.log"
echo "$(date): Verification mise a jour" >> $LOG

# Fetch
git fetch origin main --quiet

# Comparer
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" != "$REMOTE" ]; then
    echo "$(date): Mise a jour disponible" >> $LOG

    # Sauvegarder
    git stash --quiet

    # Mettre a jour
    git pull origin main --quiet
    uv sync --quiet

    # Redemarrer services
    sudo systemctl restart motor_service
    sudo systemctl restart ems22d

    echo "$(date): Mise a jour appliquee - $(git rev-parse --short HEAD)" >> $LOG
else
    echo "$(date): Systeme a jour" >> $LOG
fi
```

Ajouter au cron :
```bash
# Verifier toutes les heures
0 * * * * /home/$USER/Dome_web_v4_6/update_driftapp.sh
```

### 7. Gestion des Branches

```bash
# Lister les branches
git branch -a

# Changer de branche (ex: pour tester une feature)
git checkout feature/nouvelle-fonctionnalite

# Revenir sur main
git checkout main

# Creer une branche locale pour modifications
git checkout -b local/mes-modifications
```

### 8. Problemes Courants

| Probleme | Solution |
|----------|----------|
| Conflit de merge | `git stash`, puis `git pull`, puis `git stash pop` |
| Dependance manquante | `uv sync --refresh` |
| Service ne demarre pas | Verifier logs: `journalctl -u motor_service -n 50` |
| Migration Django echoue | `uv run python manage.py migrate --fake` puis corriger |
| Permission refusee | Verifier droits sur fichiers |

### 9. Verification Post-Update

Apres chaque mise a jour, executer :

```bash
# 1. Verifier les services
sudo systemctl status ems22d motor_service

# 2. Tester l'API
curl -s http://localhost:8000/api/health/

# 3. Tester un mouvement
curl -X POST http://localhost:8000/api/hardware/jog/ -H "Content-Type: application/json" -d '{"delta": 1}'

# 4. Verifier les logs
sudo journalctl -u motor_service -n 20 --no-pager
```

### 10. Resume

```
=== RESUME MISE A JOUR ===

Commandes principales:
  /update check     # Verifier si MAJ disponible
  /update apply     # Appliquer la MAJ
  /update rollback  # Annuler la derniere MAJ

Etapes automatiques:
  1. Arret des services
  2. git pull
  3. uv sync
  4. Migrations Django
  5. Redemarrage services
  6. Verification sante

Point de rollback sauvegarde dans: .last_update_rollback
```
