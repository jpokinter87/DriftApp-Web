# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Serge, opérateur sur site** (utilisateur principal). Il pilote la coupole depuis l'écran tactile du Raspberry Pi, avec le dashboard affiché en kiosque (Firefox plein écran), dans la coupole et pendant la nuit d'observation. Il n'est pas développeur et ne fait pas de SSH : s'il lui faut un terminal, il l'ouvre par-dessus le dashboard (Ctrl+Alt+T).
- **Serge ou d'autres utilisateurs, à distance.** Ils surveillent et commandent la coupole depuis un ordinateur portable pendant qu'elle suit seule.
- **JP, développeur, à 800 km du Pi.** Il utilise l'interface surtout en développement et en simulation (`./start_dev.sh`). Les nuits réelles, il les relit après coup à partir des logs, pas dans l'UI en direct.

## Product Purpose

DriftApp Web pilote la coupole de l'Observatoire Ubik pour que sa fente reste alignée sur le télescope pendant une observation. Le télescope suit l'objet sur sa monture équatoriale, mais la coupole ne suit pas d'elle-même : DriftApp calcule l'azimut voulu et fait les corrections. L'interface gère aussi le cimier (ouverture, fermeture, butées), la protection contre la pluie, le parking et la calibration.

Le produit réussit quand une nuit se déroule sans que personne ait à intervenir. Et quand une intervention devient nécessaire, l'opérateur doit pouvoir reprendre la main tout de suite, sur place ou à distance.

## Positioning

DriftApp est fait pour une coupole précise et son matériel. La position voulue vient d'un abaque de 275 points mesurés sur place (`data/Loi_coupole.xlsx`), pas seulement d'un modèle géométrique. Le suivi tourne en boucle fermée sur un encodeur magnétique absolu. Le système connaît le retournement de la monture (ASIAIR) et commande un cimier entièrement piloté par Shelly. L'interface sert aux personnes qui exploitent cet observatoire, pas à un public large.

## Operating Context

- Nuit d'observation en imagerie (ASIAIR) : on démarre le suivi d'un objet, la coupole fait ses corrections toutes les 30 s, le cimier s'ouvre en début de nuit et se ferme à la fin ou sous la pluie.
- Écran tactile dans la coupole, dans le noir. Rien n'est survolé : tout passe par le toucher.
- Accès à distance par le navigateur sur le réseau de l'observatoire.
- Après la nuit, Serge envoie un zip de logs (`logs/`, journal de nuit `logs/nuits/`) et des captures WhatsApp. JP en tire une chronologie, et il transmet ses comptes rendus et ses annonces de mise à jour par WhatsApp.
- Les mises à jour arrivent par OTA depuis l'interface (page Système). Une mise à jour n'est proposée que si le numéro de version a augmenté.

## Capabilities and Constraints

- Pages : Contrôle (dashboard : boussole, suivi d'objet, contrôle manuel JOG/continu, cimier, journal, modales GOTO, coordonnées manuelles, parking), Session (graphiques altitude/azimut, statistiques, historique), Système (état IPC, composants, mises à jour), Configuration.
- Stack en place : Django, gabarits HTML, Tailwind compilé (`web/static/css/tailwind-output.css`), Alpine.js, JS vanilla (`web/static/js/`). L'UI lit l'état du moteur, de l'encodeur et du cimier dans des fichiers IPC JSON (`/dev/shm/`), rafraîchis toutes les quelques secondes.
- Matériel réel derrière chaque bouton : démarrer un mouvement fait tourner la coupole. Le parking, la fermeture du cimier et la calibration forcée passent déjà par une confirmation.
- Le contrôle manuel (JOG et continu) n'est jamais bloqué par un automatisme (calibration, météo).
- Aucune information ne doit dépendre du survol (`title`, tooltip au hover, déclenchement par attente). L'aide est soit toujours visible, soit affichée au toucher.
- Interface en français.
- Les adresses et valeurs de terrain sont dans `data/config.json`, jamais en dur dans l'UI.
- Mode simulation complet en dev : simulateur Shelly unifié, moteur simulé, pluie déclenchable à la main.

## Brand Commitments

- Nom : **DriftApp**, pour l'**Observatoire Ubik** (France). Logo et favicon : `web/static/img/logo.svg`, `web/static/img/favicon.svg`.
- Ton des messages : français simple et concret, sans jargon de développeur, pour quelqu'un qui n'est pas informaticien.

## Evidence on Hand

- Abaque de 275 mesures prises sur place : `data/Loi_coupole.xlsx`.
- Rapports et protocoles terrain : `docs/rapport_NGC4151_20260416.pdf`, `docs/rapport_anticipation_meridien_v511.pdf`, `docs/description_technique_coupole.pdf`, `docs/protocole_*`.
- Nuits réelles archivées dans `logs/terrain/`.
- Aucun témoignage, chiffre d'usage ou client à mettre en avant : il ne faut pas en inventer.

## Product Principles

1. **La reprise en main passe avant tout.** STOP et le manuel restent toujours accessibles et clairement visibles. Aucun automatisme ne les verrouille.
2. **Montrer l'état réel, jamais un état supposé.** Coupole, suivi, cimier, pluie : si le service ne répond pas ou si une donnée est périmée, l'interface le dit au lieu d'afficher une valeur figée.
3. **Faire comprendre la situation d'un coup d'œil, de près comme à distance.** L'opérateur doit voir si tout va bien sans avoir à lire.
4. **Un geste a une conséquence physique.** Tout ce qui fait bouger la coupole ou le cimier est explicite, et les actions lourdes demandent une confirmation.
5. **Laisser une trace.** Ce qui se passe pendant la nuit doit pouvoir être retracé après coup.

## Accessibility & Inclusion

- **Préserver la vision nocturne est impératif.** L'écran sert dans la coupole plongée dans le noir : luminosité minimale la nuit, pas de grandes surfaces blanches ni de couleurs vives.
- Écran tactile : cibles assez grandes pour le doigt, aucune dépendance au survol.
- Écrans cibles : l'écran tactile 720p du kiosque et l'ordinateur portable pour l'accès à distance. Le téléphone n'est pas une cible.
