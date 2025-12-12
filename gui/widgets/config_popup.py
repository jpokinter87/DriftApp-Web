"""
Popup de configuration pour modifier les paramètres de tracking.
Version moderne avec design amélioré.
"""

from kivy.uix.popup import Popup
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.core.window import Window
from kivy.clock import Clock
from gui.widgets.modern_button import ModernButton


class ConfigPopup(Popup):
    """
    Popup de configuration pour seuil et intervalle.

    Équivalent de ConfigScreenWithMethod dans Textual.
    """

    def __init__(self, seuil_actuel, intervalle_actuel, callback, **kwargs):
        super().__init__(**kwargs)

        self.callback = callback

        # Configuration popup
        self.title = "Configuration"
        self.title_size = '20sp'
        self.title_align = 'center'
        self.size_hint = (0.75, None)
        self.height = 380  # Augmenté pour éviter la superposition du titre
        self.auto_dismiss = False
        self.separator_height = 25  # Plus d'espace sous le titre

        # Layout principal
        layout = BoxLayout(orientation='vertical', padding=[25, 30, 25, 25], spacing=20)

        # Fond sombre
        with layout.canvas.before:
            Color(0.1, 0.1, 0.15, 1)
            self.rect = Rectangle(size=layout.size, pos=layout.pos)
        layout.bind(size=self._update_rect, pos=self._update_rect)

        # === SEUIL ===
        seuil_container = BoxLayout(orientation='vertical', size_hint_y=None, height=80, spacing=5)

        seuil_label = Label(
            text="Seuil de correction (degrés):",
            size_hint_y=None,
            height=30,
            font_size='16sp',
            color=(1, 1, 1, 1),
            halign='left',
            valign='middle'
        )
        seuil_label.bind(size=seuil_label.setter('text_size'))
        seuil_container.add_widget(seuil_label)

        self.input_seuil = TextInput(
            text=str(seuil_actuel),
            size_hint_y=None,
            height=45,
            font_size='18sp',
            multiline=False,
            background_color=(0.2, 0.22, 0.25, 1),
            foreground_color=(1, 1, 1, 1),
            cursor_color=(0.5, 1, 0.5, 1),
            input_filter='float',
            padding=[15, 12]
        )
        self.input_seuil.bind(on_text_validate=self._focus_next)
        seuil_container.add_widget(self.input_seuil)

        layout.add_widget(seuil_container)

        # === INTERVALLE ===
        intervalle_container = BoxLayout(orientation='vertical', size_hint_y=None, height=80, spacing=5)

        intervalle_label = Label(
            text="Intervalle entre corrections (secondes):",
            size_hint_y=None,
            height=30,
            font_size='16sp',
            color=(1, 1, 1, 1),
            halign='left',
            valign='middle'
        )
        intervalle_label.bind(size=intervalle_label.setter('text_size'))
        intervalle_container.add_widget(intervalle_label)

        self.input_intervalle = TextInput(
            text=str(intervalle_actuel),
            size_hint_y=None,
            height=45,
            font_size='18sp',
            multiline=False,
            background_color=(0.2, 0.22, 0.25, 1),
            foreground_color=(1, 1, 1, 1),
            cursor_color=(0.5, 1, 0.5, 1),
            input_filter='int',
            padding=[15, 12]
        )
        self.input_intervalle.bind(on_text_validate=lambda instance: self.on_validate(None))
        intervalle_container.add_widget(self.input_intervalle)

        layout.add_widget(intervalle_container)

        # === BOUTONS (ModernButton avec effets hover/press) ===
        button_row = BoxLayout(orientation='horizontal', size_hint_y=None, height=65, spacing=15)

        btn_cancel = ModernButton(
            text="Annuler",
            font_size='17sp',
            bg_color=[0.45, 0.45, 0.45, 1],
            color=(1, 1, 1, 1),
            bold=True,
            radius=18
        )
        btn_cancel.bind(on_press=self.on_cancel)
        button_row.add_widget(btn_cancel)

        btn_ok = ModernButton(
            text="Valider",
            font_size='17sp',
            bg_color=[0.2, 0.7, 0.3, 1],
            color=(1, 1, 1, 1),
            bold=True,
            radius=18
        )
        btn_ok.bind(on_press=self.on_validate)
        button_row.add_widget(btn_ok)

        layout.add_widget(button_row)

        self.content = layout

        # Bind clavier pour Tab
        Window.bind(on_key_down=self._on_keyboard)

        # Bind événement d'ouverture pour focus
        self.bind(on_open=self._on_popup_open)

    def _on_popup_open(self, instance):
        """Appelé quand le popup s'ouvre - met le focus sur le premier champ."""
        Clock.schedule_once(lambda dt: setattr(self.input_seuil, 'focus', True), 0.2)

    def _on_keyboard(self, window, key, scancode, codepoint, modifier):
        """Gestion du clavier : Tab pour naviguer, Entrée pour valider."""
        # Tab (keycode 9)
        if key == 9:
            if self.input_seuil.focus:
                self.input_intervalle.focus = True
                return True
            elif self.input_intervalle.focus:
                self.input_seuil.focus = True
                return True
        return False

    def _focus_next(self, instance):
        """Passe au champ suivant (appelé sur Entrée dans seuil)."""
        self.input_intervalle.focus = True

    def _update_rect(self, instance, value):
        """Met à jour le rectangle de fond."""
        self.rect.pos = instance.pos
        self.rect.size = instance.size

    def on_cancel(self, instance):
        """Annulation."""
        Window.unbind(on_key_down=self._on_keyboard)
        self.dismiss()

    def on_validate(self, instance):
        """Validation des nouveaux paramètres."""
        try:
            seuil = float(self.input_seuil.text)
            intervalle = int(self.input_intervalle.text)

            if seuil <= 0 or intervalle <= 0:
                # TODO: Afficher message d'erreur
                return

            # Appeler le callback avec les nouvelles valeurs
            if self.callback:
                self.callback(seuil, intervalle)

            Window.unbind(on_key_down=self._on_keyboard)
            self.dismiss()
        except ValueError:
            # TODO: Afficher message d'erreur
            pass
