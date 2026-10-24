# Messages aux utilisateurs terrain — skill `message-user`

## Problème

Ce qui part vers Serge (ou un autre utilisateur de l'observatoire) passe par WhatsApp,
parfois en PDF. Rédigé en Markdown de terminal, c'est illisible dans WhatsApp : tableaux,
titres `#`, `**gras**` en double astérisque, liens `[x](y)`, jargon de code. Le 24/10, un
compte rendu de logs a dû être réécrit pour cette raison. La règle vivait dans la mémoire
de Claude, sans outil pour la vérifier ni pour livrer le texte.

## Décisions

- **Skill** `.claude/skills/message-user/` (nom générique : Serge par défaut, mais tout
  utilisateur non développeur). Quatre sortes de messages :
  1. **Annonce de mise à jour** : ce qui change depuis la dernière version connue sur le
     Pi, traduit du `CHANGELOG.md` en effets visibles, et ce qu'il faut observer la nuit
     suivante (section « À valider sur le terrain » de `docs/chantiers.md`) ;
  2. **Compte rendu de nuit** : mise en forme du verdict de `/analyse-nuit` ;
  3. **Question ou demande** : une seule chose à faire, comment la faire, quoi renvoyer ;
  4. **Document important** : PDF via `/pdf-report` (tableaux permis), quand le texte est
     à imprimer, archiver ou suivre pas à pas.
- **Format WhatsApp** : `*gras*`, `_italique_`, puces `•`, listes numérotées, emojis repères
  (⚠️ 👉 ✅), paragraphes courts, aucun nom de fichier/fonction/variable sauf s'il faut le
  taper. Commandes à taper : courtes, précédées de la façon d'ouvrir un terminal
  (Ctrl+Alt+T, `cd ~/DriftApp`), comme dans `/diag-terrain`.
- **Script** `.claude/skills/message-user/scripts/message_whatsapp.py FICHIER.txt` :
  - signale par numéro de ligne ce que WhatsApp n'affiche pas : tableau, titre `#`,
    `**double astérisque**`, `__double souligné__`, lien Markdown, filet `---` ;
  - si le texte est propre, le copie dans le presse-papiers (`wl-copy` sous Wayland,
    `xclip` sinon) ; sans outil, le dit et indique `sudo apt install wl-clipboard` ;
  - code de sortie 1 s'il reste un problème (rien n'est copié), 0 sinon.
- **Livraison** : le `.txt` reste dans le scratchpad (chemin complet donné à JP), copié dans
  le presse-papiers pour un Ctrl+V direct dans WhatsApp.
- `/analyse-nuit` renvoie à `/message-user` pour son compte rendu.

## Hors périmètre

- Envoyer le message soi-même : c'est JP qui l'envoie.
- Les protocoles de diagnostic : `/diag-terrain` les produit (il peut s'appuyer sur ce
  format).

## Critères de succès

- Tests du script : chaque défaut détecté avec son numéro de ligne, un texte WhatsApp
  correct n'est pas signalé (gras simple, puces, code entre backticks, heure « 21:30 »),
  code de sortie 1 sans copie quand il reste un défaut.
- Essai réel : un message produit, vérifié, présent dans le presse-papiers.
