---
name: analyse-nuit
description: >-
  Analyse une nuit terrain du système DriftApp Web (coupole Observatoire Ubik) à
  partir du zip de logs envoyé par Serge, de ses captures d'écran WhatsApp et de
  son récit : range le zip et les captures dans logs/terrain/, construit la
  chronologie fusionnée (moteur, cimier, Django, encodeur, ASIAIR, mises à jour,
  journal de nuit) avec
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

## 1. Ranger le zip et les captures

Le zip va dans `logs/terrain/AAAA-MM-JJ.zip` (date du **soir** de la nuit ; dossier
ignoré par git). S'il arrive ailleurs (`@logs.zip` à la racine, `~/Downloads/logs (N).zip`),
le copier là sous ce nom, sans l'extraire.

Les captures d'écran de Serge arrivent par WhatsApp, enregistrées dans
`~/Téléchargements` ou `~/Downloads` sous le nom `WhatsApp Image AAAA-MM-JJ at HH.MM.SS.jpeg`
(parfois suivi de ` (1)`). Retenir celles reçues entre le soir de la nuit à midi et la fin
du lendemain :

```bash
ls ~/Téléchargements/"WhatsApp Image 2026-10-24 at "* ~/Téléchargements/"WhatsApp Image 2026-10-25 at "* \
   ~/Downloads/"WhatsApp Image 2026-10-24 at "* ~/Downloads/"WhatsApp Image 2026-10-25 at "* 2>/dev/null
```

Écarter celles du soir reçues avant 12.00, montrer la liste à JP, puis les **copier**
(jamais déplacer) dans `logs/terrain/AAAA-MM-JJ/`, à côté du zip, sous leur nom d'origine.
Si JP a déjà collé des captures dans la conversation, les lire sur place : rien à ranger.

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
- Regarder **chaque capture** de `logs/terrain/AAAA-MM-JJ/` (outil Read). L'heure du nom
  de fichier est celle de l'**envoi**, pas de la capture : dater l'image par l'heure
  qu'elle affiche (horloge du dashboard, de l'ASIAIR, du bureau du Pi). Sans heure
  visible, le dire et ne la situer que par son contenu, jamais par l'heure d'envoi.
  Confronter ce qu'elle montre (position, état du cimier, message d'erreur, côté du pied)
  aux logs de ce moment.
- Vérifier la **version réellement en service** : une mise à jour dans la nuit, ou un
  service non redémarré, explique souvent un comportement « ancien ».
- Pour chaque anomalie, trancher entre :
  - **logiciel** : reproduire d'abord (test qui échoue, ou rejeu du scénario en dev) et
    chercher la cause racine, sans rustine ;
  - **terrain/matériel** : Shelly injoignable, microswitch, encodeur, alimentation…
    → protocole via `/diag-terrain` ;
  - **monture/ASIAIR** : GOTO manuel, EQMod, réglage « Flip Timing after Meridian ».
- Avant de conclure, relire la section « À valider sur le terrain » de
  `docs/chantiers.md` : elle dit ce que cette nuit pouvait valider, et quelle ligne de log
  le prouve.
- S'il manque une source (journal de nuit `logs/nuits/AAAA-MM-JJ.jsonl`, `logs/asiair/`),
  la demander à Serge plutôt que de supposer. Avant la 6.26.12, le journal de nuit était
  dans `data/nights/`, hors du zip.

## 4. Restitution

1. Pour JP, dans le terminal : verdict, chronologie courte des moments clés, et ce qui
   est validé terrain et ce qui reste à corriger, avec les preuves (heures et lignes de log).
2. Si JP le demande, un compte rendu pour Serge via `/message-user` (format WhatsApp
   vérifié et copié, ou PDF pour un document important).
3. Mettre à jour `docs/chantiers.md` via `/chantiers` (entrée validée et retirée, ou
   nouvel incident noté) et proposer les corrections, sans les lancer sans accord.
