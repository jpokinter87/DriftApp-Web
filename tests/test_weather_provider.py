"""Tests du module core.hardware.weather_provider (v6.0 Phase 2)."""

from __future__ import annotations

import json

import pytest

from core.config.config_loader import WeatherProviderConfig
from core.hardware.weather_provider import (
    NoopWeatherProvider,
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
