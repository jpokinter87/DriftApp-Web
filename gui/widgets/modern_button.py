"""
Boutons modernes avec effets hover, press et bordures arrondies.

Contient :
- BaseModernButton : Classe de base avec logique commune
- ModernButton : Bouton texte simple
- IconButton : Bouton avec icône PNG + texte
"""

from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.graphics import Color, RoundedRectangle
from kivy.properties import ListProperty, NumericProperty, StringProperty
from kivy.animation import Animation
from kivy.core.window import Window
import os


class BaseModernButton(ButtonBehavior, BoxLayout):
    """
    Classe de base pour les boutons modernes.

    Fournit :
    - Bordures arrondies
    - Effet hover (changement de couleur)
    - Effet press (animation)
    - Shadow effect

    Sous-classes : ModernButton, IconButton
    """

    bg_color = ListProperty([0.2, 0.7, 0.3, 1])
    bg_color_hover = ListProperty([0.25, 0.8, 0.35, 1])
    bg_color_press = ListProperty([0.15, 0.6, 0.25, 1])
    radius = NumericProperty(15)

    def __init__(self, **kwargs):
        # Extraire les couleurs custom avant d'appeler super()
        bg_color_custom = kwargs.pop('bg_color', None)
        bg_color_hover_custom = kwargs.pop('bg_color_hover', None)
        bg_color_press_custom = kwargs.pop('bg_color_press', None)

        super().__init__(**kwargs)

        self._setup_colors(bg_color_custom, bg_color_hover_custom, bg_color_press_custom)
        self._create_graphics()
        self._bind_events()

    def _setup_colors(self, bg_color_custom, bg_color_hover_custom, bg_color_press_custom):
        """Configure les couleurs du bouton."""
        if bg_color_custom is not None:
            self.bg_color = bg_color_custom

        # Auto-calculer hover et press si non fournis
        if bg_color_hover_custom is not None:
            self.bg_color_hover = bg_color_hover_custom
        else:
            self.bg_color_hover = [min(c * 1.2, 1) for c in self.bg_color[:3]] + [1]

        if bg_color_press_custom is not None:
            self.bg_color_press = bg_color_press_custom
        else:
            self.bg_color_press = [c * 0.8 for c in self.bg_color[:3]] + [1]

    def _create_graphics(self):
        """Crée les éléments graphiques (ombre et fond)."""
        with self.canvas.before:
            # Ombre
            Color(0, 0, 0, 0.3)
            self.shadow = RoundedRectangle(
                pos=(self.x + 2, self.y - 2),
                size=self.size,
                radius=[self.radius]
            )

            # Fond bouton
            self.color_instruction = Color(rgba=self.bg_color)
            self.bg_rect = RoundedRectangle(
                pos=self.pos,
                size=self.size,
                radius=[self.radius]
            )

    def _bind_events(self):
        """Configure les bindings d'événements."""
        self.bind(pos=self._update_graphics, size=self._update_graphics)
        Window.bind(mouse_pos=self.on_mouse_pos)

    def _update_graphics(self, *args):
        """Met à jour la position/taille des graphiques."""
        self.shadow.pos = (self.x + 2, self.y - 2)
        self.shadow.size = self.size
        self.bg_rect.pos = self.pos
        self.bg_rect.size = self.size

    def on_mouse_pos(self, window, pos):
        """Détecte le survol de la souris."""
        if not self.get_root_window():
            return

        is_hovering = self.collide_point(*self.to_widget(*pos))
        is_pressed = self.state == 'down'

        if not is_pressed:
            self.color_instruction.rgba = self.bg_color_hover if is_hovering else self.bg_color

    def on_press(self):
        """Animation au clic."""
        self.color_instruction.rgba = self.bg_color_press
        anim = Animation(size=(self.width * 0.95, self.height * 0.95), duration=0.05)
        anim.start(self)

    def on_release(self):
        """Retour à la normale après clic."""
        self.color_instruction.rgba = self.bg_color_hover
        anim = Animation(size=(self.width / 0.95, self.height / 0.95), duration=0.05)
        anim.start(self)


class ModernButton(BaseModernButton):
    """
    Bouton moderne avec texte uniquement.

    Usage:
        btn = ModernButton(
            text="Cliquez-moi",
            bg_color=[0.2, 0.5, 0.8, 1]
        )
    """

    def __init__(self, **kwargs):
        # Extraire les paramètres du label
        text = kwargs.pop('text', '')
        font_size = kwargs.pop('font_size', '17sp')
        color = kwargs.pop('color', (1, 1, 1, 1))
        bold = kwargs.pop('bold', True)

        super().__init__(**kwargs)

        self.orientation = 'horizontal'

        # Label texte centré
        self.label = Label(
            text=text,
            font_size=font_size,
            color=color,
            bold=bold,
            halign='center',
            valign='middle'
        )
        self.label.bind(size=self.label.setter('text_size'))
        self.add_widget(self.label)

    @property
    def text(self):
        """Retourne le texte du bouton."""
        return self.label.text if hasattr(self, 'label') else ""

    @text.setter
    def text(self, value):
        """Définit le texte du bouton."""
        if hasattr(self, 'label'):
            self.label.text = value


class IconButton(BaseModernButton):
    """
    Bouton moderne avec icône PNG + texte.

    Usage:
        btn = IconButton(
            text="Démarrer",
            icon_source="icons/play.png",
            bg_color=[0.15, 0.4, 0.2, 1]
        )
    """

    icon_source = StringProperty("")
    text = StringProperty("")

    def __init__(self, **kwargs):
        icon_source = kwargs.pop('icon_source', '')
        text = kwargs.pop('text', '')

        super().__init__(**kwargs)

        self.orientation = 'horizontal'
        self.spacing = 8
        self.padding = [12, 0]

        # Icône PNG (optionnelle)
        if icon_source and os.path.exists(icon_source):
            self.icon = Image(
                source=icon_source,
                size_hint_x=None,
                width=24,
                allow_stretch=True,
                keep_ratio=True
            )
            self.add_widget(self.icon)
        else:
            self.icon = None

        # Label texte
        self.label = Label(
            text=text,
            font_size='17sp',
            color=(1, 1, 1, 1),
            bold=True,
            halign='center',
            valign='middle'
        )
        self.add_widget(self.label)

    def set_icon(self, icon_source: str):
        """Change l'icône du bouton."""
        if not os.path.exists(icon_source):
            return

        if self.icon:
            self.icon.source = icon_source
        else:
            self.icon = Image(
                source=icon_source,
                size_hint_x=None,
                width=24,
                allow_stretch=True,
                keep_ratio=True
            )
            # Insérer avant le label
            self.add_widget(self.icon, index=len(self.children))