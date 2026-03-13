"""
Bandeau d'information graphique pour afficher les paramètres de tracking.
Remplace l'affichage texte par une présentation visuelle moderne.

Refactorisé pour utiliser ThemedBox et Cartouche (élimination duplication).
"""

from kivy.uix.boxlayout import BoxLayout
from kivy.properties import NumericProperty, StringProperty
from gui.widgets.timer_widget import TimerWidget
from gui.widgets.themed_widgets import ThemedBox, Cartouche


class InfoBanner(ThemedBox):
    """
    Bandeau graphique affichant les paramètres de tracking.

    Affiche :
    - Méthode (ABAQUE)
    - Seuil (degrés)
    - Intervalle (secondes)
    """

    seuil = NumericProperty(0.1)
    intervalle = NumericProperty(30)
    methode = StringProperty("ABAQUE")

    def __init__(self, seuil=0.1, intervalle=30, methode="ABAQUE", **kwargs):
        super().__init__(
            bg_color=(0.18, 0.2, 0.23, 1),
            radius=15,
            orientation='horizontal',
            size_hint_y=None,
            height=55,
            spacing=12,
            padding=[10, 8],
            **kwargs
        )

        self.seuil = seuil
        self.intervalle = intervalle
        self.methode = methode

        # Timer circulaire à gauche (toute la hauteur)
        timer_container = BoxLayout(size_hint_x=0.7, padding=[8, 0])
        self.timer = TimerWidget()
        self.timer.intervalle = intervalle
        timer_container.add_widget(self.timer)
        self.add_widget(timer_container)

        # Colonne de droite : SEUIL et INTERVALLE empilés verticalement
        right_column = BoxLayout(orientation='vertical', size_hint_x=0.3, spacing=6)
        self._create_threshold_section(right_column)
        self._create_interval_section(right_column)
        self.add_widget(right_column)

    def _create_threshold_section(self, parent):
        """Section seuil - utilise Cartouche."""
        self.threshold_cartouche = Cartouche(
            title="SEUIL",
            value=f"{self.seuil:.2f}°",
            bg_color=(0.35, 0.5, 0.25, 0.3),
            title_font_size='11sp',
            value_font_size='14sp',
            title_color=(0.6, 0.8, 0.5, 1),
            value_color=(0.85, 1, 0.75, 1)
        )
        self.threshold_label = self.threshold_cartouche.value_label
        parent.add_widget(self.threshold_cartouche)

    def _create_interval_section(self, parent):
        """Section intervalle - utilise Cartouche."""
        self.interval_cartouche = Cartouche(
            title="INTERVALLE",
            value=f"{self.intervalle}s",
            bg_color=(0.5, 0.35, 0.25, 0.3),
            title_font_size='11sp',
            value_font_size='14sp',
            title_color=(0.9, 0.7, 0.5, 1),
            value_color=(1, 0.9, 0.7, 1)
        )
        self.interval_label = self.interval_cartouche.value_label
        parent.add_widget(self.interval_cartouche)

    def update_values(self, seuil=None, intervalle=None, methode=None):
        """Met à jour les valeurs affichées."""
        if seuil is not None:
            self.seuil = seuil
            self.threshold_label.text = f"{self.seuil:.2f}°"

        if intervalle is not None:
            self.intervalle = intervalle
            self.interval_label.text = f"{self.intervalle}s"
            self.timer.intervalle = intervalle

        if methode is not None:
            self.methode = methode
            self.method_label.text = self.methode

    def update_timer(self, temps, intervalle=None):
        """Met à jour le timer circulaire."""
        self.timer.update_time(temps, intervalle)
