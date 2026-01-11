---
description: Sauvegarde et restauration de la configuration et des sessions
category: utilities-debugging
argument-hint: [optionnel] action (create, restore, list, clean)
---

# Sauvegarde et Restauration DriftApp

Gere les sauvegardes de configuration et sessions.

## Instructions

Tu vas gerer les sauvegardes : **$ARGUMENTS**

### 1. Creation d'une Sauvegarde Complete

```bash
echo "=== CREATION SAUVEGARDE ==="

# Date pour le nom
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="backups"
BACKUP_NAME="driftapp_backup_$DATE"
BACKUP_PATH="$BACKUP_DIR/$BACKUP_NAME"

# Creer le repertoire
mkdir -p "$BACKUP_PATH"

echo "Sauvegarde: $BACKUP_NAME"
echo ""

# 1. Configuration principale
echo "- Configuration..."
cp data/config.json "$BACKUP_PATH/" 2>/dev/null && echo "  config.json OK" || echo "  config.json ABSENT"

# 2. Abaque (si modifie)
cp data/Loi_coupole.xlsx "$BACKUP_PATH/" 2>/dev/null && echo "  Loi_coupole.xlsx OK" || echo "  Loi_coupole.xlsx ABSENT"

# 3. Sessions de suivi
echo "- Sessions..."
if [ -d "data/sessions" ]; then
    cp -r data/sessions "$BACKUP_PATH/"
    SESSION_COUNT=$(ls -1 data/sessions/*.json 2>/dev/null | wc -l)
    echo "  $SESSION_COUNT session(s) sauvegardee(s)"
else
    echo "  Aucune session"
fi

# 4. Services systemd (si modifies)
echo "- Services systemd..."
cp ems22d.service "$BACKUP_PATH/" 2>/dev/null
cp motor_service.service "$BACKUP_PATH/" 2>/dev/null
echo "  Services copies"

# 5. Scripts personnalises
echo "- Scripts..."
cp start_web.sh "$BACKUP_PATH/" 2>/dev/null
cp start_dev.sh "$BACKUP_PATH/" 2>/dev/null

# 6. Creer archive
echo ""
echo "Creation archive..."
tar -czf "$BACKUP_DIR/$BACKUP_NAME.tar.gz" -C "$BACKUP_DIR" "$BACKUP_NAME"
rm -rf "$BACKUP_PATH"

# Resume
BACKUP_SIZE=$(ls -lh "$BACKUP_DIR/$BACKUP_NAME.tar.gz" | awk '{print $5}')
echo ""
echo "=== SAUVEGARDE TERMINEE ==="
echo "Fichier: $BACKUP_DIR/$BACKUP_NAME.tar.gz"
echo "Taille: $BACKUP_SIZE"
```

### 2. Liste des Sauvegardes

```bash
echo "=== SAUVEGARDES DISPONIBLES ==="
echo ""

if [ -d "backups" ]; then
    ls -lht backups/*.tar.gz 2>/dev/null | head -20 | while read line; do
        FILE=$(echo $line | awk '{print $NF}')
        SIZE=$(echo $line | awk '{print $5}')
        DATE=$(echo $line | awk '{print $6, $7, $8}')
        NAME=$(basename $FILE .tar.gz)
        echo "  $NAME  ($SIZE)  $DATE"
    done

    echo ""
    TOTAL=$(ls -1 backups/*.tar.gz 2>/dev/null | wc -l)
    TOTAL_SIZE=$(du -sh backups/ 2>/dev/null | cut -f1)
    echo "Total: $TOTAL sauvegarde(s), $TOTAL_SIZE"
else
    echo "Aucune sauvegarde trouvee"
    echo "Creer avec: /backup create"
fi
```

### 3. Restauration d'une Sauvegarde

```bash
echo "=== RESTAURATION SAUVEGARDE ==="

# Nom de la sauvegarde (argument ou derniere)
BACKUP_NAME="$ARGUMENTS"
if [ -z "$BACKUP_NAME" ] || [ "$BACKUP_NAME" = "restore" ]; then
    # Prendre la derniere
    BACKUP_FILE=$(ls -t backups/*.tar.gz 2>/dev/null | head -1)
    if [ -z "$BACKUP_FILE" ]; then
        echo "ERREUR: Aucune sauvegarde trouvee"
        exit 1
    fi
else
    BACKUP_FILE="backups/$BACKUP_NAME.tar.gz"
    if [ ! -f "$BACKUP_FILE" ]; then
        # Essayer avec le nom complet
        BACKUP_FILE="backups/driftapp_backup_$BACKUP_NAME.tar.gz"
    fi
fi

if [ ! -f "$BACKUP_FILE" ]; then
    echo "ERREUR: Sauvegarde non trouvee: $BACKUP_FILE"
    echo ""
    echo "Sauvegardes disponibles:"
    ls -1 backups/*.tar.gz 2>/dev/null | sed 's/backups\//  /' | sed 's/.tar.gz//'
    exit 1
fi

echo "Restauration de: $BACKUP_FILE"
echo ""

# Confirmation
read -p "Confirmer la restauration? (oui/non): " CONFIRM
if [ "$CONFIRM" != "oui" ]; then
    echo "Annule"
    exit 0
fi

# Arreter les services
echo ""
echo "Arret des services..."
sudo systemctl stop motor_service 2>/dev/null
sudo systemctl stop ems22d 2>/dev/null

# Sauvegarder config actuelle
echo "Sauvegarde de la config actuelle..."
cp data/config.json data/config.json.before_restore 2>/dev/null

# Extraire
echo "Extraction..."
TEMP_DIR=$(mktemp -d)
tar -xzf "$BACKUP_FILE" -C "$TEMP_DIR"
BACKUP_CONTENT=$(ls "$TEMP_DIR")

# Restaurer
echo "Restauration des fichiers..."
cp "$TEMP_DIR/$BACKUP_CONTENT/config.json" data/ 2>/dev/null && echo "  config.json restaure"
cp "$TEMP_DIR/$BACKUP_CONTENT/Loi_coupole.xlsx" data/ 2>/dev/null && echo "  Loi_coupole.xlsx restaure"

# Sessions
if [ -d "$TEMP_DIR/$BACKUP_CONTENT/sessions" ]; then
    mkdir -p data/sessions
    cp -r "$TEMP_DIR/$BACKUP_CONTENT/sessions/"* data/sessions/ 2>/dev/null
    echo "  Sessions restaurees"
fi

# Nettoyer
rm -rf "$TEMP_DIR"

# Redemarrer services
echo ""
echo "Redemarrage des services..."
sudo systemctl start ems22d
sleep 2
sudo systemctl start motor_service

echo ""
echo "=== RESTAURATION TERMINEE ==="
echo "Config precedente sauvegardee: data/config.json.before_restore"
```

### 4. Sauvegarde de la Configuration Seule

```bash
echo "=== SAUVEGARDE CONFIG ==="

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="backups/config_$DATE.json"

mkdir -p backups

# Copier avec metadonnees
python3 -c "
import json
from datetime import datetime

with open('data/config.json', 'r') as f:
    config = json.load(f)

backup = {
    'backup_date': datetime.now().isoformat(),
    'backup_type': 'config_only',
    'config': config
}

with open('$BACKUP_FILE', 'w') as f:
    json.dump(backup, f, indent=2)

print(f'Sauvegarde: $BACKUP_FILE')
"
```

### 5. Sauvegarde des Sessions Seules

```bash
echo "=== SAUVEGARDE SESSIONS ==="

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="backups/sessions_$DATE.tar.gz"

if [ -d "data/sessions" ]; then
    SESSION_COUNT=$(ls -1 data/sessions/*.json 2>/dev/null | wc -l)

    if [ "$SESSION_COUNT" -gt 0 ]; then
        tar -czf "$BACKUP_FILE" -C data sessions
        echo "Sauvegarde: $BACKUP_FILE"
        echo "Sessions: $SESSION_COUNT"
        ls -lh "$BACKUP_FILE"
    else
        echo "Aucune session a sauvegarder"
    fi
else
    echo "Repertoire sessions non trouve"
fi
```

### 6. Nettoyage des Anciennes Sauvegardes

```bash
echo "=== NETTOYAGE SAUVEGARDES ==="

# Garder les 10 dernieres sauvegardes completes
echo "Sauvegardes completes (garde les 10 dernieres):"
FULL_BACKUPS=$(ls -t backups/driftapp_backup_*.tar.gz 2>/dev/null)
COUNT=0
for f in $FULL_BACKUPS; do
    COUNT=$((COUNT + 1))
    if [ $COUNT -gt 10 ]; then
        echo "  Suppression: $(basename $f)"
        rm "$f"
    else
        echo "  Conserve: $(basename $f)"
    fi
done

# Garder les 5 derniers backups config
echo ""
echo "Backups config (garde les 5 derniers):"
CONFIG_BACKUPS=$(ls -t backups/config_*.json 2>/dev/null)
COUNT=0
for f in $CONFIG_BACKUPS; do
    COUNT=$((COUNT + 1))
    if [ $COUNT -gt 5 ]; then
        echo "  Suppression: $(basename $f)"
        rm "$f"
    else
        echo "  Conserve: $(basename $f)"
    fi
done

# Supprimer backups > 30 jours
echo ""
echo "Suppression des backups > 30 jours:"
find backups/ -name "*.tar.gz" -mtime +30 -exec echo "  Suppression: {}" \; -delete 2>/dev/null
find backups/ -name "*.json" -mtime +30 -exec echo "  Suppression: {}" \; -delete 2>/dev/null

echo ""
echo "Espace utilise:"
du -sh backups/
```

### 7. Verification d'une Sauvegarde

```bash
echo "=== VERIFICATION SAUVEGARDE ==="

BACKUP_FILE="$ARGUMENTS"
if [ -z "$BACKUP_FILE" ]; then
    BACKUP_FILE=$(ls -t backups/*.tar.gz 2>/dev/null | head -1)
fi

if [ ! -f "$BACKUP_FILE" ] && [ -f "backups/$BACKUP_FILE" ]; then
    BACKUP_FILE="backups/$BACKUP_FILE"
fi

if [ ! -f "$BACKUP_FILE" ]; then
    echo "ERREUR: Fichier non trouve: $BACKUP_FILE"
    exit 1
fi

echo "Fichier: $BACKUP_FILE"
echo "Taille: $(ls -lh "$BACKUP_FILE" | awk '{print $5}')"
echo ""

echo "Contenu:"
tar -tzf "$BACKUP_FILE" | head -20

echo ""
echo "Verification integrite..."
if tar -tzf "$BACKUP_FILE" > /dev/null 2>&1; then
    echo "[OK] Archive valide"
else
    echo "[ERREUR] Archive corrompue!"
fi
```

### 8. Synchronisation avec Remote (Optionnel)

```bash
echo "=== SYNCHRONISATION REMOTE ==="

# Configurer le remote (une seule fois)
# REMOTE_PATH="user@server:/path/to/backups/"

if [ -z "$REMOTE_PATH" ]; then
    echo "Remote non configure"
    echo ""
    echo "Pour configurer:"
    echo "  export REMOTE_PATH='user@server:/path/to/backups/'"
    echo "  /backup sync"
    exit 0
fi

echo "Synchronisation vers: $REMOTE_PATH"
echo ""

# Synchroniser avec rsync
rsync -avz --progress backups/*.tar.gz "$REMOTE_PATH"

echo ""
echo "Synchronisation terminee"
```

### 9. Sauvegarde Automatique (Cron)

```bash
echo "=== CONFIGURATION BACKUP AUTOMATIQUE ==="

# Script de backup automatique
cat > /tmp/auto_backup.sh << 'EOF'
#!/bin/bash
cd /home/$USER/Dome_web_v4_6
DATE=$(date +%Y%m%d)
BACKUP_DIR="backups"
BACKUP_NAME="auto_backup_$DATE"

# Ne pas creer si existe deja
if [ -f "$BACKUP_DIR/$BACKUP_NAME.tar.gz" ]; then
    exit 0
fi

# Creer backup
mkdir -p "$BACKUP_DIR/temp_$BACKUP_NAME"
cp data/config.json "$BACKUP_DIR/temp_$BACKUP_NAME/"
cp -r data/sessions "$BACKUP_DIR/temp_$BACKUP_NAME/" 2>/dev/null
tar -czf "$BACKUP_DIR/$BACKUP_NAME.tar.gz" -C "$BACKUP_DIR" "temp_$BACKUP_NAME"
rm -rf "$BACKUP_DIR/temp_$BACKUP_NAME"

# Nettoyer anciens (> 30 jours)
find "$BACKUP_DIR" -name "auto_backup_*.tar.gz" -mtime +30 -delete
EOF

echo "Script cree: /tmp/auto_backup.sh"
echo ""
echo "Pour activer (cron quotidien a 3h):"
echo "  sudo cp /tmp/auto_backup.sh /etc/cron.daily/driftapp_backup"
echo "  sudo chmod +x /etc/cron.daily/driftapp_backup"
```

### Resume

```
=== COMMANDES BACKUP ===

Creation:
  /backup create      # Sauvegarde complete
  /backup config      # Config seule
  /backup sessions    # Sessions seules

Gestion:
  /backup list        # Lister les sauvegardes
  /backup verify      # Verifier une archive
  /backup clean       # Nettoyer les anciennes

Restauration:
  /backup restore                    # Restaurer la derniere
  /backup restore 20250111_120000    # Restaurer specifique

Automatisation:
  /backup auto        # Configurer backup quotidien
  /backup sync        # Synchroniser avec remote

Emplacements:
  backups/driftapp_backup_*.tar.gz   # Sauvegardes completes
  backups/config_*.json              # Configs seules
  backups/sessions_*.tar.gz          # Sessions seules
```
