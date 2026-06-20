# Diagnostic hardware — protocoles multimètre/pinout pour Serge

Procédures **durables** (techniques de mesure, faits matériels stables). Les IPs/ports
viennent toujours de `read_terrain_values.py`, jamais d'ici. La topologie de câblage du
cimier a évolué (Darlington → commun cathode direct → pivot Shelly capteur-only) : se
référer à la mémoire projet en cours pour le schéma exact ; les **techniques** ci-dessous
restent valables.

## Sommaire
- [Règles d'or (à rappeler systématiquement)](#règles-dor-à-rappeler-systématiquement)
- [Pico W : injoignable / surcourant / court-circuit](#pico-w--injoignable--surcourant--court-circuit)
- [Pico W : pinout et masses](#pico-w--pinout-et-masses)
- [Moteur muet ou qui « frémit » sans tourner](#moteur-muet-ou-qui-frémit-sans-tourner)
- [DM556T : alimentation, DIP, ENA, bobines](#dm556t--alimentation-dip-ena-bobines)
- [ULN2803A (si présent dans le montage)](#uln2803a-si-présent-dans-le-montage)
- [Shelly (alim + pilotage cimier)](#shelly-alim--pilotage-cimier)

## Règles d'or (à rappeler systématiquement)

- **Jamais QC 3.0 + câble USB du Pi simultanément** sur le Pico W (back-feed VBUS).
  Une seule source d'alim USB à la fois.
- **Jamais de +5V externe sur la pin 40 (VBUS)** en parallèle de l'USB → surcourant.
- **N'importe quel GND du Pico W convient** : pins 3, 8, 13, 18, 23, 28, 33, 38. La 38
  n'a rien de spécial (erreur classique : se focaliser dessus).
- **Souder un connecteur header femelle Dupont** sur le Pico, pas les fils en direct.
- **Vérifier chaque pin de destination au multimètre AVANT de souder** (continuité avec
  un GND connu / OUVERT vs tout VCC), puis connecter **fil par fil avec re-test** entre
  chaque étape.
- **STEP en 3,3 V direct suffit** pour le DM556T (la coupole le prouve depuis des mois) :
  pas besoin de réhausseur 3,3→5V ni de Darlington pour le simple signal STEP/DIR.

## Pico W : injoignable / surcourant / court-circuit

Symptômes typiques : Pico absent du réseau, diode USB qui s'éteint au branchement
(protection surcourant), message « USB current exceed », écran du Pi qui s'éteint.

Protocole multimètre (Pico **débranché de l'USB et du harnais**) :
1. Continuité entre pins **38↔39, 38↔40, 38↔36** → doit être **OUVERTE**.
   *(fermée = pont de soudure dans la zone 36-40, cause #1)*
2. Continuité **chaque sortie GPIO ↔ 38 (GND)** → **OUVERTE**.
3. Harnais seul (Pico débranché) : continuité fil-à-fil entre tous les fils du
   connecteur → **OUVERTE partout**.
4. Vérifier que « la pin 38 » est bien une GND : continuité 38 ↔ pin 3 (autre GND)
   → **FERMÉE**. Sinon faux GND (mauvaise pin).
5. Si 1-4 OK → test fonctionnel : USB **seul** (sans harnais), le Pico doit booter
   (= pas grillé), puis rebrancher **1 fil à la fois** avec re-test à chaque étape.

Erreur réelle déjà vécue : fil de masse soudé sur le **3,3 V** d'un module au lieu du
**GND** du module → court 3,3 V → GND Pico → régulateur interne grillé. Toujours
vérifier le point de masse côté module, pas seulement côté Pico.

## Pico W : pinout et masses

Pinout officiel à imprimer : https://datasheets.raspberrypi.com/picow/PicoW-A4-Pinout.pdf
Marquer au feutre les pins **36 (3V3 OUT) / 37 (3V3 EN) / 38 (GND) / 39 (VSYS) /
40 (VBUS)** avant toute soudure. Mesure attendue sur une sortie GPIO saine pilotée :
**≈ 3,07 V** en HIGH, **0 V** en LOW (un réhausseur en série tirerait ça vers ~2,5 V →
le retirer).

## Moteur muet ou qui « frémit » sans tourner

Arbre de décision (le signal STEP/DIR a déjà été validé côté Pico/firmware → ne PAS
re-suspecter le firmware si GP step mesure des fronts propres) :

- **Aucun bruit du tout** → vérifier l'alim puissance du driver et l'ENA (driver pas
  énergisé). Voir section DM556T.
- **Micro-claquement / frémissement à chaque pas mais pas de rotation** → typiquement
  **courant de phase trop bas** (DIP) ou **une bobine ouverte** (câblage moteur). Voir
  DM556T DIP + bobines.

## DM556T : alimentation, DIP, ENA, bobines

Suspects par ordre de probabilité quand le signal arrive mais le moteur ne tourne pas :
1. **Alim puissance moteur** V+/VDC du DM556T : séparée des rails logiques, typiquement
   **24-48 V**. Mesurer sa présence. NE PAS la confondre avec PUL+/DIR+ (logique).
2. **DIP switches** : courant de phase (trop bas = pas de couple) et microstepping.
   Comparer aux réglages connus de la coupole.
3. **ENA** : flottant = activé selon le câblage ; vérifier qu'il n'est pas maintenu en
   état « désactivé ».
4. **4 fils moteur A+/A−/B+/B−** : mesurer la **continuité de chaque paire** (A+↔A−,
   B+↔B−) → quelques ohms attendus. Bobine **ouverte** = moteur qui frémit sans tourner.

## ULN2803A (si présent dans le montage)

Le montage cimier a parfois utilisé un ULN2803A en sink ; faits stables :
- **pin 9 = GND commun**, **IN(x) ← GPIO Pico**, **OUT(x) → PUL-/DIR-/ENA- du DM556T**.
- **pin 10 (COM)** : laissée **flottante** pour une charge résistive (opto interne du
  DM556T = LED + résistance, pas d'inductance). Ne la câbler à V+ **que** pour une
  charge inductive (relais/solénoïde/moteur DC).
- Vérif hors tension : **pin 10 ↔ pin 9 OUVERTE** (sinon ULN HS) ; **pin 10 ↔ rail +
  OUVERTE** (sinon COM câblé par erreur).

## Shelly (alim + pilotage cimier)

Shelly Gen 1 (REST classique, pattern `/relay/0`). Host lu en config (`power_switch.host`).
```bash
curl -s http://<shelly.host>/relay/0                 # status → {"ison": true/false}
curl -s "http://<shelly.host>/relay/0?turn=on"       # forcer ON (test bringup)
curl -s "http://<shelly.host>/relay/0?turn=off"
```
Attendu : réponse JSON quasi-instantanée. Timeout = Shelly injoignable (WiFi/IP/alim).

Points d'attention pivot Shelly (pilotage moteur) :
- Les Shelly MOT/UPDN alimentés **en aval du 24 V** rebootent à chaque cycle (~2 s
  injoignables). Le Shelly **MOTOR doit avoir `default_state=ON`** (relais fermé =
  moteur arrêté au réveil), sinon moteur incontrôlé pendant le boot.
- Pour découpler les problèmes pendant un bringup : forcer le Shelly d'alim **ON
  manuellement** via `curl`, puis tester le reste séparément.
