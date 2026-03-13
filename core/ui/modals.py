"""
Fenêtres modales pour l'interface - VERSION AMÉLIORÉE.
Ajoute l'option d'activation de l'anticipation prédictive.
"""

from textual.app import ComposeResult
from textual.containers import Horizontal, Container
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Static, Input, Button, Checkbox


class ConfigScreen(ModalScreen):
    """Fenêtre modale pour les réglages - VERSION AMÉLIORÉE."""

    def __init__(self, seuil: float, intervalle: int, enable_anticipation: bool = True):
        super().__init__()
        self.seuil = seuil
        self.intervalle = intervalle
        self.enable_anticipation = enable_anticipation

    def compose(self) -> ComposeResult:
        yield Container(
            Static("⚙️ CONFIGURATION", id="config_title"),

            # Section paramètres de base
            Static("Seuil de correction (°) :", id="lbl_seuil_cfg"),
            Input(value=str(self.seuil), id="input_seuil_cfg"),

            Static("Intervalle de vérification (s) :", id="lbl_int_cfg"),
            Input(value=str(self.intervalle), id="input_intervalle_cfg"),

            # === NOUVEAU : Section anticipation ===
            Static(""),  # Espacement
            Static("Options avancées :", id="lbl_advanced_cfg"),

            Horizontal(
                Checkbox(
                    "✨ Anticipation prédictive (5 min)",
                    value=self.enable_anticipation,
                    id="checkbox_anticipation"
                ),
                id="anticipation_container"
            ),

            Static(
                "📖 L'anticipation prédit les mouvements futurs et commence\n"
                "   à corriger en avance pour lisser les grands déplacements.",
                id="anticipation_help"
            ),

            # Boutons
            Static(""),  # Espacement
            Horizontal(
                Button("✓ Valider", id="btn_cfg_ok", variant="success"),
                Button("✗ Annuler", id="btn_cfg_cancel", variant="error"),
                id="cfg_buttons"
            ),
            id="config_container"
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_cfg_ok":
            try:
                seuil_str = self.query_one("#input_seuil_cfg", Input).value.strip()
                intervalle_str = self.query_one("#input_intervalle_cfg", Input).value.strip()

                seuil = float(seuil_str)
                intervalle = int(intervalle_str)

                if seuil <= 0 or intervalle <= 0:
                    raise ValueError("Les valeurs doivent être positives")

                # Récupérer l'état de la checkbox
                checkbox_anticipation = self.query_one("#checkbox_anticipation", Checkbox)
                enable_anticipation = checkbox_anticipation.value

                # Retourner tous les paramètres
                self.dismiss((seuil, intervalle, enable_anticipation))

            except ValueError:
                pass
        elif event.button.id == "btn_cfg_cancel":
            self.dismiss(None)


class ConfirmStopScreen(ModalScreen):
    """Fenêtre de confirmation pour l'arrêt du suivi."""

    def compose(self) -> ComposeResult:
        yield Container(
            Static("⚠️ Voulez-vous vraiment arrêter le suivi ?", id="confirm_msg"),
            Horizontal(
                Button("✓ Oui", id="confirm_yes", variant="error"),
                Button("✗ Non", id="confirm_no", variant="primary"),
                id="confirm_buttons"
            ),
            id="confirm_container"
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm_yes":
            self.app.post_message(StopConfirmed())
            self.dismiss()
        elif event.button.id == "confirm_no":
            self.dismiss()


class StopConfirmed(Message):
    """Message émis quand l'utilisateur confirme l'arrêt."""
    pass