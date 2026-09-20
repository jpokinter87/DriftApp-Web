# Vitesse de la coupole — explication et protocole terrain (v6.16.0)

Destinataire : Serge, sur site.
Version concernée : **6.16.0** (20/09/2026).
Durée totale : ~1 h, dont ~20 min de mesures avec la coupole en mouvement.
Étapes 1 et 2 déjà faites le 20/09/2026 — **commencer à l'étape 3**.

---

## 1. Ce qui se passait, en deux mots

Depuis le début, la coupole tourne à **~43 °/min** alors que le boîtier de commande
du constructeur, lui, atteint **90 °/min** avec le même moteur. Tous les essais pour
combler cet écart ont échoué, et on avait fini par conclure que le driver était en
cause.

**C'était faux.** Voici l'image qui explique tout.

Pour faire tourner la coupole, le logiciel envoie des impulsions au moteur : une
impulsion = un pas. Plus les impulsions sont rapprochées, plus la coupole va vite.
On règle donc un **délai entre deux impulsions**, en microsecondes.

Le problème : l'ancien programme mettait **121 microsecondes à préparer chaque
impulsion**, avant même de commencer à attendre le délai demandé. C'est comme un
facteur à qui on dit « distribue une lettre toutes les 2 minutes » alors qu'il met
déjà 2 minutes à marcher jusqu'à la boîte aux lettres : quoi qu'on lui demande, il
ne fera jamais mieux qu'une lettre toutes les 4 minutes.

Résultat concret : quand on demandait 120 µs, le moteur recevait en réalité **247 µs**.
D'où les 45 °/min mesurés — au lieu des 90 attendus. **On mesurait le facteur, pas
le moteur.**

Et pour atteindre les 90 °/min du constructeur, il faudrait 124 µs entre deux
impulsions. L'ancien programme en consommait 121 rien que pour lui. Il restait
3 µs. C'était **arithmétiquement impossible** — aucun réglage n'y serait arrivé.

Deux détails qui confirment tout :

- Dans le tableau de mesures de décembre 2025, la ligne `0.00011` porte la mention
  « strengstens verboten ! ». Ce n'est pas le moteur qui décrochait : c'est le moment
  où le délai demandé passait **sous** le coût du programme. À partir de là, plus
  rien ne régulait les impulsions, elles partaient n'importe comment, et le moteur
  se mettait à vibrer. Un problème de **régularité**, pas de vitesse.
- L'écart « 42 vs 48 °/min » qui intriguait n'a jamais existé : c'était **la même
  vitesse**, calculée avec deux règles de conversion différentes.

**Le moteur n'a donc jamais été poussé au-delà de 247 µs par pas. La limite du
driver n'a jamais été mesurée — elle a été supposée.**

---

## 2. Ce qui a été corrigé

| | |
|---|---|
| **La vitesse sort du code** | Elle se règle maintenant depuis la page **Configuration → Avancé**, sans SSH. Valeur par défaut : 260 µs, soit exactement la vitesse actuelle. |
| **Le firmware du Pico** | La phase d'accélération calculait une formule compliquée à chaque pas — c'était le dernier endroit où le « facteur » existait encore. Les valeurs sont désormais préparées à l'avance. |
| **Un instrument de mesure** | Un script compare, à chaque palier de vitesse, **ce qu'on demande** et **ce que la coupole fait réellement** (lu sur l'encodeur). C'est précisément ce qui n'avait jamais été fait. |

**Important** : tant que le Pico n'est pas flashé et que la vitesse reste à 260 µs,
**tout se comporte exactement comme avant**. Cela a été vérifié : les commandes
envoyées au Pico sont identiques à l'octet près.

---

## 3. Le dernier doute est levé (20/09/2026)

Il restait un point physique susceptible de tout bloquer : **la tension d'alimentation
du driver**. À 124 µs par pas le moteur tourne à ~600 tr/min, et à cette vitesse le
couple en dépend directement.

**Réponse du site : driver DM860T, alimenté en 36 V.**

C'est **exactement la tension du boîtier UPAN**, qui atteint 96 °/min avec ce même
moteur. Autrement dit, la combinaison moteur + 36 V est déjà *démontrée* capable de
tourner à la vitesse visée — ce n'est plus une hypothèse.

Le calcul le confirme : établir les 2,5 A dans la bobine à 96 °/min demande entre 10 et
22 V selon l'inductance du moteur. Avec 36 V, la marge est confortable.

Trois faits concordent désormais : le boîtier constructeur fait 90 °/min, l'UPAN 96, et
la tension disponible correspond à cet ordre de grandeur. **Notre 43 °/min est le seul
chiffre qui détonne** — et on sait maintenant pourquoi.

⚠️ Au passage, cette réponse a corrigé une erreur de documentation : **deux drivers sont
montés en parallèle sur le même moteur** (le DM860T qui nous concerne, et le DM556T de
l'UPAN). Toute la doc de câblage désignait le mauvais. C'est corrigé.

---

## 4. Protocole

> ⚠️ **Règles à respecter**
> - **Ne pas modifier la vitesse (`delay_us`) avant d'avoir flashé le Pico** (étape 6).
>   L'ancien firmware ne sait pas accélérer jusqu'à une vitesse élevée : le moteur
>   décrocherait.
> - **Ne pas lancer le script de mesure avant le flash**, pour la même raison.
> - Pendant les mesures, **rester près de la coupole** et écouter : un décrochage
>   s'entend (bruit de calage, comme lors de l'incident de septembre).
> - Sur le Pico : **une seule source d'alimentation USB à la fois**.
> - La mise à jour redémarre les services, donc **la coupole bouge** (calibration au
>   démarrage). Choisir un moment tranquille.

### Étape 1 — Modèle du driver ✅ FAIT (20/09/2026)

**Réponse : DM860T.** Cela tranche l'hésitation de la documentation, et confirme que
c'est bien ce boîtier — et non le DM556T de l'UPAN, monté en parallèle sur le même
moteur — qui reçoit les signaux de notre Pico.

### Étape 2 — Tension d'alimentation ✅ FAIT (20/09/2026)

**Réponse : 36 V.** Même tension que l'UPAN. Voir section 3 : le dernier obstacle
physique est levé, rien ne s'oppose plus à viser les 90 °/min.

**→ Commencer à l'étape 3.**

### Étape 3 — Noter les micro-interrupteurs (DIP)

**À faire** : photographier ou noter la position des petits interrupteurs sur le côté
du driver (ON/OFF, généralement 8).

**À rapporter** : la photo, ou la suite ON/OFF.

*Cela permet de confirmer le réglage de courant et le microstepping (on attend
800 impulsions par tour moteur).*

---

*L'étape 3 se fait sans rien démonter ni rien lancer, et n'est pas bloquante : elle
sert à confirmer que le courant de phase et le microstepping sont bien ceux attendus.
Elle peut être faite en même temps que la suite.*

---

### Étape 4 — Installer la mise à jour 6.16.0

**À faire** : sur le tableau de bord, cliquer sur **« Mettre à jour »** et laisser
faire.

**Résultat attendu** : la version affichée en bas de page passe à **6.16.0**. La
coupole effectue sa calibration habituelle au redémarrage.

**Si une bannière de configuration apparaît** avec la mention `migrated` : c'est
normal, elle signale simplement qu'un nouveau réglage a été ajouté. Aucune valeur du
site n'a été touchée.

### Étape 5 — Vérifier que rien n'a changé

**À faire** : utiliser la coupole normalement — un GOTO, quelques JOG, éventuellement
un début de suivi.

**Résultat attendu** : **strictement le même comportement qu'avant**, même vitesse,
même son. C'est la vérification la plus importante du protocole : si quelque chose
diffère ici, **s'arrêter et prévenir**.

### Étape 6 — Sauvegarder puis flasher le Pico

En SSH sur le Pi :

```bash
ssh slenk@<pi-du-site>
cd ~/DriftApp

# 1. SAUVEGARDE de l'ancien firmware — à ne pas sauter
mkdir -p ~/firmware_backup
mpremote cp :main.py ~/firmware_backup/main.py
mpremote cp :step_generator.py ~/firmware_backup/step_generator.py
mpremote cp :ramp.py ~/firmware_backup/ramp.py
ls -l ~/firmware_backup        # doit lister les 3 fichiers

# 2. Flash du nouveau firmware
cd ~/DriftApp/firmware
mpremote cp main.py :main.py
mpremote cp step_generator.py :step_generator.py
mpremote cp ramp.py :ramp.py
```

**Résultat attendu** : aucune erreur. Le Pico redémarre tout seul.

**Pour revenir en arrière** à tout moment : recopier les trois fichiers de
`~/firmware_backup` vers le Pico (les mêmes commandes dans l'autre sens) et
débrancher/rebrancher le Pico.

### Étape 7 — Re-vérifier que rien n'a changé

**À faire** : redémarrer les services (page **Configuration → « Redémarrer les
services »**), puis refaire un GOTO et quelques JOG.

**Résultat attendu** : là encore, **comportement identique**. Le flash est censé être
neutre tant que la vitesse reste à 260 µs. Si ce n'est pas le cas, revenir à l'ancien
firmware (étape 6) et prévenir.

### Étape 8 — Campagne de mesure

C'est l'étape où la coupole va tourner de plus en plus vite. **Rester à proximité.**

```bash
cd ~/DriftApp

# D'abord voir le plan, sans rien faire bouger
python3 scripts/diagnostics/calibration_vitesse_encodeur.py --dry-run

# Puis la mesure réelle (demande de taper « go » avant de démarrer)
python3 scripts/diagnostics/calibration_vitesse_encodeur.py
```

Le script teste dix vitesses, de la plus lente à la plus rapide. À chaque palier il
fait tourner la coupole de 10° et compare la vitesse obtenue à la vitesse demandée.

**Résultat attendu** : une ligne par palier, du type

```
    délai       mesuré         visé   rendement
    260 µs      42.8°/min    42.8°/min      100 %
    235 µs      47.2°/min    47.3°/min      100 %
    ...
```

Le script **s'arrête tout seul** au premier palier où la coupole ne suit plus, et
annonce une valeur recommandée. Un rapport est écrit dans `logs/`.

**Ctrl-C** arrête tout immédiatement si quelque chose semble anormal.

**À rapporter** : le tableau complet affiché en fin de script, et le fichier
`logs/calibration_vitesse_*.json`.

### Étape 9 — Régler la vitesse définitive

**À faire** : page **Configuration → Avancé → motor_driver → delay_us**, saisir la
valeur recommandée par le script (jamais une valeur plus basse), enregistrer, puis
**« Redémarrer les services »**.

**Résultat attendu** : la coupole est plus rapide, sans bruit anormal.

**À valider sur une vraie session** avant de considérer l'affaire close : un suivi
complet, avec un passage au méridien si possible.

---

## 5. Résumé de ce qu'il faut rapporter

1. ~~Modèle du driver~~ — fait : DM860T
2. ~~Tension d'alimentation~~ — fait : 36 V
3. Position des DIP, ou photo (étape 3)
4. Confirmation que rien n'a changé après la mise à jour (étape 5) puis après le
   flash (étape 7)
5. Le tableau de mesures complet (étape 8) + le fichier `logs/calibration_vitesse_*.json`

En cas de doute à n'importe quelle étape : **s'arrêter et demander**. Rien dans ce
protocole n'est urgent, et l'ancien fonctionnement reste disponible à tout moment
(retour arrière du firmware + `delay_us` à 260).
