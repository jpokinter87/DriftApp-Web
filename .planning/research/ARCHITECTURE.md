# Architecture Patterns: Switchable GPIO Backends

**Domain:** Hardware abstraction for GPIO control (lgpio/pigpio)
**Researched:** 2026-01-25
**Confidence:** HIGH (patterns verified with official Python typing docs and gpiozero reference implementation)

## Recommended Architecture

Use **Protocol-based abstraction** with a **Factory function** for backend selection. This follows the proven pattern from gpiozero while keeping the implementation simpler and focused on DriftApp's specific needs.

```
                     ┌─────────────────────┐
                     │    config.json      │
                     │ {"gpio_backend":    │
                     │   "lgpio"}          │
                     └─────────┬───────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────┐
│                  GPIOBackend Protocol                    │
│  (core/hardware/gpio_backend.py)                        │
│                                                          │
│  setup(dir_pin, step_pin) → None                        │
│  write(pin, value) → None                               │
│  pulse(pin, duration_us) → None                         │
│  cleanup() → None                                       │
└──────────────────────────────────────────────────────────┘
                               │
           ┌───────────────────┼───────────────────┐
           │                   │                   │
           ▼                   ▼                   ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│  LgpioBackend    │ │  PigpioBackend   │ │  MockBackend     │
│  (default Pi 5)  │ │  (remote/daemon) │ │  (testing)       │
└──────────────────┘ └──────────────────┘ └──────────────────┘
```

### Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| `GPIOBackend` (Protocol) | Define interface contract | Type checker only |
| `LgpioBackend` | lgpio-based GPIO control | Linux gpiochip device |
| `PigpioBackend` | pigpio daemon-based control | pigpiod socket |
| `MockBackend` | Testing without hardware | In-memory state |
| `get_gpio_backend()` | Factory function | config.json, backend classes |
| `MoteurCoupole` | Motor control logic | GPIOBackend instance |

### Data Flow

1. `MoteurCoupole.__init__()` calls `get_gpio_backend()` with config
2. Factory reads `gpio_backend` from config.json (default: "lgpio")
3. Factory instantiates appropriate backend class
4. Backend returned to `MoteurCoupole` as dependency
5. Motor methods call backend methods (write, pulse, cleanup)

## Patterns to Follow

### Pattern 1: Protocol for Type-Safe Interface

**What:** Define a `typing.Protocol` class that specifies the contract all GPIO backends must implement.

**Why Protocol over ABC:**
- No runtime overhead (structural subtyping)
- Duck typing friendly (no inheritance required)
- Better for external implementations
- Cleaner for dependency injection
- Recommended for "ports and adapters" architecture

**Source:** [Modern Python Interfaces: ABC, Protocol, or Both?](https://tconsta.medium.com/python-interfaces-abc-protocol-or-both-3c5871ea6642), [PEP 544](https://peps.python.org/pep-0544/)

**Implementation:**

```python
# core/hardware/gpio_backend.py
from typing import Protocol, runtime_checkable

@runtime_checkable
class GPIOBackend(Protocol):
    """Protocol defining the GPIO backend interface.

    All GPIO backends must implement these methods to be used
    with MoteurCoupole. Uses structural subtyping - no inheritance
    required.
    """

    def setup(self, dir_pin: int, step_pin: int) -> None:
        """Initialize GPIO pins for motor control.

        Args:
            dir_pin: BCM pin number for direction control
            step_pin: BCM pin number for step signal
        """
        ...

    def write(self, pin: int, value: int) -> None:
        """Write a digital value to a GPIO pin.

        Args:
            pin: BCM pin number
            value: 0 (LOW) or 1 (HIGH)
        """
        ...

    def pulse(self, pin: int, duration_us: float) -> None:
        """Generate a pulse on a GPIO pin.

        Args:
            pin: BCM pin number
            duration_us: Pulse duration in microseconds
        """
        ...

    def cleanup(self) -> None:
        """Release GPIO resources."""
        ...
```

### Pattern 2: Factory Function with Config-Driven Selection

**What:** A factory function that reads configuration and returns the appropriate backend instance.

**Why Factory over direct instantiation:**
- Encapsulates backend selection logic
- Single point for configuration parsing
- Easy to add new backends
- Testable (can pass mock config)

**Source:** [Factory Design Patterns in Python](https://dagster.io/blog/python-factory-patterns)

**Implementation:**

```python
# core/hardware/gpio_backend.py (continued)
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Backend registry for extensibility
_BACKENDS: dict[str, type] = {}

def register_backend(name: str):
    """Decorator to register a backend class."""
    def decorator(cls):
        _BACKENDS[name] = cls
        return cls
    return decorator


def get_gpio_backend(config: Optional[dict] = None) -> GPIOBackend:
    """Factory function to get the configured GPIO backend.

    Args:
        config: Configuration dict. If None, loads from data/config.json.
                Looks for 'gpio_backend' key (default: 'lgpio').

    Returns:
        Configured GPIOBackend instance.

    Raises:
        ValueError: If specified backend is not available.
        RuntimeError: If backend initialization fails.

    Example:
        # Use default from config.json
        backend = get_gpio_backend()

        # Override for testing
        backend = get_gpio_backend({'gpio_backend': 'mock'})
    """
    if config is None:
        from core.config.config import load_config
        config = load_config()

    backend_name = config.get('gpio_backend', 'lgpio')

    # Auto-detect simulation mode
    if config.get('simulation', False):
        backend_name = 'mock'
        logger.info("Simulation mode enabled, using mock GPIO backend")

    if backend_name not in _BACKENDS:
        available = ', '.join(_BACKENDS.keys())
        raise ValueError(
            f"Unknown GPIO backend '{backend_name}'. "
            f"Available: {available}"
        )

    backend_class = _BACKENDS[backend_name]

    try:
        backend = backend_class(config)
        logger.info(f"GPIO backend initialized: {backend_name}")
        return backend
    except Exception as e:
        raise RuntimeError(
            f"Failed to initialize GPIO backend '{backend_name}': {e}"
        ) from e
```

### Pattern 3: lgpio Backend Implementation

**What:** The default backend using lgpio for Raspberry Pi 5 compatibility.

**Source:** Current `moteur.py` implementation, [rpi-lgpio documentation](https://rpi-lgpio.readthedocs.io/en/latest/differences.html)

**Implementation:**

```python
# core/hardware/backends/lgpio_backend.py
import logging
import time
from typing import Optional

try:
    import lgpio
    LGPIO_AVAILABLE = True
except ImportError:
    LGPIO_AVAILABLE = False
    lgpio = None

logger = logging.getLogger(__name__)


@register_backend('lgpio')
class LgpioBackend:
    """GPIO backend using lgpio (Raspberry Pi 5 native).

    Uses Linux gpiochip interface via lgpio library.
    Default backend for new installations.
    """

    def __init__(self, config: Optional[dict] = None):
        if not LGPIO_AVAILABLE:
            raise RuntimeError(
                "lgpio not available. Install: sudo apt install python3-lgpio"
            )

        self._handle: Optional[int] = None
        self._dir_pin: Optional[int] = None
        self._step_pin: Optional[int] = None

    def setup(self, dir_pin: int, step_pin: int) -> None:
        """Initialize GPIO pins using lgpio."""
        try:
            # Try Pi 5 chip first, fallback to Pi 4
            try:
                self._handle = lgpio.gpiochip_open(4)  # Pi 5
            except lgpio.error:
                self._handle = lgpio.gpiochip_open(0)  # Pi 4

            # Claim pins as outputs
            lgpio.gpio_claim_output(self._handle, dir_pin)
            lgpio.gpio_claim_output(self._handle, step_pin)

            # Initial state: LOW
            lgpio.gpio_write(self._handle, dir_pin, 0)
            lgpio.gpio_write(self._handle, step_pin, 0)

            self._dir_pin = dir_pin
            self._step_pin = step_pin

            logger.debug(f"lgpio initialized: DIR={dir_pin}, STEP={step_pin}")

        except lgpio.error as e:
            raise RuntimeError(f"lgpio initialization failed: {e}") from e

    def write(self, pin: int, value: int) -> None:
        """Write digital value via lgpio."""
        if self._handle is None:
            raise RuntimeError("GPIO not initialized. Call setup() first.")
        lgpio.gpio_write(self._handle, pin, value)

    def pulse(self, pin: int, duration_us: float) -> None:
        """Generate pulse using time.sleep().

        Note: lgpio doesn't have built-in pulse, so we use
        write HIGH, sleep, write LOW pattern.
        """
        if self._handle is None:
            raise RuntimeError("GPIO not initialized. Call setup() first.")

        duration_s = duration_us / 1_000_000
        half_duration = duration_s / 2

        lgpio.gpio_write(self._handle, pin, 1)
        time.sleep(half_duration)
        lgpio.gpio_write(self._handle, pin, 0)
        time.sleep(half_duration)

    def cleanup(self) -> None:
        """Release lgpio resources."""
        if self._handle is None:
            return

        try:
            if self._dir_pin is not None:
                try:
                    lgpio.gpio_free(self._handle, self._dir_pin)
                except lgpio.error:
                    pass

            if self._step_pin is not None:
                try:
                    lgpio.gpio_free(self._handle, self._step_pin)
                except lgpio.error:
                    pass

            try:
                lgpio.gpiochip_close(self._handle)
            except lgpio.error:
                pass

            logger.debug("lgpio resources released")

        finally:
            self._handle = None
            self._dir_pin = None
            self._step_pin = None
```

### Pattern 4: pigpio Backend Implementation

**What:** Alternative backend using pigpio daemon for remote GPIO or advanced features.

**Source:** [pigpio Python documentation](https://abyz.me.uk/rpi/pigpio/python.html), [pigpio daemon](https://abyz.me.uk/rpi/pigpio/pigpiod.html)

**Key Difference:** pigpio requires a running daemon (`pigpiod`). The backend must handle:
1. Connection to daemon
2. Daemon availability check
3. Graceful handling of daemon restart

**Implementation:**

```python
# core/hardware/backends/pigpio_backend.py
import logging
import time
from typing import Optional

try:
    import pigpio
    PIGPIO_AVAILABLE = True
except ImportError:
    PIGPIO_AVAILABLE = False
    pigpio = None

logger = logging.getLogger(__name__)


@register_backend('pigpio')
class PigpioBackend:
    """GPIO backend using pigpio daemon.

    Requires pigpiod daemon to be running:
        sudo pigpiod

    Advantages over lgpio:
    - Hardware-timed pulses (gpio_trigger)
    - Remote GPIO access
    - Better PWM support

    Limitations:
    - Not compatible with Pi 5 (as of 2025)
    - Requires daemon process
    """

    def __init__(self, config: Optional[dict] = None):
        if not PIGPIO_AVAILABLE:
            raise RuntimeError(
                "pigpio not available. Install: pip install pigpio"
            )

        self._pi: Optional[pigpio.pi] = None
        self._dir_pin: Optional[int] = None
        self._step_pin: Optional[int] = None

        # Extract pigpio-specific config
        pigpio_config = (config or {}).get('pigpio', {})
        self._host = pigpio_config.get('host', 'localhost')
        self._port = pigpio_config.get('port', 8888)

    def _ensure_connected(self) -> pigpio.pi:
        """Ensure connection to pigpio daemon, reconnecting if needed."""
        if self._pi is None or not self._pi.connected:
            self._pi = pigpio.pi(host=self._host, port=self._port)

            if not self._pi.connected:
                raise RuntimeError(
                    f"Cannot connect to pigpio daemon at {self._host}:{self._port}. "
                    "Start with: sudo pigpiod"
                )

        return self._pi

    def setup(self, dir_pin: int, step_pin: int) -> None:
        """Initialize GPIO pins using pigpio."""
        pi = self._ensure_connected()

        # Set pin modes to OUTPUT
        pi.set_mode(dir_pin, pigpio.OUTPUT)
        pi.set_mode(step_pin, pigpio.OUTPUT)

        # Initial state: LOW
        pi.write(dir_pin, 0)
        pi.write(step_pin, 0)

        self._dir_pin = dir_pin
        self._step_pin = step_pin

        logger.debug(
            f"pigpio initialized: DIR={dir_pin}, STEP={step_pin} "
            f"(daemon: {self._host}:{self._port})"
        )

    def write(self, pin: int, value: int) -> None:
        """Write digital value via pigpio."""
        pi = self._ensure_connected()
        pi.write(pin, value)

    def pulse(self, pin: int, duration_us: float) -> None:
        """Generate hardware-timed pulse via pigpio.

        Uses gpio_trigger for precise timing.
        """
        pi = self._ensure_connected()

        # pigpio.gpio_trigger(gpio, pulse_len, level)
        # pulse_len is in microseconds, level is the active level
        pi.gpio_trigger(pin, int(duration_us), 1)

    def cleanup(self) -> None:
        """Release pigpio resources."""
        if self._pi is not None:
            try:
                self._pi.stop()
                logger.debug("pigpio connection closed")
            except Exception:
                pass
            finally:
                self._pi = None
                self._dir_pin = None
                self._step_pin = None
```

### Pattern 5: Mock Backend for Testing

**What:** A test double that records GPIO operations without hardware access.

**Source:** [gpiozero MockFactory](https://gpiozero.readthedocs.io/en/stable/development.html), [Mock.GPIO](https://github.com/codenio/Mock.GPIO)

**Implementation:**

```python
# core/hardware/backends/mock_backend.py
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class PinState:
    """Tracks state of a single GPIO pin."""
    mode: str = 'unset'  # 'input', 'output', 'unset'
    value: int = 0
    pulse_count: int = 0
    last_pulse_duration_us: float = 0.0


@register_backend('mock')
class MockBackend:
    """Mock GPIO backend for testing.

    Records all GPIO operations for verification in tests.
    Optionally simulates timing delays.

    Example:
        backend = MockBackend({'simulate_delays': False})
        backend.setup(17, 18)
        backend.pulse(18, 1500)

        assert backend.pins[18].pulse_count == 1
        assert backend.pins[18].last_pulse_duration_us == 1500
    """

    def __init__(self, config: Optional[dict] = None):
        mock_config = (config or {}).get('mock_gpio', {})
        self._simulate_delays = mock_config.get('simulate_delays', False)

        self.pins: dict[int, PinState] = {}
        self._setup_called = False
        self._cleanup_called = False
        self._operations: list[tuple[str, dict]] = []  # Operation log

    def setup(self, dir_pin: int, step_pin: int) -> None:
        """Record pin setup."""
        self.pins[dir_pin] = PinState(mode='output', value=0)
        self.pins[step_pin] = PinState(mode='output', value=0)
        self._setup_called = True
        self._operations.append(('setup', {'dir_pin': dir_pin, 'step_pin': step_pin}))

        logger.debug(f"Mock GPIO setup: DIR={dir_pin}, STEP={step_pin}")

    def write(self, pin: int, value: int) -> None:
        """Record pin write."""
        if pin not in self.pins:
            self.pins[pin] = PinState(mode='output')

        self.pins[pin].value = value
        self._operations.append(('write', {'pin': pin, 'value': value}))

    def pulse(self, pin: int, duration_us: float) -> None:
        """Record pulse operation."""
        if pin not in self.pins:
            self.pins[pin] = PinState(mode='output')

        state = self.pins[pin]
        state.pulse_count += 1
        state.last_pulse_duration_us = duration_us

        self._operations.append(('pulse', {'pin': pin, 'duration_us': duration_us}))

        if self._simulate_delays:
            time.sleep(duration_us / 1_000_000)

    def cleanup(self) -> None:
        """Record cleanup."""
        self._cleanup_called = True
        self._operations.append(('cleanup', {}))
        self.pins.clear()

        logger.debug("Mock GPIO cleanup")

    # Test helpers
    def reset(self) -> None:
        """Reset all state for test isolation."""
        self.pins.clear()
        self._operations.clear()
        self._setup_called = False
        self._cleanup_called = False

    def get_operations(self, operation_type: Optional[str] = None) -> list:
        """Get recorded operations, optionally filtered by type."""
        if operation_type is None:
            return self._operations.copy()
        return [op for op in self._operations if op[0] == operation_type]
```

### Pattern 6: Integration with MoteurCoupole

**What:** Refactor `MoteurCoupole` to use dependency injection for the GPIO backend.

**Implementation:**

```python
# core/hardware/moteur.py (refactored)
from typing import Optional
from core.hardware.gpio_backend import GPIOBackend, get_gpio_backend

class MoteurCoupole:
    """Motor controller with pluggable GPIO backend.

    VERSION 4.8: Switchable GPIO backends (lgpio/pigpio/mock).
    """

    def __init__(
        self,
        config_moteur: dict,
        gpio_backend: Optional[GPIOBackend] = None
    ):
        """Initialize motor controller.

        Args:
            config_moteur: Motor configuration dict
            gpio_backend: Optional GPIO backend instance.
                          If None, uses factory with config.
        """
        self.logger = logging.getLogger(__name__)
        self.stop_requested = False

        self._charger_config(config_moteur)
        self._calculer_steps_par_tour()

        # Use provided backend or create from config
        if gpio_backend is None:
            gpio_backend = get_gpio_backend()

        self._gpio = gpio_backend
        self._gpio.setup(self.DIR, self.STEP)

        self.logger.info(
            f"Motor initialized with {type(self._gpio).__name__} backend"
        )

    def definir_direction(self, direction: int) -> None:
        """Set rotation direction."""
        self.direction_actuelle = 1 if direction >= 0 else -1
        self._gpio.write(self.DIR, 1 if self.direction_actuelle == 1 else 0)

    def faire_un_pas(self, delai: float = 0.0015) -> None:
        """Execute one motor step.

        Args:
            delai: Delay between pulses in seconds (min 10us)
        """
        delai_us = max(delai * 1_000_000, 10)  # Convert to us, min 10us
        self._gpio.pulse(self.STEP, delai_us)

    def nettoyer(self) -> None:
        """Cleanup GPIO resources."""
        if self._gpio is not None:
            self._gpio.cleanup()
            self._gpio = None
            self.logger.info("GPIO backend cleaned up")
```

## Anti-Patterns to Avoid

### Anti-Pattern 1: Leaking Backend Details to Callers

**What:** Exposing backend-specific methods or types outside the motor module.

**Why bad:**
- Callers become coupled to specific backend
- Cannot switch backends without changing caller code
- Testing becomes harder

**Instead:** Keep all GPIO interaction behind `MoteurCoupole`. Callers should only use motor methods like `rotation()`, `faire_un_pas()`.

### Anti-Pattern 2: Global Backend Singleton

**What:** Creating a single global backend instance shared across all code.

**Why bad:**
- Cannot use different backends in different contexts
- Test isolation becomes difficult
- Hard to handle backend failures gracefully

**Instead:** Pass backend instance via dependency injection. Each `MoteurCoupole` owns its backend.

### Anti-Pattern 3: Mixing Protocol and ABC

**What:** Creating a class that is both `Protocol` and `ABC`.

**Why bad:** Type checkers do not support mixing non-protocol bases with Protocols.

**Instead:** Use Protocol for interface definition. If you need shared implementation, create a separate base class that implementations can inherit from (optional).

### Anti-Pattern 4: Checking Backend Type in Motor Code

**What:** Using `isinstance()` or type checks to branch behavior based on backend type.

**Why bad:**
- Defeats purpose of abstraction
- Each new backend requires changes to motor code
- Violates Open/Closed principle

**Instead:** All backends must implement the same interface completely. Backend-specific behavior stays inside backend class.

### Anti-Pattern 5: Silent Fallback Without Logging

**What:** Automatically falling back to a different backend when the configured one fails, without clear logging.

**Why bad:**
- User may not realize they're running with different backend
- Performance characteristics may differ unexpectedly
- Debugging becomes difficult

**Instead:** Log clearly when fallback occurs. Consider making fallback explicit in config:
```json
{
  "gpio_backend": "lgpio",
  "gpio_backend_fallback": "pigpio"
}
```

## pigpio Daemon Lifecycle Management

### Checking Daemon Status

```python
def is_pigpiod_running() -> bool:
    """Check if pigpio daemon is running."""
    import subprocess
    try:
        result = subprocess.run(
            ['pgrep', '-x', 'pigpiod'],
            capture_output=True,
            timeout=2
        )
        return result.returncode == 0
    except Exception:
        return False
```

### Starting Daemon Programmatically

```python
def start_pigpiod() -> bool:
    """Attempt to start pigpio daemon.

    Returns:
        True if daemon started successfully.

    Note: Requires sudo or appropriate permissions.
    """
    import subprocess
    import time

    if is_pigpiod_running():
        return True

    try:
        subprocess.run(
            ['sudo', 'pigpiod'],
            check=True,
            timeout=5
        )
        time.sleep(0.5)  # Allow daemon to initialize
        return is_pigpiod_running()
    except Exception:
        return False
```

### Systemd Service Configuration

For production, use systemd to manage pigpiod lifecycle:

```ini
# /etc/systemd/system/pigpiod.service
[Unit]
Description=pigpio daemon
After=network.target

[Service]
Type=forking
ExecStart=/usr/bin/pigpiod
ExecStop=/bin/kill -TERM $MAINPID
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## Testing Strategy

### Unit Tests with MockBackend

```python
# tests/test_moteur_backends.py
import pytest
from core.hardware.gpio_backend import get_gpio_backend
from core.hardware.backends.mock_backend import MockBackend
from core.hardware.moteur import MoteurCoupole


@pytest.fixture
def mock_backend():
    """Provide clean mock backend for each test."""
    backend = MockBackend({'simulate_delays': False})
    yield backend
    backend.cleanup()


@pytest.fixture
def motor_config():
    """Standard motor configuration."""
    return {
        'gpio_pins': {'dir': 17, 'step': 18},
        'steps_per_revolution': 200,
        'microsteps': 4,
        'gear_ratio': 2230,
        'steps_correction_factor': 1.08849
    }


class TestMoteurWithMockBackend:
    """Test motor operations using mock GPIO backend."""

    def test_direction_sets_pin(self, mock_backend, motor_config):
        motor = MoteurCoupole(motor_config, gpio_backend=mock_backend)

        motor.definir_direction(1)  # Clockwise
        assert mock_backend.pins[17].value == 1

        motor.definir_direction(-1)  # Counter-clockwise
        assert mock_backend.pins[17].value == 0

    def test_step_generates_pulse(self, mock_backend, motor_config):
        motor = MoteurCoupole(motor_config, gpio_backend=mock_backend)

        motor.faire_un_pas(delai=0.001)  # 1ms

        assert mock_backend.pins[18].pulse_count == 1
        assert mock_backend.pins[18].last_pulse_duration_us == 1000

    def test_cleanup_releases_resources(self, mock_backend, motor_config):
        motor = MoteurCoupole(motor_config, gpio_backend=mock_backend)
        motor.nettoyer()

        assert mock_backend._cleanup_called


class TestBackendFactory:
    """Test backend factory function."""

    def test_simulation_mode_uses_mock(self):
        config = {'simulation': True}
        backend = get_gpio_backend(config)
        assert isinstance(backend, MockBackend)

    def test_unknown_backend_raises(self):
        config = {'gpio_backend': 'nonexistent'}
        with pytest.raises(ValueError, match="Unknown GPIO backend"):
            get_gpio_backend(config)
```

### Integration Tests (Hardware Required)

```python
# tests/integration/test_gpio_backends.py
import pytest

# Skip on non-Pi hardware
pytestmark = pytest.mark.skipif(
    not is_raspberry_pi(),
    reason="Requires Raspberry Pi hardware"
)


class TestLgpioBackendIntegration:
    """Integration tests for lgpio backend on real hardware."""

    @pytest.fixture
    def lgpio_backend(self):
        from core.hardware.backends.lgpio_backend import LgpioBackend
        backend = LgpioBackend()
        yield backend
        backend.cleanup()

    def test_pin_setup(self, lgpio_backend):
        # Use safe test pins (not connected to hardware)
        lgpio_backend.setup(dir_pin=22, step_pin=23)
        # If we get here without exception, setup succeeded


class TestPigpioBackendIntegration:
    """Integration tests for pigpio backend."""

    @pytest.fixture
    def pigpio_backend(self):
        if not is_pigpiod_running():
            pytest.skip("pigpiod not running")

        from core.hardware.backends.pigpio_backend import PigpioBackend
        backend = PigpioBackend()
        yield backend
        backend.cleanup()

    def test_daemon_connection(self, pigpio_backend):
        # Setup should connect to daemon
        pigpio_backend.setup(dir_pin=22, step_pin=23)
        assert pigpio_backend._pi.connected
```

## Configuration Schema

Add to `data/config.json`:

```json
{
  "gpio_backend": "lgpio",
  "_gpio_backend_comment": "Options: lgpio (default, Pi 5), pigpio (daemon), mock (testing)",

  "pigpio": {
    "host": "localhost",
    "port": 8888,
    "_comment": "Only used when gpio_backend is 'pigpio'"
  },

  "mock_gpio": {
    "simulate_delays": false,
    "_comment": "Only used when gpio_backend is 'mock' or simulation is true"
  }
}
```

## File Structure

```
core/hardware/
├── gpio_backend.py          # Protocol + factory + registry
├── backends/
│   ├── __init__.py          # Imports all backends for registration
│   ├── lgpio_backend.py     # Default lgpio implementation
│   ├── pigpio_backend.py    # pigpio daemon implementation
│   └── mock_backend.py      # Testing mock
├── moteur.py                # Refactored to use GPIOBackend
└── ...
```

## Migration Path

1. **Phase 1:** Create `gpio_backend.py` with Protocol and factory (no changes to moteur.py)
2. **Phase 2:** Implement `LgpioBackend` matching current moteur.py behavior
3. **Phase 3:** Refactor `MoteurCoupole` to use injected backend
4. **Phase 4:** Implement `PigpioBackend`
5. **Phase 5:** Implement `MockBackend` and update tests

Each phase can be deployed independently. Phase 3 is the breaking change - test thoroughly.

## Sources

**Confidence: HIGH**

- [PEP 544 - Protocols: Structural subtyping](https://peps.python.org/pep-0544/) - Official Python specification
- [typing.Protocol documentation](https://typing.python.org/en/latest/spec/protocol.html) - Official Python docs
- [Modern Python Interfaces: ABC, Protocol, or Both?](https://tconsta.medium.com/python-interfaces-abc-protocol-or-both-3c5871ea6642) - Nov 2025 best practices
- [gpiozero Pin Factory API](https://gpiozero.readthedocs.io/en/stable/api_pins.html) - Reference implementation
- [pigpio Python module](https://abyz.me.uk/rpi/pigpio/python.html) - Official pigpio docs
- [pigpio daemon](https://abyz.me.uk/rpi/pigpio/pigpiod.html) - Daemon lifecycle
- [rpi-lgpio differences](https://rpi-lgpio.readthedocs.io/en/latest/differences.html) - lgpio vs RPi.GPIO
- [Raspberry Pi GPIO comparison thread](https://forums.raspberrypi.com/viewtopic.php?t=373963) - Community guidance on library choice
- [Factory Design Patterns in Python](https://dagster.io/blog/python-factory-patterns) - Factory pattern reference
