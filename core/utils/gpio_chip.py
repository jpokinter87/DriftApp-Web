"""Contrôleur GPIO de la tête 40 broches, trouvé par son label.

Son numéro n'est pas stable : le noyau 6.12.109 (Pi 5, octobre 2026) a renuméroté
les contrôleurs en gpiochip11 à 15, plus de gpiochip0. Le label, lui, ne bouge pas.

Bibliothèque standard seule : importé par le démon encodeur (Python système).
"""

from pathlib import Path

# Pi 5 (RP1), Pi 4, Pi 1-3.
HEADER_CHIP_LABELS = ("pinctrl-rp1", "pinctrl-bcm2711", "pinctrl-bcm2835")


def open_header_gpiochip(lgpio, dev_dir: Path = Path("/dev")) -> tuple[int, int]:
    """Ouvre le contrôleur de la tête 40 broches ; renvoie (numéro, handle lgpio).

    Les autres contrôleurs ouverts au passage sont refermés. RuntimeError si
    aucun ne porte un label attendu.
    """
    numeros = sorted(
        int(p.name[len("gpiochip") :])
        for p in dev_dir.glob("gpiochip*")
        if p.name[len("gpiochip") :].isdigit()
    )
    vus = []
    for n in numeros:
        try:
            handle = lgpio.gpiochip_open(n)
        except Exception:
            continue
        try:
            label = lgpio.gpio_get_chip_info(handle)[3]
        except Exception:
            label = None
        if label in HEADER_CHIP_LABELS:
            return n, handle
        vus.append(f"gpiochip{n}={label}")
        lgpio.gpiochip_close(handle)
    raise RuntimeError(
        f"aucun contrôleur GPIO {'/'.join(HEADER_CHIP_LABELS)} (vus : {', '.join(vus) or 'aucun'})"
    )
