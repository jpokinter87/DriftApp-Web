"""
Acquisition de l'inclinomètre WitMotion WT9011DCL-BT50 (Bluetooth BLE) fixé sur la monture.

Objectif (17/10/2026) : enregistrer l'orientation de la monture pendant une nuit pour voir
si le retournement au méridien par l'ASIAIR se détecte de façon fiable. Le jour où c'est
le cas, DriftApp pourra attendre ce signal pour faire basculer la coupole, au lieu de la
faire basculer au passage au méridien.

Le script n'agit sur rien : il lit le capteur, écrit un CSV dans logs/ et affiche chaque
mouvement de la monture (début, fin, durée, variation de roulis et de tangage).

Protocole capteur (famille WT901BLE / WT9011DCL) : service 0000ffe5, notifications sur
0000ffe4, trames de 20 octets 0x55 0x61 + 9 entiers 16 bits signés little-endian :
accélération (±16 g), vitesse angulaire (±2000 °/s), roulis / tangage / lacet (±180°).
10 trames par seconde par défaut.

Usage (sur le Pi, Bluetooth intégré) :
    uv run --with bleak python scripts/diagnostics/inclinometre_monture.py --scan
    uv run --with bleak python scripts/diagnostics/inclinometre_monture.py
    uv run --with bleak python scripts/diagnostics/inclinometre_monture.py --adresse AA:BB:CC:DD:EE:FF
Arrêt : Ctrl+C.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import math
import struct
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from core.utils.log_paths import logs_subdir  # noqa: E402

NOTIFY_UUID = "0000ffe4-0000-1000-8000-00805f9a34fb"
TAILLE_TRAME = 20
ENTETE = 0x55
DRAPEAU_MESURE = 0x61

ECHELLE_ACCEL_G = 16.0 / 32768
ECHELLE_GYRO_DPS = 2000.0 / 32768
ECHELLE_ANGLE_DEG = 180.0 / 32768

SEUIL_MOUVEMENT_DPS = 1.0  # le suivi sidéral tourne à 0,004 °/s
CALME_FIN_MOUVEMENT_S = 3.0


@dataclass(frozen=True)
class Mesure:
    ax_g: float
    ay_g: float
    az_g: float
    wx_dps: float
    wy_dps: float
    wz_dps: float
    roll_deg: float
    pitch_deg: float
    yaw_deg: float

    @property
    def gyro_dps(self) -> float:
        return math.sqrt(self.wx_dps**2 + self.wy_dps**2 + self.wz_dps**2)


def extraire_trames(buffer: bytes) -> tuple[list[Mesure], bytes]:
    """Découpe le flux en mesures. Retourne (mesures, octets d'une trame incomplète à garder)."""
    mesures = []
    i = 0
    while i < len(buffer):
        if buffer[i] != ENTETE:
            i += 1
            continue
        if len(buffer) - i < TAILLE_TRAME:
            return mesures, buffer[i:]
        if buffer[i + 1] == DRAPEAU_MESURE:
            v = struct.unpack_from("<9h", buffer, i + 2)
            mesures.append(
                Mesure(
                    *(x * ECHELLE_ACCEL_G for x in v[0:3]),
                    *(x * ECHELLE_GYRO_DPS for x in v[3:6]),
                    *(x * ECHELLE_ANGLE_DEG for x in v[6:9]),
                )
            )
        # Autres drapeaux (0x71 = réponse de registre) : trame ignorée
        i += TAILLE_TRAME
    return mesures, b""


def _ecart_angle(a: float, b: float) -> float:
    return (a - b + 180.0) % 360.0 - 180.0


class DetecteurMouvement:
    """Repère les mouvements de la monture (pointage, retournement) dans la vitesse angulaire."""

    def __init__(
        self, seuil_dps: float = SEUIL_MOUVEMENT_DPS, calme_s: float = CALME_FIN_MOUVEMENT_S
    ):
        self.seuil_dps = seuil_dps
        self.calme_s = calme_s
        self.en_mouvement = False
        self.duree_s = 0.0
        self.delta_roll = 0.0
        self.delta_pitch = 0.0
        self._t_debut = 0.0
        self._t_calme: float | None = None
        self._roll0 = 0.0
        self._pitch0 = 0.0

    def mise_a_jour(self, t: float, gyro_dps: float, roll: float, pitch: float) -> str | None:
        """Retourne "debut" ou "fin" au changement d'état, sinon None."""
        if not self.en_mouvement:
            if gyro_dps > self.seuil_dps:
                self.en_mouvement = True
                self._t_debut, self._roll0, self._pitch0 = t, roll, pitch
                self._t_calme = None
                return "debut"
            return None
        if gyro_dps > self.seuil_dps:
            self._t_calme = None
            return None
        if self._t_calme is None:
            self._t_calme = t
            return None
        if t - self._t_calme < self.calme_s:
            return None
        self.en_mouvement = False
        self.duree_s = self._t_calme - self._t_debut
        self.delta_roll = abs(_ecart_angle(roll, self._roll0))
        self.delta_pitch = abs(_ecart_angle(pitch, self._pitch0))
        return "fin"


async def _scanner() -> None:
    from bleak import BleakScanner

    print("Recherche des appareils Bluetooth (10 s)...")
    trouves = await BleakScanner.discover(timeout=10.0, return_adv=True)
    for adresse, (appareil, annonce) in sorted(trouves.items(), key=lambda x: -x[1][1].rssi):
        nom = appareil.name or "?"
        repere = "  <-- capteur WitMotion probable" if nom.upper().startswith("WT") else ""
        print(f"  {adresse}  RSSI {annonce.rssi:4d} dBm  {nom}{repere}")


async def _trouver_capteur() -> str | None:
    from bleak import BleakScanner

    for appareil in await BleakScanner.discover(timeout=10.0):
        if (appareil.name or "").upper().startswith("WT"):
            print(f"Capteur trouvé : {appareil.name} ({appareil.address})")
            return appareil.address
    return None


async def _acquerir(adresse: str | None) -> None:
    from bleak import BleakClient

    chemin = logs_subdir("diagnostics") / f"inclinometre_{datetime.now():%Y%m%d_%H%M%S}.csv"
    detecteur = DetecteurMouvement()
    tampon = b""
    dernier_affichage = 0.0
    n_mesures = 0

    with chemin.open("w", newline="") as fichier:
        ecrivain = csv.writer(fichier)
        ecrivain.writerow(
            [
                "heure_locale",
                "t_unix",
                "ax_g",
                "ay_g",
                "az_g",
                "wx_dps",
                "wy_dps",
                "wz_dps",
                "roll_deg",
                "pitch_deg",
                "yaw_deg",
                "evenement",
            ]
        )
        print(f"Enregistrement dans {chemin}")

        def recevoir(_caracteristique, donnees: bytearray) -> None:
            nonlocal tampon, dernier_affichage, n_mesures
            mesures, tampon = extraire_trames(tampon + bytes(donnees))
            for m in mesures:
                t = time.time()
                n_mesures += 1
                evenement = detecteur.mise_a_jour(t, m.gyro_dps, m.roll_deg, m.pitch_deg) or ""
                heure = datetime.fromtimestamp(t).strftime("%H:%M:%S.%f")[:-3]
                ecrivain.writerow(
                    [
                        heure,
                        f"{t:.3f}",
                        f"{m.ax_g:.4f}",
                        f"{m.ay_g:.4f}",
                        f"{m.az_g:.4f}",
                        f"{m.wx_dps:.3f}",
                        f"{m.wy_dps:.3f}",
                        f"{m.wz_dps:.3f}",
                        f"{m.roll_deg:.2f}",
                        f"{m.pitch_deg:.2f}",
                        f"{m.yaw_deg:.2f}",
                        evenement,
                    ]
                )
                if evenement == "debut":
                    print(f"{heure}  >>> MOUVEMENT de la monture")
                elif evenement == "fin":
                    print(
                        f"{heure}  <<< fin du mouvement : {detecteur.duree_s:.0f} s, "
                        f"roulis {detecteur.delta_roll:.0f}°, tangage {detecteur.delta_pitch:.0f}°"
                    )
                    fichier.flush()
                elif t - dernier_affichage >= 10.0:
                    dernier_affichage = t
                    print(
                        f"{heure}  roulis {m.roll_deg:7.2f}°  tangage {m.pitch_deg:7.2f}°  "
                        f"lacet {m.yaw_deg:7.2f}°  ({n_mesures} mesures)"
                    )
                    fichier.flush()

        while True:
            cible = adresse or await _trouver_capteur()
            if cible is None:
                print("Aucun capteur WitMotion visible ; nouvel essai dans 10 s (capteur allumé ?)")
                await asyncio.sleep(10)
                continue
            try:
                async with BleakClient(cible) as client:
                    print(f"Connecté à {cible}")
                    await client.start_notify(NOTIFY_UUID, recevoir)
                    while client.is_connected:
                        await asyncio.sleep(1.0)
                print("Connexion perdue ; reconnexion dans 5 s")
            except Exception as e:  # BLE : capteur hors de portée, batterie vide…
                print(f"Erreur Bluetooth : {e} ; nouvel essai dans 5 s")
            fichier.flush()
            await asyncio.sleep(5)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Acquisition de l'inclinomètre WitMotion de la monture"
    )
    parser.add_argument(
        "--scan", action="store_true", help="lister les appareils Bluetooth visibles"
    )
    parser.add_argument(
        "--adresse", help="adresse Bluetooth du capteur (sinon : premier « WT… » trouvé)"
    )
    args = parser.parse_args()
    # Sortie redirigée (nohup … > fichier) : écrire chaque ligne tout de suite
    sys.stdout.reconfigure(line_buffering=True)
    try:
        asyncio.run(_scanner() if args.scan else _acquerir(args.adresse))
    except KeyboardInterrupt:
        print("\nArrêt demandé.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
