# Script de base cimier V3 — séquencement manuel des commandes Shelly

**Date** : 2026-06-15
**Statut** : design validé, prêt pour plan d'implémentation
**Contexte** : retour terrain Serge 14-15/06 — le cimier part en vrille (sens aléatoire,
mouvement erratique, stops fantômes) malgré 6.7.1/6.7.2/6.7.3. Hypothèse partagée JP/Serge
(15/06 22:00) : le code traîne 7-8 évolutions correspondant à du hardware différent ; un
résidu d'ancienne couche fausse le comportement. Décision : repartir d'un **script de base nu**
qui séquence les commandes brutes, le valider sur le hardware, puis calquer ces commandes dans
le code derrière les boutons existants.

## Source de vérité

`docs/synoptique electronique cimier V3.pdf` (synoptique Serge, page « Commandes » +
« Cinématique »). Le script encode cette vérité **sans aucune abstraction héritée**.

### Commandes brutes (verbatim synoptique)

| Élément | IP | Action | URL |
|---|---|---|---|
| SHELLY-1-24 (alim module) | .83 | ON | `http://192.168.1.83/relay/0?turn=on` |
| | | OFF | `http://192.168.1.83/relay/0?turn=off` |
| SHELLY-1-MOT (moteur) | .85 | **moteur tourne** | `http://192.168.1.85/relay/0?turn=off` ⚠️ inversé |
| | | **moteur arrêt** | `http://192.168.1.85/relay/0?turn=on` |
| SHELLY-1-UPDN (sens) | .86 | UP (montée) | `http://192.168.1.86/relay/0?turn=on` |
| | | DN (descente) | `http://192.168.1.86/relay/0?turn=off` |
| SHELLY-HAUT (état) | .84 | lecture | `http://192.168.1.84/rpc/Input.GetStatus?id=1` |
| SHELLY-BAS (état) | .84 | lecture | `http://192.168.1.84/rpc/Input.GetStatus?id=0` |

**Logique moteur inversée** (annotation Serge) : moteur à l'arrêt quand le contact est fermé,
donc relais `turn=on`. → `motor_run` = `turn=off`, `motor_stop` = `turn=on`.

**Lecture butées** : `state=True` → butée *Ouverte* (contact ouvert, butée NON atteinte) ;
`state=False` → butée *fermée* (contact fermé, **butée atteinte**).

> ⚠️ Piège de nommage : le tableau « Commandes » du synoptique étiquette `ON/OFF` selon
> l'intention *moteur*, la « Cinématique » étiquette `MOT/ON` `MOT/OFF` selon l'état du *relais*.
> Les deux sont donc opposés. Le script supprime l'ambiguïté avec `motor_run()` / `motor_stop()`.

### Cinématique (verbatim synoptique)

**Ouverture** :
1. SHELLY-1-24/ON : alimentation du module cimier
2. Attente 2 s (à mesurer) — appairage Wifi des Shelly
3. SHELLY-1-MOT démarre par défaut à l'état relais ON (moteur éteint)
4. SHELLY-1-UPDN/UP : sens montée
5. Vérifier état SHELLY-HAUT. Si fermé (False) → fin (déjà ouvert). Si Ouvert (True) → suite
6. SHELLY-1-MOT/OFF (relais) : démarrage du moteur
7. Surveillance switch haut (boucle SHELLY-HAUT toutes les 100 ms)
8. SHELLY-1-MOT/ON (relais) quand le switch haut est fermé (HAUT=False)
9. SHELLY-1-24/OFF : coupure d'alimentation

**Fermeture** : identique, sens DN (.86 turn=off) + surveillance SHELLY-BAS.

**Stop** : SHELLY-1-MOT/ON (relais → moteur arrêt).

## Décisions de design (validées)

- **Forme** : Python standalone, fichier unique.
- **Source IPs/conventions** : constantes en tête du fichier + flags CLI pour basculer une
  convention à la volée. Script diagnostic jetable → hors règle no-hardcoded-IPs (qui vise le
  code de prod ; la vérité découverte sera reportée dans `config.json` en phase 2).
- **Emplacement** : `scripts/diagnostics/cimier_manual.py`.
- **Dépendances** : stdlib `urllib` uniquement → lançable en `python3` pur sur le Pi, hors env uv.

## Architecture du script

**Bloc `CONFIG`** en tête : 4 hosts + templates d'URL + conventions, recopiés du synoptique,
commentaire pointant le PDF.

**Helper HTTP transparent** `_call(url)` : imprime l'URL exacte puis la réponse (Serge voit
littéralement le `curl` équivalent). Timeout configurable.

**Primitives** (une commande = un appel manuel) :
- `power on|off` → `.83 turn=on|off`
- `dir up|down` → `.86 turn=on|off`
- `motor run|stop` → `.85 turn=off|on` (inversé)
- `read` → lit HAUT (id=1) + BAS (id=0), affiche brut + interprété (Ouvert/fermé)

**Composites** (raffinements, ajoutés après validation des primitives) — séquencent la
cinématique exacte :
- `open` / `close` : 24V ON → attente `--settle` → dir → pré-check butée → motor run →
  poll butée /100 ms → motor stop → 24V OFF
- `stop` : motor stop immédiat

**Flags de validation au banc** : `--settle=2.0`, `--mot-run=off|on`, `--dir-up=on|off`,
`--switch-closed=false|true`, `--timeout=3.0`, `--poll=0.1`.

### CLI

```
python3 cimier_manual.py read          # état des deux butées
python3 cimier_manual.py power on
python3 cimier_manual.py dir up
python3 cimier_manual.py motor run     # → .85 turn=off
python3 cimier_manual.py motor stop
python3 cimier_manual.py open          # séquence complète une fois primitives OK
python3 cimier_manual.py close
python3 cimier_manual.py stop
```

## Hors périmètre (YAGNI)

Pas de cooldown, pas de mode drop, pas de `_pending_command`, pas de parser de config, pas de
Noop*, pas d'IPC, pas de Shelly 12V/.82 ni 220V/.81 (chaîne d'alim amont gérée par le Konyks,
hors mouvement). Du séquencement nu.

## Tests

2-3 tests pytest légers sur la **logique pure**, HTTP mocké (`urllib` patché) :
- construction des URLs primitives selon les conventions/flags
- parsing du booléen butée (`{"state": true}` → Ouvert, `false` → fermé/atteinte)
- la boucle `open` s'arrête dès que la butée lue passe à « fermée »

Pas plus : c'est un outil de banc, la vraie validation est l'exécution sur hardware par Serge.

## Phase 2 (séparée, après validation terrain)

Calquer les primitives validées derrière les boutons Django existants (ouvrir/fermer/stop), en
**corrigeant dans `data/config.json`** les deux conventions que le synoptique contredit :
- `motor_shelly.motor_on_relay_state: true` → **`false`** (moteur tourne quand `turn=off`)
- `switch_reader` : aligner sémantique/`invert` sur « butée atteinte = state False »

Ces corrections sont la cible réelle du chantier ; le script sert à les **prouver** sur le
hardware avant de toucher au code de prod.

## Critères de succès

1. Serge lance `read` → voit l'état réel des deux butées, cohérent avec la position physique.
2. Serge enchaîne `power on` / `dir up` / `motor run` / `motor stop` à la main → le moteur
   tourne dans le bon sens et s'arrête, de façon déterministe (plus de sens aléatoire).
3. `open` puis `close` font un cycle complet propre, le moteur s'arrête sur butée (pas de
   timeout, pas de stop fantôme).
4. Les valeurs de convention validées (`--mot-run`, `--dir-up`, `--switch-closed`, `--settle`)
   sont consignées → prêtes à reporter dans `config.json` en phase 2.
