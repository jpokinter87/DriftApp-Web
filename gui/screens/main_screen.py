"""
Écran principal - VERSION MODERNE ET COMPLÈTE.

Interface Kivy avec design amélioré et fonctionnalités complètes.
"""

from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.graphics import Color, Rectangle, RoundedRectangle, Line
from kivy.core.window import Window
from kivy.clock import Clock

from core.observatoire import AstronomicalCalculations
from core.tracking.tracking_logger import TrackingLogger
from core.hardware.moteur import MoteurCoupole
from core.hardware.moteur_simule import MoteurSimule
from core.observatoire.catalogue import GestionnaireCatalogue

from gui.widgets.config_popup import ConfigPopup
from gui.widgets.modern_button import ModernButton
from gui.widgets.unified_banner import UnifiedBanner
from gui.widgets.icon_button import IconButton
from gui.widgets.encoder_cartouche import EncoderCartouche
import os


class MainScreen(Screen):
    """
    Écran principal avec design moderne.
    """

    def __init__(self, config, **kwargs):
        super().__init__(**kwargs)
        self.config = config
        self.name = "main"

        # Initialisation des composants
        self._init_hardware_detection()
        self._init_tracking_params()
        self._init_business_components()
        self._init_state()

        # Construction de l'interface
        layout = self._create_main_layout()
        layout.add_widget(self._create_header())
        layout.add_widget(self._create_object_input_row())
        layout.add_widget(self._create_button_row())
        layout.add_widget(self._create_manual_control_row())  # Touches < II > pour contrôle manuel
        layout.add_widget(self._create_unified_banner())
        layout.add_widget(self._create_log_zone())

        # Initialiser le matériel
        self._initialize_hardware()

        # Ajouter logs bufferisés
        self._flush_log_buffer()

        layout.add_widget(self._create_footer())
        self.add_widget(layout)

        # Raccourcis clavier
        Window.bind(on_key_down=self._on_keyboard)

        # Focus sur le champ Objet au démarrage
        Clock.schedule_once(lambda dt: setattr(self.input_obj, 'focus', True), 0.3)

    # ========================================================================
    # INITIALISATION
    # ========================================================================

    def _init_hardware_detection(self):
        """Détecte le matériel disponible."""
        from core.hardware.hardware_detector import HardwareDetector
        self.is_production, self.hardware_info = HardwareDetector.detect_hardware()
        self.simulation = not self.is_production or self.config.simulation

    def _init_tracking_params(self):
        """Initialise les paramètres de tracking."""
        self.seuil = self.config.tracking.seuil_correction_deg
        self.intervalle = self.config.tracking.intervalle_verification_sec

    def _init_business_components(self):
        """Initialise les composants métier."""
        self.logger = TrackingLogger()
        self.catalogue = GestionnaireCatalogue()
        self.calc = AstronomicalCalculations(
            self.config.site.latitude,
            self.config.site.longitude,
            self.config.site.tz_offset,
            self.config.geometrie.deport_tube_m,
            self.config.geometrie.rayon_coupole_m
        )

    def _init_state(self):
        """Initialise l'état de l'application."""
        self.tracking_session = None
        self.current_object_info = None
        self._status_timer = None
        self._corr_timer = None
        self._log_buffer = []
        self._input_has_focus = False

    # ========================================================================
    # CRÉATION DE L'INTERFACE
    # ========================================================================

    def _create_main_layout(self):
        """Crée le layout principal avec fond sombre."""
        layout = BoxLayout(orientation='vertical', padding=10, spacing=8)
        with layout.canvas.before:
            Color(0.12, 0.13, 0.16, 1)
            self.rect = Rectangle(size=layout.size, pos=layout.pos)
        layout.bind(size=self._update_rect, pos=self._update_rect)
        return layout

    def _create_header(self):
        """Crée le header avec nom observatoire et statut production/simulation."""
        # Récupérer le nom de l'observatoire depuis la config
        obs_name = getattr(self.config.site, 'nom', 'Observatoire')

        if self.is_production:
            status_text = f"{obs_name} | PRODUCTION | {self.hardware_info.get('rpi_model', 'RPi')}"
            status_color = (0.3, 1, 0.3, 1)  # Vert
        else:
            status_text = f"{obs_name} | SIMULATION | {self.hardware_info['machine']}"
            status_color = (1, 0.7, 0.3, 1)  # Orange

        return Label(
            text=status_text,
            size_hint_y=None,
            height=22,
            font_size='12sp',
            color=status_color,
            bold=True
        )

    def _create_object_input_row(self):
        """Crée la ligne de saisie d'objet avec RA/DEC et encodeur."""
        obj_container = BoxLayout(orientation='horizontal', size_hint_y=None, height=48, spacing=8)

        # Label "Objet:"
        obj_label = Label(
            text="Objet:",
            size_hint_x=None,
            width=80,
            font_size='18sp',
            color=(1, 1, 1, 1),
            bold=True
        )
        obj_container.add_widget(obj_label)

        # Input avec fond arrondi
        obj_container.add_widget(self._create_object_input())

        # Zone RA/DEC
        self.radec_label = Label(
            text="",
            size_hint_x=0.3,
            font_size='14sp',
            color=(0.5, 1, 0.5, 1),
            halign='left',
            valign='middle',
            markup=True,
            bold=True
        )
        self.radec_label.bind(size=self.radec_label.setter('text_size'))
        obj_container.add_widget(self.radec_label)

        # Cartouche encodeur
        encoder_box = BoxLayout(size_hint_x=0.15, padding=[0, 7])
        self.encoder_cartouche = EncoderCartouche()
        encoder_box.add_widget(self.encoder_cartouche)
        obj_container.add_widget(encoder_box)

        return obj_container

    def _create_object_input(self):
        """Crée le champ de saisie d'objet avec fond arrondi."""
        input_wrapper = BoxLayout(size_hint_x=0.55, padding=[0, 0])
        with input_wrapper.canvas.before:
            Color(0.2, 0.22, 0.25, 1)
            self.input_bg = RoundedRectangle(
                pos=input_wrapper.pos,
                size=input_wrapper.size,
                radius=[12]
            )
        input_wrapper.bind(
            pos=lambda *args: setattr(self.input_bg, 'pos', input_wrapper.pos),
            size=lambda *args: setattr(self.input_bg, 'size', input_wrapper.size)
        )

        self.input_obj = TextInput(
            hint_text="Ex: M13, Vega, Jupiter, Eltanin",
            size_hint_x=1,
            font_size='16sp',
            multiline=False,
            background_color=(0, 0, 0, 0),  # Transparent, fond géré par le wrapper
            foreground_color=(1, 1, 1, 1),
            cursor_color=(0.5, 1, 0.5, 1),
            padding=[12, 10]  # Padding réduit pour s'adapter à la hauteur
        )
        self.input_obj.bind(on_text_validate=self.on_input_enter)
        self.input_obj.bind(focus=self._on_input_focus)
        input_wrapper.add_widget(self.input_obj)

        return input_wrapper

    def _create_button_row(self):
        """Crée la ligne de boutons (Démarrer, Stopper, Configurer)."""
        button_row = BoxLayout(orientation='horizontal', size_hint_y=None, height=68, spacing=12)
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons')

        # Démarrer
        self.btn_start = IconButton(
            text="DÉMARRER",
            icon_source=os.path.join(icon_path, 'play.png'),
            bg_color=[0.15, 0.4, 0.2, 1],  # Vert foncé (ambiance observatoire)
            radius=18
        )
        self.btn_start.bind(on_press=self.on_start)
        button_row.add_widget(self.btn_start)

        # Stopper
        self.btn_stop = IconButton(
            text="STOPPER",
            icon_source=os.path.join(icon_path, 'stop.png'),
            bg_color=[0.4, 0.15, 0.15, 1],  # Rouge foncé
            radius=18
        )
        self.btn_stop.bind(on_press=self.on_stop)
        button_row.add_widget(self.btn_stop)

        # Configurer
        self.btn_config = IconButton(
            text="CONFIGURER",
            icon_source=os.path.join(icon_path, 'settings.png'),
            bg_color=[0.2, 0.3, 0.5, 1],  # Bleu foncé
            radius=18
        )
        self.btn_config.bind(on_press=self.on_config)
        button_row.add_widget(self.btn_config)

        return button_row

    def _create_manual_control_row(self):
        """Crée la ligne de contrôle manuel < II > (gauche, stop, droite) centrée.

        Comportement TOGGLE : un appui simple démarre la rotation,
        un autre appui sur le même bouton ou sur STOP l'arrête.
        """
        # Container externe pour centrer les boutons
        outer_row = BoxLayout(orientation='horizontal', size_hint_y=None, height=48, spacing=0)

        # État du contrôle manuel
        self._manual_control_active = False
        self._manual_direction = 0  # -1 = gauche, 0 = stop, 1 = droite

        # Spacer gauche (pour centrer)
        outer_row.add_widget(BoxLayout(size_hint_x=0.2))

        # Container central pour les 3 boutons
        control_row = BoxLayout(orientation='horizontal', size_hint_x=0.6, spacing=6)

        # Bouton < (rotation anti-horaire) - ModernButton avec coins arrondis
        self.btn_manual_left = ModernButton(
            text="<",
            font_size='24sp',
            size_hint_x=0.3,
            bg_color=[0.25, 0.25, 0.45, 1],
            radius=12
        )
        self.btn_manual_left.bind(on_press=self._on_manual_left_toggle)
        control_row.add_widget(self.btn_manual_left)

        # Bouton II (stop) - ModernButton avec coins arrondis
        self.btn_manual_stop = ModernButton(
            text="II",
            font_size='20sp',
            size_hint_x=0.4,
            bg_color=[0.5, 0.18, 0.18, 1],
            radius=12
        )
        self.btn_manual_stop.bind(on_press=self._on_manual_stop)
        control_row.add_widget(self.btn_manual_stop)

        # Bouton > (rotation horaire) - ModernButton avec coins arrondis
        self.btn_manual_right = ModernButton(
            text=">",
            font_size='24sp',
            size_hint_x=0.3,
            bg_color=[0.25, 0.25, 0.45, 1],
            radius=12
        )
        self.btn_manual_right.bind(on_press=self._on_manual_right_toggle)
        control_row.add_widget(self.btn_manual_right)

        outer_row.add_widget(control_row)

        # Spacer droite (pour centrer)
        outer_row.add_widget(BoxLayout(size_hint_x=0.2))

        return outer_row

    def _on_manual_left_toggle(self, instance):
        """Toggle la rotation manuelle vers la gauche (anti-horaire)."""
        if self._manual_control_active and self._manual_direction == -1:
            # Déjà en rotation gauche → stopper
            self._stop_manual_rotation()
            self.append_log("[color=FFA500]Rotation manuelle: STOP[/color]")
        else:
            # Arrêter toute rotation précédente et démarrer gauche
            if self._manual_control_active:
                self._stop_manual_rotation()
            self._manual_direction = -1
            self._start_manual_rotation(-1)
            self.append_log("[color=00FFFF]Rotation manuelle: GAUCHE (anti-horaire)[/color]")

    def _on_manual_right_toggle(self, instance):
        """Toggle la rotation manuelle vers la droite (horaire)."""
        if self._manual_control_active and self._manual_direction == 1:
            # Déjà en rotation droite → stopper
            self._stop_manual_rotation()
            self.append_log("[color=FFA500]Rotation manuelle: STOP[/color]")
        else:
            # Arrêter toute rotation précédente et démarrer droite
            if self._manual_control_active:
                self._stop_manual_rotation()
            self._manual_direction = 1
            self._start_manual_rotation(1)
            self.append_log("[color=00FFFF]Rotation manuelle: DROITE (horaire)[/color]")

    def _on_manual_stop(self, instance):
        """Arrêt de la rotation manuelle."""
        if self._manual_control_active:
            self._stop_manual_rotation()
            self.append_log("[color=FFA500]Rotation manuelle: STOP[/color]")

    def _start_manual_rotation(self, direction: int):
        """
        Démarre la rotation manuelle en continu dans un thread dédié.

        IMPORTANT: Utilise un thread pour garantir un flux continu de pas
        comme calibration_moteur.py. Clock.schedule_interval créait des
        discontinuités (bursts de pas) qui causaient des vibrations.

        Args:
            direction: 1 pour horaire, -1 pour anti-horaire
        """
        import threading

        self._manual_control_active = True

        # Utiliser la vitesse FAST_TRACK pour le contrôle manuel
        if hasattr(self, 'moteur') and self.moteur:
            # Obtenir le délai moteur depuis la config
            # Utiliser 0.00022s = ~42°/min (recommandation max utilisateur)
            fast_track_delay = 0.00022
            if hasattr(self.config, 'adaptive') and self.config.adaptive:
                fast_track_mode = self.config.adaptive.modes.get('fast_track')
                if fast_track_mode:
                    fast_track_delay = fast_track_mode.motor_delay

            # Définir la direction une seule fois
            self.moteur.definir_direction(direction)

            # Lancer le thread de rotation continue
            self._manual_rotation_thread = threading.Thread(
                target=self._manual_rotation_loop,
                args=(direction, fast_track_delay),
                daemon=True
            )
            self._manual_rotation_thread.start()

            # Démarrer la mise à jour de l'affichage pendant la rotation manuelle
            self._manual_display_event = Clock.schedule_interval(
                self._update_manual_display, 0.1  # Rafraîchir toutes les 100ms
            )

    def _manual_rotation_loop(self, direction: int, delay: float):
        """
        Boucle de rotation manuelle dans un thread dédié.

        Identique à calibration_moteur.py : flux continu de pas sans discontinuité.
        """
        if not hasattr(self, 'moteur') or not self.moteur:
            return

        try:
            while self._manual_control_active:
                self.moteur.faire_un_pas(delay)
        except Exception as e:
            # Utiliser Clock.schedule_once pour appeler depuis le thread principal
            Clock.schedule_once(
                lambda dt: self.append_log(f"[color=FF0000]Erreur rotation manuelle: {e}[/color]"),
                0
            )
            Clock.schedule_once(lambda dt: self._stop_manual_rotation(), 0)

    def _stop_manual_rotation(self):
        """Arrête la rotation manuelle."""
        self._manual_control_active = False
        self._manual_direction = 0

        if hasattr(self, '_manual_rotation_event') and self._manual_rotation_event:
            self._manual_rotation_event.cancel()
            self._manual_rotation_event = None

        # Arrêter la mise à jour de l'affichage
        if hasattr(self, '_manual_display_event') and self._manual_display_event:
            self._manual_display_event.cancel()
            self._manual_display_event = None

        # Demander l'arrêt au moteur si disponible
        if hasattr(self, 'moteur') and self.moteur:
            self.moteur.request_stop()

    def _update_manual_display(self, dt):
        """Met à jour l'affichage pendant la rotation manuelle."""
        try:
            # Récupérer la position simulée
            if self.simulation:
                position = MoteurSimule.get_daemon_angle()
            else:
                position = MoteurCoupole.get_daemon_angle()

            # Mettre à jour la boussole et l'affichage de position
            self.unified_banner.update_dome_positions(
                position_actuelle=position,
                position_cible=position  # En mode manuel, pas de cible
            )

            # Mettre à jour le cartouche encodeur si disponible
            if hasattr(self, 'encoder_cartouche'):
                self.encoder_cartouche.update_value(f"{position:.1f}°")

        except Exception as e:
            print(f"[MANUAL] Erreur mise à jour affichage: {e}")

    def _create_unified_banner(self):
        """Crée le bandeau unifié (Timer + Config + Statut)."""
        self.unified_banner = UnifiedBanner(
            seuil=self.seuil,
            intervalle=self.intervalle
        )
        return self.unified_banner

    def _create_log_zone(self):
        """Crée la zone de logs avec titre et scroll."""
        log_container = BoxLayout(orientation='vertical', spacing=0)

        # Titre
        log_title = Label(
            text="Logs de tracking",
            size_hint_y=None,
            height=30,
            font_size='15sp',
            color=(0.7, 0.9, 1, 1),
            bold=True,
            halign='left',
            valign='middle'
        )
        log_title.bind(size=log_title.setter('text_size'))
        log_container.add_widget(log_title)

        # ScrollView avec label de logs
        self.log_scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        self.log_label = Label(
            text=self._get_initial_logs(),
            size_hint_y=None,
            font_size='13sp',
            color=(0.9, 0.9, 0.9, 1),
            halign='left',
            valign='top',
            markup=True,
            padding=[10, 10]
        )
        self.log_label.bind(texture_size=self._update_log_size)
        self.log_label.text_size = (Window.width - 40, None)
        self.log_scroll.add_widget(self.log_label)
        log_container.add_widget(self.log_scroll)

        return log_container

    def _create_footer(self):
        """Crée le footer avec les raccourcis clavier."""
        return Label(
            text="Raccourcis: [d] Démarrer | [s] Stopper | [c] Configurer | [q] Quitter | [Entrée] dans le champ = Démarrer",
            size_hint_y=None,
            height=28,
            font_size='11sp',
            color=(0.5, 0.5, 0.6, 1),
            italic=True
        )

    def _flush_log_buffer(self):
        """Ajoute les logs bufferisés au label."""
        for log_msg in self._log_buffer:
            self.log_label.text += f"\n{log_msg}"
        self._log_buffer = []

    def _update_rect(self, instance, value):
        self.rect.pos = instance.pos
        self.rect.size = instance.size

    def _initialize_hardware(self):
        """Initialise le matériel."""
        if self.simulation:
            self.moteur = MoteurSimule(self.config.motor)
            self.append_log("[SIM] Mode simulation activé")
        else:
            try:
                self.moteur = MoteurCoupole(self.config.motor)
                self.append_log("[PROD] Moteur initialisé")
            except ValueError as e:
                self.append_log(f"[color=FF0000]Erreur moteur : {e}[/color]")
                raise

    def _get_initial_logs(self):
        """Logs initiaux."""
        mode = "PRODUCTION" if self.is_production else "SIMULATION"

        logs = f"""[color=00FF00]=== MODE {mode} ===[/color]

[color=FFA500]Méthode de calcul :[/color]
  ABAQUE (mesures réelles sur site)

[color=FFFF00]Procédure :[/color]
  1. Pointez le télescope sur l'objet
  2. Centrez manuellement la trappe sur le tube
  3. Saisissez le nom de l'objet et appuyez sur Entrée
  4. Le suivi démarre automatiquement

"""
        return logs

    def append_log(self, msg):
        """Ajoute un message aux logs."""
        # Debug : afficher dans la console
        print(f"[GUI LOG] {msg}")

        if hasattr(self, 'log_label'):
            # Ajouter le message aux logs
            current_text = self.log_label.text
            self.log_label.text = current_text + f"\n{msg}"

            # Forcer la mise à jour de la taille du label
            self.log_label.texture_update()

            # Auto-scroll vers le bas pour voir les nouveaux logs
            Clock.schedule_once(lambda dt: self._scroll_to_bottom(), 0.05)
        else:
            self._log_buffer.append(msg)

    def _update_log_size(self, instance, value):
        """Met à jour la hauteur du label de logs."""
        instance.height = value[1]

    def _scroll_to_bottom(self):
        """Scroll automatique vers le bas des logs."""
        if hasattr(self, 'log_scroll'):
            self.log_scroll.scroll_y = 0  # 0 = bas, 1 = haut

    def _on_keyboard(self, window, key, scancode, codepoint, modifier):
        """Raccourcis clavier."""
        # Désactiver raccourcis si le champ input objet a le focus
        if self._input_has_focus:
            return False

        # Traiter uniquement les raccourcis définis, laisser passer le reste
        if codepoint == 'd':
            self.on_start(None)
            return True
        elif codepoint == 's':
            self.on_stop(None)
            return True
        elif codepoint == 'c':
            self.on_config(None)
            return True
        elif codepoint == 'q':
            from kivy.app import App
            App.get_running_app().stop()
            return True

        # Pour toutes les autres touches (backspace, delete, chiffres, etc.)
        # retourner False pour les laisser passer aux widgets
        return False

    def _on_input_focus(self, instance, value):
        """Gère le focus du champ objet pour désactiver les raccourcis."""
        self._input_has_focus = value

    def _on_input_wrapper_touch(self, instance, touch):
        """
        Fix pour écran tactile : maintient le focus sur le champ de saisie
        quand l'utilisateur touche dans la zone du wrapper.

        Le problème sur écran tactile est que le focus est perdu quand
        l'utilisateur touche ailleurs puis revient sur le champ.
        Cette méthode force le maintien du focus.
        """
        if instance.collide_point(*touch.pos):
            # L'utilisateur touche dans la zone du champ de saisie
            # Forcer le focus et empêcher la perte de focus
            if not self.input_obj.focus:
                # Donner le focus immédiatement
                self.input_obj.focus = True
            # Maintenir le focus même si l'utilisateur garde le doigt appuyé
            # en utilisant un schedule pour le ré-appliquer après le traitement touch
            Clock.schedule_once(lambda dt: self._ensure_input_focus(), 0.1)
            return True  # Consommer l'événement pour éviter la propagation
        return False

    def _ensure_input_focus(self):
        """S'assure que le champ de saisie garde le focus."""
        if hasattr(self, 'input_obj') and self.input_obj:
            self.input_obj.focus = True

    def on_input_enter(self, instance):
        """Entrée → Démarrer."""
        self.on_start(None)

    def search_and_display_object(self, objet_name):
        """Recherche et affiche l'objet."""
        result = self.catalogue.rechercher(objet_name)

        if not result or 'ra_deg' not in result or 'dec_deg' not in result:
            self.radec_label.text = ""
            self.current_object_info = None
            return False, f"Objet '{objet_name}' introuvable"

        self.current_object_info = result

        nom = result.get('nom', objet_name)
        ra_deg = result['ra_deg']
        dec_deg = result['dec_deg']
        obj_type = result.get('type', 'Unknown')

        # Afficher uniquement RA et DEC dans la zone à droite
        info_text = f"RA: {ra_deg:.2f}° | DEC: {dec_deg:.2f}°"
        self.radec_label.text = info_text

        self.append_log(f"[color=00FF00]Objet trouvé : {nom}[/color]")
        self.append_log(f"  Type: {obj_type} | RA={ra_deg:.2f}° | DEC={dec_deg:.2f}°")

        return True, result

    def on_start(self, instance):
        """Démarrage du suivi."""
        if self.tracking_session and self.tracking_session.running:
            self.append_log("[color=FFA500]Suivi déjà en cours.[/color]")
            return

        objet = self.input_obj.text.strip()
        if not objet:
            self.append_log("[color=FF0000]Entrez un objet.[/color]")
            return

        # Rechercher l'objet
        self.append_log(f"[color=00FFFF]Recherche de '{objet}'...[/color]")
        success, result = self.search_and_display_object(objet)

        if not success:
            self.append_log(f"[color=FF0000]{result}[/color]")
            return

        # Créer session
        from core.tracking import TrackingSession

        try:
            self.tracking_session = TrackingSession(
                self.moteur,
                self.calc,
                self.logger,
                seuil=self.seuil,
                intervalle=self.intervalle,
                abaque_file=self.config.tracking.abaque_file,
                adaptive_config=self.config.adaptive,
                motor_config=self.config.motor,
                encoder_config=self.config.encoder
            )
        except Exception as e:
            self.append_log(f"[color=FF0000]Erreur : {e}[/color]")
            import traceback
            traceback.print_exc()
            return

        # Démarrer
        success_start, msg = self.tracking_session.start(objet)

        if success_start:
            mode_str = "SIM" if self.simulation else "PROD"

            self.append_log("[color=00FF00]" + "=" * 50 + "[/color]")
            self.append_log(f"[color=00FF00]{msg}[/color]")
            self.append_log(
                f"Mode: {mode_str} | Méthode: ABAQUE | "
                f"Seuil={self.seuil:.2f}° | Intervalle={self.intervalle}s"
            )
            self.append_log("[color=00FF00]" + "=" * 50 + "[/color]")

            # Timers
            self._status_timer = Clock.schedule_interval(self._update_status, 1)
            self._corr_timer = Clock.schedule_interval(self._do_correction, self.intervalle)
        else:
            self.append_log(f"[color=FF0000]{msg}[/color]")

    def on_stop(self, instance):
        """Arrêt du suivi."""
        if not self.tracking_session or not self.tracking_session.running:
            self.append_log("[color=FFA500]Aucun suivi en cours.[/color]")
            return

        self.append_log("[color=FFA500]Suivi arrêté[/color]")
        self._stop_tracking()

    def _stop_tracking(self):
        """Arrête le suivi."""
        if self._status_timer:
            self._status_timer.cancel()
            self._status_timer = None
        if self._corr_timer:
            self._corr_timer.cancel()
            self._corr_timer = None

        if self.tracking_session:
            # Demander l'arrêt de la boucle feedback en cours (non bloquant)
            if hasattr(self.tracking_session, 'moteur') and self.tracking_session.moteur:
                self.tracking_session.moteur.request_stop()

            self.tracking_session.stop()

    def _update_status(self, dt):
        """Mise à jour statut."""
        if not self.tracking_session or not self.tracking_session.running:
            return

        session = self.tracking_session
        params = session.adaptive_manager.current_params
        status = session.get_status()

        # Position encodeur (utilise le moteur approprié selon le mode)
        try:
            if self.simulation:
                from core.hardware.moteur_simule import MoteurSimule
                position = MoteurSimule.get_daemon_angle()
            else:
                position = MoteurCoupole.get_daemon_angle()
            pos_encoder = f"{position:.2f}°"
        except RuntimeError:
            position = None
            pos_encoder = "N/A"

        # Mettre à jour le bandeau unifié (statut + timer)
        self.unified_banner.update_status(
            azimut=float(status['obj_az_raw']),
            altitude=float(status['obj_alt']),
            coupole=float(status['position_cible']),
            encodeur=pos_encoder,
            mode=params.mode.value,
            position=float(session.position_relative % 360),
            corrections_nb=int(session.total_corrections),
            corrections_total=float(session.total_movement)
        )

        # Mettre à jour l'indicateur MERIDIEN (grands déplacements >30°)
        is_large_movement = status.get('is_large_movement', False)
        is_fast_track = params.mode.value == 'fast_track'
        self.unified_banner.set_meridien_flip(is_large_movement or is_fast_track)

        # Mettre à jour le timer circulaire avec intervalle actuel
        self.unified_banner.update_timer(
            int(status['remaining_seconds']),
            intervalle=params.check_interval
        )

        # Mettre à jour la boussole coupole
        # position_actuelle = position actuelle de la coupole (session.position_relative)
        # position_cible = position théorique où elle devrait être
        self.unified_banner.update_dome_positions(
            position_actuelle=float(session.position_relative % 360),
            position_cible=float(status['position_cible'])
        )

    def _do_correction(self, dt):
        """Correction."""
        if not self.tracking_session or not self.tracking_session.running:
            return

        try:
            correction_applied, log_msg = self.tracking_session.check_and_correct()

            if log_msg:
                self.append_log(log_msg)

            # Ajuster intervalle
            params = self.tracking_session.adaptive_manager.current_params
            if params.check_interval != self.intervalle:
                old_interval = self.intervalle
                self.intervalle = params.check_interval

                if self._corr_timer:
                    self._corr_timer.cancel()
                self._corr_timer = Clock.schedule_interval(self._do_correction, self.intervalle)

                self.append_log(
                    f"[color=00FFFF]Intervalle: {old_interval}s -> {self.intervalle}s "
                    f"(mode {params.mode.value})[/color]"
                )
        except Exception as e:
            self.append_log(f"[color=FF0000]Erreur: {e}[/color]")
            import traceback
            traceback.print_exc()

    def on_config(self, instance):
        """Configuration."""
        popup = ConfigPopup(
            seuil_actuel=self.seuil,
            intervalle_actuel=self.intervalle,
            callback=self._on_config_validated
        )
        popup.open()

    def _on_config_validated(self, seuil, intervalle):
        """Validation config."""
        old_seuil = self.seuil
        old_intervalle = self.intervalle

        self.seuil = seuil
        self.intervalle = intervalle

        # Mettre à jour le bandeau unifié
        self.unified_banner.update_values(seuil=self.seuil, intervalle=self.intervalle)

        self.append_log(
            f"[color=00FFFF]Configuration mise à jour:[/color]\n"
            f"  Seuil: {old_seuil:.2f}° -> {self.seuil:.2f}°\n"
            f"  Intervalle: {old_intervalle}s -> {self.intervalle}s"
        )

        if self.tracking_session and self.tracking_session.running:
            if self._corr_timer:
                self._corr_timer.cancel()
            self._corr_timer = Clock.schedule_interval(self._do_correction, self.intervalle)
            self.append_log(f"[color=FFA500]  Timer recréé ({self.intervalle}s)[/color]")

        # Restaurer le focus sur le champ Objet après fermeture du popup
        Clock.schedule_once(lambda dt: setattr(self.input_obj, 'focus', True), 0.2)
