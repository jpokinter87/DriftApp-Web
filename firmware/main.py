"""
Firmware principal RP2040 pour pilotage moteur pas-a-pas.

Recoit des commandes serie depuis le Raspberry Pi et genere les
impulsions STEP/DIR via PIO state machines.

Version 2 : PIO autonome en croisiere, pas-a-pas pour rampe uniquement.

Protocole serie :
  Commandes (Pi → Pico) :
    MOVE <steps> <direction> <target_delay_us> <ramp_type>\n
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
from ramp import Ramp


# Configuration
STEP_PIN = 2   # GP2 → PUL+ du DM556T
DIR_PIN = 3    # GP3 → DIR+ du DM556T

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
        parts: Liste de tokens ["MOVE", steps, direction, delay_us, ramp_type]

    Returns:
        tuple: (steps, direction, delay_us, ramp_type) ou None si erreur
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

    return (steps, direction, delay_us, ramp_type)


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


def execute_move(sg, steps, direction, delay_us, ramp_type):
    """
    Execute un mouvement avec rampe optionnelle.

    Architecture PIO autonome :
    - Croisiere : PIO recoit N pas + delai, tourne en autonome
    - Accel/decel : PIO recoit 1 pas + delai variable a chaque iteration
      (overhead MicroPython acceptable car vitesse faible en rampe)

    Args:
        sg: StepGenerator instance
        steps: Nombre de pas
        direction: 0=CCW, 1=CW
        delay_us: Delai cible en microsecondes
        ramp_type: "SCURVE", "LINEAR", ou "NONE"

    Returns:
        tuple: (steps_done, stopped)
    """
    # Positionner la direction
    sg.set_direction(direction)

    # Calculer la rampe
    ramp = Ramp(steps, delay_us, ramp_type)
    has_ramp = ramp.compute_delays()

    steps_done = 0
    stopped = False

    # Reset etat StepGenerator
    sg._steps_done = 0

    if not has_ramp:
        # Pas de rampe : tout en PIO autonome
        done = sg.move_steps(steps, delay_us, stop_checker=check_for_stop)
        steps_done = done
        stopped = sg._stop_flag
    else:
        # Mode 3 phases : accel (variable) / cruise (autonome) / decel (variable)
        accel_end = ramp.accel_end
        decel_start = ramp.decel_start

        # Phase 1 : Acceleration (delais variables, PIO pas-par-pas)
        accel_steps = min(accel_end, steps)
        if accel_steps > 0:
            done = sg.move_steps_variable(
                accel_steps, ramp.get_delay, start_index=0,
                stop_checker=check_for_stop,
            )
            steps_done += done
            stopped = sg._stop_flag

        # Phase 2 : Croisiere (PIO autonome — zero overhead Python)
        if not stopped:
            cruise_steps = min(decel_start, steps) - accel_end
            if cruise_steps > 0:
                done = sg.move_steps(
                    cruise_steps, delay_us,
                    stop_checker=check_for_stop,
                )
                steps_done += done
                stopped = sg._stop_flag

        # Phase 3 : Deceleration (delais variables, PIO pas-par-pas)
        if not stopped:
            decel_steps = steps - decel_start
            if decel_steps > 0:
                done = sg.move_steps_variable(
                    decel_steps, ramp.get_delay, start_index=decel_start,
                    stop_checker=check_for_stop,
                )
                steps_done += done
                stopped = sg._stop_flag

    # Mettre a jour le compteur total
    sg._steps_done = steps_done

    return steps_done, stopped


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

                steps, direction, delay_us, ramp_type = params
                steps_done, stopped = execute_move(
                    sg, steps, direction, delay_us, ramp_type
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
