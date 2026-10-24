---
name: message-user
description: >-
  Rédige un message à transmettre à un utilisateur de l'observatoire (Serge par
  défaut, ou tout utilisateur non développeur) au format WhatsApp, vérifie qu'il
  s'affichera proprement et le copie dans le presse-papiers ; ou en fait un PDF
  quand le document est important. Quatre sortes : annonce de mise à jour (ce qui
  change, ce qu'il faut observer), compte rendu de nuit (après /analyse-nuit),
  question ou demande (une chose à faire, comment, quoi renvoyer), document à
  imprimer ou archiver. À utiliser dès que JP dit « écris à Serge », « prépare un
  message pour Serge », « annonce la mise à jour », « compte rendu pour Serge »,
  « demande-lui… », « fais-lui un PDF », ou quand un texte destiné au terrain doit
  sortir du terminal.
---

# message-user — écrire à l'utilisateur terrain

Le destinataire n'est pas développeur. Il lit sur son téléphone (WhatsApp) et agit au
clavier du Pi, devant le dashboard en kiosque, sans SSH. C'est JP qui envoie le message :
ne rien envoyer soi-même.

## 1. Choisir la sorte de message

**Annonce de mise à jour**
- Version de départ : celle que le Pi fait tourner. La prendre dans la synthèse
  « Mises à jour » du dernier zip (`/analyse-nuit`, `logs/terrain/`), sinon la demander à JP.
- Lire les lignes de `CHANGELOG.md` entre cette version et `pyproject.toml`. N'en garder
  que ce qui se **voit ou se ressent** sur place (dashboard, coupole, cimier, pluie,
  suivi) ; regrouper le reste en « corrections internes », sans détail.
- Ce qu'il faut observer : section « À valider sur le terrain » de `docs/chantiers.md`,
  traduite en « ce que tu devrais voir » et « si tu vois autre chose, note l'heure ».
- Rappeler comment appliquer la mise à jour si ce n'est pas automatique (bouton de la
  page Système), et qu'un redémarrage du service moteur fait bouger la coupole.

**Compte rendu de nuit** : partir du verdict de `/analyse-nuit`. Ce qui s'est bien passé
d'abord, puis chaque anomalie en une ligne (heure, ce qui s'est vu, cause en mots
simples, ce qui va être fait), puis ce qu'on attend de lui (rien, ou une chose précise).

**Question ou demande** : une seule chose à faire par message. Pourquoi en une phrase,
puis comment (étapes numérotées), puis quoi renvoyer (photo, fichier, valeur lue). Pour
une vraie procédure de diagnostic, passer par `/diag-terrain`.

**Document important** (à imprimer, archiver ou suivre pas à pas pendant la nuit) :
PDF via `/pdf-report`. Les tableaux y sont permis. Ranger le PDF dans `docs/` s'il doit
rester ; envoyer en plus un court message WhatsApp qui l'annonce.

## 2. Écrire au format WhatsApp

- Ouverture courte (« Bonsoir Serge, »), puis l'essentiel dans les deux premières lignes :
  sur l'écran du téléphone, c'est ce qu'on lit sans dérouler.
- Mise en forme permise : `*gras*`, `_italique_`, puces `•`, listes `1.` `2.`, quelques
  emojis repères (✅ fait/ok, ⚠️ attention, 👉 à faire, 🕘 heure). Paragraphes de 1 à 3
  lignes.
- **Interdit** : tableau, titre `#`, `**double astérisque**`, lien `[texte](url)`, filet
  `---`. Le script les refuse.
- Chronologie : une ligne par moment, « • *21:42* : la coupole s'est arrêtée ».
- Mots d'utilisateur : « la coupole », « le cimier », « le suivi », « la page Système »,
  pas `motor_service`, `IPC`, `tracking_mixin`, ni nom de fichier, de fonction ou de
  variable, sauf s'il faut les **taper**.
- Commande à taper : dire d'abord comment ouvrir un terminal par-dessus le dashboard
  (Ctrl+Alt+T, retour par Alt+Tab), commencer par `cd ~/DriftApp`, une commande courte
  par ligne entre backticks simples ou dans un bloc ```, ce qu'il doit voir s'afficher.
  Ne jamais lui faire recopier une adresse ou une valeur que le script peut trouver seul.
- Dates et heures en clair, heure locale (« ce soir vers 22 h », « nuit du 23 au 24 »).

## 3. Vérifier et livrer

1. Écrire le message dans le scratchpad, `message_<sujet>.txt`.
2. Lancer :
   ```bash
   python3 .claude/skills/message-user/scripts/message_whatsapp.py <scratchpad>/message_<sujet>.txt
   ```
   Il liste les défauts par ligne (code de sortie 1, rien de copié) : corriger et
   relancer. Propre, il copie le texte dans le presse-papiers.
3. Montrer le message à JP dans un bloc de code (sinon le terminal mange les `*`), avec le
   **chemin complet** du `.txt`, et dire s'il est déjà dans le presse-papiers. Si le script
   signale qu'aucun outil n'est installé, rappeler `sudo apt install wl-clipboard`.
4. Si le message annonce une validation terrain ou attend un retour, le noter dans
   `docs/chantiers.md` via `/chantiers`.
