"""Tests du module core.hardware.weather_provider (v6.0 Phase 2)."""

from __future__ import annotations

import json

import pytest

from core.config.config_loader import WeatherProviderConfig
from core.hardware.weather_provider import (
    NoopWeatherProvider,
    RAIN_DRY,
    RAIN_UNREACHABLE,
    RAIN_WET,
    ShellyRainWeatherProvider,
    WeatherProvider,
    WeatherProviderError,
    make_weather_provider,
)


# ----------------------------------------------------------------------
# NoopWeatherProvider — contrat de base
# ----------------------------------------------------------------------


class TestNoopWeatherProvider:
    def test_is_safe_to_open_returns_true(self):
        assert NoopWeatherProvider().is_safe_to_open() is True

    def test_is_safe_to_keep_open_returns_true(self):
        assert NoopWeatherProvider().is_safe_to_keep_open() is True

    def test_describe_returns_dict_with_provider_key(self):
        d = NoopWeatherProvider().describe()
        assert isinstance(d, dict)
        assert d.get("provider") == "noop"

    def test_describe_is_serializable_to_json(self):
        # Le service log describe() inline dans la ligne `cimier_event=cycle_start`.
        payload = json.dumps(NoopWeatherProvider().describe(), sort_keys=True)
        assert payload == '{"provider": "noop"}'

    def test_protocol_conformance(self):
        # Protocol runtime_checkable : NoopWeatherProvider doit etre reconnu.
        assert isinstance(NoopWeatherProvider(), WeatherProvider)


# ----------------------------------------------------------------------
# Factory make_weather_provider
# ----------------------------------------------------------------------


class TestMakeWeatherProvider:
    def test_returns_noop_for_explicit_noop_type(self):
        p = make_weather_provider(WeatherProviderConfig(type="noop"))
        assert isinstance(p, NoopWeatherProvider)

    def test_returns_noop_for_default_config(self):
        # WeatherProviderConfig() -> type='noop' par defaut (retro-compat).
        p = make_weather_provider(WeatherProviderConfig())
        assert isinstance(p, NoopWeatherProvider)

    def test_raises_value_error_for_unknown_type(self):
        with pytest.raises(ValueError, match="bogus"):
            make_weather_provider(WeatherProviderConfig(type="bogus"))

    def test_type_case_insensitive(self):
        # Coherent avec make_power_switch (lowercase normalization).
        p = make_weather_provider(WeatherProviderConfig(type="NOOP"))
        assert isinstance(p, NoopWeatherProvider)


# ----------------------------------------------------------------------
# WeatherProviderError — sanity check (reserve aux providers reels)
# ----------------------------------------------------------------------


def test_weather_provider_error_is_exception():
    assert issubclass(WeatherProviderError, Exception)


# ----------------------------------------------------------------------
# ShellyRainWeatherProvider
# ----------------------------------------------------------------------


class FakeRainShelly:
    """urlopen programmable : ``script`` = liste de bool ou d'exceptions."""

    def __init__(self, script):
        self._script = list(script)
        self.calls = []

    def __call__(self, url, timeout=None):
        self.calls.append(url)
        idx = min(len(self.calls) - 1, len(self._script) - 1)
        item = self._script[idx]
        if isinstance(item, Exception):
            raise item
        return _FakeResp(('{"id":0,"state":%s}' % ("true" if item else "false")).encode())


class _FakeResp:
    def __init__(self, body, status=200):
        self._body = body
        self.status = status

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def make_provider(script, **kwargs):
    return ShellyRainWeatherProvider(host="1.2.3.4", urlopen=FakeRainShelly(script), **kwargs)


class TestShellyRainProviderReading:
    def test_initial_state_is_unreachable_before_any_read(self):
        p = make_provider([False])
        assert p.state == RAIN_UNREACHABLE

    def test_two_dry_reads_confirm_dry(self):
        p = make_provider([False, False])
        p.read_now()
        assert p.read_now() == RAIN_DRY

    def test_two_wet_reads_confirm_wet(self):
        p = make_provider([True, True])
        p.read_now()
        assert p.read_now() == RAIN_WET

    def test_single_wet_read_confirms_wet_immediately(self):
        # Retour terrain du 16/08/2026 : sous une averse, le système est resté
        # « sec » 5 minutes alors que le Shelly rapportait la pluie. L'ancien
        # anti-rebond symétrique exigeait N lectures *consécutives* — à
        # l'amorce d'une averse la sortie du comparateur bavarde autour du
        # seuil du trimpot et le compteur ne cumulait jamais.
        # Décision : entrer en « pluie » est immédiat, en sortir demande
        # confirmation. Ce test verrouille l'asymétrie.
        p = make_provider([False, False, True])
        p.read_now()
        p.read_now()
        assert p.state == RAIN_DRY
        assert p.read_now() == RAIN_WET

    def test_flapping_sensor_detects_and_holds_rain(self):
        # Le scénario terrain exact : lectures alternées à l'amorce de
        # l'averse. La pluie doit être détectée dès le premier « mouillé »,
        # et un « sec » isolé ne doit pas la lever.
        p = make_provider([False, False, True, False, True, False, True])
        p.read_now()
        p.read_now()
        assert p.state == RAIN_DRY
        for _ in range(5):
            assert p.read_now() == RAIN_WET

    def test_high_confirm_reads_does_not_delay_detection(self):
        # L'invariant qui rend le réglage de sortie gratuit : durcir
        # confirm_reads renforce la persistance de l'état « pluie » sans
        # jamais retarder sa détection. Si un jour l'asymétrie disparaît,
        # ce test tombe avant que le terrain ne le paie.
        p = make_provider([False] * 4 + [True], confirm_reads=4)
        for _ in range(4):
            p.read_now()
        assert p.state == RAIN_DRY
        assert p.read_now() == RAIN_WET

    def test_brief_dry_spell_under_heavy_rain_holds_wet(self):
        # Terrain 16/08/2026 : sous une averse drue, le capteur a produit
        # assez de lectures sèches pour lever l'état pluie (18:51 → 18:58).
        # Avec 4 lectures exigées, une accalmie de lecture ne suffit plus.
        p = make_provider([True, False, False, False, True], confirm_reads=4)
        assert p.read_now() == RAIN_WET
        for _ in range(3):
            assert p.read_now() == RAIN_WET

    def test_leaving_wet_still_requires_confirmation(self):
        p = make_provider([True, False, False])
        assert p.read_now() == RAIN_WET
        assert p.read_now() == RAIN_WET
        assert p.read_now() == RAIN_DRY

    def test_single_unreachable_read_does_not_leave_wet(self):
        import urllib.error

        p = make_provider([True, urllib.error.URLError("down"), True])
        assert p.read_now() == RAIN_WET
        assert p.read_now() == RAIN_WET

    def test_divergent_read_is_logged(self, caplog):
        # Angle mort du 16/08 : pendant les 5 minutes de bavardage, aucune
        # ligne n'était écrite (le journal n'enregistre que les transitions
        # *confirmées*). Une lecture brute qui diverge de l'état confirmé doit
        # laisser une trace — c'est ce qui discrimine « capteur qui bavarde »
        # de « seuil du trimpot trop dur ».
        p = make_provider([True, False, False])
        p.read_now()
        caplog.clear()  # la 1re lecture diverge aussi (état initial unreachable)
        with caplog.at_level("INFO", logger="core.hardware.weather_provider"):
            p.read_now()
        assert "rain_read" in caplog.text
        assert "raw=dry" in caplog.text
        assert "confirmed=wet" in caplog.text

    def test_steady_state_reads_are_silent(self, caplog):
        p = make_provider([True, True, True])
        p.read_now()
        caplog.clear()  # idem : seul le régime établi qui suit nous intéresse
        with caplog.at_level("INFO", logger="core.hardware.weather_provider"):
            p.read_now()
            p.read_now()
        assert "rain_read" not in caplog.text

    def test_invert_flips_interpretation(self):
        p = make_provider([True, True], invert=True)
        p.read_now()
        assert p.read_now() == RAIN_DRY

    def test_confirm_reads_one_flips_immediately(self):
        p = make_provider([True], confirm_reads=1)
        assert p.read_now() == RAIN_WET


class TestShellyRainProviderDecisions:
    def test_dry_is_safe_for_both(self):
        p = make_provider([False, False])
        p.read_now()
        p.read_now()
        assert p.is_safe_to_open() is True
        assert p.is_safe_to_keep_open() is True

    def test_wet_blocks_both(self):
        p = make_provider([True, True])
        p.read_now()
        p.read_now()
        assert p.is_safe_to_open() is False
        assert p.is_safe_to_keep_open() is False

    def test_unreachable_after_confirmed_wet_stops_blocking_keep_open(self):
        # Comportement VOULU, verrouillé ici : une pluie confirmée puis un
        # capteur injoignable ne ferme pas la session (on ne ferme jamais sur
        # une absence de donnée). Ce test existe pour qu'une évolution de
        # l'anti-rebond ne change pas ce compromis en silence.
        import urllib.error

        p = make_provider(
            [True, True, urllib.error.URLError("down"), urllib.error.URLError("down")]
        )
        p.read_now()
        p.read_now()
        assert p.state == RAIN_WET
        p.read_now()
        p.read_now()
        assert p.state == RAIN_UNREACHABLE
        assert p.is_safe_to_keep_open() is True
        assert p.is_safe_to_open() is False

    def test_unreachable_blocks_opening_but_never_closes(self):
        # Décision terrain : on n'ouvre pas à l'aveugle, mais on ne ferme
        # jamais une session sur une absence de donnée.
        import urllib.error

        p = make_provider([urllib.error.URLError("down"), urllib.error.URLError("down")])
        p.read_now()
        p.read_now()
        assert p.state == RAIN_UNREACHABLE
        assert p.is_safe_to_open() is False
        assert p.is_safe_to_keep_open() is True

    def test_never_raises_on_network_error(self):
        import urllib.error

        p = make_provider([urllib.error.URLError("down")])
        assert p.read_now() == RAIN_UNREACHABLE


class TestShellyRainProviderDescribe:
    def test_describe_is_json_serializable_and_complete(self):
        p = make_provider([True, True])
        p.read_now()
        p.read_now()
        d = p.describe()
        assert d["provider"] == "shelly_rain"
        assert d["state"] == RAIN_WET
        assert d["host"] == "1.2.3.4"
        assert d["input_id"] == 0
        assert d["last_read_at"] is not None
        # Le service logge describe() inline dans cimier_event=cycle_start.
        json.dumps(d, sort_keys=True)

    def test_describe_carries_error_when_unreachable(self):
        import urllib.error

        p = make_provider([urllib.error.URLError("down")])
        p.read_now()
        assert p.describe()["error"]

    def test_protocol_conformance(self):
        assert isinstance(make_provider([False]), WeatherProvider)


class TestMakeWeatherProviderRain:
    def test_shelly_rain_type_builds_rain_provider_wrapped(self):
        from core.config.config_loader import WeatherProviderConfig
        from core.hardware.weather_provider import RainProtection

        p = make_weather_provider(WeatherProviderConfig(type="shelly_rain", host="1.2.3.4"))
        assert isinstance(p, RainProtection)

    def test_shelly_rain_without_host_raises(self):
        from core.config.config_loader import WeatherProviderConfig

        with pytest.raises(ValueError, match="host"):
            make_weather_provider(WeatherProviderConfig(type="shelly_rain", host=""))


# ----------------------------------------------------------------------
# RainProtection
# ----------------------------------------------------------------------


class StubRainProvider:
    """Provider minimal pour tester la politique sans réseau."""

    def __init__(self, state=RAIN_DRY):
        self.state = state
        self.read_calls = 0

    def read_now(self):
        self.read_calls += 1
        return self.state

    def is_safe_to_open(self):
        return self.state == RAIN_DRY

    def is_safe_to_keep_open(self):
        return self.state != RAIN_WET

    def describe(self):
        return {"provider": "stub", "state": self.state}


class TestRainProtectionDisarmed:
    def test_disarmed_allows_everything_even_under_rain(self):
        from core.hardware.weather_provider import RainProtection

        p = RainProtection(StubRainProvider(RAIN_WET), armed=False)
        assert p.is_safe_to_open() is True
        assert p.is_safe_to_keep_open() is True

    def test_disarmed_still_exposes_real_state(self):
        # C'est tout l'intérêt du mode observation : on voit sans agir.
        from core.hardware.weather_provider import RainProtection

        p = RainProtection(StubRainProvider(RAIN_WET), armed=False)
        assert p.state == RAIN_WET
        assert p.describe()["state"] == RAIN_WET
        assert p.describe()["armed"] is False

    def test_disarmed_still_reads(self):
        from core.hardware.weather_provider import RainProtection

        inner = StubRainProvider(RAIN_WET)
        RainProtection(inner, armed=False).read_now()
        assert inner.read_calls == 1


class TestRainProtectionArmed:
    def test_armed_relays_provider_under_rain(self):
        from core.hardware.weather_provider import RainProtection

        p = RainProtection(StubRainProvider(RAIN_WET), armed=True)
        assert p.is_safe_to_open() is False
        assert p.is_safe_to_keep_open() is False

    def test_armed_allows_when_dry(self):
        from core.hardware.weather_provider import RainProtection

        p = RainProtection(StubRainProvider(RAIN_DRY), armed=True)
        assert p.is_safe_to_open() is True
        assert p.is_safe_to_keep_open() is True

    def test_armed_can_be_toggled_at_runtime(self):
        # Hot-reload de la case à cocher, sans redémarrer le service.
        from core.hardware.weather_provider import RainProtection

        p = RainProtection(StubRainProvider(RAIN_WET), armed=False)
        assert p.is_safe_to_keep_open() is True
        p.armed = True
        assert p.is_safe_to_keep_open() is False


class TestRainProtectionLatch:
    def test_latch_blocks_reopening_even_once_dry(self):
        from core.hardware.weather_provider import RainProtection

        inner = StubRainProvider(RAIN_WET)
        p = RainProtection(inner, armed=True)
        p.latch()
        inner.state = RAIN_DRY
        assert p.is_safe_to_open() is False

    def test_release_lifts_the_latch(self):
        from core.hardware.weather_provider import RainProtection

        inner = StubRainProvider(RAIN_DRY)
        p = RainProtection(inner, armed=True)
        p.latch()
        p.release()
        assert p.is_safe_to_open() is True

    def test_latch_does_not_block_keeping_open_when_dry(self):
        # Le verrou porte sur l'ouverture, pas sur le maintien.
        from core.hardware.weather_provider import RainProtection

        p = RainProtection(StubRainProvider(RAIN_DRY), armed=True)
        p.latch()
        assert p.is_safe_to_keep_open() is True

    def test_latch_is_reported_in_describe(self):
        from core.hardware.weather_provider import RainProtection

        p = RainProtection(StubRainProvider(RAIN_DRY), armed=True)
        p.latch()
        assert p.describe()["latched"] is True

    def test_disarmed_ignores_latch(self):
        from core.hardware.weather_provider import RainProtection

        p = RainProtection(StubRainProvider(RAIN_DRY), armed=False)
        p.latch()
        assert p.is_safe_to_open() is True
