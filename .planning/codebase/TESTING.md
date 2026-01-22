# Testing Patterns

**Analysis Date:** 2026-01-22

## Test Framework

**Runner:**
- Pytest 7.0.0+
- Config: `pytest.ini`
- Discovery pattern: `tests/test_*.py` files, `Test*` classes, `test_*` methods

**Assertion Library:**
- pytest built-in assertions
- `pytest.approx()` for floating-point comparisons (angle tolerance)
- Custom helper: `approx_angle()` in `tests/conftest.py`

**Run Commands:**
```bash
# All tests (455 total)
uv run pytest -v

# Without astropy (fast, ~315 tests)
uv run pytest tests/ -k "not astropy" -v

# Watch mode (use pytest-watch if installed)
uv run pytest -v --tb=short

# Coverage report
uv run pytest --cov=core --cov=services --cov=web

# Specific test file
uv run pytest tests/test_moteur.py -v

# Specific test class
uv run pytest tests/test_moteur.py::TestDaemonEncoderReader -v

# Specific test method
uv run pytest tests/test_angle_utils.py::TestNormalizeAngle360::test_angle_normal -v
```

**pytest.ini Configuration:**
```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -v --tb=short
filterwarnings =
    ignore::DeprecationWarning
    ignore::PendingDeprecationWarning
markers =
    slow: marks tests as slow (deselect with '-m "not slow"')
    hardware: marks tests that require hardware (GPIO, SPI)
    integration: marks integration tests
```

## Test File Organization

**Location:**
- Co-located in `tests/` directory (separate from source)
- Pattern: `tests/test_*.py` mirrors `core/`, `services/`, `web/` structure
- Examples:
  - `tests/test_moteur.py` → `core/hardware/moteur.py`
  - `tests/test_angle_utils.py` → `core/utils/angle_utils.py`
  - `tests/test_command_handlers.py` → `services/command_handlers.py`

**Naming:**
- Test files: `test_<module>.py`
- Test classes: `Test<Subject>` (e.g., `TestMoteurCoupoleControl`, `TestDaemonEncoderReader`)
- Test methods: `test_<scenario>` with snake_case (e.g., `test_angle_superior_360`, `test_read_raw_json_invalide`)

**Structure Example (`tests/test_angle_utils.py`):**
```
test_angle_utils.py
├── TestNormalizeAngle360
│   ├── test_angle_normal
│   ├── test_angle_superieur_360
│   └── test_angle_negatif
├── TestNormalizeAngle180
│   ├── test_angle_deja_dans_intervalle
│   └── test_angle_superieur_180
└── TestShortestAngularDistance
    ├── test_distance_directe_positive
    └── test_traversee_zero
```

## Test Structure

**Suite Organization:**
- One test class per logical unit/function
- Setup/teardown via pytest fixtures (not unittest setUp/tearDown)
- Use `conftest.py` for shared fixtures

**Fixture Pattern (from `tests/conftest.py`):**
```python
@pytest.fixture
def sample_config() -> Dict[str, Any]:
    """Configuration de test minimale."""
    return {
        "site": {...},
        "motor": {...},
        "gpio": {...}
    }

@pytest.fixture
def temp_config_file(sample_config, tmp_path) -> Path:
    """Crée un fichier config.json temporaire."""
    config_file = tmp_path / "config.json"
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(sample_config, f)
    return config_file
```

**Patterns:**
- Arrange-Act-Assert (AAA):
```python
def test_shortest_angular_distance_positive(self):
    """Distance directe dans le sens horaire."""
    # Arrange (implicit in test data)
    # Act
    result = shortest_angular_distance(0.0, 90.0)
    # Assert
    assert result == 90.0
```

- Descriptive test method names:
```python
def test_is_available_false(self):
    """is_available retourne False si fichier n'existe pas."""

def test_read_raw_json_invalide(self, tmp_path):
    """Lecture brute retourne None si JSON invalide."""
```

- Docstring explains expectation, method name is descriptive

**Teardown Pattern (autouse fixture):**
```python
@pytest.fixture(autouse=True)
def reset_simulation_state():
    """
    Reset automatique de l'état de simulation avant chaque test.
    Garantit l'isolation des tests.
    """
    from core.hardware.moteur_simule import reset_all_simulated_positions
    from core.hardware.moteur import reset_daemon_reader
    reset_all_simulated_positions()
    reset_daemon_reader()
    yield
    reset_all_simulated_positions()
    reset_daemon_reader()
```

## Mocking

**Framework:** `unittest.mock` (Python standard library)

**Patterns:**

1. **Mock GPIO modules (all tests)**:
```python
@pytest.fixture
def mock_gpio():
    """Mock pour les bibliothèques GPIO."""
    with patch.dict('sys.modules', {
        'RPi': MagicMock(),
        'RPi.GPIO': MagicMock(),
        'lgpio': MagicMock(),
        'spidev': MagicMock()
    }):
        yield
```

2. **Mock specific module attributes**:
```python
@patch('services.ipc_manager.COMMAND_FILE', helper.command_file)
@patch('services.ipc_manager.STATUS_FILE', helper.status_file)
def test_ipc_flow(self, ...):
    ...
```

3. **MagicMock for complex objects**:
```python
@pytest.fixture
def mock_moteur():
    """Mock du moteur."""
    moteur = MagicMock()
    moteur.rotation = MagicMock()
    moteur.clear_stop_request = MagicMock()
    moteur.request_stop = MagicMock()
    return moteur
```

4. **Patch with return values**:
```python
@pytest.fixture
def mock_daemon_reader():
    """Mock du lecteur d'encodeur."""
    reader = MagicMock()
    reader.is_available = MagicMock(return_value=True)
    reader.read_angle = MagicMock(return_value=45.0)
    return reader
```

**What to Mock:**
- External system calls: GPIO operations, file I/O on missing files
- Hardware interactions: Encoder daemon, motor control
- Time-dependent operations: datetime, sleep calls (if testing timing)
- Network/IPC: Motor service communication

**What NOT to Mock:**
- Core business logic: angle calculations, position tracking
- Utility functions: Use real implementations
- Configuration loading: Use test fixtures instead of mocking
- Internal state management: Let it work naturally

## Fixtures and Factories

**Test Data Fixtures (conftest.py):**

1. **Configuration:**
```python
@pytest.fixture
def sample_config() -> Dict[str, Any]:
    """Configuration de test minimale."""
    return {
        "site": {"latitude": 44.15, "longitude": 5.23, ...},
        "motor": {"steps_per_revolution": 200, ...},
        "gpio": {"dir_pin": 17, "step_pin": 18},
        "dome_offsets": {"meridian_offset": 180.0, ...}
    }
```

2. **Astronomical Data:**
```python
@pytest.fixture
def observation_datetime() -> datetime:
    """Date/heure d'observation fixe pour tests reproductibles."""
    return datetime(2025, 6, 21, 22, 0, 0, tzinfo=timezone.utc)

@pytest.fixture
def known_objects() -> Dict[str, Dict[str, float]]:
    """Objets célestes avec coordonnées connues."""
    return {
        "M13": {"ra_deg": 250.42, "dec_deg": 36.46, ...},
        "Vega": {"ra_deg": 279.23, "dec_deg": 38.78, ...}
    }
```

3. **Abaque Data:**
```python
@pytest.fixture
def sample_abaque_data() -> Dict[float, Dict[str, list]]:
    """Données d'abaque simulées pour tests."""
    return {
        30.0: {
            'az_astre': [0, 45, 90, ...],
            'az_coupole': [2, 47, 95, ...]
        },
        ...
    }
```

4. **Hardware Simulation:**
```python
@pytest.fixture
def mock_daemon_encoder_data() -> Dict[str, Any]:
    """Données simulées du daemon encodeur."""
    return {
        "angle": 45.5,
        "raw": 512,
        "total_counts": 47104,
        "timestamp": "2025-06-21T22:00:00",
        "age_ms": 10,
        "calibrated": True
    }

@pytest.fixture
def mock_encoder_json_file(mock_daemon_encoder_data, tmp_path) -> Path:
    """Crée un fichier JSON daemon simulé."""
    json_file = tmp_path / "ems22_position.json"
    with open(json_file, "w") as f:
        json.dump(mock_daemon_encoder_data, f)
    return json_file
```

**Location:**
- All shared fixtures in `tests/conftest.py`
- Module-specific fixtures inline in test files (if not reused)

**Factory Pattern (IPC helper):**
```python
class IpcTestHelper:
    """Helper pour créer un environnement IPC de test isolé."""

    def __init__(self, tmp_path: Path):
        self.tmp_path = tmp_path
        self.command_file = tmp_path / 'motor_command.json'
        self.status_file = tmp_path / 'motor_status.json'

    def write_command_django_side(self, command: Dict[str, Any]):
        """Simule Django écrivant une commande."""
        with open(self.command_file, 'w') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.write(json.dumps(command))
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
```

## Coverage

**Requirements:**
- Not enforced project-wide
- Critical modules have >90% coverage (core/utils, core/hardware basics)
- Tracking and calculation modules have good coverage due to complexity

**View Coverage:**
```bash
# Generate coverage report
uv run pytest --cov=core --cov=services --cov=web --cov-report=html

# View in browser
open htmlcov/index.html

# Terminal report
uv run pytest --cov=core --cov=services --cov=web --cov-report=term-missing
```

## Test Types

**Unit Tests:**
- Scope: Single function or method in isolation
- Example: `test_normalize_angle_360()` in `tests/test_angle_utils.py`
- Mocks: All external dependencies
- Files: `tests/test_*.py` (most tests are unit tests)
- Count: ~300 tests

**Integration Tests:**
- Scope: Multiple components working together
- Example: IPC command flow (Django → Motor Service → Status) in `tests/test_integration.py`
- Mocks: Only external systems (files use tmp_path)
- Marker: `@pytest.mark.integration`
- Files: `tests/test_integration.py`, `tests/test_e2e.py`
- Count: ~30 tests

**E2E Tests:**
- Scope: Full feature flow (tracking session start to completion)
- Example: `tests/test_e2e.py` - Tracking with real calculations
- Mocks: Hardware only (GPIO, daemon), use real astronomy
- Marker: `@pytest.mark.slow` (takes >10s)
- Requires: astropy library

**Marked Tests:**
```python
@pytest.mark.slow
def test_full_tracking_session(self):
    """Full tracking session with astropy calculations."""
    ...

@pytest.mark.hardware
def test_gpio_initialization(self):
    """Requires GPIO available."""
    ...

@pytest.mark.integration
def test_ipc_command_flow(self):
    """Integration test of IPC."""
    ...
```

## Common Patterns

**Async Testing:**
- Not used (no async in this codebase)
- Synchronous operations with manual threading for testing concurrency

**Concurrent Testing Pattern (IPC):**
```python
def test_concurrent_ipc_access(self, ipc_manager_patched):
    """Tests concurrent writes/reads with locks."""
    ipc, helper = ipc_manager_patched

    # Simulate concurrent Django and Motor Service access
    def django_write():
        helper.write_command_django_side({'command': 'goto', 'angle': 90})

    def motor_read():
        time.sleep(0.01)  # Let Django write first
        return ipc.read_command()

    with ThreadPoolExecutor() as executor:
        write_future = executor.submit(django_write)
        read_future = executor.submit(motor_read)

        write_future.result()
        result = read_future.result()
        assert result['command'] == 'goto'
```

**Error Testing:**
```python
def test_read_angle_timeout(self, tmp_path):
    """Lecture d'angle avec timeout."""
    reader = DaemonEncoderReader(Path("/inexistant.json"))

    with pytest.raises(RuntimeError, match="Démon inaccessible"):
        reader.read_angle(timeout_ms=100)

def test_invalid_json_handling(self, tmp_path):
    """Gestion JSON invalide."""
    json_file = tmp_path / "invalid.json"
    json_file.write_text("{ broken json }")

    reader = DaemonEncoderReader(json_file)
    result = reader.read_raw()

    assert result is None  # Graceful degradation
```

**Parametrized Tests:**
```python
@pytest.mark.parametrize("angle,expected", [
    (370.0, 10.0),
    (720.0, 0.0),
    (365.5, pytest.approx(5.5))
])
def test_normalize_angle_360(self, angle, expected):
    """Test multiple angle inputs."""
    assert normalize_angle_360(angle) == expected
```

**Floating-point Comparisons:**
```python
# Custom helper from conftest.py
def approx_angle(expected: float, rel: float = 1e-3, abs: float = 0.01):
    """Helper pour comparaison d'angles avec tolérance."""
    return pytest.approx(expected, rel=rel, abs=abs)

# Usage
assert result_angle == approx_angle(45.0, abs=0.5)

# Or inline
assert normalize_angle_360(365.5) == pytest.approx(5.5)
```

## Test Dependencies

**Conditional imports (astropy):**
```python
# Skip entire test module if astropy missing
try:
    import astropy
    HAS_ASTROPY = True
except ImportError:
    HAS_ASTROPY = False

requires_astropy = pytest.mark.skipif(
    not HAS_ASTROPY,
    reason="Ces tests nécessitent astropy"
)

# In test class
@requires_astropy
def test_astronomical_calculations(self):
    """Requires astropy."""
    ...
```

**Test runs:**
- Fast run: `uv run pytest tests/ -k "not astropy" -v` (~2 minutes, 315 tests)
- Full run: `uv run pytest -v` (~5 minutes, 455 tests with astropy)

## Test Isolation

**State Reset Pattern (autouse fixture):**
```python
@pytest.fixture(autouse=True)
def reset_simulation_state():
    """Reset before and after each test."""
    from core.hardware.moteur_simule import reset_all_simulated_positions
    reset_all_simulated_positions()
    yield
    reset_all_simulated_positions()
```

**Temporary Files:**
```python
# pytest provides tmp_path fixture automatically
def test_config_save(self, tmp_path):
    config_file = tmp_path / "config.json"
    # File auto-deleted after test
```

**IPC File Isolation (test_integration.py):**
```python
@pytest.fixture
def ipc_manager_patched(tmp_path):
    """Patches IPC file paths to tmp_path."""
    helper = IpcTestHelper(tmp_path)
    with patch('services.ipc_manager.COMMAND_FILE', helper.command_file):
        yield IpcManager(), helper
```

---

*Testing analysis: 2026-01-22*
