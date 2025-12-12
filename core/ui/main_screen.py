"""
Interface principale de l'application DriftApp.

VERSION 4.1 : Refactorisé pour lisibilité et maintenabilité.
Méthode de calcul : Abaque (mesures réelles sur site).
"""

from datetime import datetime
from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Container
from textual.screen import ModalScreen
from textual.widgets import Static, Input, Button, Header, Footer, Log, Label

from core.config.config_loader import DriftAppConfig, load_config
from core.hardware.hardware_detector import HardwareDetector
from core.hardware.moteur import MoteurCoupole
from core.hardware.moteur_simule import MoteurSimule
from core.observatoire import AstronomicalCalculations
from core.tracking.tracking_logger import TrackingLogger


# =============================================================================
# UTILITAIRES
# =============================================================================

class DualLogger:
    """Logger vers fichier et UI."""

    def __init__(self, base_dir: str = "logs"):
        Path(base_dir).mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = Path(base_dir) / f"textual_{ts}.log"
        self.f = open(self.log_file, "a", encoding="utf-8")

    def write(self, msg: str) -> str:
        """Écrit un message dans le fichier log."""
        self._ensure_file_open()
        try:
            self.f.write(msg + "\n")
            self.f.flush()
        except Exception as e:
            print(f"Erreur écriture log: {e}")
        return msg

    def _ensure_file_open(self):
        """Réouvre le fichier s'il a été fermé."""
        if self.f.closed:
            try:
                self.f = open(self.log_file, "a", encoding="utf-8")
            except Exception as e:
                print(f"Erreur réouverture log: {e}")

    def close(self):
        """Ferme le fichier log."""
        try:
            if not self.f.closed:
                self.f.close()
        except Exception:
            pass


def deg_to_dms(deg: float, is_latitude: bool = False) -> str:
    """
    Convertit degrés décimaux en format sexagésimal.

    Args:
        deg: Angle en degrés décimaux
        is_latitude: True pour ajouter signe + si positif

    Returns:
        Chaîne formatée "274°53'51"" ou "+52°55'17""
    """
    sign = ""
    if is_latitude and deg >= 0:
        sign = "+"
    elif deg < 0:
        sign = "-"
        deg = abs(deg)

    degrees = int(deg)
    minutes_dec = (deg - degrees) * 60
    minutes = int(minutes_dec)
    seconds = int((minutes_dec - minutes) * 60)

    return f'{sign}{degrees}°{minutes:02d}\'{seconds:02d}"'


# =============================================================================
# ÉCRAN DE CONFIGURATION
# =============================================================================


class ConfigScreenWithMethod(ModalScreen):
    """Écran de configuration (méthode abaque uniquement)."""

    CSS = """
    ConfigScreenWithMethod {
        align: center middle;
    }

    #config_dialog {
        width: 60;
        height: auto;
        border: thick $background 80%;
        background: $surface;
        padding: 1 2;
    }

    .config_row {
        height: auto;
        margin: 1 0;
    }

    #button_row {
        height: auto;
        align: center middle;
        margin-top: 1;
    }
    """

    def __init__(self, seuil: float, intervalle: int):
        super().__init__()
        self.seuil = seuil
        self.intervalle = intervalle

    def compose(self) -> ComposeResult:
        yield Container(
            Label("⚙️ Configuration", id="config_title"),

            Container(
                Label("Seuil de correction (degrés):"),
                Input(value=str(self.seuil), id="input_seuil"),
                classes="config_row"
            ),

            Container(
                Label("Intervalle entre corrections (secondes):"),
                Input(value=str(self.intervalle), id="input_intervalle"),
                classes="config_row"
            ),

            Horizontal(
                Button("Annuler", id="btn_cancel", variant="default"),
                Button("Valider", id="btn_ok", variant="success"),
                id="button_row"
            ),

            id="config_dialog"
        )

    async def on_button_pressed(self, event) -> None:
        if event.button.id == "btn_ok":
            try:
                seuil = float(self.query_one("#input_seuil", Input).value)
                intervalle = int(self.query_one("#input_intervalle", Input).value)

                if seuil <= 0 or intervalle <= 0:
                    raise ValueError("Valeurs invalides")

                self.dismiss((seuil, intervalle))
            except ValueError:
                # TODO: Afficher un message d'erreur
                pass
        else:
            self.dismiss(None)


class DriftApp(App):
    """Application principale avec support de l'abaque."""
    CSS = """
    /* Styles similaires à l'original, à adapter selon besoins */
    #hardware_info {
        background: $boost;
        color: $text;
        height: auto;
        padding: 0 1;
        text-align: center;
    }
    
    #input_container {
        height: auto;
        padding: 1;
    }
    
    #button_row {
        height: auto;
        align: center middle;
        padding: 1;
    }
    
    #status, #parallax_info, #method_info {
        background: $panel;
        height: auto;
        padding: 0 1;
        color: $text;
    }
    
    #log {
        height: 1fr;
        border: solid $primary;
    }
    """

    BINDINGS = [
        ("d", "start_tracking", "Démarrer"),
        ("s", "stop_tracking", "Stopper"),
        ("c", "config", "Configurer"),
        ("q", "quit", "Quitter"),
    ]

    def __init__(self, config: DriftAppConfig):
        super().__init__()
        self.config = config

        # Détection matériel
        self.is_production, self.hardware_info = HardwareDetector.detect_hardware()

        self.simulation = not self.is_production or config.simulation

        # Composants
        self.logger = TrackingLogger()
        self.dual_logger = DualLogger()

        # Créer calculateur
        self.calc = AstronomicalCalculations(
            config.site.latitude,
            config.site.longitude,
            config.site.tz_offset,
            config.geometrie.deport_tube_m,
            config.geometrie.rayon_coupole_m
        )

        self.tracking_session = None

        # Paramètres tracking depuis config
        self.seuil = config.tracking.seuil_correction_deg
        self.intervalle = config.tracking.intervalle_verification_sec
        self.enable_anticipation = config.tracking.enable_anticipation

        # Timers
        self._status_timer = None
        self._corr_timer = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(self._get_hardware_status(), id="hardware_info")

        yield Container(
            Static("Objet:", id="prompt"),
            Input(placeholder="Ex: M13, Vega, Jupiter, Eltanin", id="input_obj"),
            id="input_container"
        )

        yield Horizontal(
            Button("▶ Démarrer", id="btn_start", variant="success"),
            Button("⏹ Stopper", id="btn_stop", variant="error"),
            Button("⚙ Configurer", id="btn_config", variant="primary"),
            id="button_row"
        )

        yield Static("", id="method_info")
        yield Static("", id="status")
        yield Static("", id="parallax_info")
        yield Static("", id="adaptive_mode_display")

        yield Log(id="log")
        yield Footer()

    def on_mount(self) -> None:
        """Initialisation au démarrage."""
        self._log_startup_info()
        self._initialize_hardware()
        self._update_method_display()

    def _log_startup_info(self):
        """Affiche les informations de démarrage."""
        mode = "PRODUCTION" if self.is_production else "SIMULATION"
        self._append_log(f"=== MODE {mode} ===")

        if self.is_production:
            self._append_log(f"RPi: {self.hardware_info.get('rpi_model', 'Inconnu')} | GPIO: OK")
        else:
            self._append_log(
                f"Plateforme: {self.hardware_info['system']}/{self.hardware_info['machine']}"
            )

        self._append_log("")
        self._append_log("Méthode: ABAQUE (mesures réelles)")
        self._append_log("Procédure: Pointer > Centrer > Démarrer")
        self._append_log("")

    def _get_hardware_status(self) -> str:
        """Génère le résumé du statut matériel."""
        if self.is_production:
            return "PRODUCTION"
        else:
            return f"SIMULATION | {self.hardware_info['machine']}"

    def _initialize_hardware(self):
        """Initialise le matériel (moteur, calculs)."""
        # Calculs astronomiques
        self.calc = AstronomicalCalculations(
            latitude=self.config.site.latitude,
            longitude=self.config.site.longitude,
            tz_offset=self.config.site.tz_offset,
            deport_tube=self.config.geometrie.deport_tube_cm,
            rayon_coupole=self.config.geometrie.rayon_coupole_cm
        )

        # Stocker les configs
        self.motor_config = self.config.motor
        self.tracking_config = self.config.tracking

        # Initialiser le moteur avec valeurs depuis config
        # Utiliser self.simulation qui combine détection matérielle ET config
        if self.simulation:
            self.moteur = MoteurSimule()
            self._append_log("[SIM] Mode simulation activé (détection auto ou config)")
        else:
            try:
                # Passer tout le dictionnaire motor_config au constructeur
                self.moteur = MoteurCoupole(self.motor_config)
                self._append_log("[PROD] Moteur initialisé")
            except ValueError as e:
                print(f"❌ Erreur d'initialisation du moteur : {e}")
                print(f"Vérifiez les valeurs dans config.json['moteur']")
                raise

        # Utiliser les valeurs de tracking depuis config
        self.seuil = self.tracking_config.seuil_correction_deg
        self.intervalle = self.tracking_config.intervalle_verification_sec


    def _update_method_display(self):
        """Met à jour l'affichage de la configuration."""
        mode_str = "SIM" if self.simulation else "PROD"
        self.query_one("#method_info", Static).update(
            f"[{mode_str}] Méthode: ABAQUE (mesures réelles) | Seuil={self.seuil:.2f}° | Int={self.intervalle}s"
        )

    async def on_button_pressed(self, event) -> None:
        """Gestion des clics sur les boutons."""
        button_id = event.button.id

        if button_id == "btn_start":
            await self._handle_start()
        elif button_id == "btn_stop":
            await self._handle_stop()
        elif button_id == "btn_config":
            self._handle_config()

    async def _handle_start(self):
        """Démarrage du suivi."""

        if self.tracking_session and self.tracking_session.running:
            self._append_log("⚠️ Suivi déjà en cours.")
            return

        objet = self.query_one("#input_obj", Input).value.strip()
        if not objet:
            self._append_log("⚠️ Entrez un objet.")
            return

        # Import du tracker avec abaque
        from core.tracking import TrackingSession

        # Utiliser le logger de l'instance (déjà initialisé ligne 301)
        tracking_logger = self.logger

        # Créer session de suivi (méthode abaque uniquement)
        try:
            self.tracking_session = TrackingSession(
                self.moteur,
                self.calc,
                tracking_logger,
                seuil=self.seuil,
                intervalle=self.intervalle,
                abaque_file=self.config.tracking.abaque_file,
                enable_anticipation=self.enable_anticipation,
                adaptive_config=self.config.adaptive,
                motor_config=self.config.motor,
                encoder_config=self.config.encoder
            )
        except Exception as e:
            self._append_log(f"✗ Erreur d'initialisation: {e}")
            return

        # Démarrer
        success, msg = self.tracking_session.start(objet)

        if success:
            mode_str = "SIM" if self.simulation else "PROD"

            self._append_log("=" * 50)
            self._append_log(msg)
            self._append_log(
                f"Mode: {mode_str} | Méthode: ABAQUE | "
                f"Seuil={self.seuil:.2f}° | Intervalle={self.intervalle}s"
            )
            # self._append_log(
            #     f"Déport={self.config.geometrie.deport_tube_cm:.0f}cm | "
            #     f"Rayon={self.config.geometrie.rayon_coupole_cm:.0f}cm"
            # )
            self._append_log("=" * 50)

            # Démarrer les timers
            self._status_timer = self.set_interval(1, self._update_status)
            self._corr_timer = self.set_interval(self.intervalle, self._do_correction)
        else:
            self._append_log(f"✗ {msg}")

    async def _handle_stop(self):
        """Arrêt du suivi."""
        if not self.tracking_session or not self.tracking_session.running:
            self._append_log("⚠️ Aucun suivi en cours.")
            return

        # Logger avant d'arrêter (pour éviter problème de fichier fermé)
        self._append_log("⏹ Suivi arrêté")

        # TODO: Ajouter confirmation si besoin
        await self._stop_tracking()

    def _handle_config(self):
        """Ouverture de la fenêtre de configuration."""

        def handle_config(result):
            if result is not None:
                self.seuil, self.intervalle = result
                self._append_log(
                    f"⚙️ Config: Seuil={self.seuil:.2f}° | "
                    f"Intervalle={self.intervalle}s | "
                    f"Méthode=ABAQUE"
                )

                # Mettre à jour la session en cours si elle existe
                if self.tracking_session and not self.tracking_session.running:
                    # La méthode ne peut pas changer pendant le suivi
                    pass

                self._update_method_display()

        self.push_screen(
            ConfigScreenWithMethod(self.seuil, self.intervalle),
            handle_config
        )

    async def _stop_tracking(self):
        """Arrête le suivi et nettoie les ressources."""
        self._append_log("⏹ Arrêt du suivi...")

        # Arrêter les timers
        try:
            if self._status_timer:
                self._status_timer.stop()
            if self._corr_timer:
                self._corr_timer.stop()
        except Exception:
            pass
        finally:
            self._status_timer = None
            self._corr_timer = None

        # Arrêter la session
        if self.tracking_session:
            self.tracking_session.stop()

        # Fermer les logs
        try:
            self.dual_logger.close()
        except Exception:
            pass

        # Vider les zones d'affichage
        self.query_one("#status", Static).update("")
        self.query_one("#parallax_info", Static).update("")

    # =========================================================================
    # MISE À JOUR DU STATUT
    # =========================================================================

    def _update_status(self):
        """Met à jour le statut du suivi."""
        if not self.tracking_session or not self.tracking_session.running:
            return

        status = self.tracking_session.get_status()
        params = self.tracking_session.adaptive_manager.current_params

        status_line1 = self._format_status_line1(status, params)
        status_line2 = self._format_status_line2()

        self.query_one("#status", Static).update(status_line1)
        self.query_one("#parallax_info", Static).update(status_line2)

    def _format_status_line1(self, status: dict, params) -> str:
        """Formate la ligne 1 du statut (position, mode)."""
        mode_icons = {'normal': '🟢', 'critical': '🟠', 'continuous': '🔴'}
        mode_icon = mode_icons.get(params.mode.value, '⚪')
        pos_encoder = self._get_encoder_position()

        return (
            f"⏳ {status['remaining_seconds']}s | "
            f"Az={deg_to_dms(status['obj_az_raw'])} "
            f"Alt={deg_to_dms(status['obj_alt'], is_latitude=True)} "
            f"AzCoupole={status['position_cible']:.1f}° | "
            f"Enc={pos_encoder} | "
            f"{mode_icon} {params.mode.value.upper()} | "
            f"Int.:{params.check_interval}s"
        )

    def _format_status_line2(self) -> str:
        """Formate la ligne 2 du statut (stats)."""
        session = self.tracking_session
        return (
            f"ABAQUE | "
            f"AZCoupole={session.position_relative % 360:.1f}° | "
            f"Corrections: {session.total_corrections} "
            f"({session.total_movement:.1f}° total)"
        )

    def _get_encoder_position(self) -> str:
        """Lit la position de l'encodeur."""
        try:
            position = MoteurCoupole.get_daemon_angle()
            return f"{position:.1f}°"
        except RuntimeError:
            return "N/A"

    def _do_correction(self):
        """Effectue une correction si nécessaire."""
        if not self.tracking_session or not self.tracking_session.running:
            return

        try:
            # Récupérer le résultat ET le message détaillé
            correction_applied, log_msg = self.tracking_session.check_and_correct()

            # Afficher le message détaillé dans le TUI
            if log_msg:
                self._append_log(log_msg)

            # Ajuster l'intervalle si changé (comme avant)
            params = self.tracking_session.adaptive_manager.current_params
            if params.check_interval != self.intervalle:
                old_interval = self.intervalle
                self.intervalle = params.check_interval
                if self._corr_timer:
                    self._corr_timer.stop()
                self._corr_timer = self.set_interval(self.intervalle, self._do_correction)
                self._append_log(
                    f"🔄 Intervalle: {old_interval}s → {self.intervalle}s "
                    f"(mode {params.mode.value})"
                )
        except Exception as e:
            self._append_log(f"❌ Erreur correction: {e}")

    def _append_log(self, msg: str):
        """Ajoute un message aux logs (fichier + UI)."""
        self.dual_logger.write(msg)
        log_widget = self.query_one("#log", Log)
        try:
            log_widget.auto_scroll = True
        except Exception:
            pass
        log_widget.write(str(msg) + "\n")


    # Actions (appelées par les raccourcis clavier)
    async def action_start_tracking(self) -> None:
        """Action démarrer (touche 'd')."""
        await self._handle_start()

    async def action_stop_tracking(self) -> None:
        """Action arrêter (touche 's')."""
        await self._handle_stop()

    def action_config(self) -> None:
        """Action config (touche 'c')."""
        self._handle_config()


def main():
    """Lance l'application."""
    config = load_config()
    app = DriftApp(config)
    app.run()


if __name__ == "__main__":
    main()