# Bouton « Éteindre le Pi » sur le dashboard

**Date** : 27/10/2026 — **Demande** : Serge, via JP.

## Problème

Le matin, Serge éteint le Pi en coupant le courant. Le Pi 5 de l'observatoire n'a pas de
pile d'horloge : il redémarre à l'heure du dernier enregistrement et ne se recale par
NTP qu'environ 30 s plus tard (nuit du 26/10), et les logs finissent par des octets nuls
(écriture interrompue, risque pour la carte SD). Il n'existe aucun moyen d'éteindre
proprement depuis le dashboard en kiosque, et Serge ne fait pas de SSH.

## Décisions (JP, 27/10)

- **Emplacement** : dashboard, ligne du haut, à l'extrême droite (fin du bloc
  `status_indicator`, après l'état des services). Bouton rouge.
- **Session pas terminée → refus.** L'extinction est refusée tant que :
  - la coupole suit ou bouge (`motor_status.status` ∈ `tracking`, `moving`,
    `initializing`, `calibrating`) ;
  - le cimier est ouvert ou en mouvement (`cimier_status.state == "cycle"`, ou butée
    `open_switch` active, hors `state == "disabled"`).
  Un service muet (état `unknown`) ne bloque pas : on ne doit jamais enfermer Serge, et
  le bouton du Pi 5 reste de toute façon disponible.
- **Confirmation** : une fenêtre explique ce qui va se passer ; en cas de refus, elle
  affiche la raison en clair (écran tactile : pas d'information au survol).

## Fonctionnement

1. Tap sur le bouton → `GET /api/health/shutdown/` → `{allowed, reason}`.
2. Fenêtre : soit la raison du refus (bouton « Fermer »), soit la confirmation
   (« Annuler » / « Éteindre le Pi »).
3. Confirmation → `POST /api/health/shutdown/` : la vue revérifie les conditions (elle
   fait autorité), puis lance `sudo -n scripts/shutdown_pi.sh`.
4. Le script refuse s'il ne tourne pas sur un Raspberry Pi (`/proc/device-tree/model`),
   pour qu'un essai en dev n'éteigne jamais le PC de développement ; sinon il journalise
   dans `logs/shutdown.log` et programme `systemctl poweroff` 3 s plus tard, en
   arrière-plan, pour que la réponse HTTP parte avant l'arrêt de Django.
5. La page affiche « Arrêt en cours : attendez que la LED verte du Pi s'éteigne, puis
   vous pouvez couper le courant. Pour rallumer : bouton du Pi. » L'écran s'éteint avec
   le Pi : rien d'autre à fermer.

## Droits

Une ligne de plus dans `setup/driftapp-updater.sudoers`, pour ce seul script (jamais
`systemctl` en entier). Le sudoers est redéployé par l'OTA depuis le dépôt tiré : le
bouton marche dès la mise à jour qui l'apporte.

## Hors périmètre

Séquence automatique (parking + fermeture puis extinction), redémarrage du Pi, bouton
sur les autres pages, pile d'horloge (matériel).

## Critères de succès

- Tests : refus pour chaque condition, autorisation quand tout est rangé ou inconnu,
  script appelé seulement après les vérifications, échec de `sudo` remonté ; script :
  refus hors Raspberry Pi, `poweroff` programmé sur un Pi (faux `systemctl`) ; sudoers
  limité au script.
- Dev (Chrome headless) : bouton visible en haut à droite du dashboard, fenêtre de refus
  pendant un suivi, fenêtre de confirmation coupole au repos et cimier fermé ; en dev,
  la confirmation échoue proprement (pas de sudoers, pas de Raspberry Pi).
