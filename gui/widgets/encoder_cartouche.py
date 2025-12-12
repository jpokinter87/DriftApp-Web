"""
Cartouche encodeur compact affichant l'angle du démon.
Format: ENC=xx.x° avec couleur de fond selon statut.
"""

from kivy.uix.label import Label
from kivy.graphics import Color, RoundedRectangle
from kivy.clock import Clock
import json
from pathlib import Path


class EncoderCartouche(Label):
    """
    Cartouche compact affichant l'angle encodeur.
    Couleur de fond: gris (inactif), orange (non calibré), vert (calibré)
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Configuration du label
        self.text = "ENC=N/A"
        self.font_size = '13sp'
        self.bold = True
        self.halign = 'center'
        self.valign = 'middle'
        self.color = (1, 1, 1, 1)

        # Taille compacte (environ moitié d'un cartouche)
        self.size_hint = (None, None)
        self.size = (110, 40)
        self.padding = [8, 6]

        # Chemin vers le fichier JSON du démon
        self.daemon_json = Path("/dev/shm/ems22_position.json")

        # État
        self.encoder_angle = 0.0
        self.is_calibrated = False
        self.daemon_ok = False

        # Fond du cartouche avec couleur par défaut (gris)
        with self.canvas.before:
            self.bg_color = Color(0.3, 0.3, 0.3, 1)  # Gris par défaut
            self.bg_rect = RoundedRectangle(
                pos=self.pos,
                size=self.size,
                radius=[8]
            )
        self.bind(pos=self._update_bg, size=self._update_bg, text_size=lambda *args: setattr(self, 'text_size', self.size))

        # Timer pour lire le JSON périodiquement (toutes les 500ms)
        Clock.schedule_interval(self._update_from_daemon, 0.5)

    def _update_bg(self, *args):
        """Met à jour le fond."""
        self.bg_rect.pos = self.pos
        self.bg_rect.size = self.size

    def _update_from_daemon(self, dt):
        """Lit les données du démon encodeur."""
        try:
            if not self.daemon_json.exists():
                self._set_daemon_unavailable()
                return

            # Lire le JSON
            data = json.loads(self.daemon_json.read_text())

            # Extraire les données
            angle = data.get("angle", 0.0)
            calibrated = data.get("calibrated", False)
            status = data.get("status", "OK")

            # Mettre à jour l'affichage
            self.encoder_angle = angle
            self.is_calibrated = calibrated
            self.daemon_ok = (status == "OK")

            # Mise à jour visuelle - format compact
            if not self.daemon_ok:
                self.text = "ENC=ERR"
                self.bg_color.rgba = (0.4, 0.15, 0.15, 1)  # Fond rouge foncé
            elif calibrated:
                self.text = f"ENC={angle:.2f}°"
                self.bg_color.rgba = (0.15, 0.35, 0.2, 1)  # Fond vert foncé
            else:
                self.text = f"ENC={angle:.2f}°"
                self.bg_color.rgba = (0.4, 0.3, 0.15, 1)  # Fond orange foncé

        except json.JSONDecodeError:
            self._set_daemon_unavailable()
        except Exception:
            self._set_daemon_unavailable()

    def _set_daemon_unavailable(self):
        """Affichage quand le démon n'est pas disponible."""
        self.text = "ENC=N/A"
        self.bg_color.rgba = (0.3, 0.3, 0.3, 1)  # Fond gris
        self.daemon_ok = False
