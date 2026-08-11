#!/usr/bin/env python3
"""Test terrain du capteur de pluie MH-RD lu par un Shelly Plus Uni.

Standalone de diagnostic : stdlib pure, aucun import du projet, aucune config.
Se lance depuis n'importe quelle machine du réseau local — typiquement le
portable emporté dehors, à côté du capteur.

  python3 pluie_manual.py read       # lecture ponctuelle des 2 entrées, brut
  python3 pluie_manual.py monitor    # bandeau + bips aux transitions + journal
  python3 pluie_manual.py monitor --demo   # sans réseau, pour tester le son

Ce que ce programme sert à établir sur le terrain (rien n'est figé ici) :
  1. quelle entrée du Shelly porte le D0 du capteur (id=0 ou id=1) ;
  2. la polarité telle que le Shelly la rapporte (--invert si elle est inversée) ;
  3. le réglage du trimpot du module ;
  4. que la chaîne capteur -> Shelly -> réseau -> Python est vivante ;
  5. le temps de séchage du capteur (durée des épisodes PLUIE, cf. résumé de sortie).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import wave
from datetime import datetime

# Défauts terrain — surchargeables par flags CLI, comme dans cimier_manual.py.
DEFAULT_HOST = "192.168.1.87"
DEFAULT_INTERVAL_S = 1.0
DEFAULT_TIMEOUT_S = 3.0

# Les 2 entrées digitales du Shelly Plus Uni. On lit LES DEUX par défaut :
# « entrée n°1 » est ambigu (sérigraphie 1/2 sur le boîtier, ids 0/1 en RPC).
DIGITAL_INPUT_IDS = (0, 1)

WET = "PLUIE"
DRY = "SEC"
UNREACHABLE = "INJOIGNABLE"

# Trois signaux distincts, reconnaissables à l'oreille sans regarder l'écran.
# (fréquence Hz, durée ms) — le sens du glissando porte l'information.
BEEPS = {
    "up": ((880, 120), (1320, 160)),  # sec -> pluie : ça monte
    "down": ((1320, 120), (660, 160)),  # pluie -> sec : ça descend
    "error": ((220, 150), (220, 150), (220, 300)),  # Shelly injoignable : 3 coups graves
}


def _write_wav(notes, rate: int = 22050) -> str:
    """Génère un WAV mono 16 bits pour une suite de (freq_hz, durée_ms). Renvoie un chemin."""
    frames = bytearray()
    for freq, milliseconds in notes:
        count = int(rate * milliseconds / 1000)
        fade = max(1.0, rate * 0.005)  # 5 ms d'attaque/extinction, sinon ça claque
        for i in range(count):
            envelope = min(1.0, min(i, count - i) / fade)
            value = int(16000 * envelope * math.sin(2 * math.pi * freq * i / rate))
            frames += struct.pack("<h", value)
    handle, path = tempfile.mkstemp(prefix="pluie_", suffix=".wav")
    os.close(handle)
    with wave.open(path, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(bytes(frames))
    return path


def _winsound_beeper():
    import winsound  # stdlib, Windows uniquement

    def beep(kind: str) -> None:
        try:
            for freq, milliseconds in BEEPS[kind]:
                winsound.Beep(freq, milliseconds)
        except RuntimeError:  # machine sans pilote audio : on continue en silence
            pass

    return beep


def _player_beeper(player: str):
    def beep(kind: str) -> None:
        path = _write_wav(BEEPS[kind])
        try:
            subprocess.run(
                [player, path],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:  # binaire trouvé par which mais inutilisable : on continue en silence
            pass
        finally:
            os.unlink(path)

    return beep


def _bel_beeper():
    def beep(kind: str) -> None:
        for _ in range(3 if kind == "error" else 2):
            sys.stdout.write("\a")
            sys.stdout.flush()
            time.sleep(0.15)

    return beep


def make_beeper(enabled: bool):
    """Renvoie (beep, label). beep(kind) avec kind dans {up, down, error}.

    Cascade : winsound (Windows) -> paplay -> aplay -> afplay -> BEL terminal.
    Le label est affiché au démarrage : Serge doit savoir AVANT de sortir s'il
    peut compter sur le son.
    """
    if not enabled:
        return (lambda kind: None), "coupé (--no-sound)"
    if sys.platform.startswith("win"):
        try:
            return _winsound_beeper(), "winsound"
        except ImportError:
            pass
    for player in ("paplay", "aplay", "afplay"):
        if shutil.which(player):
            return _player_beeper(player), player
    return (
        _bel_beeper(),
        "BEL terminal — beaucoup d'émulateurs le coupent, vérifiez le volume avant de sortir",
    )


def transition_sound(previous: str, new: str) -> str:
    """Quel signal pour quelle transition. L'état d'arrivée décide."""
    if new == UNREACHABLE:
        return "error"
    if new == WET:
        return "up"
    return "down"


def timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def format_duration(seconds: float) -> str:
    total = int(seconds)
    if total < 60:
        return str(total) + " s"
    return str(total // 60) + " min " + str(total % 60).zfill(2) + " s"


def default_log_path() -> str:
    """Répertoire courant, PAS logs/ du dépôt : le portable de Serge n'a pas le dépôt."""
    return datetime.now().strftime("pluie_test_%Y%m%d_%H%M%S.log")


class Journal:
    """Consigne les transitions à l'écran et dans un fichier (append + flush).

    Le flush à chaque ligne est délibéré : une campagne d'une heure ne doit rien
    perdre sur un Ctrl-C ou une batterie à plat.

    La durée de l'état PRÉCÉDENT est portée sur la ligne de transition. C'est
    elle qui répond à la question du séchage : la durée de l'épisode PLUIE qui
    suit le dernier arrosage EST le temps de séchage du capteur.
    """

    def __init__(self, path=None):
        self.path = path
        self.lines = []
        self.episodes = []  # (état, durée_s) des états clos
        self.final = None
        try:
            self._handle = open(path, "a", encoding="utf-8") if path else None
        except OSError as exc:
            raise SystemExit(
                "Impossible d'écrire le journal dans " + str(path) + " : " + str(exc)
            ) from exc
        self._write("# campagne démarrée " + timestamp())

    def _write(self, text: str) -> None:
        if not self._handle:
            return
        try:
            self._handle.write(text + "\n")
            self._handle.flush()
        except (OSError, ValueError) as exc:
            # ValueError couvre le cas d'un descripteur déjà fermé (ex. support
            # débranché entre deux écritures) — même famille de panne que OSError.
            sys.stderr.write(
                "! écriture journal impossible (" + str(exc) + ") — poursuite sans fichier\n"
            )
            self._handle = None

    def transition(self, previous: str, new: str, held_s: float) -> None:
        line = (
            timestamp()
            + " "
            + previous.ljust(11)
            + " -> "
            + new.ljust(11)
            + " (état précédent tenu "
            + format_duration(held_s)
            + ")"
        )
        self.lines.append(line)
        self.episodes.append((previous, held_s))
        self._write(line)

    def close(self, current: str, held_s: float) -> None:
        # PAS d'append à episodes : cet état n'est pas clos, sa durée n'est pas
        # un épisode complet et fausserait le temps de séchage.
        self.final = (current, held_s)
        self._write(
            "# campagne arrêtée "
            + timestamp()
            + " — état final "
            + current
            + " tenu "
            + format_duration(held_s)
            + " (épisode inachevé, non comptabilisé)"
        )
        if self._handle:
            try:
                self._handle.close()
            except OSError:
                pass
            self._handle = None

    def summary(self):
        """Lignes du résumé de sortie. C'est CE bloc que Serge nous renvoie."""
        wet = [duration for state, duration in self.episodes if state == WET]
        out = ["", "=== RÉSUMÉ ==="]
        if not wet:
            out.append("Aucun épisode PLUIE observé.")
        else:
            out.append(str(len(wet)) + " épisode(s) PLUIE :")
            for index, duration in enumerate(wet, 1):
                out.append("  #" + str(index) + " : " + format_duration(duration))
            out.append(
                "Le plus long : "
                + format_duration(max(wet))
                + "   <-- temps de séchage à retenir pour clear_delay_s"
            )
        if self.final is not None:
            out.append(
                "État à l'arrêt : "
                + self.final[0]
                + " tenu "
                + format_duration(self.final[1])
                + " (épisode inachevé, non compté)"
            )
        if self.path:
            out.append("Journal complet : " + self.path)
        return out


class ShellyError(Exception):
    """Le Shelly n'a pas répondu, ou pas comme attendu."""


def clean_host(host: str) -> str:
    """Tolère une saisie collée depuis un navigateur : http://x/ -> x."""
    for prefix in ("http://", "https://"):
        if host.startswith(prefix):
            host = host[len(prefix) :]
    return host.rstrip("/")


def read_input(host: str, input_id: int, timeout_s: float = DEFAULT_TIMEOUT_S):
    """Lit une entrée digitale. Renvoie (state: bool, payload: dict) ou lève ShellyError."""
    url = "http://" + clean_host(host) + "/rpc/Input.GetStatus?id=" + str(input_id)
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as resp:
            status = getattr(resp, "status", 200)
            raw = resp.read()
    except urllib.error.URLError as exc:
        raise ShellyError("injoignable (" + str(exc.reason) + ")") from exc
    except OSError as exc:
        raise ShellyError("erreur socket (" + str(exc) + ")") from exc
    if status != 200:
        raise ShellyError("HTTP " + str(status))
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise ShellyError("JSON invalide (" + str(exc) + ")") from exc
    if not isinstance(payload, dict) or "state" not in payload:
        raise ShellyError("payload sans 'state' : " + repr(payload))
    return bool(payload["state"]), payload


def interpret(state: bool, invert: bool) -> str:
    """État brut du Shelly -> PLUIE / SEC.

    Par défaut state=True -> PLUIE. Le D0 du LM393 est actif bas côté module,
    mais ce que le Shelly rapporte dépend de son câblage d'entrée : d'où --invert
    plutôt qu'une constante. C'est le verre d'eau qui tranche, pas la datasheet.
    """
    return WET if state != invert else DRY


def input_ids(choice: str):
    """'both' -> les deux entrées ; '0'/'1' -> celle-là seulement."""
    if choice == "both":
        return DIGITAL_INPUT_IDS
    return (int(choice),)


def cmd_read(args) -> int:
    """Lecture ponctuelle : affiche l'interprétation ET le JSON brut."""
    print("Shelly " + args.host + " — lecture ponctuelle")
    for input_id in input_ids(args.input):
        try:
            state, payload = read_input(args.host, input_id, args.timeout)
        except ShellyError as exc:
            print("  id=" + str(input_id) + " : " + UNREACHABLE + " — " + str(exc))
            continue
        print(
            "  id="
            + str(input_id)
            + " : "
            + interpret(state, args.invert).ljust(6)
            + " state="
            + str(state).ljust(5)
            + " brut="
            + json.dumps(payload)
        )
    print("\nArrosez la plaque, relancez : l'entrée qui bouge est celle du capteur.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "command",
        choices=("read", "monitor"),
        nargs="?",
        default="monitor",
        help="read = une lecture brute ; monitor = surveillance continue (défaut)",
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help="IP du Shelly (défaut %(default)s)")
    parser.add_argument(
        "--input",
        choices=("0", "1", "both"),
        default="both",
        help="entrée(s) à lire (défaut %(default)s)",
    )
    parser.add_argument(
        "--interval", type=float, default=DEFAULT_INTERVAL_S, help="secondes entre 2 lectures"
    )
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S, help="timeout HTTP")
    parser.add_argument(
        "--invert", action="store_true", help="inverse la polarité (state=True -> SEC)"
    )
    parser.add_argument("--no-sound", action="store_true", help="coupe les bips")
    parser.add_argument(
        "--log",
        help="fichier journal (défaut : pluie_test_<horodatage>.log dans le répertoire courant)",
    )
    parser.add_argument("--no-log", action="store_true", help="n'écrit aucun fichier")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "read":
        return cmd_read(args)
    print("monitor : implémenté en Task 4")
    return 0


if __name__ == "__main__":
    sys.exit(main())
