"""Choix du contrôleur GPIO de la tête 40 broches par son label.

Terrain 21/10 : le noyau 6.12.109 a renuméroté les contrôleurs (gpiochip11 à 15,
plus de gpiochip0) ; ouvrir le numéro 0 en dur faisait mourir le démon encodeur.
"""

from unittest.mock import MagicMock

import pytest

from core.utils.gpio_chip import open_header_gpiochip

# Relevé sur le Pi de Serge (21/10, noyau 6.12.109+rpt-rpi-2712).
LABELS_PI5_6_12_109 = {
    11: "gpio-brcmstb@107d517c00",
    12: "gpio-brcmstb@107d517c20",
    13: "gpio-brcmstb@107d508500",
    14: "gpio-brcmstb@107d508520",
    15: "pinctrl-rp1",
}


def _fake_lgpio(labels):
    """lgpio factice : un handle par numéro ouvert, label renvoyé par gpio_get_chip_info."""
    lgpio = MagicMock()

    def gpiochip_open(n):
        if n not in labels:
            raise Exception("can not open gpiochip")
        return 100 + n

    lgpio.gpiochip_open.side_effect = gpiochip_open
    lgpio.gpio_get_chip_info.side_effect = lambda h: [0, 54, f"gpiochip{h - 100}", labels[h - 100]]
    return lgpio


def _dev_dir(tmp_path, numbers):
    for n in numbers:
        (tmp_path / f"gpiochip{n}").touch()
    return tmp_path


def test_pi5_renumbered_finds_rp1(tmp_path):
    lgpio = _fake_lgpio(LABELS_PI5_6_12_109)
    dev = _dev_dir(tmp_path, LABELS_PI5_6_12_109)

    chip, handle = open_header_gpiochip(lgpio, dev)

    assert (chip, handle) == (15, 115)
    # Les contrôleurs écartés sont refermés.
    closed = {c.args[0] for c in lgpio.gpiochip_close.call_args_list}
    assert closed == {111, 112, 113, 114}


def test_pi4_bcm2711_on_chip0(tmp_path):
    labels = {0: "pinctrl-bcm2711", 1: "raspberrypi-exp-gpio"}
    chip, _ = open_header_gpiochip(_fake_lgpio(labels), _dev_dir(tmp_path, labels))
    assert chip == 0


def test_no_header_chip_raises(tmp_path):
    labels = {11: "gpio-brcmstb@107d517c00"}
    with pytest.raises(RuntimeError, match="pinctrl-rp1"):
        open_header_gpiochip(_fake_lgpio(labels), _dev_dir(tmp_path, labels))
