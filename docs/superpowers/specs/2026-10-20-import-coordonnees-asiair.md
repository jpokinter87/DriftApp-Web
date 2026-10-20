# Import des coordonnées pointées par l'ASIAIR

Date : 20/10/2026 — statut : **spec validée** (décisions JP du 20/10)

## Besoin

Serge a obtenu de l'ASIAIR les coordonnées pointées par la monture
(`test_suivi5.py` : JSON-RPC `scope_get_info` sur le port TCP 4400, réponse
`result.RA` en heures, `result.Dec` en degrés, `result.sidereal_time`).

On veut un bouton qui récupère ces coordonnées et les injecte dans la recherche
d'objet. Pour une cible faible, absente du catalogue et de SIMBAD, on n'aura plus
à recopier l'AD/Déc à la main : la monture vient d'y pointer, souvent après un
plate-solve.

Ce n'est pas encore l'heure du retournement au méridien (piste inclinomètre,
6.21.10–6.21.11), mais c'est le premier canal ASIAIR → DriftApp.

## Décisions

| # | Question | Décision |
|---|---|---|
| 1 | Époque des coordonnées ASIAIR | **J2000, sans conversion** — hypothèse non vérifiée, cf. « Point ouvert » |
| 2 | Effet du clic | **Injection directe**, comme une recherche réussie |
| 3 | Bouton sans adresse configurée | **Toujours actif** ; le clic affiche l'erreur |
| 4 | Libellé, place | **« ASIAIR »** à droite de « Coordonnées », même ligne |

Adresse et port dans `data/config.json` (règle : aucune adresse terrain en dur
dans le code), nouvelle section `asiair`.

## Conception

### Configuration

`data/config.template.json`, nouvelle section :

```json
"asiair": {
  "_comment": "ASIAIR de la monture (bouton « ASIAIR » du dashboard : importe l'AD/Déc pointée). Port JSON-RPC 4400.",
  "host": "192.168.1.70",
  "port": 4400,
  "timeout_s": 3.0
}
```

Le merge structurel (chantier A) l'ajoute au `config.json` terrain à la mise à
jour ; elle apparaît seule sur la page Configuration (aide portée par
`_comment`). `host` vide → erreur « ASIAIR non configuré » au clic.

`core/config/config_loader.py` : dataclass `AsiairConfig(host, port, timeout_s)`,
champ `DriftAppConfig.asiair` avec défaut (config sans section → valeurs par
défaut, pas d'erreur).

### Lecture ASIAIR — `core/hardware/asiair_client.py`

`lire_coordonnees(host, port, timeout_s) -> (ra_deg, dec_deg)` :

- connexion TCP, envoi `{"id": …, "method": "scope_get_info"}` + `\r\n` ;
- lecture ligne par ligne jusqu'à la réponse portant **notre** `id` (l'ASIAIR
  émet aussi des événements non sollicités sur la même connexion — le script de
  Serge les écarte déjà) ; délai global borné par `timeout_s` ;
- `ra_deg = RA × 15`, `dec_deg = Dec`, normalisés/bornés (RA dans [0 ; 360[) ;
- **l'époque est traitée à cet endroit et nulle part ailleurs** : si l'ASIAIR
  s'avère renvoyer du JNow, la conversion vers J2000 s'ajoute ici ;
- échecs → `AsiairError` avec un message lisible pour Serge : injoignable
  (connexion refusée / délai), réponse sans `RA`/`Dec`, réponse d'erreur JSON-RPC.

Bibliothèque standard seule (`socket`, `json`), pas de dépendance.

### API — `GET /api/tracking/asiair/`

Dans `web/tracking/views.py`, à côté de `ManualCoordsView` :

- lit `asiair` dans la config ; `host` vide → 400 « ASIAIR non configuré » ;
- `lire_coordonnees(...)` ; `AsiairError` → **502** avec le message ;
- succès → même format que `/api/tracking/coords/` : `ra_deg`, `dec_deg`,
  `meridian_seconds`, `meridian_time` (réutilise `_add_meridian_info`).

Requête synchrone, bornée par `timeout_s` (3 s) : acceptable pour un clic.

### Dashboard

- `dashboard.html` : bouton `#btn-asiair` « ASIAIR » (`btn btn-secondary`) après
  « Coordonnées ». Aucun survol requis (écran tactile).
- `dashboard.js` : `importAsiair()` → `GET /api/tracking/asiair/`, puis
  `applyManualCoords(nom, ra, dec, 'ASIAIR')` — la fonction existante gagne un
  paramètre de libellé (« manuel » par défaut, « ASIAIR » ici), rien d'autre ne
  change dans la chaîne de suivi (`ra_deg`/`dec_deg` déjà transmis jusqu'au
  `motor_service` depuis la 6.17).
- Nom : contenu du champ objet s'il n'est pas vide, sinon
  `ASIAIR RA hhhmmmss.ss DEC ±dd°mm'ss"`.
- Bouton désactivé pendant la requête (anti double clic), message au journal :
  `Lecture ASIAIR…` puis succès ou `ASIAIR : <motif>`.
- 720p : vérifier que la ligne tient avec 3 boutons (mode compact).

## Hors périmètre

- Heure du retournement au méridien (autre chantier).
- Lecture continue / suivi de la monture : un clic = une lecture.
- Simulateur ASIAIR dans `start_dev.sh` : les tests utilisent un vrai serveur
  TCP local ; en dev, l'adresse terrain répond « injoignable » au bout de 3 s.

## Point ouvert — à faire vérifier par Serge

1. **Époque.** GOTO sur M31 + plate-solve, puis `python3 test_suivi5.py` :
   - J2000 : RA ≈ 0,7123 h (00h42m44s), Dec ≈ +41,27° ;
   - JNow 2026 : RA ≈ 0,736 h (00h44m10s), Dec ≈ +41,40°.
2. **Réponse complète** de `scope_get_info` (afficher tout `result`) : un champ
   d'état (monture connectée, suivi, parquée) permettrait de refuser l'import
   d'une monture parquée. Non exploité tant qu'on ne le connaît pas.

## Critères de succès

- Tests : client contre un serveur TCP local (réponse nominale, événements
  parasites avant la réponse, réponse d'erreur, champs manquants, délai,
  connexion refusée) ; vue (succès, host vide → 400, ASIAIR en échec → 502) ;
  parsing config (section absente → défauts).
- Stack dev : bouton « ASIAIR » contre un faux serveur local → coordonnées
  affichées « (ASIAIR) », cartouche méridien, « Démarrer le suivi » armé, suivi
  démarré sur ces coordonnées.
- `ruff format --check .`, `ruff check .`, suite pytest verte.
