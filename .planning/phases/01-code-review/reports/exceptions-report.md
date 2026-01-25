# Exception Handling Report

**Generated:** 2026-01-25
**Tool:** ruff 0.14.14
**Rules checked:** E722, BLE001, B012, B013, B014, B017, B904

## Summary

| Rule | Description | Count |
|------|-------------|-------|
| E722 | Bare `except:` | 14 |
| BLE001 | Blind `except Exception:` | 52 |
| B904 | Missing `raise ... from` | 1 |
| **Total** | | **67** |

## By Category

### Intentional (Daemon/Hardware Probing Code)

These exceptions are intentional in daemon code, hardware detection, and diagnostic scripts where:
- Graceful failure is required (hardware may not be present)
- Silent fallback is the correct behavior
- Recovery from any error is preferable to crashing

| File | Line | Rule | Pattern | Justification |
|------|------|------|---------|---------------|
| `ems22d_calibrated.py` | 31 | BLE001 | `except Exception:` | spidev import fallback - library may not be installed |
| `ems22d_calibrated.py` | 99 | BLE001 | `except Exception:` | Log cleanup - non-critical, should not crash daemon |
| `ems22d_calibrated.py` | 144 | BLE001 | `except Exception:` | SPI close - resource may already be released |
| `ems22d_calibrated.py` | 156 | BLE001 | `except Exception:` | SPI close - resource may already be released |
| `ems22d_calibrated.py` | 310 | BLE001 | `except Exception:` | JSON write - log error and continue loop |
| `ems22d_calibrated.py` | 338 | BLE001 | `except Exception:` | TCP GET response - send ERR and continue |
| `ems22d_calibrated.py` | 342 | BLE001 | `except Exception:` | TCP accept loop - brief sleep and retry |
| `ems22d_calibrated.py` | 363 | BLE001 | `except Exception:` | SPI open retry - daemon must stay alive |
| `ems22d_calibrated.py` | 379 | BLE001 | `except Exception:` | SPI reopen after error - daemon recovery |
| `ems22d_calibrated.py` | 414 | BLE001 | `except Exception:` | Main loop SPI error - log and continue |
| `ems22d_calibrated.py` | 426 | BLE001 | `except Exception:` | SPI reset - daemon must not crash |
| `ems22d_calibrated.py` | 458 | BLE001 | `except Exception:` | Main entry fatal error - log and exit |
| `core/hardware/hardware_detector.py` | 37 | BLE001 | `except Exception:` | cpuinfo read - Pi detection fallback |
| `core/hardware/hardware_detector.py` | 48 | BLE001 | `except Exception:` | device-tree read - Pi detection fallback |
| `core/hardware/hardware_detector.py` | 87 | BLE001 | `except Exception:` | lgpio probe - library may fail |
| `core/hardware/hardware_detector.py` | 99 | BLE001 | `except Exception:` | gpiod probe - library may fail |
| `core/hardware/hardware_detector.py` | 157 | BLE001 | `except Exception:` | Daemon access - IPC may be unavailable |
| `core/hardware/hardware_detector.py` | 272 | BLE001 | `except Exception:` | Pi model read - file may not exist |
| `core/hardware/hardware_detector.py` | 393 | BLE001 | `except Exception:` | Report save - non-critical IO operation |
| `core/hardware/moteur.py` | 436 | BLE001 | `except Exception:` | GPIO cleanup - must not crash on exit |
| `scripts/diagnostics/calibration_vitesse_max.py` | 84 | E722 | bare `except:` | pgrep check - process may not exist |
| `scripts/diagnostics/calibration_vitesse_max.py` | 93 | E722 | bare `except:` | JSON read fallback - file may not exist |
| `scripts/diagnostics/calibration_vitesse_max.py` | 137 | BLE001 | `except Exception:` | Test execution - log error and continue |
| `scripts/diagnostics/calibration_vitesse_max.py` | 187 | BLE001 | `except Exception:` | Test execution - log error and continue |
| `scripts/diagnostics/calibration_vitesse_max.py` | 374 | BLE001 | `except Exception:` | IPC write - log error and continue |
| `scripts/diagnostics/calibration_vitesse_max.py` | 417 | E722 | bare `except:` | Main cleanup - must not crash |
| `scripts/diagnostics/calibration_vitesse_max.py` | 516 | BLE001 | `except Exception:` | Test batch - log error and continue |
| `scripts/diagnostics/diagnostic_moteur_complet.py` | 125 | E722 | bare `except:` | pgrep check - process may not exist |
| `scripts/diagnostics/diagnostic_moteur_complet.py` | 137 | BLE001 | `except Exception:` | Service stop - log error and continue |
| `scripts/diagnostics/diagnostic_moteur_complet.py` | 162 | BLE001 | `except Exception:` | Service start - log error and continue |
| `scripts/diagnostics/diagnostic_moteur_complet.py` | 195 | BLE001 | `except Exception:` | Daemon check - log error and continue |
| `scripts/diagnostics/diagnostic_moteur_complet.py` | 210 | E722 | bare `except:` | JSON read fallback - file may not exist |
| `scripts/diagnostics/diagnostic_moteur_complet.py` | 266 | BLE001 | `except Exception:` | Test execution - log error and continue |
| `scripts/diagnostics/diagnostic_moteur_complet.py` | 291 | BLE001 | `except Exception:` | Test execution - log error and continue |
| `scripts/diagnostics/diagnostic_moteur_complet.py` | 304 | E722 | bare `except:` | Motor service check - may fail |
| `scripts/diagnostics/diagnostic_moteur_complet.py` | 439 | E722 | bare `except:` | Test cleanup - must not crash |
| `scripts/diagnostics/diagnostic_moteur_complet.py` | 451 | E722 | bare `except:` | Test cleanup - must not crash |
| `scripts/diagnostics/diagnostic_moteur_complet.py` | 457 | E722 | bare `except:` | Test cleanup - must not crash |
| `scripts/diagnostics/diagnostic_moteur_complet.py` | 622 | BLE001 | `except Exception:` | Hardware test - log error and continue |
| `scripts/diagnostics/diagnostic_moteur_complet.py` | 675 | BLE001 | `except Exception:` | Main execution - log error and exit |
| `scripts/diagnostics/motor_service_test_manuel.py` | 62 | E722 | bare `except:` | pgrep check - process may not exist |
| `scripts/diagnostics/motor_service_test_manuel.py` | 73 | E722 | bare `except:` | File stat check - may fail |
| `scripts/diagnostics/motor_service_test_manuel.py` | 83 | E722 | bare `except:` | JSON read fallback - file may not exist |
| `scripts/diagnostics/motor_service_test_manuel.py` | 105 | BLE001 | `except Exception:` | Command write - log error and continue |
| `scripts/diagnostics/motor_service_test_manuel.py` | 225 | E722 | bare `except:` | Test cleanup - must not crash |
| `scripts/diagnostics/test_gpio_electrique.py` | 65 | BLE001 | `except Exception:` | GPIO test - hardware may fail |
| `scripts/diagnostics/test_gpio_electrique.py` | 73 | BLE001 | `except Exception:` | GPIO test - hardware may fail |
| `scripts/diagnostics/test_gpio_electrique.py` | 87 | BLE001 | `except Exception:` | GPIO cleanup - resource may be released |
| `scripts/diagnostics/test_gpio_electrique.py` | 95 | BLE001 | `except Exception:` | GPIO cleanup - resource may be released |
| `scripts/diagnostics/test_moteur_direct.py` | 42 | BLE001 | `except Exception:` | Motor test - hardware may fail |
| `scripts/diagnostics/test_moteur_direct.py` | 46 | BLE001 | `except Exception:` | Motor cleanup - resource may be released |
| `scripts/diagnostics/test_moteur_direct.py` | 55 | BLE001 | `except Exception:` | Main execution - log error and exit |

**Count:** 52 instances (14 E722 + 38 BLE001)

### To Fix (Can Specify Concrete Exception)

These exceptions should be more specific for better error handling and debugging.

| File | Line | Rule | Pattern | Recommendation |
|------|------|------|---------|----------------|
| `core/config/config.py` | 55 | BLE001 | `except Exception:` | Use `except (json.JSONDecodeError, OSError):` - only JSON parse or file IO can fail |
| `core/observatoire/catalogue.py` | 74 | BLE001 | `except Exception:` | Use `except (json.JSONDecodeError, OSError):` - cache load failure |
| `core/observatoire/catalogue.py` | 91 | BLE001 | `except Exception:` | Use `except OSError:` - cache save failure |
| `core/observatoire/catalogue.py` | 181 | BLE001 | `except Exception:` | Use specific SIMBAD/network exceptions or `except (ConnectionError, Timeout, HTTPError):` |
| `core/tracking/abaque_manager.py` | 127 | BLE001 | `except Exception:` | Use `except (FileNotFoundError, pd.errors.EmptyDataError, KeyError):` - Excel load errors |
| `core/tracking/abaque_manager.py` | 251 | BLE001 | `except Exception:` | Use `except (ValueError, IndexError):` - interpolation math errors |
| `core/tracking/abaque_manager.py` | 351 | BLE001 | `except Exception:` | Use `except OSError:` - JSON export failure |
| `core/tracking/tracker.py` | 120 | BLE001 | `except Exception:` | Use `except RuntimeError:` - DaemonEncoderReader specific error |
| `core/tracking/tracker.py` | 432 | BLE001 | `except Exception:` | Use specific session module exceptions or `except (ImportError, OSError):` |
| `core/tracking/tracking_goto_mixin.py` | 99 | BLE001 | `except Exception:` | Use `except RuntimeError:` - DaemonEncoderReader specific error |
| `core/tracking/tracking_goto_mixin.py` | 160 | BLE001 | `except Exception:` | Use `except RuntimeError:` - DaemonEncoderReader specific error |
| `core/tracking/tracking_goto_mixin.py` | 218 | BLE001 | `except Exception:` | Use `except RuntimeError:` - DaemonEncoderReader specific error |
| `core/tracking/tracking_goto_mixin.py` | 232 | BLE001 | `except Exception:` | Should specify motor/feedback errors or use `except (RuntimeError, MotorError):` |
| `core/tracking/tracker.py` | 258 | BLE001 | `except Exception:` | Use `except RuntimeError:` - DaemonEncoderReader specific error |
| `core/hardware/daemon_encoder_reader.py` | 142 | B904 | `raise RuntimeError` | Use `raise RuntimeError(...) from e` to preserve exception chain |

**Count:** 15 instances

### To Evaluate (Need Project Decision)

None - all exceptions have been classified.

## Statistics by Directory

| Directory | E722 | BLE001 | B904 | Total |
|-----------|------|--------|------|-------|
| `core/config/` | 0 | 1 | 0 | 1 |
| `core/hardware/` | 0 | 8 | 1 | 9 |
| `core/observatoire/` | 0 | 3 | 0 | 3 |
| `core/tracking/` | 0 | 8 | 0 | 8 |
| `ems22d_calibrated.py` | 0 | 12 | 0 | 12 |
| `scripts/diagnostics/` | 14 | 20 | 0 | 34 |
| **Total** | **14** | **52** | **1** | **67** |

## Recommendations

### Priority 1: Quick Wins (Low Risk, High Value)

1. **Add exception chaining (B904)**
   - File: `core/hardware/daemon_encoder_reader.py:142`
   - Change: `raise RuntimeError(f"Erreur lecture demon: {e}")`
   - To: `raise RuntimeError(f"Erreur lecture demon: {e}") from e`
   - Impact: Better debugging with full traceback

2. **Config file loading**
   - File: `core/config/config.py:55`
   - Change: `except Exception:` to `except (json.JSONDecodeError, OSError):`
   - Impact: Clearer error handling

### Priority 2: Core Business Logic (Medium Risk, High Value)

3. **Tracking encoder access**
   - Files: `core/tracking/tracker.py`, `core/tracking/tracking_goto_mixin.py`
   - Pattern: All `except Exception:` around `_get_encoder_angle()` calls
   - Recommendation: Create custom `EncoderError` exception type or use `RuntimeError`
   - Impact: Better error categorization for debugging

4. **Catalogue and SIMBAD queries**
   - File: `core/observatoire/catalogue.py`
   - Pattern: Network/IO exceptions
   - Recommendation: Use `requests.exceptions` types for SIMBAD, `OSError` for local cache
   - Impact: Distinguish network failures from local IO failures

5. **Abaque manager**
   - File: `core/tracking/abaque_manager.py`
   - Pattern: Excel loading and interpolation
   - Recommendation: Use pandas-specific exceptions and `ValueError`/`IndexError` for math
   - Impact: Better error messages for misconfigured abaque

### Priority 3: Leave as Intentional (No Change Required)

6. **Daemon code (ems22d_calibrated.py)**
   - All 12 exceptions are intentional
   - Daemon must stay alive regardless of errors
   - Current approach is correct for embedded systems

7. **Diagnostic scripts (scripts/diagnostics/)**
   - All 34 exceptions are intentional
   - Scripts probe hardware that may not exist
   - Silent failures are the correct behavior

8. **Hardware detection (core/hardware/hardware_detector.py)**
   - All 7 exceptions are intentional
   - Probing libraries and hardware requires graceful degradation

9. **GPIO cleanup (core/hardware/moteur.py)**
   - Single exception is intentional
   - Cleanup must not crash even if GPIO is already released

## Implementation Notes

### Custom Exception Approach (Recommended)

Consider defining project-specific exceptions:

```python
# core/exceptions.py
class DriftAppError(Exception):
    """Base exception for DriftApp."""
    pass

class EncoderError(DriftAppError):
    """Encoder communication failure."""
    pass

class MotorError(DriftAppError):
    """Motor control failure."""
    pass

class AbaqueError(DriftAppError):
    """Abaque loading or interpolation failure."""
    pass
```

This would allow:
- More precise exception handling
- Better error messages in logs
- Easier debugging

### Ruff Configuration

Add to `pyproject.toml` to enforce exception rules:

```toml
[tool.ruff.lint]
select = ["E", "F", "B", "BLE"]
ignore = ["E722"]  # Allow bare except in scripts/diagnostics/
per-file-ignores = {"scripts/diagnostics/*.py" = ["E722", "BLE001"], "ems22d_calibrated.py" = ["BLE001"]}
```

## Conclusion

- **67 total exceptions** found across the codebase
- **52 intentional** (daemon, hardware probing, diagnostic scripts)
- **15 to fix** (core business logic with specific exception types)
- **0 critical issues** - no security vulnerabilities or bugs from exception handling

The codebase follows reasonable exception handling practices. The daemon and hardware code correctly uses broad exceptions for resilience. The core business logic can be improved with more specific exceptions for better debugging.
