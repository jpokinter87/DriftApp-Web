"""
Abstraction logique de la meteo cimier (v6.0 Phase 2).

Strategy minimaliste qui repond a deux questions binaires que la suite v6.0
voudra poser avant d'agir :

  - "puis-je ouvrir le cimier maintenant ?"        -> is_safe_to_open()
  - "puis-je le laisser ouvert ?"                  -> is_safe_to_keep_open()
  - "que dis-je sur la meteo ? (logs, debug)"     -> describe()

Phase 2 ne livre que NoopWeatherProvider (toujours OK). Aucun capteur reel
n'est branche : c'est une interface posee pour Phase 3 (scheduler ephemerides
qui consultera is_safe_to_open avant l'ouverture auto) et pour un milestone
capteurs ulterieur (v6.4+, capteur sur Pico W cimier d'apres l'interview de
cadrage 2026-04-29 theme J). Tant qu'aucun capteur reel n'existe, on ne fige
pas de dataclass WeatherSnapshot ni de seuils dans la config — describe()
expose un dict opaque pour les logs.

Implementations disponibles :
  - NoopWeatherProvider : repond toujours True, describe() = {"provider": "noop"}.

A venir (out of scope Phase 2) :
  - PicoWWeatherProvider : interroge un capteur sur le Pico W cimier (humidite,
    pluie, vent), evalue les seuils contre une nouvelle section de config.

Le module est volontairement court et sans dependance reseau. Il copie le
pattern de core/hardware/power_switch.py (Strategy + Noop + factory).
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


def make_weather_provider(cfg: "WeatherProviderConfig") -> WeatherProvider:
    """Factory : instancie le provider d'apres la config.

    type ∈ {noop}. Les types reels (ex. "pico_w_sensor") arriveront avec un
    milestone capteurs ulterieur — ils doivent rester opt-in et explicitement
    listes ici, pas inferes silencieusement.
    """
    t = (cfg.type or "noop").lower()
    if t == "noop":
        return NoopWeatherProvider()
    raise ValueError("WeatherProviderConfig.type inconnu: " + repr(cfg.type))


