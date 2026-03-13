"""
Bandeau de statut graphique pour afficher l'état du tracking en temps réel.

Refactorisé pour utiliser ThemedBox et CartoucheCompact (élimination duplication).
"""

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.graphics import Color, RoundedRectangle
from kivy.properties import StringProperty, NumericProperty
from gui.widgets.themed_widgets import ThemedBox, CartoucheCompact


class StatusBanner(ThemedBox):
    """
    Bandeau graphique affichant le statut du tracking en temps réel.

    Affiche :
    - Azimut/Altitude objet
    - Position coupole
    - Position encodeur
    - Mode adaptatif
    - Statistiques corrections
    """

    temps = NumericProperty(0)
    azimut = NumericProperty(0)
    altitude = NumericProperty(0)
    coupole = NumericProperty(0)
    encodeur = StringProperty("N/A")
    mode = StringProperty("NORMAL")
    position = NumericProperty(0)
    corrections_nb = NumericProperty(0)
    corrections_total = NumericProperty(0)

    def __init__(self, **kwargs):
        super().__init__(
            bg_color=(0.15, 0.17, 0.2, 1),
            radius=15,
            orientation='horizontal',
            size_hint_y=None,
            height=80,
            spacing=6,
            padding=[10, 8],
            **kwargs
        )

        # Spacer à gauche (70% pour aligner avec le timer)
        self.add_widget(BoxLayout(size_hint_x=0.7))

        # Colonne de droite : tous les cartouches empilés
        right_column = BoxLayout(orientation='vertical', size_hint_x=0.3, spacing=4)
        self._create_cartouches(right_column)
        self.add_widget(right_column)

    def _create_cartouches(self, parent):
        """Crée tous les cartouches empilés verticalement."""
        # AZ/ALT
        self.azalt_cartouche = CartoucheCompact(
            title="AZ/ALT",
            value="0° / 0°",
            bg_color=(0.3, 0.6, 0.9, 0.3)
        )
        self.azalt_label = self.azalt_cartouche.value_label
        parent.add_widget(self.azalt_cartouche)

        # COUPOLE
        self.coupole_cartouche = CartoucheCompact(
            title="COUPOLE",
            value="0°",
            bg_color=(0.2, 0.7, 0.5, 0.3)
        )
        self.coupole_label = self.coupole_cartouche.value_label
        parent.add_widget(self.coupole_cartouche)

        # ENCODEUR
        self.encodeur_cartouche = CartoucheCompact(
            title="ENCODEUR",
            value="N/A",
            bg_color=(0.6, 0.4, 0.7, 0.3)
        )
        self.encodeur_label = self.encodeur_cartouche.value_label
        parent.add_widget(self.encodeur_cartouche)

        # MODE (avec fond dynamique - garde le code manuel pour couleur dynamique)
        mode_box = BoxLayout(orientation='vertical', padding=[4, 2], spacing=1)
        with mode_box.canvas.before:
            self.mode_color = Color(0.9, 0.6, 0.2, 0.3)
            self.mode_bg = RoundedRectangle(
                pos=mode_box.pos,
                size=mode_box.size,
                radius=[6]
            )
        mode_box.bind(
            pos=lambda *args: setattr(self.mode_bg, 'pos', mode_box.pos),
            size=lambda *args: setattr(self.mode_bg, 'size', mode_box.size)
        )

        mode_title = Label(
            text="MODE",
            font_size='7sp',
            color=(0.7, 0.7, 0.7, 1),
            size_hint_y=0.35,
            bold=True
        )
        mode_box.add_widget(mode_title)

        self.mode_label = Label(
            text="NORMAL",
            font_size='9sp',
            color=(1, 1, 1, 1),
            size_hint_y=0.65,
            bold=True
        )
        mode_box.add_widget(self.mode_label)
        parent.add_widget(mode_box)

        # POSITION
        self.position_cartouche = CartoucheCompact(
            title="POSITION",
            value="0.0°",
            bg_color=(0.3, 0.5, 0.8, 0.3)
        )
        self.position_label = self.position_cartouche.value_label
        parent.add_widget(self.position_cartouche)

        # CORRECTIONS
        self.corrections_cartouche = CartoucheCompact(
            title="CORRECTIONS",
            value="0 (0.0° total)",
            bg_color=(0.7, 0.3, 0.5, 0.3)
        )
        self.corrections_label = self.corrections_cartouche.value_label
        parent.add_widget(self.corrections_cartouche)

    def update_status(self, temps=None, azimut=None, altitude=None, coupole=None,
                     encodeur=None, mode=None, position=None,
                     corrections_nb=None, corrections_total=None):
        """Met à jour les valeurs affichées."""
        # temps n'est plus affiché ici (redondant avec timer circulaire)

        if azimut is not None and altitude is not None:
            self.azimut = azimut
            self.altitude = altitude
            self.azalt_label.text = f"{self.azimut:.2f}° / {self.altitude:.2f}°"

        if coupole is not None:
            self.coupole = coupole
            self.coupole_label.text = f"{self.coupole:.2f}°"

        if encodeur is not None:
            self.encodeur = encodeur
            self.encodeur_label.text = str(self.encodeur)

        if mode is not None:
            self.mode = mode
            # Simplifier le mode si c'est TrackingMode.XXXX
            mode_display = mode.split('.')[-1] if '.' in mode else mode
            self.mode_label.text = mode_display.upper()

            # Changer la couleur du fond selon le mode
            mode_upper = mode_display.upper()
            if mode_upper == "NORMAL":
                self.mode_color.rgba = (0.2, 0.5, 0.3, 0.5)  # Vert foncé
            elif mode_upper == "CRITICAL":
                self.mode_color.rgba = (0.6, 0.4, 0.2, 0.5)  # Orange foncé
            elif mode_upper in ["CONTINU", "CONTINUOUS"]:
                self.mode_color.rgba = (0.5, 0.2, 0.2, 0.5)  # Rouge foncé
            else:
                self.mode_color.rgba = (0.4, 0.4, 0.4, 0.5)  # Gris par défaut

        if position is not None:
            self.position = position
            self.position_label.text = f"{self.position:.2f}°"

        if corrections_nb is not None and corrections_total is not None:
            self.corrections_nb = corrections_nb
            self.corrections_total = corrections_total
            self.corrections_label.text = f"{self.corrections_nb} ({self.corrections_total:.2f}° total)"