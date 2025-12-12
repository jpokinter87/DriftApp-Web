"""
Écran de statut affichant la position actuelle du dôme.
Boussole temps réel + informations système.
"""

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.graphics import Color, Rectangle
from gui.widgets.compass import CompassWidget


class StatusScreen(Screen):
    """
    Écran de monitoring avec boussole temps réel.

    Affiche :
    - Boussole graphique (position du dôme)
    - Angle numérique
    - Bouton retour
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = "status"

        # Layout principal (vertical)
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)

        # Fond sombre
        with layout.canvas.before:
            Color(0.1, 0.1, 0.15, 1)
            self.rect = Rectangle(size=layout.size, pos=layout.pos)
        layout.bind(size=self._update_rect, pos=self._update_rect)

        # Titre
        title = Label(
            text="Position actuelle du dôme",
            font_size='24sp',
            size_hint_y=None,
            height=50,
            color=(1, 1, 1, 1)
        )
        layout.add_widget(title)

        # Widget boussole (prend l'espace principal)
        self.compass = CompassWidget(size_hint=(1, 0.7))
        layout.add_widget(self.compass)

        # Label angle numérique
        self.angle_label = Label(
            text="Angle : 0.0°",
            font_size='32sp',
            size_hint_y=None,
            height=60,
            color=(1, 0.5, 0, 1)  # Orange
        )
        layout.add_widget(self.angle_label)

        # Mise à jour du label quand l'angle change
        self.compass.bind(angle=self._update_angle_label)

        # Bouton retour
        back_btn = Button(
            text="← Retour",
            size_hint_y=None,
            height=80,
            font_size='20sp',
            background_color=(0.3, 0.3, 0.3, 1),
            color=(1, 1, 1, 1)
        )
        back_btn.bind(on_press=self.go_back)
        layout.add_widget(back_btn)

        self.add_widget(layout)

    def _update_rect(self, instance, value):
        """Met à jour le rectangle de fond."""
        self.rect.pos = instance.pos
        self.rect.size = instance.size

    def _update_angle_label(self, instance, value):
        """Met à jour le label d'angle numérique."""
        self.angle_label.text = f"Angle : {value:.2f}°"

    def go_back(self, instance):
        """Retour à l'écran principal."""
        self.manager.current = 'main'