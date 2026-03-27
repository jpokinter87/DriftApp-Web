"""
Simulateur serie pour developpement sans Pi Pico physique.

Emule les reponses du firmware RP2040 (protocole MOVE/STOP/STATUS)
pour permettre le dev et les tests sans materiel.

Version: 5.3
Date: Mars 2026
"""

import logging
import threading
import time
from collections import deque

logger = logging.getLogger(__name__)


class SerialSimulator:
    """
    Simule un port serie compatible pyserial.

    Repond aux commandes MOVE/STOP/STATUS conformement au protocole
    firmware RP2040 defini en Phase 1.
    """

    def __init__(self):
        self.is_open = True
        self.timeout = 2.0
        self._response_buffer: deque[bytes] = deque()
        self._lock = threading.Lock()
        self._pending_move = None  # (steps, sim_duration) pour delai simule
        # Le firmware envoie READY au demarrage
        self._response_buffer.append(b"READY\n")

    def write(self, data: bytes) -> int:
        """
        Recoit une commande et genere la reponse simulee.

        Args:
            data: Commande encodee en bytes (ex: b"MOVE 1000 1 2000 SCURVE\\n")

        Returns:
            Nombre de bytes ecrits
        """
        if not self.is_open:
            raise IOError("Port serie ferme")

        line = data.decode("utf-8", errors="replace").strip()
        if not line:
            return len(data)

        parts = line.split()
        command = parts[0].upper()

        with self._lock:
            if command == "MOVE":
                if len(parts) >= 5:
                    try:
                        steps = int(parts[1])
                        delay_us = int(parts[3])
                        # Simuler la duree du mouvement (accelere x100)
                        real_duration = (steps * delay_us) / 1_000_000
                        sim_duration = real_duration / 50
                        self._pending_move = (steps, sim_duration)
                        response = f"OK {steps}\n"
                    except (ValueError, IndexError):
                        response = "ERROR invalid_command\n"
                else:
                    response = "ERROR invalid_command\n"
            elif command == "STOP":
                response = "IDLE\n"
            elif command == "STATUS":
                response = "IDLE\n"
            else:
                response = "ERROR unknown_command\n"

            self._response_buffer.append(response.encode("utf-8"))

        return len(data)

    def readline(self) -> bytes:
        """
        Lit la prochaine reponse du buffer.

        Simule le delai de mouvement pour les commandes MOVE
        (accelere x100 par rapport au reel).

        Returns:
            Reponse encodee en bytes (terminee par \\n)
        """
        if not self.is_open:
            raise IOError("Port serie ferme")

        # Simuler le delai de mouvement avant de retourner la reponse MOVE
        if self._pending_move is not None:
            _, sim_duration = self._pending_move
            self._pending_move = None
            if sim_duration > 0.01:
                time.sleep(sim_duration)

        with self._lock:
            if self._response_buffer:
                return self._response_buffer.popleft()
        return b""

    def reset_input_buffer(self):
        """Vide le buffer d'entree (compatibilite pyserial)."""
        with self._lock:
            self._response_buffer.clear()

    def close(self):
        """Ferme le port serie simule."""
        self.is_open = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
