"""
Bandeau unifié combinant timer, boussole coupole, configuration et statut de tracking.
Layout 35/30/35 : Timer+MODE à gauche, Boussole au centre, cartouches à droite.

Refactorisé pour utiliser ThemedBox et Cartouche (élimination duplication).
"""

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.graphics import Color, RoundedRectangle
from kivy.properties import NumericProperty, StringProperty, BooleanProperty
from kivy.clock import Clock
from gui.widgets.timer_widget import TimerWidget
from gui.widgets.dome_compass import DomeCompass
from gui.widgets.themed_widgets import Cartouche, CartoucheHorizontal


class UnifiedBanner(BoxLayout):
    """
    Bandeau unifié affichant timer, boussole, configuration et statut.

    Layout:
    - Gauche 35% : Timer circulaire + MODE
    - Centre 30% : Boussole coupole + COUPOLE/POSITION
    - Droite 35% : (SEUIL/INTERVALLE) + (AZIMUT/ALTITUDE) + CORRECTIONS
    """

    # Propriétés configuration
    seuil = NumericProperty(0.1)
    intervalle = NumericProperty(30)

    # Propriétés statut
    azimut = NumericProperty(0)
    altitude = NumericProperty(0)
    coupole = NumericProperty(0)
    encodeur = StringProperty("N/A")
    mode = StringProperty("NORMAL")
    position = NumericProperty(0)
    corrections_nb = NumericProperty(0)
    corrections_total = NumericProperty(0)

    # Propriétés boussole
    dome_position_actuelle = NumericProperty(0)
    dome_position_cible = NumericProperty(0)

    def __init__(self, seuil=0.1, intervalle=30, **kwargs):
        super().__init__(**kwargs)

        self.seuil = seuil
        self.intervalle = intervalle

        self.orientation = 'horizontal'
        self.size_hint_y = None
        self.height = 240
        self.spacing = 10
        self.padding = [10, 8]

        # Fond du bandeau
        with self.canvas.before:
            Color(0.18, 0.2, 0.23, 1)
            self.bg_rect = RoundedRectangle(
                pos=self.pos,
                size=self.size,
                radius=[15]
            )
        self.bind(pos=self._update_bg, size=self._update_bg)

        # Partie gauche : Timer + MODE
        self._create_left_section()

        # Partie centrale : Boussole coupole
        self._create_center_section()

        # Partie droite : 2 colonnes + CORRECTIONS
        self._create_right_section()

    def _update_bg(self, *args):
        """Met à jour le fond."""
        self.bg_rect.pos = self.pos
        self.bg_rect.size = self.size

    def _create_left_section(self):
        """Section gauche : Timer circulaire + MODE."""
        left_container = BoxLayout(orientation='vertical', size_hint_x=0.35, spacing=4)

        # Timer circulaire (occupe l'essentiel de l'espace - augmenté)
        timer_box = BoxLayout(size_hint_y=0.82, padding=[0, 0])
        self.timer = TimerWidget()
        self.timer.intervalle = self.intervalle
        timer_box.add_widget(self.timer)
        left_container.add_widget(timer_box)

        # MODE (en dessous du timer - réduit)
        mode_box = BoxLayout(size_hint_y=0.18, padding=[10, 0])
        mode_inner = BoxLayout(orientation='vertical', padding=[8, 4], spacing=1)

        with mode_inner.canvas.before:
            self.mode_color = Color(0.2, 0.5, 0.3, 0.5)  # Vert par défaut
            self.mode_bg = RoundedRectangle(
                pos=mode_inner.pos,
                size=mode_inner.size,
                radius=[10]
            )
        mode_inner.bind(
            pos=lambda *args: setattr(self.mode_bg, 'pos', mode_inner.pos),
            size=lambda *args: setattr(self.mode_bg, 'size', mode_inner.size)
        )

        mode_title = Label(
            text="MODE",
            font_size='10sp',
            color=(0.7, 0.7, 0.7, 1),
            size_hint_y=0.35,
            bold=True
        )
        mode_inner.add_widget(mode_title)

        self.mode_label = Label(
            text="NORMAL",
            font_size='14sp',
            color=(1, 1, 1, 1),
            size_hint_y=0.65,
            bold=True
        )
        mode_inner.add_widget(self.mode_label)
        mode_box.add_widget(mode_inner)
        left_container.add_widget(mode_box)

        self.add_widget(left_container)

    def _create_center_section(self):
        """Section centrale : Boussole coupole + indicateur MERIDIEN + COUPOLE/POSITION."""
        center_container = BoxLayout(orientation='vertical', size_hint_x=0.30, spacing=4, padding=[10, 0])

        # Container pour boussole + indicateur MERIDIEN en overlay
        compass_container = BoxLayout(size_hint_y=0.82, padding=[0, 0])

        # Boussole coupole
        self.dome_compass = DomeCompass(size=(180, 180))
        compass_container.add_widget(self.dome_compass)

        center_container.add_widget(compass_container)

        # Indicateur MERIDIEN clignotant (au-dessus de la boussole, coin nord-ouest)
        self._create_meridien_indicator(center_container)

        # Deux cartouches TÉLESCOPE et COUPOLE en ligne (réduit)
        # TÉLESCOPE = position calculée du télescope (bouge en permanence) - à gauche, vert
        # COUPOLE = position réelle de la coupole (ne bouge que lors des corrections) - à droite, bleu
        positions_row = BoxLayout(orientation='horizontal', size_hint_y=0.18, spacing=4)

        # Cartouche TÉLESCOPE (position calculée, bouge en permanence) - vert, à gauche
        self.telescope_cartouche = Cartouche(
            title="TÉLESCOPE",
            value="0.0°",
            bg_color=(0.2, 0.7, 0.5, 0.3)
        )
        self.dome_telescope_label = self.telescope_cartouche.value_label
        positions_row.add_widget(self.telescope_cartouche)

        # Cartouche COUPOLE (position réelle, ne bouge que lors des corrections) - bleu, à droite
        self.coupole_cartouche = Cartouche(
            title="COUPOLE",
            value="0.0°",
            bg_color=(0.3, 0.5, 0.8, 0.3)
        )
        self.dome_coupole_label = self.coupole_cartouche.value_label
        positions_row.add_widget(self.coupole_cartouche)

        center_container.add_widget(positions_row)

        self.add_widget(center_container)

    def _create_right_section(self):
        """Section droite : SEUIL/INTERVALLE en haut, AZ/ALT en dessous, CORRECTIONS en bas."""
        right_container = BoxLayout(orientation='vertical', size_hint_x=0.35, spacing=6)

        # Ligne 1 : SEUIL et INTERVALLE côte à côte
        row1 = BoxLayout(orientation='horizontal', size_hint_y=0.33, spacing=4)
        col1_r1 = BoxLayout(orientation='vertical', spacing=4)
        self._create_threshold_cartouche(col1_r1)
        row1.add_widget(col1_r1)

        col2_r1 = BoxLayout(orientation='vertical', spacing=4)
        self._create_interval_cartouche(col2_r1)
        row1.add_widget(col2_r1)
        right_container.add_widget(row1)

        # Ligne 2 : AZ et ALT côte à côte
        row2 = BoxLayout(orientation='horizontal', size_hint_y=0.33, spacing=4)
        col1_r2 = BoxLayout(orientation='vertical', spacing=4)
        self._create_azimut_cartouche(col1_r2)
        row2.add_widget(col1_r2)

        col2_r2 = BoxLayout(orientation='vertical', spacing=4)
        self._create_altitude_cartouche(col2_r2)
        row2.add_widget(col2_r2)
        right_container.add_widget(row2)

        # Ligne 3 : CORRECTIONS sur toute la largeur
        self._create_corrections_cartouche(right_container)

        self.add_widget(right_container)

    def _create_threshold_cartouche(self, parent):
        """SEUIL - utilise CartoucheHorizontal."""
        cartouche = CartoucheHorizontal(
            title="SEUIL",
            value=f"{self.seuil:.2f}°",
            bg_color=(0.35, 0.5, 0.25, 0.3),
            icon_name="tool.png"
        )
        self.threshold_label = cartouche.value_label
        parent.add_widget(cartouche)

    def _create_interval_cartouche(self, parent):
        """INTERVALLE - utilise CartoucheHorizontal."""
        cartouche = CartoucheHorizontal(
            title="INTERVALLE",
            value=f"{self.intervalle}s",
            bg_color=(0.5, 0.35, 0.25, 0.3),
            icon_name="refresh.png"
        )
        self.interval_label = cartouche.value_label
        parent.add_widget(cartouche)

    def _create_azimut_cartouche(self, parent):
        """AZIMUT - utilise CartoucheHorizontal."""
        cartouche = CartoucheHorizontal(
            title="AZIMUT",
            value="0.0°",
            bg_color=(0.3, 0.6, 0.9, 0.3)
        )
        self.azimut_label = cartouche.value_label
        parent.add_widget(cartouche)

    def _create_altitude_cartouche(self, parent):
        """ALTITUDE - utilise CartoucheHorizontal."""
        cartouche = CartoucheHorizontal(
            title="ALTITUDE",
            value="0.0°",
            bg_color=(0.5, 0.4, 0.8, 0.3)
        )
        self.altitude_label = cartouche.value_label
        parent.add_widget(cartouche)

    def _create_corrections_cartouche(self, parent):
        """CORRECTIONS (toute la largeur) - cartouche personnalisé avec nombre et total séparés."""
        box = BoxLayout(size_hint_y=0.34, padding=[0, 4, 0, 0])

        # Conteneur avec fond coloré
        cartouche = BoxLayout(orientation='horizontal', padding=[8, 4], spacing=8)
        with cartouche.canvas.before:
            Color(0.7, 0.3, 0.5, 0.3)
            self._corrections_bg = RoundedRectangle(
                pos=cartouche.pos,
                size=cartouche.size,
                radius=[10]
            )
        cartouche.bind(pos=self._update_corrections_bg, size=self._update_corrections_bg)

        # Partie gauche : titre
        title_label = Label(
            text="CORRECTIONS",
            font_size='11sp',
            color=(0.7, 0.7, 0.7, 1),
            size_hint_x=0.4,
            halign='left',
            valign='middle'
        )
        title_label.bind(size=title_label.setter('text_size'))
        cartouche.add_widget(title_label)

        # Partie droite : nombre (gros) + total (petit)
        values_container = BoxLayout(orientation='horizontal', size_hint_x=0.6, spacing=10)

        # Nombre de corrections (gros)
        self.corrections_count_label = Label(
            text="0",
            font_size='20sp',
            bold=True,
            color=(1, 1, 1, 1),
            size_hint_x=0.4,
            halign='right',
            valign='middle'
        )
        self.corrections_count_label.bind(size=self.corrections_count_label.setter('text_size'))
        values_container.add_widget(self.corrections_count_label)

        # Total des corrections (plus petit, avec séparateur visuel)
        total_box = BoxLayout(orientation='horizontal', size_hint_x=0.6, spacing=4)

        separator = Label(
            text="|",
            font_size='14sp',
            color=(0.5, 0.5, 0.5, 1),
            size_hint_x=None,
            width=10
        )
        total_box.add_widget(separator)

        self.corrections_total_label = Label(
            text="0.00° total",
            font_size='12sp',
            color=(0.8, 0.8, 0.8, 1),
            halign='left',
            valign='middle'
        )
        self.corrections_total_label.bind(size=self.corrections_total_label.setter('text_size'))
        total_box.add_widget(self.corrections_total_label)

        values_container.add_widget(total_box)
        cartouche.add_widget(values_container)

        box.add_widget(cartouche)
        parent.add_widget(box)

    def _update_corrections_bg(self, instance, value):
        """Met à jour le fond du cartouche corrections."""
        self._corrections_bg.pos = instance.pos
        self._corrections_bg.size = instance.size

    def update_values(self, seuil=None, intervalle=None):
        """Met à jour les valeurs de configuration."""
        if seuil is not None:
            self.seuil = seuil
            self.threshold_label.text = f"{self.seuil:.2f}°"

        if intervalle is not None:
            self.intervalle = intervalle
            self.interval_label.text = f"{self.intervalle}s"
            self.timer.intervalle = intervalle
            # Réinitialiser le temps du timer au nouvel intervalle
            self.timer.temps = intervalle

    def update_status(self, azimut=None, altitude=None, coupole=None,
                     encodeur=None, mode=None, position=None,
                     corrections_nb=None, corrections_total=None):
        """Met à jour les valeurs de statut."""
        if azimut is not None:
            self.azimut = azimut
            self.azimut_label.text = f"{self.azimut:.2f}°"

        if altitude is not None:
            self.altitude = altitude
            self.altitude_label.text = f"{self.altitude:.2f}°"

        if coupole is not None:
            self.coupole = coupole
            # coupole = position cible, va dans TÉLESCOPE (bouge en permanence)
            self.dome_telescope_label.text = f"{self.coupole:.2f}°"

        if mode is not None:
            self.mode = mode
            mode_display = mode.split('.')[-1] if '.' in mode else mode
            self.mode_label.text = mode_display.upper()

            # Couleur dynamique
            mode_upper = mode_display.upper()
            if mode_upper == "NORMAL":
                self.mode_color.rgba = (0.2, 0.5, 0.3, 0.5)  # Vert
            elif mode_upper == "CRITICAL":
                self.mode_color.rgba = (0.6, 0.4, 0.2, 0.5)  # Orange
            elif mode_upper in ["CONTINU", "CONTINUOUS"]:
                self.mode_color.rgba = (0.9, 0.15, 0.15, 0.9)  # Rouge vif (attire l'attention)
            elif mode_upper == "FAST_TRACK":
                self.mode_color.rgba = (0.8, 0.2, 0.8, 0.9)  # Violet vif (vitesse max)
            else:
                self.mode_color.rgba = (0.4, 0.4, 0.4, 0.5)  # Gris

        if position is not None:
            self.position = position
            # position = position actuelle de la coupole (ne bouge que lors des corrections)
            self.dome_coupole_label.text = f"{self.position:.2f}°"

        if corrections_nb is not None and corrections_total is not None:
            self.corrections_nb = corrections_nb
            self.corrections_total = corrections_total
            self.corrections_count_label.text = str(self.corrections_nb)
            self.corrections_total_label.text = f"{self.corrections_total:.2f}° total"

    def update_timer(self, temps, intervalle=None):
        """Met à jour le timer circulaire."""
        self.timer.update_time(temps, intervalle)

    def update_dome_positions(self, position_actuelle=None, position_cible=None):
        """
        Met à jour les positions de la boussole coupole.

        Args:
            position_actuelle: Position actuelle de la coupole (degrés)
            position_cible: Position cible de la coupole (degrés)
        """
        if position_actuelle is not None:
            self.dome_position_actuelle = position_actuelle
            self.dome_compass.position_actuelle = position_actuelle
            # Pas besoin de mettre à jour dome_coupole_label ici,
            # c'est déjà fait dans update_status() avec le paramètre 'coupole'

        if position_cible is not None:
            self.dome_position_cible = position_cible
            self.dome_compass.position_cible = position_cible
            # Pas besoin de mettre à jour dome_position_label ici,
            # c'est déjà fait dans update_status() avec le paramètre 'position'

    # =========================================================================
    # INDICATEUR MERIDIEN CLIGNOTANT
    # =========================================================================

    def _create_meridien_indicator(self, parent):
        """
        Crée l'indicateur MERIDIEN clignotant rouge.
        Cet indicateur s'affiche lors d'un basculement de méridien.
        """
        # Container pour l'indicateur (initialement invisible)
        self.meridien_box = BoxLayout(
            size_hint=(None, None),
            size=(100, 28),
            pos_hint={'x': 0, 'top': 1}  # Coin nord-ouest
        )

        with self.meridien_box.canvas.before:
            self.meridien_bg_color = Color(0.9, 0.1, 0.1, 0)  # Rouge, invisible par défaut
            self.meridien_bg = RoundedRectangle(
                pos=self.meridien_box.pos,
                size=self.meridien_box.size,
                radius=[8]
            )
        self.meridien_box.bind(
            pos=lambda *args: setattr(self.meridien_bg, 'pos', self.meridien_box.pos),
            size=lambda *args: setattr(self.meridien_bg, 'size', self.meridien_box.size)
        )

        self.meridien_label = Label(
            text="MERIDIEN",
            font_size='11sp',
            color=(1, 1, 1, 0),  # Invisible par défaut
            bold=True
        )
        self.meridien_box.add_widget(self.meridien_label)

        # État du clignotement
        self._meridien_active = False
        self._meridien_blink_event = None
        self._meridien_visible = True

    def set_meridien_flip(self, active: bool):
        """
        Active ou désactive l'indicateur de basculement méridien.

        Args:
            active: True pour activer le clignotement, False pour désactiver
        """
        if active == self._meridien_active:
            return

        self._meridien_active = active

        if active:
            # Démarrer le clignotement
            self._meridien_visible = True
            self._update_meridien_visibility()
            self._meridien_blink_event = Clock.schedule_interval(
                self._blink_meridien, 0.5  # Clignote toutes les 500ms
            )
        else:
            # Arrêter le clignotement
            if self._meridien_blink_event:
                self._meridien_blink_event.cancel()
                self._meridien_blink_event = None
            # Masquer l'indicateur
            self.meridien_bg_color.a = 0
            self.meridien_label.color = (1, 1, 1, 0)

    def _blink_meridien(self, dt):
        """Fait clignoter l'indicateur MERIDIEN."""
        self._meridien_visible = not self._meridien_visible
        self._update_meridien_visibility()

    def _update_meridien_visibility(self):
        """Met à jour la visibilité de l'indicateur MERIDIEN."""
        if self._meridien_visible:
            self.meridien_bg_color.a = 0.9
            self.meridien_label.color = (1, 1, 1, 1)
        else:
            self.meridien_bg_color.a = 0.3
            self.meridien_label.color = (1, 1, 1, 0.3)
