"""
Widget boussole pour afficher la position du dôme en temps réel.
Lit les données du daemon EMS22A depuis /dev/shm/ems22_position.json
"""

import json
import math
from pathlib import Path
from kivy.uix.widget import Widget
from kivy.graphics import Color, Line, Ellipse, Rectangle
from kivy.clock import Clock
from kivy.properties import NumericProperty


class CompassWidget(Widget):
    """
    Widget circulaire affichant l'angle du dôme.

    - Cercle extérieur : cadran
    - Aiguille rouge : position actuelle
    - Marquages cardinaux (N/E/S/W)
    """

    angle = NumericProperty(0.0)  # Angle du dôme (0-360°)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.daemon_file = Path("/dev/shm/ems22_position.json")

        # Démarrer mise à jour temps réel (10 Hz)
        Clock.schedule_interval(self.update_angle, 0.1)

        # Redessiner quand l'angle change
        self.bind(angle=lambda *_: self.draw_compass())
        self.bind(size=lambda *_: self.draw_compass())
        self.bind(pos=lambda *_: self.draw_compass())

    def update_angle(self, dt):
        """Lit l'angle depuis le fichier daemon."""
        try:
            if self.daemon_file.exists():
                data = json.loads(self.daemon_file.read_text())
                self.angle = data.get("angle", 0.0)
        except Exception:
            pass  # Silencieux en cas d'erreur de lecture

    def draw_compass(self):
        """Dessine la boussole (cercle + aiguille + graduations)."""
        self.canvas.clear()

        if self.width == 0 or self.height == 0:
            return

        # Centre et rayon
        center_x = self.x + self.width / 2
        center_y = self.y + self.height / 2
        radius = min(self.width, self.height) / 2 - 20

        with self.canvas:
            # Fond noir
            Color(0, 0, 0, 1)
            Rectangle(pos=self.pos, size=self.size)

            # Cercle extérieur (gris)
            Color(0.3, 0.3, 0.3, 1)
            Line(circle=(center_x, center_y, radius), width=3)

            # Graduations cardinales
            self._draw_cardinal_marks(center_x, center_y, radius)

            # Aiguille (rouge, pointe vers l'angle actuel)
            Color(1, 0, 0, 1)
            angle_rad = math.radians(self.angle - 90)  # -90 pour que 0° = Nord (haut)
            needle_x = center_x + radius * 0.8 * math.cos(angle_rad)
            needle_y = center_y + radius * 0.8 * math.sin(angle_rad)
            Line(points=[center_x, center_y, needle_x, needle_y], width=4)

            # Point central
            Color(1, 1, 1, 1)
            Ellipse(pos=(center_x - 5, center_y - 5), size=(10, 10))

    def _draw_cardinal_marks(self, cx, cy, radius):
        """Dessine les marquages N/E/S/W."""
        from kivy.graphics import Color, Line

        marks = [
            (0, "N"),    # Nord
            (90, "E"),   # Est
            (180, "S"),  # Sud
            (270, "W")   # Ouest
        ]

        for angle_deg, label in marks:
            angle_rad = math.radians(angle_deg - 90)

            # Trait de graduation
            x1 = cx + radius * 0.9 * math.cos(angle_rad)
            y1 = cy + radius * 0.9 * math.sin(angle_rad)
            x2 = cx + radius * math.cos(angle_rad)
            y2 = cy + radius * math.sin(angle_rad)

            Color(0.7, 0.7, 0.7, 1)
            Line(points=[x1, y1, x2, y2], width=2)

            # TODO: Ajouter labels texte (nécessite kivy.uix.label.Label en overlay)