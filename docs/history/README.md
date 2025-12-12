# 📚 Historique des Modifications - DriftApp

Ce dossier archive les documents de changements ponctuels effectués sur le projet.

## 📋 Contenu

### Décembre 2025 - Corrections Critiques

| Fichier | Date | Sujet |
|---------|------|-------|
| **SUPPRESSION_MODE_VECTORIEL.md** | 6 déc 2025 | Suppression complète du mode vectoriel (non fonctionnel) |
| **ANALYSE_FORK_V4_4.md** | 6 déc 2025 | Analyse comparative v4.3 vs v4.4 (fork) |
| **MODIFICATIONS_APPLIQUEES_V4_4.md** | 6 déc 2025 | Log des modifications v4.4 appliquées à v4.3 |
| **RESUME_ANALYSE_V4_4.md** | 6 déc 2025 | Résumé de l'analyse fork v4.4 |

### Novembre 2025 - Migration Démon

| Fichier | Date | Sujet |
|---------|------|-------|
| **GUIDE_MIGRATION_DAEMON.md** | 18 nov 2025 | Migration vers architecture démon encodeur |

---

## 🔍 Résumé des Événements

### 5-6 Décembre 2025 : Corrections Critiques

**Problèmes résolus** :
1. ✅ **Méthode incrémentale encodeur** : Passage de méthode ABSOLUE → INCRÉMENTALE (bug majeur)
2. ✅ **Suppression mode vectoriel** : Simplification du code (méthode abaque uniquement)
3. ✅ **Facteur calibration** : 0.010851 (corrigé, validé terrain)
4. ✅ **GUI Boussole** : Animation Tkinter fixée (ordre Canvas→Pack→Animation)
5. ✅ **Switch calibration** : Auto-recalage à 45° via GPIO 27

### 18 Novembre 2025 : Architecture Démon

**Évolution majeure** :
- Migration vers démon encodeur indépendant (`ems22d_calibrated.py`)
- Communication via `/dev/shm/ems22_position.json`
- Isolation complète SPI/GPIO → Zéro interférence

---

## 📌 Note

Ces documents sont conservés pour référence historique. Pour la documentation à jour, consultez :
- `/README.md` - Documentation principale
- `/CLAUDE.md` - Guide développeur Claude Code
- `/CONTEXT.md` - Contexte projet complet

*Dernière mise à jour : 7 décembre 2025*
