# Analyse d'une nuit terrain — skill `analyse-nuit` + chronologie fusionnée

## Problème

Après chaque nuit, Serge envoie un zip de `logs/`. L'analyse se refait à la main à chaque
fois (7 sessions entre le 11/10 et le 24/10) : décompresser, trier les fichiers, écrire des
scripts Python jetables pour croiser moteur, cimier, Django, encodeur, ASIAIR et le journal
de nuit, puis reconstruire la chronologie. Les logs du Pi finissaient en plus mélangés avec
ceux de la machine de dev dans `logs/moteur/`, etc.

## Décisions

- **Rangement** : les zips de Serge vont dans `logs/terrain/` (déjà ignoré par git), un
  fichier par nuit, idéalement `AAAA-MM-JJ.zip` (date du soir). Le nom n'est pas imposé.
- **Script** `scripts/diagnostics/chronologie_nuit.py`, lancé sur la machine de dev :
  - entrée : un zip ou un dossier ; par défaut le zip le plus récent de `logs/terrain/` ;
  - lit le zip sans l'extraire, quelle que soit sa structure (à plat avant la 6.22, rangée
    par thème après) ; ignore `__MACOSX/` ;
  - sources : `motor_service_*.log`, `cimier_service.log*`, `django_*.log`, `ems22d_*.log`,
    `asiair_monitor.log`, `update.log`, `restart.log`, et le journal de nuit
    `AAAA-MM-JJ.jsonl` s'il est dans le zip ;
  - nuit = midi → midi (même découpage que `services/night_journal.py`) ; par défaut la
    dernière nuit présente ; `--nuit AAAA-MM-JJ` pour une autre, `--de/--a HH:MM` pour
    zoomer ;
  - enlève le bruit répétitif (heartbeat, ipc_snapshot, corrections de suivi, lectures
    pluie et poll cimier en DEBUG, bannières de démarrage), regroupe les lignes identiques
    consécutives (`×N`), `--tout` pour tout garder ;
  - sortie texte : une synthèse (sources lues, redémarrages, mises à jour, objets suivis,
    nombre de corrections et plus grand écart, avertissements/erreurs par message) puis la
    chronologie `HH:MM:SS [source] NIVEAU message`.
- **Skill** `.claude/skills/analyse-nuit/` : méthode fixe (lancer le script, lire la
  synthèse, zoomer sur les moments utiles, trier logiciel/terrain, comparer avec le récit
  de Serge), puis compte rendu au format WhatsApp. Ne lance jamais rien sur le Pi.

## Hors périmètre

- Les jsonl bruts de l'ASIAIR (une ligne par interrogation) : seul `asiair_monitor.log`,
  qui ne garde que les changements, entre dans la chronologie.
- Modifier ce que le Pi met dans le zip : si le journal de nuit manque, le skill le
  demande à Serge (`data/nights/AAAA-MM-JJ.jsonl`).

## Critères de succès

- Tests sur un zip synthétique : les deux structures de zip, la découpe midi → midi, le
  filtrage du bruit, le regroupement `×N`.
- Sur un vrai zip de Serge (`~/Downloads/logs (2).zip`), la chronologie d'une nuit tient
  en quelques centaines de lignes lisibles.
