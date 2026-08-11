# Capteur de pluie — mini-programme de validation terrain

**Date** : 2026-08-11
**Statut** : design validé, prêt pour plan d'implémentation
**Périmètre** : un standalone de diagnostic. Ni provider, ni automatisation, ni UI.

---

## 1. Contexte

Serge a installé le matériel décrit dans le backlog météo :

- module **AZdelivery MH-RD** (plaque de détection + carte comparateur LM393, sortie D0 TOR,
  seuil réglé par trimpot, LED DO embarquée) — fiche `docs/AZdelivery raindrops module.pdf` ;
- un **Shelly Plus Uni** dédié à l'adresse **192.168.1.87**, distinct du Uni+ `.84` dont les
  deux entrées sont déjà prises par les butées HAUT/BAS du cimier ;
- D0 câblé sur ce qu'il décrit comme « l'entrée digitale n°1 » du Shelly.

Le montage est à l'extérieur de la coupole (photo `logs/WhatsApp Image 2026-08-11 at 15.22.06.jpeg` :
plaque inclinée sur équerre, boîtier étanche sur poteau). L'écran d'exploitation est à l'intérieur.
D'où la demande : **un mini-programme de test avec signal lumineux et sonore**, pour valider le
concept sans faire l'aller-retour entre le capteur et l'écran à chaque goutte d'eau.

Ce cycle applique la méthode qui a fonctionné pour le cimier V3 : un standalone nu validé sur le
terrain **d'abord**, les conventions figées dans la config **ensuite**. Le standalone
`scripts/diagnostics/cimier_manual.py` avait tourné du premier coup, aux valeurs par défaut.

## 2. Objectif et critères de succès

Le programme doit permettre à Serge, seul, dehors, un verre d'eau à la main, d'établir :

1. **quelle entrée** du Shelly `.87` porte réellement le D0 (`id=0` ou `id=1`) ;
2. **la polarité** telle que le Shelly la rapporte (`state=true` = pluie, ou l'inverse) ;
3. **le réglage du trimpot** — combien d'eau déclenche la bascule ;
4. que la chaîne complète **capteur → Shelly → réseau → Python** est vivante ;
5. **le temps de séchage** du MH-RD — combien de temps le capteur reste vu « mouillé » après la
   dernière goutte. C'est la valeur qui fixera `clear_delay_s` (600 s proposés le 31/05, jamais
   mesurés).

Ces cinq points sont des *résultats de test*, pas des paramètres à deviner ici. Aucun n'est figé
dans le code : ils seront gravés en config au cycle suivant.

Succès = Serge revient avec les cinq réponses, obtenues en une seule sortie, sans assistance à
distance.

## 3. Décisions de conception

### 3.1 Un standalone, pas une intégration

`scripts/diagnostics/pluie_manual.py` : Python 3 **stdlib pure**, aucun import du projet, aucune
lecture de `data/config.json`, aucun IPC, aucune dépendance à Django ou au Pi. Se lance depuis
n'importe quelle machine du réseau local — le poste de test retenu est **le portable que Serge
emporte dehors**, à côté du capteur, pour avoir le bip et l'affichage sous les yeux.

Alternatives écartées :

- *page web servie par le Pi, ouverte sur le téléphone* — le son d'un smartphone porte mieux
  dehors, mais il faut un bout de serveur, du Web Audio (qui exige une interaction utilisateur
  avant de pouvoir émettre) et un Pi allumé. Trop de pièces pour un test de concept ;
- *brancher le capteur dans le simulateur ou Django* — on ne validerait plus le capteur mais
  l'intégration, qui est justement le cycle suivant.

### 3.2 Lire les deux entrées, pas « la n°1 »

« Entrée digitale n°1 » est ambigu : les entrées sont sérigraphiées 1 et 2 sur le boîtier, alors
que l'API RPC les numérote `id=0` et `id=1`. Plutôt que de parier — et de risquer un aller-retour
de plusieurs jours avec une machine de dev à 800 km — **le programme lit et affiche les deux**.
L'ambiguïté se dissout sur le terrain : celle qui bouge quand l'eau tombe est la bonne.

### 3.3 Bip aux transitions seulement

Un bip à chaque tour de boucle serait insupportable sous une pluie continue et masquerait
l'information utile. Le son marque **les changements d'état**, avec trois tonalités distinctes :

| Événement | Signal |
|---|---|
| sec → pluie | bip montant (deux notes) |
| pluie → sec | bip descendant (deux notes) |
| Shelly injoignable | triple bip grave |

Le cas « injoignable » est un signal sonore à part entière, jamais un silence : c'est le mode de
défaillance qu'on redoute le plus en exploitation (fiabilité Shelly Gen 1 connue), et le test doit
apprendre à Serge à le reconnaître à l'oreille.

### 3.4 Cascade sonore multiplateforme, annoncée au démarrage

L'OS du portable n'est pas connu avec certitude. Le programme essaie dans l'ordre :
`winsound` (Windows, stdlib) → `paplay` → `aplay` (Linux) → `afplay` (macOS) → `\a` (BEL terminal).
Pour les trois commandes externes, le WAV est généré en mémoire avec le module `wave` de la
stdlib et écrit dans un fichier temporaire.

Le backend retenu est **détecté une fois au démarrage et affiché en clair** :

```
son : paplay
son : BEL terminal — beaucoup d'émulateurs le coupent, vérifiez le volume avant de sortir
```

Serge sait ainsi, *avant* de traverser la cour, s'il pourra compter sur le son.

### 3.5 Signal lumineux : bandeau ANSI plein contraste

L'état courant occupe un bandeau large, lisible d'un coup d'œil sur un écran en extérieur :
**vert SEC**, **rouge PLUIE**, **jaune INJOIGNABLE**. Le bloc affiché — bandeau, durée de l'état
courant, puis les 5 dernières transitions — est redessiné en place à chaque tour de boucle
(retour curseur ANSI), pour que l'écran ne défile pas pendant une campagne d'une heure. Rappel : le module MH-RD porte
déjà une LED DO qui s'allume à la détection — le bandeau ne duplique pas cette information locale,
il prouve que le Shelly et le réseau l'ont vue.

### 3.6 Journal horodaté des transitions

Chaque transition est horodatée, affichée sous le bandeau (les 5 dernières restent visibles) et
**écrite immédiatement dans un fichier**, en append avec `flush` — un `Ctrl-C` ou une coupure ne
doit rien perdre d'une campagne d'une heure.

Format, une ligne par transition, lisible à l'œil autant qu'exploitable :

```
2026-08-11T15:22:06 SEC   -> PLUIE  (état précédent tenu 412 s)
2026-08-11T15:24:31 PLUIE -> SEC    (état précédent tenu 145 s)
```

La durée de l'état précédent est portée sur la ligne de transition, et non calculée après coup :
c'est elle qui répond directement à la question du séchage. Serge verse son eau, note l'heure où
il s'arrête, et la durée de l'épisode PLUIE qui suit **est** le temps de séchage.

À la sortie (`Ctrl-C`), le programme affiche un **résumé des épisodes PLUIE** avec leurs durées et
la plus longue observée. C'est ce résumé, pas le fichier brut, que Serge nous renvoie pour trancher
`clear_delay_s`.

Fichier par défaut : `pluie_test_<AAAAMMJJ_HHMMSS>.log` **dans le répertoire courant** — pas dans
`logs/` du dépôt, qui n'existe pas forcément sur le portable de Serge. Surchargeable par `--log`.

### 3.7 Mode `--demo`

Alterne SEC / PLUIE / INJOIGNABLE sans toucher au réseau. Serge vérifie que le son et les couleurs
fonctionnent sur *son* portable avant de sortir. Une dizaine de lignes qui économisent un
aller-retour terrain.

## 4. Interface

```
python3 scripts/diagnostics/pluie_manual.py read
python3 scripts/diagnostics/pluie_manual.py monitor [--interval 1.0]
python3 scripts/diagnostics/pluie_manual.py monitor --demo
```

- **`read`** — une lecture ponctuelle, affiche le **JSON brut** des deux entrées et l'interprétation.
  C'est la commande du verre d'eau : lancer, arroser, relancer, comparer.
- **`monitor`** — boucle de polling, bandeau + bips + journal. `Ctrl-C` pour sortir, ce qui affiche
  le résumé des épisodes PLUIE.

Flags communs : `--host` (défaut `192.168.1.87`), `--input {0,1,both}` (défaut `both`),
`--interval` (défaut `1.0` s), `--timeout` (défaut `3.0` s), `--invert`, `--no-sound`, `--demo`,
`--log CHEMIN` (défaut `pluie_test_<horodatage>.log` dans le répertoire courant), `--no-log`.

Les valeurs terrain n'apparaissent que comme **défauts CLI documentés et surchargeables**, comme
dans `cimier_manual.py`. La règle « pas d'IP en dur » vise le code applicatif, qui lit
`data/config.json` ; un standalone de diagnostic doit rester lançable d'une seule ligne, sans config.

## 5. Détails techniques

**Transport** : `GET http://<host>/rpc/Input.GetStatus?id=<n>` → `{"id": n, "state": <bool>}`,
identique à `ShellySwitchReader` (`core/hardware/shelly_switch_reader.py`), sans le réutiliser —
le standalone reste autonome. `urllib.request` avec timeout.

**Erreurs** : `urllib.error.URLError`, `OSError`, HTTP ≠ 200, JSON invalide, payload sans `state` →
état **INJOIGNABLE**. Le programme ne s'arrête jamais sur une erreur réseau : il l'affiche, la
sonorise, et continue de poller. Une coupure Wi-Fi passagère ne doit pas tuer un test en cours.

**Interprétation** : par défaut `state=true` → PLUIE ; `--invert` bascule. La datasheet donne le D0
du LM393 actif bas (D0 = 0 quand pluie), mais ce que le Shelly rapporte dépend de son câblage
d'entrée — d'où un flag, et non une constante.

## 6. Vérification avant envoi

Le répertoire `scripts/diagnostics/` n'est pas collecté par pytest, et ce script n'introduit aucun
test unitaire — cohérent avec `cimier_manual.py`. La vérification est manuelle, en deux temps :

1. `--demo` : les trois états s'affichent, les trois tonalités sortent, le backend son est annoncé,
   le journal se remplit et le résumé de sortie liste les épisodes PLUIE simulés ;
2. **faux Shelly local** : un serveur HTTP jetable d'une dizaine de lignes (lancé en `python3 -c`,
   non versionné) répond `{"id":0,"state":true}` sur `/rpc/Input.GetStatus`. On pointe le script
   dessus via `--host 127.0.0.1:8099` — l'URL accepte un `host:port` tel quel. Vérifie le parsing,
   les transitions, les durées consignées et le passage en INJOIGNABLE quand on tue le serveur.

## 7. Hors périmètre

Explicitement remis au cycle suivant, une fois les conventions établies sur le terrain :

- `ShellyRainWeatherProvider` (contrat `WeatherProvider`, `weather_provider.type` en config) ;
- fermeture d'urgence sur pluie (veille `rain_watch_interval_s` → `tracking_stop` → `goto 45°` → `close`) ;
- point météo sur le dashboard ;
- fail-safe « Shelly injoignable = risque pluie » — le mini-programme se contente de le **signaler**,
  il ne décide de rien ;
- lecture de l'entrée analogique A0 (intensité de pluie).

Le **journal horodaté** fait en revanche partie du périmètre (§3.6) : il permet de couvrir les cinq
questions du §2 en une seule sortie terrain, plutôt que de renvoyer Serge dehors pour mesurer le
séchage.

## 8. Risque connu

Le D0 du LM393 sort en logique 3,3 V. Si l'entrée digitale du Shelly Plus Uni attend une tension
plus élevée ou un contact sec, elle ne bougera jamais, quelle que soit la quantité d'eau. La
commande `read` le révélera dès le premier essai. **C'est un résultat de test utile, pas un échec
du programme** — il orienterait vers un étage d'adaptation (transistor, optocoupleur, ou passage
par la sortie relais du module).

---

## Références

- Backlog : mémoire `project_cimier_weather_rain_backlog`
- Spec initiale (approche GPIO, remplacée) : `docs/superpowers/specs/2026-05-31-cimier-capteur-pluie-design.md`
- Standalone modèle : `scripts/diagnostics/cimier_manual.py`
- Infra RPC équivalente : `core/hardware/shelly_switch_reader.py`
- Contrat météo : `core/hardware/weather_provider.py`
- Fiche capteur : `docs/AZdelivery raindrops module.pdf`
