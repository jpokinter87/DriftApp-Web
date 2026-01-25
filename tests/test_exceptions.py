"""
Tests pour les exceptions personnalisees DriftApp.

Verifie la hierarchie d'exceptions, les attributs contextuels,
et le chainage d'exceptions.

Date: Janvier 2026
"""

import pytest

from core.exceptions import (
    DriftAppError,
    MotorError,
    EncoderError,
    AbaqueError,
    IPCError,
    ConfigError,
)


class TestExceptionHierarchy:
    """Tests pour la hierarchie d'exceptions."""

    def test_driftapp_error_inherits_from_exception(self):
        """DriftAppError herite de Exception."""
        assert issubclass(DriftAppError, Exception)

    def test_motor_error_inherits_from_driftapp(self):
        """MotorError herite de DriftAppError."""
        assert issubclass(MotorError, DriftAppError)
        assert issubclass(MotorError, Exception)

    def test_encoder_error_inherits_from_driftapp(self):
        """EncoderError herite de DriftAppError."""
        assert issubclass(EncoderError, DriftAppError)
        assert issubclass(EncoderError, Exception)

    def test_abaque_error_inherits_from_driftapp(self):
        """AbaqueError herite de DriftAppError."""
        assert issubclass(AbaqueError, DriftAppError)
        assert issubclass(AbaqueError, Exception)

    def test_ipc_error_inherits_from_driftapp(self):
        """IPCError herite de DriftAppError."""
        assert issubclass(IPCError, DriftAppError)
        assert issubclass(IPCError, Exception)

    def test_config_error_inherits_from_driftapp(self):
        """ConfigError herite de DriftAppError."""
        assert issubclass(ConfigError, DriftAppError)
        assert issubclass(ConfigError, Exception)


class TestExceptionMessages:
    """Tests pour les messages d'exception."""

    def test_driftapp_error_message(self):
        """DriftAppError preserves message."""
        error = DriftAppError("Test message")
        assert str(error) == "Test message"

    def test_motor_error_message(self):
        """MotorError preserves message."""
        error = MotorError("Moteur bloque")
        assert str(error) == "Moteur bloque"

    def test_encoder_error_message(self):
        """EncoderError preserves message."""
        error = EncoderError("Daemon non accessible")
        assert str(error) == "Daemon non accessible"

    def test_abaque_error_message(self):
        """AbaqueError preserves message."""
        error = AbaqueError("Fichier introuvable")
        assert str(error) == "Fichier introuvable"

    def test_ipc_error_message(self):
        """IPCError preserves message."""
        error = IPCError("Timeout lecture")
        assert str(error) == "Timeout lecture"

    def test_config_error_message(self):
        """ConfigError preserves message."""
        error = ConfigError("Cle manquante")
        assert str(error) == "Cle manquante"


class TestMotorErrorAttributes:
    """Tests pour les attributs de MotorError."""

    def test_default_attributes_are_none(self):
        """Attributs par defaut sont None."""
        error = MotorError("Test")
        assert error.pin is None
        assert error.delay is None
        assert error.operation is None

    def test_pin_attribute(self):
        """Attribut pin accessible."""
        error = MotorError("Test", pin=18)
        assert error.pin == 18

    def test_delay_attribute(self):
        """Attribut delay accessible."""
        error = MotorError("Test", delay=0.001)
        assert error.delay == 0.001

    def test_operation_attribute(self):
        """Attribut operation accessible."""
        error = MotorError("Test", operation="rotation")
        assert error.operation == "rotation"

    def test_all_attributes(self):
        """Tous les attributs ensemble."""
        error = MotorError("Test", pin=17, delay=0.002, operation="init")
        assert error.pin == 17
        assert error.delay == 0.002
        assert error.operation == "init"


class TestEncoderErrorAttributes:
    """Tests pour les attributs de EncoderError."""

    def test_default_attributes_are_none(self):
        """Attributs par defaut sont None."""
        error = EncoderError("Test")
        assert error.daemon_path is None
        assert error.timeout_ms is None

    def test_daemon_path_attribute(self):
        """Attribut daemon_path accessible."""
        error = EncoderError("Test", daemon_path="/dev/shm/ems22_position.json")
        assert error.daemon_path == "/dev/shm/ems22_position.json"

    def test_timeout_ms_attribute(self):
        """Attribut timeout_ms accessible."""
        error = EncoderError("Test", timeout_ms=200)
        assert error.timeout_ms == 200


class TestAbaqueErrorAttributes:
    """Tests pour les attributs de AbaqueError."""

    def test_default_attributes_are_none(self):
        """Attributs par defaut sont None."""
        error = AbaqueError("Test")
        assert error.file_path is None
        assert error.altitude is None
        assert error.azimut is None

    def test_file_path_attribute(self):
        """Attribut file_path accessible."""
        error = AbaqueError("Test", file_path="data/Loi_coupole.xlsx")
        assert error.file_path == "data/Loi_coupole.xlsx"

    def test_altitude_azimut_attributes(self):
        """Attributs altitude et azimut accessibles."""
        error = AbaqueError("Test", altitude=45.0, azimut=180.0)
        assert error.altitude == 45.0
        assert error.azimut == 180.0


class TestIPCErrorAttributes:
    """Tests pour les attributs de IPCError."""

    def test_default_attributes_are_none(self):
        """Attributs par defaut sont None."""
        error = IPCError("Test")
        assert error.file_path is None
        assert error.operation is None

    def test_file_path_attribute(self):
        """Attribut file_path accessible."""
        error = IPCError("Test", file_path="/dev/shm/motor_status.json")
        assert error.file_path == "/dev/shm/motor_status.json"

    def test_operation_attribute(self):
        """Attribut operation accessible."""
        error = IPCError("Test", operation="write")
        assert error.operation == "write"


class TestConfigErrorAttributes:
    """Tests pour les attributs de ConfigError."""

    def test_default_attributes_are_none(self):
        """Attributs par defaut sont None."""
        error = ConfigError("Test")
        assert error.config_path is None
        assert error.key is None

    def test_config_path_attribute(self):
        """Attribut config_path accessible."""
        error = ConfigError("Test", config_path="data/config.json")
        assert error.config_path == "data/config.json"

    def test_key_attribute(self):
        """Attribut key accessible."""
        error = ConfigError("Test", key="site.latitude")
        assert error.key == "site.latitude"


class TestExceptionChaining:
    """Tests pour le chainage d'exceptions (from e)."""

    def test_motor_error_chaining(self):
        """MotorError peut etre chaine avec from e."""
        original = ValueError("GPIO error")
        try:
            raise MotorError("Init failed", pin=18) from original
        except MotorError as e:
            assert e.__cause__ is original
            assert str(e.__cause__) == "GPIO error"

    def test_encoder_error_chaining(self):
        """EncoderError peut etre chaine avec from e."""
        original = FileNotFoundError("Daemon not found")
        try:
            raise EncoderError("Read failed", daemon_path="/dev/shm/test.json") from original
        except EncoderError as e:
            assert e.__cause__ is original

    def test_abaque_error_chaining(self):
        """AbaqueError peut etre chaine avec from e."""
        original = KeyError("altitude")
        try:
            raise AbaqueError("Interpolation failed", altitude=90.0) from original
        except AbaqueError as e:
            assert e.__cause__ is original

    def test_ipc_error_chaining(self):
        """IPCError peut etre chaine avec from e."""
        original = OSError("Permission denied")
        try:
            raise IPCError("Write failed", operation="write") from original
        except IPCError as e:
            assert e.__cause__ is original

    def test_config_error_chaining(self):
        """ConfigError peut etre chaine avec from e."""
        original = json.JSONDecodeError("Invalid JSON", "", 0)
        try:
            raise ConfigError("Parse failed", config_path="config.json") from original
        except ConfigError as e:
            assert e.__cause__ is original


class TestCatchingByBase:
    """Tests pour la capture par exception de base."""

    def test_catch_motor_error_as_driftapp(self):
        """MotorError peut etre capture comme DriftAppError."""
        with pytest.raises(DriftAppError):
            raise MotorError("Test")

    def test_catch_encoder_error_as_driftapp(self):
        """EncoderError peut etre capture comme DriftAppError."""
        with pytest.raises(DriftAppError):
            raise EncoderError("Test")

    def test_catch_abaque_error_as_driftapp(self):
        """AbaqueError peut etre capture comme DriftAppError."""
        with pytest.raises(DriftAppError):
            raise AbaqueError("Test")

    def test_catch_ipc_error_as_driftapp(self):
        """IPCError peut etre capture comme DriftAppError."""
        with pytest.raises(DriftAppError):
            raise IPCError("Test")

    def test_catch_config_error_as_driftapp(self):
        """ConfigError peut etre capture comme DriftAppError."""
        with pytest.raises(DriftAppError):
            raise ConfigError("Test")


# Import needed for test_config_error_chaining
import json
