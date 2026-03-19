"""
Firmware principal RP2040 pour pilotage moteur pas-a-pas.

Recoit des commandes serie depuis le Raspberry Pi et genere les
impulsions STEP/DIR via PIO state machines.

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

# Intervalle de verification STOP pendant un mouvement (en pas)
STOP_CHECK_INTERVAL = 100


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

    Returns:
        bool: True si STOP recu
    """
    # Utiliser select.poll pour verifier si des donnees sont disponibles
    poller = select.poll()
    poller.register(sys.stdin, select.POLLIN)
    events = poller.poll(0)  # Non-bloquant
    poller.unregister(sys.stdin)

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
    delays = ramp.compute_delays()

    if delays is not None:
        # Mode rampe : delais variables
        # On doit executer pas par pas pour pouvoir verifier STOP
        steps_done = 0
        stopped = False

        sg._moving = True
        sg._stop_flag = False
        sg._steps_done = 0
        sg._sm.active(1)

        try:
            for i in range(steps):
                # Verification periodique de STOP
                if i % STOP_CHECK_INTERVAL == 0 and i > 0:
                    if check_for_stop():
                        stopped = True
                        break

                cycles = sg._delay_us_to_cycles(delays[i])
                sg._sm.put(cycles)
                steps_done += 1
        finally:
            sg._sm.active(0)
            sg._moving = False
            sg._steps_done = steps_done

        return steps_done, stopped
    else:
        # Mode uniforme : delai constant
        # Meme logique avec verification STOP
        steps_done = 0
        stopped = False
        cycles = sg._delay_us_to_cycles(delay_us)

        sg._moving = True
        sg._stop_flag = False
        sg._steps_done = 0
        sg._sm.active(1)

        try:
            for i in range(steps):
                if i % STOP_CHECK_INTERVAL == 0 and i > 0:
                    if check_for_stop():
                        stopped = True
                        break

                sg._sm.put(cycles)
                steps_done += 1
        finally:
            sg._sm.active(0)
            sg._moving = False
            sg._steps_done = steps_done

        return steps_done, stopped


def main():
    """Boucle principale du firmware."""
    # Initialiser le generateur de pas
    sg = StepGenerator(step_pin=STEP_PIN, dir_pin=DIR_PIN)
    moving = False

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
