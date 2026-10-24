---
name: chantiers
description: >-
  Tient le registre unique des chantiers DriftApp Web, docs/chantiers.md (versionné) :
  noter un chantier pour plus tard, reprendre un chantier avec tout son contexte après
  un /clear, faire le point sur ce qui reste ouvert, clore un chantier validé. À
  utiliser dès que JP dit « note ce chantier pour plus tard », « mémorise le plan pour
  qu'on reparte d'un contexte vide », « on reprend le chantier X », « reprends où nous
  en étions », « reste-t-il un chantier non couvert ? », « où en est-on ? », ou quand
  un retour terrain valide (ou invalide) un point marqué « à valider ».
---

# chantiers — registre unique des chantiers

`docs/chantiers.md` est **la** source sur l'état des chantiers. La mémoire n'en garde
plus (seulement les faits durables : pièges, références, décisions d'architecture). Le
fichier est versionné et part avec le prochain commit, sans bump à lui seul.

Sections, dans cet ordre : **À valider sur le terrain** (code livré, pas vu marcher sur
le Pi), **En attente d'un événement**, **Plus tard** (une puce par sujet), **Écartés (ne
pas re-proposer)**. Un chantier en cours de code n'a pas de section : il vit dans sa
spec et son plan committés, et entre en « À valider » une fois poussé.

Format d'une entrée (sauf « Plus tard » et « Écartés », en puces) :

```markdown
### Titre court
- **Ouvert le** JJ/MM/AAAA, livré en X.Y.Z (ce que ça fait, en une ligne).
- **État** : faits établis, avec leur source (log, nuit, retour de Serge).
- **Prochaine étape** : l'action concrète et ce qui dira que c'est bon.
- **Réf.** : spec, plan, commit.
```

## Noter (« note ce chantier pour plus tard »)

1. Lire `docs/chantiers.md` ; s'il existe déjà une entrée sur le sujet, la compléter
   plutôt qu'en créer une seconde.
2. Écrire ce qu'il faut pour repartir **d'un contexte vide** : le symptôme mesuré
   (chiffres, dates, extraits de log), les pistes à départager, ce qui est déjà exclu et
   pourquoi, les fichiers concernés. Pas de récit de la session.
3. Si le chantier a déjà une spec ou un plan, les committer avec (méthode habituelle).
4. Dire à JP en une ligne où c'est noté.

## Reprendre (« on reprend le chantier X », après un /clear)

1. Lire l'entrée, puis sa spec et son plan s'il y en a, puis
   `git log --oneline` depuis la date de l'entrée, pour voir ce qui a bougé entre-temps.
2. Vérifier dans le code que l'état décrit est toujours vrai (fonctions, clés de config) :
   l'entrée peut avoir vieilli.
3. Résumer à JP en quelques lignes : où on en est, la prochaine étape proposée, la question
   à trancher s'il y en a une. Puis enchaîner.

## Faire le point (« reste-t-il un chantier ? », « où en est-on ? »)

Lister les titres par section, une ligne chacun avec sa prochaine étape. Signaler ce
qu'un retour terrain récent permettrait de clore, et les entrées dont la prochaine étape
ne dépend que de nous.

## Clore ou déplacer

- Validé sur le terrain → **retirer l'entrée** (l'histoire reste dans `CHANGELOG.md` et
  git). Si c'était la condition d'un « validé terrain » au CHANGELOG, le noter dans la
  ligne de la version concernée.
- Abandonné par JP → une puce dans **Écartés**, avec la date et la raison en une ligne.
- Un point « Plus tard » qu'on attaque → spec et plan, comme tout chantier non trivial.
- Toujours mettre à jour le registre dans le même commit que le code qui fait avancer le
  chantier.
