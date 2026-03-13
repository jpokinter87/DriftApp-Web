"""
Application Kivy principale pour DriftApp GUI.
"""

from kivy.app import App
from kivy.uix.screenmanager import ScreenManager
from kivy.config import Config

from gui.screens.main_screen import MainScreen
from gui.screens.status_screen import StatusScreen
from core.observatoire.catalogue import GestionnaireCatalogue


class DriftAppGUI(App):
    """
    Application graphique Kivy pour le suivi de coupole.

    Architecture :
    - ScreenManager pour navigation entre écrans
    - Partage du code métier (core/) avec l'interface Textual
    - Optimisé pour écran tactile
    """

    def __init__(self, config, **kwargs):
        super().__init__(**kwargs)
        self.config_data = config

    def build(self):
        """Construit l'interface graphique."""
        # Configuration Kivy pour écran tactile
        Config.set('graphics', 'fullscreen', 'auto')
        Config.set('input', 'mouse', 'mouse,multitouch_on_demand')

        # Gestionnaire d'écrans
        sm = ScreenManager()

        # Ajouter les écrans
        sm.add_widget(MainScreen(self.config_data, name='main'))
        sm.add_widget(StatusScreen(name='status'))

        # TODO: Ajouter écran de tracking
        # sm.add_widget(TrackingScreen(name='tracking'))

        return sm

    def on_stop(self):
        """Nettoyage à la fermeture."""
        print("Fermeture de l'application GUI")
        return True