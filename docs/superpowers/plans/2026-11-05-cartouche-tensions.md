# Plan — cartouche « Tensions »

Spec : `docs/superpowers/specs/2026-11-05-cartouche-tensions.md`.

0. Butées perdues en cycle : test qui reproduit (moteur jusqu'à 90 s), puis
   `switch_lost_timeout_s` dans `_poll_target_switch`.
1. `shelly_rpc.read_voltage` + tests (`tests/test_shelly_rpc.py`) → pytest vert.
2. `VoltagesConfig` dans `config_loader` + `config.template.json` / `config.json`
   + aides `HELP_REGISTRY` → `tests/test_config_loader.py`, `test_config_resilience.py`.
3. `core/hardware/voltage_monitor.py` + `tests/test_voltage_monitor.py`.
4. Branchement `cimier_service` (tick, `_publish_status`, dev overrides)
   → `tests/test_cimier_service.py`.
5. Simulateur : `Voltmeter.GetStatus`, `/dev/voltage` → `tests/test_cimier_simulator.py`.
5b. Pastille « prêt » : `PowerSwitch.probe()`, `_health_check()`, simulateur
   `/relay/<n>` sans `turn` en lecture seule.
6. Dashboard : cartouches CAPTEURS + TENSIONS, fonctions JS, CSS (3 thèmes) → essai en dev.
7. Doc (CLAUDE.md « Debugging »), CHANGELOG, bump mineur, ruff, push.
