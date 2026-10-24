---
name: analyse-nuit
description: >-
  Analyse une nuit terrain du système DriftApp Web (coupole Observatoire Ubik) à
  partir du zip de logs envoyé par Serge et de son récit : range le zip dans
  logs/terrain/, construit la chronologie fusionnée (moteur, cimier, Django,
  encodeur, ASIAIR, mises à jour, journal de nuit) avec
  scripts/diagnostics/chronologie_nuit.py, confronte au récit, trie cause
  logicielle / terrain / monture, puis rédige le compte rendu au format WhatsApp.
  À utiliser dès qu'un retour de nuit arrive : « voici les logs de la nuit »,
  « @logs.zip », « Serge a eu un comportement curieux cette nuit », « vérifie
  que tout s'est bien passé », « analyse les logs ».
---

# analyse-nuit — relire une nuit terrain

La machine de dev est à 800 km du Pi : on ne lance **rien** sur le Pi, on ne lit que ce
que Serge a envoyé. S'il faut une commande ou une mesure sur place, passer par
`/diag-terrain`.

## 1. Ranger le zip

Le zip va dans `logs/terrain/AAAA-MM-JJ.zip` (date du **soir** de la nuit ; dossier
ignoré par git). S'il arrive ailleurs (`@logs.zip` à la racine, `~/Downloads/logs (N).zip`),
le copier là sous ce nom, sans l'extraire. Les captures d'écran restent où elles sont.

## 2. Chronologie

```bash
python3 scripts/diagnostics/chronologie_nuit.py logs/terrain/2026-10-23.zip > <scratchpad>/nuit.txt
```

- Lire d'abord la **synthèse** : nuits présentes, version installée (« Mises à jour »),
  objets suivis, redémarrages de services, avertissements et erreurs, journal de nuit
  présent ou non.
- Par défaut, le script prend la dernière nuit où un suivi a démarré. Utiliser
  `--nuit AAAA-MM-JJ` si le récit parle d'une autre nuit.
- Zoomer avec `--de HH:MM --a HH:MM` (la fenêtre peut passer minuit) autour des heures du
  récit de Serge. Ajouter `--tout` seulement pour un zoom de quelques minutes, pour voir
  les heartbeats, les corrections et le DEBUG.
- Les jsonl bruts de l'ASIAIR (`logs/asiair/AAAA-MM-JJ.jsonl`, une ligne par
  interrogation) ne sont pas dans la chronologie. Les lire avec un petit script seulement
  s'il faut la position de la monture (RA, temps sidéral, côté du pied) à une heure précise.

## 3. Confronter au récit

- Mettre en regard **chaque affirmation de Serge** (heure, comportement observé) avec ce
  que disent les logs, à la minute près. Les heures du Pi et de WhatsApp sont toutes deux
  en heure locale.
- Vérifier la **version réellement en service** : une mise à jour dans la nuit, ou un
  service non redémarré, explique souvent un comportement « ancien ».
- Pour chaque anomalie, trancher entre :
  - **logiciel** : reproduire d'abord (test qui échoue, ou rejeu du scénario en dev) et
    chercher la cause racine, sans rustine ;
  - **terrain/matériel** : Shelly injoignable, microswitch, encodeur, alimentation…
    → protocole via `/diag-terrain` ;
  - **monture/ASIAIR** : GOTO manuel, EQMod, réglage « Flip Timing after Meridian ».
- Avant de conclure, relire les notes de mémoire `project_*` récentes sur le sujet
  (bascule, cimier, pluie, dépassement) : elles disent ce qui est « non testé terrain »
  et donc à valider cette nuit-là.
- S'il manque une source (journal de nuit `data/nights/AAAA-MM-JJ.jsonl`, `logs/asiair/`),
  la demander à Serge plutôt que de supposer.

## 4. Restitution

1. Pour JP, dans le terminal : verdict, chronologie courte des moments clés, et ce qui
   est validé terrain et ce qui reste à corriger, avec les preuves (heures et lignes de log).
2. Si JP le demande, un compte rendu pour Serge au **format WhatsApp** : un `.txt` dans
   le scratchpad, sans tableau, avec du *gras* et des puces, des phrases courtes et sans
   jargon de code. Un PDF (`/pdf-report`) seulement pour un document important.
3. Mettre à jour la note de mémoire du chantier concerné (validé terrain, ou nouvel
   incident) et proposer les corrections, sans les lancer sans accord.
