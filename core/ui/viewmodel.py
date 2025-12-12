import logging
from datetime import datetime
from typing import Dict, Any

from core.tracking.adaptive_tracking import TrackingMode

logger = logging.getLogger("ViewModel")


class TrackingViewModel:
    """
    Classe responsable de la mise en forme des données brutes du Tracker
    pour l'affichage UI (formatage, icônes, couleurs).

    Elle sépare la logique de formatage (Vue) de la logique métier (Tracker).
    """

    @staticmethod
    def format_status_for_ui(status_data: Dict[str, Any]) -> Dict[str, str]:
        """
        Prend les données brutes de TrackingSession.get_status() et retourne
        un dictionnaire prêt à être affiché par les widgets de l'UI.
        """
        if not status_data.get('running'):
            return {
                'tracking_status': "🔴 INACTIF",
                'status_color': "#c07a6a",  # Rouge atténué
                'obj_az': "---",
                'obj_alt': "---",
                'dome_target': "---",
                'dome_current': "---",
                'next_check': "---",
                'delta': "---",
                'mode_icon': '🔴',
                'adaptive_mode_label': "MANUEL/ARRÊTÉ"
            }

        # --- Données principales ---
        az = status_data.get('obj_az_raw', 0.0)
        alt = status_data.get('obj_alt', 0.0)
        target = status_data.get('position_cible', 0.0)
        current = status_data.get('position_relative', 0.0)
        delta = target - current
        delta = (delta + 180) % 360 - 180  # Chemin le plus court

        mode = status_data.get('adaptive_mode')
        mode_str = mode.value.upper() if isinstance(mode, TrackingMode) else str(mode).upper()

        # --- Formattage des couleurs et icônes ---
        if 'CRITICAL' in mode_str:
            icon = '🟠'
            color = "#b89a6a"  # Ambre
        elif 'CONTINUOUS' in mode_str:
            icon = '🔴'
            color = "#ff6060"  # Rouge vif
        else:
            icon = '🟢'
            color = "#60ff60"  # Vert

        # --- Formatage final ---
        return {
            'tracking_status': f"{icon} SUIVI {status_data['objet'].upper()}",
            'status_color': color,
            'obj_az': f"{az:.2f}°",
            'obj_alt': f"{alt:.2f}°",
            'dome_target': f"{target:.2f}°",
            'dome_current': f"{current:.2f}°",
            'next_check': f"{status_data.get('next_check', 0)}s",
            'delta': f"{delta:+.2f}°",
            'mode_icon': icon,
            'adaptive_mode_label': mode_str
        }

    @staticmethod
    def format_parallax_info(azimut: float, altitude: float, correction: float) -> str:
        """
        Formate la ligne d'information sur la correction de parallaxe (méthode abaque uniquement).
        """
        return (
            f"Méthode: Abaque | "
            f"Alt/Az: {altitude:.1f}°/{azimut:.1f}° | "
            f"Correction appliquée: {correction:+.2f}°"
        )

    @staticmethod
    def format_sync_info(encoder_ok: bool, encoder_angle: float, last_ts: float) -> str:
        """
        Formate l'état du démon encodeur et de la synchronisation.
        """
        if encoder_ok:
            if last_ts > 0:
                age = (datetime.now().timestamp() - last_ts) * 1000
                ts_str = f"Âge: {age:.0f}ms"
            else:
                ts_str = "OK"

            return f"✅ Démon Encodeur | Angle: {encoder_angle:.2f}° | {ts_str}"
        else:
            return "❌ Démon Encodeur HORS LIGNE (mode sans feedback)"