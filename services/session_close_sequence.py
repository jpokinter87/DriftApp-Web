"""Séquence unique de fermeture d'une session d'observation.

``tracking_stop`` → attente de sa consommation → ``goto`` parking → fermeture
du cimier. Trois appelants la partagent :

  - ``CimierScheduler._trigger_close``  — fin de nuit sur éphémérides ;
  - ``ParkingSessionView``              — bouton « Parking » du dashboard ;
  - la veille pluie de ``cimier_service`` — fermeture d'urgence.

**Pourquoi un module et pas trois copies.** Elle a vécu en deux exemplaires
jusqu'en août 2026. Le correctif du 02/05 (attendre la consommation du
``tracking_stop`` avant d'émettre le ``goto``) n'avait été appliqué qu'à l'un
des deux : ``motor_command.json`` n'ayant qu'un seul slot lu à 20 Hz, le
``goto`` écrasait le ``tracking_stop``, le suivi restait actif et la coupole
dérivait hors du parking pendant des heures — bug terrain des 08 et 09/08,
corrigé en 6.11.3. Une troisième copie rejouerait la même histoire.

La fermeture du cimier est passée en **callable** : le scheduler écrit dans
``cimier_command.json`` via ``CimierIpcManager``, Django passe par son propre
client. Le module n'a pas à connaître les deux.

Tout est **best-effort** : aucune étape n'interrompt les suivantes. Un parking
imparfait vaut mieux qu'un cimier resté ouvert.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict

logger = logging.getLogger(__name__)


def close_session(
    motor_ipc: Any,
    send_close: Callable[[], bool],
    parking_target_deg: float,
    reason: str,
) -> Dict[str, Any]:
    """Exécute la séquence complète et retourne le détail de chaque étape.

    Args:
        motor_ipc: writer exposant ``send_tracking_stop``, ``wait_tracking_stopped``
            et ``send_goto``.
        send_close: callable sans argument déclenchant la fermeture du cimier,
            retournant une valeur vraie en cas de succès.
        parking_target_deg: azimut de parking de la coupole.
        reason: motif journalisé (``auto``, ``manual``, ``rain``).
    """
    tracking_stop_sent = bool(motor_ipc.send_tracking_stop())
    tracking_stop_confirmed = bool(motor_ipc.wait_tracking_stopped())
    goto_sent = bool(motor_ipc.send_goto(float(parking_target_deg)))
    try:
        cimier_close_sent = bool(send_close())
    except Exception as exc:  # noqa: BLE001 — best-effort, jamais de propagation
        logger.error("cimier_event=session_close_cimier_failed reason=%s exc=%s", reason, exc)
        cimier_close_sent = False

    logger.info(
        "cimier_event=session_close reason=%s parking_target_deg=%.2f "
        "tracking_stop_sent=%s tracking_stop_confirmed=%s goto_sent=%s cimier_close_sent=%s",
        reason,
        float(parking_target_deg),
        tracking_stop_sent,
        tracking_stop_confirmed,
        goto_sent,
        cimier_close_sent,
    )
    return {
        "tracking_stop_sent": tracking_stop_sent,
        "tracking_stop_confirmed": tracking_stop_confirmed,
        "goto_sent": goto_sent,
        "cimier_close_sent": cimier_close_sent,
        "parking_target_deg": float(parking_target_deg),
        "reason": reason,
    }
