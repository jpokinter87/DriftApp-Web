"""
Abstraction logique de la meteo cimier (v6.0 Phase 2, capteur pluie v6.12+).

Strategy minimaliste qui repond a deux questions binaires que la suite v6.0
voudra poser avant d'agir :

  - "puis-je ouvrir le cimier maintenant ?"        -> is_safe_to_open()
  - "puis-je le laisser ouvert ?"                  -> is_safe_to_keep_open()
  - "que dis-je sur la meteo ? (logs, debug)"     -> describe()

Tant qu'aucun capteur reel n'existe pour un phenomene donne, on ne fige pas
de dataclass WeatherSnapshot ni de seuils dans la config — describe() expose
un dict opaque pour les logs.

Implementations disponibles :
  - NoopWeatherProvider : repond toujours True, describe() = {"provider": "noop"}.
  - ShellyRainWeatherProvider : capteur de pluie MH-RD lu via un Shelly Plus
    Uni dedie (RPC Input.GetStatus), avec anti-rebond et fail-safe asymetrique
    sur capteur injoignable.
  - RainProtection : politique d'armement (case "Protection pluie") + verrou
    anti-reouverture autour d'un provider pluie.

Le module est volontairement court. Il copie le pattern de
core/hardware/power_switch.py (Strategy + Noop + factory).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Protocol, runtime_checkable

if TYPE_CHECKING:
    from core.config.config_loader import WeatherProviderConfig


class WeatherProviderError(Exception):
    """Erreur de communication avec le provider meteo (reserve aux providers reels)."""


@runtime_checkable
class WeatherProvider(Protocol):
    """Contrat minimaliste expose aux consommateurs (cimier_service, scheduler Phase 3).

    Trois methodes seulement. Si un provider reel a besoin d'exposer plus
    d'information, il le fait via describe() — pas en ajoutant des methodes
    publiques (qui casseraient le contrat des consommateurs existants).
    """

    def is_safe_to_open(self) -> bool: ...

    def is_safe_to_keep_open(self) -> bool: ...

    def describe(self) -> Dict[str, Any]: ...


class NoopWeatherProvider:
    """Provider trivial : repond toujours True. Pas de capteur, pas de seuils.

    Default Phase 2 partout (dev, prod, tests). Phase 3 le consultera sans
    blocage runtime. Un capteur reel arrivera dans un milestone ulterieur.
    """

    def is_safe_to_open(self) -> bool:
        return True

    def is_safe_to_keep_open(self) -> bool:
        return True

    def describe(self) -> Dict[str, Any]:
        return {"provider": "noop"}


# États confirmés du capteur de pluie.
RAIN_WET = "wet"
RAIN_DRY = "dry"
RAIN_UNREACHABLE = "unreachable"


class ShellyRainWeatherProvider:
    """Capteur de pluie MH-RD lu via un Shelly Plus Uni dédié.

    La sortie D0 du comparateur LM393 est câblée sur une entrée digitale du
    Shelly, lue en RPC (``Input.GetStatus``). Le seuil pluie/sec est réglé en
    **matériel** par le trimpot du module : ce provider ne fait que lire un
    état déjà comparé.

    **Aucune I/O dans les méthodes du contrat.** ``read_now()`` fait la
    requête et met à jour l'état ; ``is_safe_to_*`` et ``describe()`` lisent le
    dernier état connu. Ainsi la veille de ``cimier_service`` et le scheduler
    partagent une lecture unique, sans se marcher dessus ni doubler le trafic.

    **Anti-rebond** : il faut ``confirm_reads`` lectures concordantes pour
    changer d'état. Une lecture aberrante isolée ne doit pas mettre fin à une
    nuit d'observation.

    **Asymétrie du fail-safe** — capteur injoignable :
      - ``is_safe_to_open()`` → False : on n'ouvre pas à l'aveugle (refuser est
        réversible et sans coût) ;
      - ``is_safe_to_keep_open()`` → True : on ne ferme **jamais** sur une
        absence de donnée. La fiabilité des Shelly est un sujet connu du
        projet ; une coupure Wi-Fi passagère ne doit pas tuer une session.

    Ne lève jamais vers ses consommateurs.
    """

    def __init__(
        self,
        host: str,
        input_id: int = 0,
        invert: bool = False,
        timeout_s: float = 3.0,
        confirm_reads: int = 2,
        urlopen=None,
        clock=None,
    ) -> None:
        import time as _time

        self._host = host
        self._input_id = int(input_id)
        self._invert = bool(invert)
        self._timeout_s = float(timeout_s)
        self._confirm_reads = max(1, int(confirm_reads))
        self._urlopen = urlopen
        self._clock = clock or _time.time

        self._state = RAIN_UNREACHABLE
        self._pending = None
        self._pending_count = 0
        self._last_read_ts = None
        self._last_error = ""

    @property
    def state(self) -> str:
        """Dernier état confirmé : ``wet`` | ``dry`` | ``unreachable``."""
        return self._state

    def read_now(self) -> str:
        """Interroge le Shelly, applique l'anti-rebond, retourne l'état confirmé."""
        from core.hardware.shelly_rpc import ShellyRpcError, read_input_state

        try:
            raw, _payload = read_input_state(
                self._host, self._input_id, self._timeout_s, self._urlopen
            )
        except ShellyRpcError as exc:
            observed = RAIN_UNREACHABLE
            self._last_error = str(exc)
        else:
            # Convention mesurée le 14/08/2026 : state=true = pluie
            # (invert=false). `invert` reste offert si le câblage change.
            observed = RAIN_WET if raw != self._invert else RAIN_DRY
            self._last_error = ""

        if observed == self._pending:
            self._pending_count += 1
        else:
            self._pending = observed
            self._pending_count = 1
        if self._pending_count >= self._confirm_reads:
            self._state = observed

        self._last_read_ts = self._clock()
        return self._state

    def is_safe_to_open(self) -> bool:
        return self._state == RAIN_DRY

    def is_safe_to_keep_open(self) -> bool:
        return self._state != RAIN_WET

    def describe(self) -> Dict[str, Any]:
        from datetime import datetime

        last_read_at = None
        if self._last_read_ts is not None:
            last_read_at = datetime.fromtimestamp(self._last_read_ts).isoformat(timespec="seconds")
        return {
            "provider": "shelly_rain",
            "state": self._state,
            "host": self._host,
            "input_id": self._input_id,
            "last_read_at": last_read_at,
            "error": self._last_error,
        }


class RainProtection:
    """Politique d'armement autour d'un provider pluie.

    Le provider mesure ; cet objet décide si la mesure a le droit de commander
    quoi que ce soit. Implémente le même contrat, donc transparent pour le
    scheduler.

    - **Désarmé** (défaut) : ``is_safe_to_*`` renvoient True sans condition. Le
      capteur est lu, publié, affiché, journalisé — et strictement inerte.
      C'est le mode qui permet d'observer un orage réel sans risque avant de
      confier la protection au système.
    - **Armé** : relaie le provider. Refus d'ouverture *et* fermeture
      d'urgence — la case gouverne tout le comportement pluie.

    ``latched`` est le **verrou anti-réouverture** : une fermeture pluie le
    pose, et plus aucune ouverture automatique n'est autorisée, même si le
    capteur redevient sec. Décision produit : on ne rouvre pas sur une
    éclaircie, la monture n'a pas à être re-exposée en pleine nuit. Seule une
    commande d'ouverture humaine (ou un redémarrage) le lève.

    ``armed`` est mutable : ``cimier_service`` le rafraîchit depuis
    ``config.json`` à chaque tour de veille, ce qui fait prendre effet la case
    en quelques secondes sans redémarrage.
    """

    def __init__(self, provider, armed: bool = False) -> None:
        self._inner = provider
        self.armed = bool(armed)
        self.latched = False

    @property
    def inner(self):
        return self._inner

    @property
    def state(self):
        return getattr(self._inner, "state", None)

    def read_now(self):
        """Délègue la lecture — l'observation a lieu même désarmée."""
        return self._inner.read_now()

    def latch(self) -> None:
        self.latched = True

    def release(self) -> None:
        self.latched = False

    def is_safe_to_open(self) -> bool:
        if not self.armed:
            return True
        if self.latched:
            return False
        return self._inner.is_safe_to_open()

    def is_safe_to_keep_open(self) -> bool:
        if not self.armed:
            return True
        return self._inner.is_safe_to_keep_open()

    def describe(self) -> Dict[str, Any]:
        payload = dict(self._inner.describe())
        payload["armed"] = self.armed
        payload["latched"] = self.latched
        return payload


def make_weather_provider(cfg: "WeatherProviderConfig") -> WeatherProvider:
    """Factory : instancie le provider d'après la config.

    type ∈ {noop, shelly_rain}. Un type inconnu lève — jamais d'inférence
    silencieuse sur un composant de protection.

    Le provider pluie est toujours renvoyé **enveloppé dans RainProtection**,
    qui porte l'armement : sans armement explicite (case décochée), il ne
    commande rien.
    """
    t = (cfg.type or "noop").lower()
    if t == "noop":
        return NoopWeatherProvider()
    if t == "shelly_rain":
        if not cfg.host:
            raise ValueError("WeatherProviderConfig.host vide pour shelly_rain")
        inner = ShellyRainWeatherProvider(
            host=cfg.host,
            input_id=cfg.input_id,
            invert=cfg.invert,
            timeout_s=cfg.timeout_s,
            confirm_reads=cfg.confirm_reads,
        )
        return RainProtection(inner, armed=cfg.protection_enabled)
    raise ValueError("WeatherProviderConfig.type inconnu: " + repr(cfg.type))
