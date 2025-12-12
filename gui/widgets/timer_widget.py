"""
Widget timer circulaire moderne pour afficher le compte à rebours.
"""

from kivy.uix.widget import Widget
from kivy.uix.label import Label
from kivy.graphics import Color, Ellipse, Line
from kivy.properties import NumericProperty
import math


class TimerWidget(Widget):
    """
    Timer circulaire avec progression et temps au centre.

    Affiche:
    - Cercle de fond
    - Arc de progression
    - Temps restant au centre (secondes)
    """

    temps = NumericProperty(0)  # Temps restant (secondes)
    intervalle = NumericProperty(30)  # Intervalle total (pour calcul %)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Label temps au centre
        self.time_label = Label(
            text="0s",
            font_size='24sp',
            color=(1, 1, 1, 1),
            bold=True
        )
        self.add_widget(self.time_label)

        self.bind(pos=self._update_graphics, size=self._update_graphics)
        self.bind(temps=self._update_time_display, intervalle=self._update_time_display)

    def _update_graphics(self, *args):
        """Redessine le cercle et l'arc."""
        self.canvas.before.clear()

        if self.width == 0 or self.height == 0:
            return

        # Centre et rayon
        center_x = self.x + self.width / 2
        center_y = self.y + self.height / 2
        radius = min(self.width, self.height) / 2 - 2

        with self.canvas.before:
            # Cercle de fond (gris foncé)
            Color(0.25, 0.27, 0.3, 1)
            Ellipse(
                pos=(center_x - radius, center_y - radius),
                size=(radius * 2, radius * 2)
            )

            # Arc de progression (commence en haut = 90°, sens horaire inverse)
            if self.intervalle > 0:
                progress = self.temps / self.intervalle
                angle_total = 360 * progress

                # Couleur selon progression
                if progress > 0.5:
                    color = (0.3, 0.7, 0.4, 1)  # Vert
                elif progress > 0.25:
                    color = (0.7, 0.6, 0.3, 1)  # Orange
                else:
                    color = (0.7, 0.3, 0.3, 1)  # Rouge

                Color(*color)
                # Arc démarre à 360° (=0°) pour atteindre position 12h
                # Pattern observé: 90°→15h, 180°→18h, 270°→21h, donc 360°→24h(=12h)
                # Se vide dans le sens anti-horaire
                Line(
                    circle=(center_x, center_y, radius - 3, 360 - angle_total, 360),
                    width=8
                )

        # Mettre à jour position du label
        self.time_label.center_x = center_x
        self.time_label.center_y = center_y

    def _update_time_display(self, *args):
        """Met à jour l'affichage du temps."""
        self.time_label.text = f"{int(self.temps)}s"
        self._update_graphics()

    def update_time(self, temps, intervalle=None):
        """Met à jour le temps restant."""
        self.temps = temps
        if intervalle is not None:
            self.intervalle = intervalle