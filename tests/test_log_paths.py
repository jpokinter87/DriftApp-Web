"""Chemins des logs par thème et rangement des anciens fichiers (6.22.0).

Spec : docs/superpowers/specs/2026-10-19-logs-sous-repertoires.md
"""

import os
from pathlib import Path

import pytest

from core.utils.log_paths import logs_root, logs_subdir, ranger_anciens_logs


@pytest.fixture
def racine(tmp_path, monkeypatch):
    monkeypatch.setenv("DRIFTAPP_LOGS_DIR", str(tmp_path))
    return tmp_path


def test_racine_suit_la_variable_d_environnement(racine):
    assert logs_root() == racine


def test_racine_par_defaut_est_logs_du_projet(monkeypatch):
    monkeypatch.delenv("DRIFTAPP_LOGS_DIR", raising=False)
    assert logs_root() == Path(__file__).resolve().parent.parent / "logs"


def test_sous_dossier_cree(racine):
    dossier = logs_subdir("moteur")
    assert dossier == racine / "moteur"
    assert dossier.is_dir()


def test_range_les_fichiers_du_motif_seulement(racine):
    (racine / "motor_service_20261001_120000.log").write_text("a")
    (racine / "ems22d_20261001_120000.log").write_text("b")

    assert ranger_anciens_logs(["motor_service_*.log"], "moteur") == 1

    assert (racine / "moteur" / "motor_service_20261001_120000.log").read_text() == "a"
    assert (racine / "ems22d_20261001_120000.log").exists()


def test_plusieurs_motifs(racine):
    for nom in ("cimier_service.log", "cimier_service.log.1", "cimier_service.log.3"):
        (racine / nom).write_text(nom)

    assert ranger_anciens_logs(["cimier_service.log", "cimier_service.log.*"], "cimier") == 3
    assert sorted(p.name for p in (racine / "cimier").iterdir()) == [
        "cimier_service.log",
        "cimier_service.log.1",
        "cimier_service.log.3",
    ]


def test_second_appel_ne_deplace_rien(racine):
    (racine / "django_20261001_120000.log").write_text("x")
    ranger_anciens_logs(["django_*.log"], "web")

    assert ranger_anciens_logs(["django_*.log"], "web") == 0


def test_destination_existante_non_ecrasee(racine):
    logs_subdir("web")
    (racine / "web" / "django_20261001_120000.log").write_text("récent")
    (racine / "django_20261001_120000.log").write_text("ancien")

    assert ranger_anciens_logs(["django_*.log"], "web") == 0
    assert (racine / "web" / "django_20261001_120000.log").read_text() == "récent"
    assert (racine / "django_20261001_120000.log").read_text() == "ancien"


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignore les droits du dossier")
def test_racine_sans_droit_d_ecriture_ne_leve_pas(racine):
    logs_subdir("moteur")
    (racine / "motor_service_20261001_120000.log").write_text("a")
    racine.chmod(0o500)
    try:
        assert ranger_anciens_logs(["motor_service_*.log"], "moteur") == 0
    finally:
        racine.chmod(0o700)
    assert (racine / "motor_service_20261001_120000.log").exists()


def test_sous_dossier_impossible_a_creer_ne_leve_pas(racine):
    (racine / "moteur").write_text("un fichier à la place du dossier")
    (racine / "motor_service_20261001_120000.log").write_text("a")

    assert ranger_anciens_logs(["motor_service_*.log"], "moteur") == 0


@pytest.mark.parametrize(
    "motifs",
    [
        ["motor_service_*.log"],
        ["ems22d_*.log"],
        ["django_*.log"],
        ["cimier_service.log", "cimier_service.log.*"],
    ],
)
def test_fichiers_de_mise_a_jour_jamais_concernes(racine, motifs):
    """Décision 1 de la spec : l'OTA lit et écrit ces fichiers à la racine."""
    garder = ["update.log", "update_status.json", "restart.log", "restart_status.json"]
    for nom in garder:
        (racine / nom).write_text("{}")

    ranger_anciens_logs(motifs, "x")

    for nom in garder:
        assert (racine / nom).exists(), nom
