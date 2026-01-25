# Phase 2 Refactoring Changelog

## [Unreleased]

### Added
- `core/exceptions.py`: Custom exception hierarchy (DriftAppError, MotorError, EncoderError, AbaqueError, IPCError, ConfigError)
- `tests/test_exceptions.py`: Tests for exception classes (39 tests for hierarchy, attributes, chaining)

### Changed (SOLID - OCP)
- `services/motor_service.py`: Refactored process_command() to use command registry pattern
  - Extracted handler methods: _handle_goto, _handle_jog, _handle_stop, _handle_continuous, _handle_tracking_start, _handle_tracking_stop, _handle_status
  - Added _command_registry dict for O(1) command dispatch
  - Adding new commands now only requires adding to registry (OCP compliant)
- `tests/test_motor_service.py`: Added 22 tests for registry pattern
  - TestCommandRegistry: registry completeness, OCP extension test
  - TestProcessCommand: command dispatch via registry
  - TestHandlerMethods: individual handler behavior

### Changed
- `core/config/config.py`: Replaced bare exception with (JSONDecodeError, OSError)
- `core/observatoire/catalogue.py`: Replaced 3 bare exceptions with specific types
  - Line 74: (JSONDecodeError, OSError) for cache load
  - Line 91: OSError for cache save
  - Line 181: (ConnectionError, TimeoutError, OSError) for SIMBAD queries
- `core/tracking/abaque_manager.py`: Replaced 3 bare exceptions with specific types
  - Line 127: (FileNotFoundError, ValueError, KeyError) for abaque load
  - Line 251: (ValueError, IndexError) for interpolation
  - Line 351: OSError for JSON export
- `core/tracking/tracker.py`: Replaced 3 bare exceptions with (EncoderError, RuntimeError)
  - Added import: `from core.exceptions import EncoderError`
- `core/tracking/tracking_goto_mixin.py`: Replaced 4 bare exceptions with (EncoderError, MotorError, RuntimeError)
  - Added import: `from core.exceptions import EncoderError, MotorError`
- `core/hardware/daemon_encoder_reader.py`: Fixed B904 with exception chaining
  - Changed RuntimeError to EncoderError with `from e` for proper chaining
- `tests/test_abaque_manager.py`: Updated test to use ValueError instead of generic Exception

### Fixed
- B904 violation: Exception chaining now preserved in daemon_encoder_reader.py
