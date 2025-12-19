"""
Tests pour le module IPC Manager.

Ce module teste la gestion des fichiers de communication inter-processus
entre Motor Service et Django.
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


class TestIpcManager:
    """Tests pour la classe IpcManager."""

    @pytest.fixture
    def ipc_manager(self, tmp_path):
        """Crée un IpcManager avec des chemins temporaires."""
        with patch('services.ipc_manager.COMMAND_FILE', tmp_path / 'command.json'), \
             patch('services.ipc_manager.STATUS_FILE', tmp_path / 'status.json'), \
             patch('services.ipc_manager.ENCODER_FILE', tmp_path / 'encoder.json'):
            from services.ipc_manager import IpcManager
            return IpcManager()

    @pytest.fixture
    def command_file(self, tmp_path):
        """Retourne le chemin du fichier de commandes."""
        return tmp_path / 'command.json'

    @pytest.fixture
    def status_file(self, tmp_path):
        """Retourne le chemin du fichier de status."""
        return tmp_path / 'status.json'


class TestReadCommand:
    """Tests pour la lecture des commandes."""

    @pytest.fixture
    def ipc_manager(self, tmp_path):
        """Crée un IpcManager avec des chemins temporaires."""
        with patch('services.ipc_manager.COMMAND_FILE', tmp_path / 'command.json'), \
             patch('services.ipc_manager.STATUS_FILE', tmp_path / 'status.json'), \
             patch('services.ipc_manager.ENCODER_FILE', tmp_path / 'encoder.json'):
            from services.ipc_manager import IpcManager
            return IpcManager()

    def test_read_command_no_file(self, ipc_manager, tmp_path):
        """Retourne None si le fichier n'existe pas."""
        with patch('services.ipc_manager.COMMAND_FILE', tmp_path / 'nonexistent.json'):
            result = ipc_manager.read_command()
            assert result is None

    def test_read_command_empty_file(self, ipc_manager, tmp_path):
        """Retourne None si le fichier est vide."""
        cmd_file = tmp_path / 'command.json'
        cmd_file.write_text('')

        with patch('services.ipc_manager.COMMAND_FILE', cmd_file):
            result = ipc_manager.read_command()
            assert result is None

    def test_read_command_valid(self, ipc_manager, tmp_path):
        """Lit correctement une commande valide."""
        cmd_file = tmp_path / 'command.json'
        command = {'command': 'goto', 'angle': 90.0, 'id': 'cmd_001'}
        cmd_file.write_text(json.dumps(command))

        with patch('services.ipc_manager.COMMAND_FILE', cmd_file):
            result = ipc_manager.read_command()
            assert result == command

    def test_read_command_duplicate_ignored(self, ipc_manager, tmp_path):
        """Les commandes avec le même ID sont ignorées."""
        cmd_file = tmp_path / 'command.json'
        command = {'command': 'goto', 'angle': 90.0, 'id': 'cmd_001'}
        cmd_file.write_text(json.dumps(command))

        with patch('services.ipc_manager.COMMAND_FILE', cmd_file):
            # Première lecture
            result1 = ipc_manager.read_command()
            assert result1 == command

            # Deuxième lecture avec même ID
            result2 = ipc_manager.read_command()
            assert result2 is None

    def test_read_command_new_id_accepted(self, ipc_manager, tmp_path):
        """Une nouvelle commande avec un ID différent est acceptée."""
        cmd_file = tmp_path / 'command.json'

        with patch('services.ipc_manager.COMMAND_FILE', cmd_file):
            # Première commande
            cmd1 = {'command': 'goto', 'angle': 90.0, 'id': 'cmd_001'}
            cmd_file.write_text(json.dumps(cmd1))
            result1 = ipc_manager.read_command()
            assert result1 == cmd1

            # Deuxième commande avec nouvel ID
            cmd2 = {'command': 'jog', 'delta': 10.0, 'id': 'cmd_002'}
            cmd_file.write_text(json.dumps(cmd2))
            result2 = ipc_manager.read_command()
            assert result2 == cmd2

    def test_read_command_invalid_json(self, ipc_manager, tmp_path):
        """Retourne None si le JSON est invalide."""
        cmd_file = tmp_path / 'command.json'
        cmd_file.write_text('{invalid json')

        with patch('services.ipc_manager.COMMAND_FILE', cmd_file):
            result = ipc_manager.read_command()
            assert result is None


class TestWriteStatus:
    """Tests pour l'écriture du status."""

    @pytest.fixture
    def ipc_manager(self, tmp_path):
        """Crée un IpcManager avec des chemins temporaires."""
        with patch('services.ipc_manager.COMMAND_FILE', tmp_path / 'command.json'), \
             patch('services.ipc_manager.STATUS_FILE', tmp_path / 'status.json'), \
             patch('services.ipc_manager.ENCODER_FILE', tmp_path / 'encoder.json'):
            from services.ipc_manager import IpcManager
            return IpcManager()

    def test_write_status_creates_file(self, ipc_manager, tmp_path):
        """Le status est écrit dans un nouveau fichier."""
        status_file = tmp_path / 'status.json'
        status = {'status': 'idle', 'position': 45.0}

        with patch('services.ipc_manager.STATUS_FILE', status_file):
            ipc_manager.write_status(status)

            assert status_file.exists()
            written = json.loads(status_file.read_text())
            assert written['status'] == 'idle'
            assert written['position'] == 45.0

    def test_write_status_adds_timestamp(self, ipc_manager, tmp_path):
        """Le timestamp last_update est ajouté automatiquement."""
        status_file = tmp_path / 'status.json'
        status = {'status': 'moving'}

        with patch('services.ipc_manager.STATUS_FILE', status_file):
            ipc_manager.write_status(status)

            written = json.loads(status_file.read_text())
            assert 'last_update' in written

    def test_write_status_overwrites(self, ipc_manager, tmp_path):
        """Le status existant est écrasé."""
        status_file = tmp_path / 'status.json'

        with patch('services.ipc_manager.STATUS_FILE', status_file):
            ipc_manager.write_status({'status': 'idle'})
            ipc_manager.write_status({'status': 'moving'})

            written = json.loads(status_file.read_text())
            assert written['status'] == 'moving'


class TestClearCommand:
    """Tests pour l'effacement des commandes."""

    @pytest.fixture
    def ipc_manager(self, tmp_path):
        """Crée un IpcManager avec des chemins temporaires."""
        with patch('services.ipc_manager.COMMAND_FILE', tmp_path / 'command.json'), \
             patch('services.ipc_manager.STATUS_FILE', tmp_path / 'status.json'), \
             patch('services.ipc_manager.ENCODER_FILE', tmp_path / 'encoder.json'):
            from services.ipc_manager import IpcManager
            return IpcManager()

    def test_clear_command_empties_file(self, ipc_manager, tmp_path):
        """Le fichier de commande est vidé."""
        cmd_file = tmp_path / 'command.json'
        cmd_file.write_text('{"command": "stop"}')

        with patch('services.ipc_manager.COMMAND_FILE', cmd_file):
            ipc_manager.clear_command()

            assert cmd_file.read_text() == ''

    def test_clear_command_no_file(self, ipc_manager, tmp_path):
        """Pas d'erreur si le fichier n'existe pas."""
        with patch('services.ipc_manager.COMMAND_FILE', tmp_path / 'nonexistent.json'):
            # Ne doit pas lever d'exception
            ipc_manager.clear_command()


class TestReadEncoderFile:
    """Tests pour la lecture du fichier encodeur."""

    @pytest.fixture
    def ipc_manager(self, tmp_path):
        """Crée un IpcManager avec des chemins temporaires."""
        with patch('services.ipc_manager.COMMAND_FILE', tmp_path / 'command.json'), \
             patch('services.ipc_manager.STATUS_FILE', tmp_path / 'status.json'), \
             patch('services.ipc_manager.ENCODER_FILE', tmp_path / 'encoder.json'):
            from services.ipc_manager import IpcManager
            return IpcManager()

    def test_read_encoder_valid(self, ipc_manager, tmp_path):
        """Lit correctement le fichier encodeur."""
        enc_file = tmp_path / 'encoder.json'
        encoder_data = {'angle': 123.5, 'calibrated': True, 'status': 'OK'}
        enc_file.write_text(json.dumps(encoder_data))

        with patch('services.ipc_manager.ENCODER_FILE', enc_file):
            result = ipc_manager.read_encoder_file()
            assert result == encoder_data

    def test_read_encoder_no_file(self, ipc_manager, tmp_path):
        """Retourne None si le fichier n'existe pas."""
        with patch('services.ipc_manager.ENCODER_FILE', tmp_path / 'nonexistent.json'):
            result = ipc_manager.read_encoder_file()
            assert result is None

    def test_read_encoder_empty_file(self, ipc_manager, tmp_path):
        """Retourne None si le fichier est vide."""
        enc_file = tmp_path / 'encoder.json'
        enc_file.write_text('')

        with patch('services.ipc_manager.ENCODER_FILE', enc_file):
            result = ipc_manager.read_encoder_file()
            assert result is None
