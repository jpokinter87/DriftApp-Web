"""
Widgets Kivy avec thème visuel réutilisable.

Classes utilitaires pour éliminer la duplication de code dans les bandeaux GUI.
Centralise la logique de fond arrondi coloré avec auto-binding.
"""

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.image import Image
from kivy.graphics import Color, RoundedRectangle
from kivy.properties import ListProperty, NumericProperty
import os


class ThemedBox(BoxLayout):
    """
    BoxLayout avec fond arrondi coloré et auto-binding.

    Élimine la duplication du pattern :
        with box.canvas.before:
            Color(r, g, b, a)
            bg = RoundedRectangle(pos=box.pos, size=box.size, radius=[10])
        box.bind(pos=..., size=...)

    Usage:
        box = ThemedBox(bg_color=(0.3, 0.5, 0.8, 0.3), radius=10)
    """

    bg_color = ListProperty([0.2, 0.2, 0.2, 0.3])
    radius = NumericProperty(10)

    def __init__(self, bg_color=(0.2, 0.2, 0.2, 0.3), radius=10, **kwargs):
        super().__init__(**kwargs)

        self.bg_color = list(bg_color)
        self.radius = radius

        with self.canvas.before:
            self._color_instruction = Color(*self.bg_color)
            self._bg_rect = RoundedRectangle(
                pos=self.pos,
                size=self.size,
                radius=[self.radius]
            )

        self.bind(pos=self._update_bg, size=self._update_bg)

    def _update_bg(self, *args):
        """Met à jour la position et taille du fond."""
        self._bg_rect.pos = self.pos
        self._bg_rect.size = self.size

    def set_bg_color(self, r, g, b, a=1.0):
        """Change la couleur de fond dynamiquement."""
        self.bg_color = [r, g, b, a]
        self._color_instruction.rgba = self.bg_color


class Cartouche(ThemedBox):
    """
    Cartouche d'information avec titre et valeur.

    Layout vertical :
    - Titre (petit, gris)
    - Valeur (grand, blanc)

    Usage:
        cart = Cartouche(
            title="AZIMUT",
            value="45.2°",
            bg_color=(0.3, 0.6, 0.9, 0.3)
        )
        cart.set_value("123.4°")
    """

    def __init__(self, title="LABEL", value="0", bg_color=(0.2, 0.2, 0.2, 0.3),
                 title_font_size='9sp', value_font_size='12sp',
                 title_color=(0.7, 0.7, 0.7, 1), value_color=(1, 1, 1, 1),
                 radius=10, padding=None, spacing=1, **kwargs):
        # Paramètres par défaut
        if padding is None:
            padding = [6, 4]

        super().__init__(
            bg_color=bg_color,
            radius=radius,
            orientation='vertical',
            padding=padding,
            spacing=spacing,
            **kwargs
        )

        # Titre
        self.title_label = Label(
            text=title,
            font_size=title_font_size,
            color=title_color,
            size_hint_y=0.4,
            bold=True
        )
        self.add_widget(self.title_label)

        # Valeur
        self.value_label = Label(
            text=value,
            font_size=value_font_size,
            color=value_color,
            size_hint_y=0.6,
            bold=True
        )
        self.add_widget(self.value_label)

    def set_value(self, value):
        """Met à jour la valeur affichée."""
        self.value_label.text = str(value)

    def set_title(self, title):
        """Met à jour le titre."""
        self.title_label.text = title


class CartoucheHorizontal(ThemedBox):
    """
    Cartouche horizontal avec titre à gauche et valeur à droite.

    Layout horizontal :
    - [Icône optionnelle] Titre (gauche)
    - Valeur (droite)

    Usage:
        cart = CartoucheHorizontal(
            title="SEUIL",
            value="0.50°",
            bg_color=(0.35, 0.5, 0.25, 0.3),
            icon_name="tool.png"
        )
    """

    def __init__(self, title="LABEL", value="0", bg_color=(0.2, 0.2, 0.2, 0.3),
                 title_font_size='11sp', value_font_size='14sp',
                 title_color=(0.7, 0.7, 0.7, 1), value_color=(1, 1, 1, 1),
                 icon_name=None, radius=10, padding=None, spacing=8, **kwargs):
        # Paramètres par défaut
        if padding is None:
            padding = [8, 6]

        super().__init__(
            bg_color=bg_color,
            radius=radius,
            orientation='horizontal',
            padding=padding,
            spacing=spacing,
            **kwargs
        )

        # Partie gauche : icône + titre
        left_container = BoxLayout(orientation='horizontal', size_hint_x=0.5, spacing=4)

        if icon_name:
            icon_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                'icons',
                icon_name
            )
            if os.path.exists(icon_path):
                icon = Image(
                    source=icon_path,
                    size_hint_x=None,
                    width=16,
                    allow_stretch=True,
                    keep_ratio=True
                )
                left_container.add_widget(icon)

        self.title_label = Label(
            text=title,
            font_size=title_font_size,
            color=title_color,
            bold=True,
            halign='left',
            valign='middle'
        )
        self.title_label.bind(size=self.title_label.setter('text_size'))
        left_container.add_widget(self.title_label)
        self.add_widget(left_container)

        # Partie droite : valeur
        self.value_label = Label(
            text=value,
            font_size=value_font_size,
            color=value_color,
            size_hint_x=0.5,
            bold=True,
            halign='right',
            valign='middle'
        )
        self.value_label.bind(size=self.value_label.setter('text_size'))
        self.add_widget(self.value_label)

    def set_value(self, value):
        """Met à jour la valeur affichée."""
        self.value_label.text = str(value)

    def set_title(self, title):
        """Met à jour le titre."""
        self.title_label.text = title


class CartoucheCompact(ThemedBox):
    """
    Cartouche compact horizontal pour StatusBanner.

    Layout horizontal :
    - Titre (40%, petit)
    - Valeur (60%, grand)

    Usage:
        cart = CartoucheCompact(
            title="AZ/ALT",
            value="45° / 30°",
            bg_color=(0.3, 0.6, 0.9, 0.3)
        )
    """

    def __init__(self, title="LABEL", value="0", bg_color=(0.2, 0.2, 0.2, 0.3),
                 title_font_size='7sp', value_font_size='9sp',
                 title_color=(0.7, 0.7, 0.7, 1), value_color=(1, 1, 1, 1),
                 radius=6, padding=None, spacing=4, **kwargs):
        # Paramètres par défaut
        if padding is None:
            padding = [4, 2]

        super().__init__(
            bg_color=bg_color,
            radius=radius,
            orientation='horizontal',
            padding=padding,
            spacing=spacing,
            **kwargs
        )

        # Titre
        self.title_label = Label(
            text=title,
            font_size=title_font_size,
            color=title_color,
            size_hint_x=0.4,
            bold=True
        )
        self.add_widget(self.title_label)

        # Valeur
        self.value_label = Label(
            text=value,
            font_size=value_font_size,
            color=value_color,
            size_hint_x=0.6,
            bold=True
        )
        self.add_widget(self.value_label)

    def set_value(self, value):
        """Met à jour la valeur affichée."""
        self.value_label.text = str(value)


class ModeIndicator(ThemedBox):
    """
    Indicateur de mode avec couleur dynamique.

    Affiche un titre "MODE" et une valeur (NORMAL, CRITICAL, CONTINUOUS)
    avec couleur de fond adaptée automatiquement.

    Couleurs par mode :
    - NORMAL : Vert (0.2, 0.5, 0.3, 0.5)
    - CRITICAL : Orange (0.6, 0.4, 0.2, 0.5)
    - CONTINUOUS/CONTINU : Rouge vif (0.9, 0.15, 0.15, 0.9)
    - Autre : Gris (0.4, 0.4, 0.4, 0.5)

    Usage:
        indicator = ModeIndicator()
        indicator.set_mode("CRITICAL")  # Change couleur automatiquement
    """

    # Mapping des couleurs par mode
    MODE_COLORS = {
        'normal': (0.2, 0.5, 0.3, 0.5),
        'critical': (0.6, 0.4, 0.2, 0.5),
        'continuous': (0.9, 0.15, 0.15, 0.9),
        'continu': (0.9, 0.15, 0.15, 0.9),
    }
    DEFAULT_COLOR = (0.4, 0.4, 0.4, 0.5)

    def __init__(self, mode="NORMAL", title_font_size='10sp',
                 value_font_size='14sp', radius=10, padding=None,
                 spacing=1, **kwargs):
        if padding is None:
            padding = [8, 4]

        # Couleur initiale basée sur le mode
        initial_color = self._get_mode_color(mode)

        super().__init__(
            bg_color=initial_color,
            radius=radius,
            orientation='vertical',
            padding=padding,
            spacing=spacing,
            **kwargs
        )

        # Titre "MODE"
        self.title_label = Label(
            text="MODE",
            font_size=title_font_size,
            color=(0.7, 0.7, 0.7, 1),
            size_hint_y=0.35,
            bold=True
        )
        self.add_widget(self.title_label)

        # Valeur du mode
        self.value_label = Label(
            text=mode.upper(),
            font_size=value_font_size,
            color=(1, 1, 1, 1),
            size_hint_y=0.65,
            bold=True
        )
        self.add_widget(self.value_label)

    def _get_mode_color(self, mode: str) -> tuple:
        """Retourne la couleur associée au mode."""
        mode_key = mode.lower().split('.')[-1]  # Gérer "TrackingMode.NORMAL"
        return self.MODE_COLORS.get(mode_key, self.DEFAULT_COLOR)

    def set_mode(self, mode: str):
        """
        Change le mode affiché et adapte la couleur.

        Args:
            mode: Nom du mode (NORMAL, CRITICAL, CONTINUOUS, etc.)
        """
        # Extraire le nom du mode si format "TrackingMode.XXX"
        mode_display = mode.split('.')[-1] if '.' in mode else mode
        self.value_label.text = mode_display.upper()

        # Changer la couleur de fond
        new_color = self._get_mode_color(mode)
        self.set_bg_color(*new_color)