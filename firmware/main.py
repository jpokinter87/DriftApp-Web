"""
Firmware principal RP2040 pour pilotage moteur pas-a-pas.

Recoit des commandes serie depuis le Raspberry Pi et genere les
impulsions STEP/DIR via PIO state machines.

Version 3 (v6.19) : PIO autonome, rampe a acceleration constante en paliers.

Protocole serie :
  Commandes (Pi → Pico) :
    MOVE <steps> <direction> <target_delay_us> <ramp_type> [accel]\n
      accel (v6.19, optionnel) : pas/s^2 de la rampe a acceleration
      constante ; absent -> DEFAULT_ACCEL
    STOP\n
    STATUS\n

  Reponses (Pico → Pi) :
    OK <steps_executed>\n
    STOPPED <steps_done>\n
    ERROR <message>\n
    BUSY\n
    IDLE\n
    MOVING <steps_remaining>\n

Fonctionne via USB CDC serie (sys.stdin/sys.stdout).
"""

import sys
import select
from step_generator import StepGenerator
from ramp import ProfilAccelConstante, arret_doux, lire_accel


# Configuration
STEP_PIN = 2   # GP2 → PUL+ du DM860T
DIR_PIN = 3    # GP3 → DIR+ du DM860T

# Pre-allouer le poller pour check_for_stop()
# Evite creation/destruction d'objet a chaque appel (cause GC)
_poller = select.poll()
_poller.register(sys.stdin, select.POLLIN)


def send_response(message):
    """Envoie une reponse serie terminee par newline."""
    sys.stdout.write(message + "\n")


def parse_move_command(parts):
    """
    Parse les arguments de la commande MOVE.

    Args:
        parts: Liste de tokens ["MOVE", steps, direction, delay_us, ramp_type, (accel)]

    Returns:
        tuple: (steps, direction, delay_us, ramp_type, accel) ou None si erreur
    """
    if len(parts) < 5:
        return None

    try:
        steps = int(parts[1])
        direction = int(parts[2])
        delay_us = int(parts[3])
        ramp_type = parts[4].upper()
    except (ValueError, IndexError):
        return None

    # Validation
    if steps <= 0:
        return None
    if direction not in (0, 1):
        return None
    if delay_us <= 0:
        return None
    if ramp_type not in ("SCURVE", "LINEAR", "NONE"):
        return None

    return (steps, direction, delay_us, ramp_type, lire_accel(parts))


def check_for_stop():
    """
    Verifie si une commande STOP a ete recue pendant un mouvement.

    Utilise un poller pre-alloue (pas d'allocation a chaque appel).

    Returns:
        bool: True si STOP recu
    """
    events = _poller.poll(0)  # Non-bloquant
    if events:
        try:
            line = sys.stdin.readline().strip()
            if line.upper() == "STOP":
                return True
        except Exception:
            pass
    return False


def execute_move(sg, steps, direction, delay_us, ramp_type, accel):
    """
    Execute un mouvement avec rampe optionnelle.

    Avec rampe (SCURVE/LINEAR) : profil a acceleration constante, en paliers
    enchaines par le PIO (v6.19 ; tous les mouvements depuis v6.19.1).
    STOP doux sous 260 us, immediat au-dela (calibration).
    Sans rampe (NONE) : N pas a delai constant.

    Args:
        sg: StepGenerator instance
        steps: Nombre de pas
        direction: 0=CCW, 1=CW
        delay_us: Delai cible en microsecondes
        ramp_type: "SCURVE", "LINEAR", ou "NONE"
        accel: Acceleration (pas/s^2) de la rampe

    Returns:
        tuple: (steps_done, stopped)
    """
    sg.set_direction(direction)
    sg._steps_done = 0

    if ramp_type == "NONE":
        done = sg.move_steps(steps, delay_us, stop_checker=check_for_stop)
        return done, sg._stop_flag

    profil = ProfilAccelConstante(steps, delay_us, accel)
    return sg.move_segments(
        profil.paliers(),
        stop_checker=check_for_stop,
        on_stop=profil.demander_arret if arret_doux(delay_us) else None,
    )


def main():
    """Boucle principale du firmware."""
    # Initialiser le generateur de pas
    sg = StepGenerator(step_pin=STEP_PIN, dir_pin=DIR_PIN)

    send_response("READY")

    while True:
        try:
            # Lire une commande (bloquant)
            line = sys.stdin.readline()
            if not line:
                continue

            line = line.strip()
            if not line:
                continue

            # Parser la commande
            parts = line.split()
            command = parts[0].upper()

            if command == "STATUS":
                if sg.is_moving:
                    remaining = sg._steps_total - sg._steps_done
                    send_response("MOVING {}".format(remaining))
                else:
                    send_response("IDLE")

            elif command == "STOP":
                if sg.is_moving:
                    done = sg.stop()
                    send_response("STOPPED {}".format(done))
                else:
                    send_response("IDLE")

            elif command == "MOVE":
                if sg.is_moving:
                    send_response("BUSY")
                    continue

                params = parse_move_command(parts)
                if params is None:
                    send_response("ERROR invalid_command")
                    continue

                steps, direction, delay_us, ramp_type, accel = params
                steps_done, stopped = execute_move(
                    sg, steps, direction, delay_us, ramp_type, accel
                )

                if stopped:
                    send_response("STOPPED {}".format(steps_done))
                else:
                    send_response("OK {}".format(steps_done))

            else:
                send_response("ERROR unknown_command")

        except Exception as e:
            send_response("ERROR {}".format(str(e)))


# Demarrage automatique au boot du Pico
main()
