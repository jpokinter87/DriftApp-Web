"""Noyau de résilience de data/config.json (chantier A).

Stdlib-pur (aucun import projet) pour pouvoir tourner avant tout chargement de
configuration. Voir docs/superpowers/specs/2026-06-19-config-resilience-design.md.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CONFIG_PATH = _PROJECT_ROOT / "data" / "config.json"
DEFAULT_TEMPLATE_PATH = _PROJECT_ROOT / "data" / "config.template.json"
DEFAULT_BACKUP_PATH = _PROJECT_ROOT / "data" / ".config.lastgood.json"


# --- Chantier B : génération du schéma de formulaire depuis le template ---

ADVANCED_SECTIONS = {
    "moteur",
    "encodeur",
    "motor_driver",
    "boot_calibration",
    "thresholds",
}

# Énumérations connues : chemin pointé → options proposées (menu déroulant UI).
# Les listes d'entiers sécurisent les indices/modes matériels (0/1, modes SPI) :
# le menu déroulant empêche la saisie d'une valeur hors plage.
ENUM_REGISTRY: dict[str, list] = {
    "cimier.automation.mode": ["manual", "semi", "full"],
    "logging.level": ["DEBUG", "INFO", "WARNING", "ERROR"],
    "motor_driver.type": ["gpio", "rp2040"],
    "cimier.switch_reader.type": ["shelly_uni", "noop"],
    "cimier.power_switch.type": ["shelly_gen1", "shelly_gen2", "noop"],
    "cimier.weather_provider.type": ["noop"],
    "cimier.motor_shelly.api": ["legacy", "rpc"],
    "cimier.switch_reader.api": ["legacy", "rpc"],
    # Indices relais/entrées Shelly (0/1).
    "cimier.motor_shelly.relay_motor": [0, 1],
    "cimier.motor_shelly.relay_dir": [0, 1],
    "cimier.power_switch.switch_id": [0, 1],
    "cimier.switch_reader.open_input_id": [0, 1],
    "cimier.switch_reader.closed_input_id": [0, 1],
    # SPI encodeur.
    "encodeur.spi.bus": [0, 1],
    "encodeur.spi.device": [0, 1],
    "encodeur.spi.mode": [0, 1, 2, 3],
}

# Aide par champ (chemin pointé → texte). Filet pour les champs SANS `_…_comment`
# voisin dans le template. Le commentaire du template, s'il existe, a priorité.
# Garde `config.json` épuré (l'aide vit dans le code, pas dans la config terrain).
HELP_REGISTRY: dict[str, str] = {
    # --- Général ---
    "simulation": (
        "Force le mode simulation (true) : le moteur et l'encodeur sont émulés, "
        "aucun accès matériel. false = pilotage réel sur le Raspberry Pi."
    ),
    # --- thresholds (seuils de mouvement, en degrés) ---
    "thresholds.feedback_min_deg": (
        "Delta minimum (degrés) pour utiliser la boucle feedback ; en dessous, "
        "rotation directe plus fluide. Typiquement 3°."
    ),
    "thresholds.large_movement_deg": (
        "Seuil (degrés) au-delà duquel un déplacement est considéré « grand » "
        "(logs, détection de transit méridien)."
    ),
    "thresholds.feedback_protection_deg": (
        "Garde-fou (degrés) dans la boucle feedback : abandon si l'erreur dépasse "
        "ce seuil (protection contre un mouvement anormal)."
    ),
    "thresholds.default_tolerance_deg": (
        "Tolérance par défaut (degrés) pour une rotation avec feedback : précision "
        "cible avant arrêt."
    ),
    # --- site ---
    "site.latitude": (
        "Latitude du site en degrés décimaux (positif = hémisphère Nord). Ex. 44.15."
    ),
    "site.longitude": (
        "Longitude du site en degrés décimaux (positif = Est de Greenwich). Ex. 5.23."
    ),
    "site.altitude": "Altitude du site en mètres au-dessus du niveau de la mer.",
    "site.nom": "Nom du site/observatoire (affichage et rapports).",
    "site.fuseau": (
        "Fuseau horaire au format IANA (ex. « Europe/Paris ») pour les calculs "
        "d'éphémérides et l'affichage local."
    ),
    # --- suivi ---
    "suivi.seuil_correction_deg": (
        "Écart (degrés) déclenchant une correction de suivi. En vitesse unique "
        "(v5.10) le code impose 0.3° (SINGLE_SPEED_CORRECTION_THRESHOLD_DEG)."
    ),
    "suivi.intervalle_verification_sec": (
        "Intervalle (secondes) entre deux vérifications de suivi. En vitesse unique "
        "(v5.10) le code impose 30 s (SINGLE_SPEED_CHECK_INTERVAL_S)."
    ),
    "suivi.abaque_file": (
        "Chemin (relatif au projet) du fichier abaque Loi_coupole.xlsx utilisé pour "
        "l'interpolation 2D azimut coupole ↔ position télescope."
    ),
    # --- meridian_anticipation ---
    "meridian_anticipation.enabled": (
        "Active l'anticipation du flip méridien (true) : GOTO directif au moment "
        "optimal pour réduire le lag pendant le retournement. false = comportement "
        "v5.10 strict."
    ),
    # --- motor_driver ---
    "motor_driver.type": (
        "Mode de pilotage du moteur. « gpio » : le motor_service pilote le driver "
        "DM556T directement via GPIO. « rp2040 » : commandes série vers le Pi Pico."
    ),
    "motor_driver.serial.baudrate": (
        "Débit (bauds) de la liaison série USB CDC vers le Pi Pico. Typiquement 115200."
    ),
    "motor_driver.serial.timeout": (
        "Délai d'attente (secondes) de lecture sur le port série du Pi Pico."
    ),
    # --- moteur ---
    "moteur.gpio_pins.dir": (
        "Broche GPIO (numérotation BCM) du signal DIR (sens) vers le driver DM556T."
    ),
    "moteur.gpio_pins.step": (
        "Broche GPIO (numérotation BCM) du signal STEP (impulsions) vers le driver DM556T."
    ),
    "moteur.steps_per_revolution": (
        "Pas par tour du moteur NEMA avant micro-pas (200 en full step pour un moteur 1,8°)."
    ),
    "moteur.steps_correction_factor": (
        "Facteur correctif mesuré appliqué au nombre de pas (1.0 = aucune correction) "
        "pour compenser les écarts mécaniques."
    ),
    "moteur.max_speed_steps_per_sec": (
        "Vitesse maximale du moteur en pas par seconde (plafond de la rampe d'accélération)."
    ),
    "moteur.acceleration_steps_per_sec2": (
        "Accélération de la rampe S-curve, en pas par seconde au carré."
    ),
    "moteur.motor_delay_base": (
        "Délai de base (secondes) entre deux pas moteur ; plus il est petit, plus le "
        "moteur tourne vite."
    ),
    # --- encodeur ---
    "encodeur.spi.bus": ("Bus SPI (0 ou 1) auquel est raccordé l'encodeur magnétique EMS22A."),
    "encodeur.spi.device": ("Périphérique (chip select) SPI de l'encodeur EMS22A : 0 ou 1."),
    "encodeur.spi.speed_hz": "Fréquence d'horloge SPI en hertz (ex. 1000000 = 1 MHz).",
    "encodeur.spi.mode": "Mode SPI (0 à 3). L'EMS22A utilise le mode 0.",
    "encodeur.mecanique.wheel_diameter_mm": (
        "Diamètre (mm) de la roue de mesure entraînée par la couronne de la coupole."
    ),
    "encodeur.mecanique.ring_diameter_mm": (
        "Diamètre (mm) de la couronne (anneau) de la coupole ; sert au rapport de "
        "réduction roue/couronne."
    ),
    "encodeur.mecanique.counts_per_rev": (
        "Nombre de positions par tour de l'encodeur. EMS22A 10 bits = 1024."
    ),
    "encodeur.calibration_factor": (
        "Facteur de calibration : ratio degrés roue → degrés couronne (≈ réduction "
        "roue/couronne) appliqué à la position. Issu de la calibration terrain. "
        "Modifier avec précaution."
    ),
    # --- logging ---
    "logging.level": ("Niveau de verbosité des logs : DEBUG, INFO, WARNING ou ERROR."),
    "logging.log_dir": "Répertoire (relatif au projet) où sont écrits les fichiers de log.",
    "logging.max_file_size_mb": ("Taille maximale (Mo) d'un fichier de log avant rotation."),
    "logging.backup_count": ("Nombre de fichiers de log archivés conservés lors de la rotation."),
    # --- cimier (archi V3 tout-Shelly) ---
    "cimier.enabled": (
        "Active le pilotage du cimier (true). false = cimier_service ignoré "
        "(template repo). À activer uniquement sur le Pi terrain."
    ),
    "cimier.cycle_timeout_s": (
        "Durée maximale (secondes) d'un cycle d'ouverture/fermeture avant arrêt de "
        "sécurité s'il n'atteint pas la butée."
    ),
    "cimier.post_off_quiet_s": (
        "Temps de calme (secondes) imposé après l'arrêt du moteur, avant d'accepter "
        "une nouvelle commande."
    ),
    "cimier.shelly_settle_s": (
        "Temps d'établissement (secondes) laissé aux Shelly après commutation d'un "
        "relais avant l'action suivante."
    ),
    "cimier.dir_settle_s": (
        "Temps (secondes) entre le réglage du sens (DPDT) et la mise en marche du "
        "moteur, pour laisser le relais de direction s'établir."
    ),
    "cimier.cycle_poll_interval_s": (
        "Période (secondes) de relecture des butées HAUT/BAS pendant un cycle. "
        "Terrain : 0.1 (100 ms)."
    ),
    "cimier.verbose_logging": (
        "Active les logs détaillés (niveau DEBUG, traces poll_status) du "
        "cimier_service. true pour le diagnostic, false en prod."
    ),
    # cimier.switch_reader (lecture des microswitches via Shelly Uni+)
    "cimier.switch_reader.type": (
        "Source de lecture des butées. « shelly_uni » : Shelly Uni+ via RPC. "
        "« noop » : lecteur factice (dev/template)."
    ),
    "cimier.switch_reader.host": (
        "Hôte/IP du Shelly Uni+ lisant les microswitches HAUT/BAS du cimier."
    ),
    "cimier.switch_reader.api": (
        "Protocole d'accès au Shelly Uni+ : « rpc » (Gen 2+) ou « legacy » (Gen 1)."
    ),
    "cimier.switch_reader.open_input_id": (
        "Index de l'entrée Shelly Uni+ du microswitch d'ouverture (HAUT) : 0 ou 1."
    ),
    "cimier.switch_reader.closed_input_id": (
        "Index de l'entrée Shelly Uni+ du microswitch de fermeture (BAS) : 0 ou 1."
    ),
    "cimier.switch_reader.invert": (
        "Inverse la lecture des microswitches NC (true) : butée atteinte = entrée "
        "false. Convention validée terrain = true."
    ),
    "cimier.switch_reader.timeout_s": (
        "Délai d'attente (secondes) des requêtes vers le Shelly Uni+."
    ),
    # cimier.power_switch (alim 24V du module cimier)
    "cimier.power_switch.type": (
        "Type du Shelly d'alimentation 24V du module cimier. « shelly_gen1 » "
        "(legacy /relay), « shelly_gen2 » (RPC) ou « noop » (factice)."
    ),
    "cimier.power_switch.host": (
        "Hôte/IP du Shelly alimentant le module cimier (coupé hors cycle)."
    ),
    "cimier.power_switch.switch_id": (
        "Index du relais d'alimentation 24V sur le Shelly power : 0 ou 1."
    ),
    # cimier.weather_provider
    "cimier.weather_provider.type": (
        "Source météo consultée avant ouverture. « noop » = toujours OK (capteur "
        "pluie : backlog séparé)."
    ),
    # cimier.automation (scheduler astropy)
    "cimier.automation.mode": (
        "Mode d'automatisation du cimier. « manual » : pilotage manuel. « semi » : "
        "fermeture auto seule. « full » : ouverture et fermeture automatiques."
    ),
    "cimier.automation.opening_sun_altitude_deg": (
        "Altitude du Soleil (degrés, négatif sous l'horizon) déclenchant l'ouverture "
        "automatique en descente. Ex. -12."
    ),
    "cimier.automation.closing_target_sun_altitude_deg": (
        "Altitude du Soleil (degrés) montante visée pour la fermeture automatique en "
        "fin de nuit. Ex. -6."
    ),
    "cimier.automation.closing_advance_minutes": (
        "Avance (minutes) avant l'altitude solaire cible pour anticiper la fermeture."
    ),
    "cimier.automation.clock_safety_margin_minutes": (
        "Marge de sécurité (minutes) ajoutée aux calculs d'horaire d'automatisation."
    ),
    "cimier.automation.parking_target_azimuth_deg": (
        "Azimut (degrés) de parking de la coupole en fin de session. Aligné sur le "
        "microswitch de calibration (45°)."
    ),
    "cimier.automation.parking_timeout_minutes": (
        "Délai maximal (minutes) accordé au GOTO de parking avant abandon."
    ),
    "cimier.automation.deparking_nudge_deg": (
        "Petit déplacement (degrés) émis à l'ouverture pour faire passer la couronne "
        "sur le microswitch de calibration 45° et réacquérir la référence encodeur."
    ),
    "cimier.automation.scheduler_interval_seconds": (
        "Période (secondes) du polling du scheduler d'automatisation cimier."
    ),
    "cimier.automation.retrigger_cooldown_hours": (
        "Délai minimal (heures) avant de pouvoir redéclencher la même action "
        "automatique (anti-rebond jour/nuit)."
    ),
    # cimier.motor_shelly (moteur ON/OFF + sens via DPDT)
    "cimier.motor_shelly.host_motor": (
        "Hôte/IP du Shelly MOT (ON/OFF du moteur cimier). Vide → moteur factice (non déployé)."
    ),
    "cimier.motor_shelly.host_dir": (
        "Hôte/IP du Shelly UPDN (sens du moteur via DPDT externe). Vide → factice."
    ),
    "cimier.motor_shelly.relay_motor": (
        "Index du relais ON/OFF moteur sur le Shelly MOT : 0 ou 1."
    ),
    "cimier.motor_shelly.relay_dir": (
        "Index du relais de sens (DPDT) sur le Shelly UPDN : 0 ou 1."
    ),
    "cimier.motor_shelly.open_dir_state": (
        "État du relais UPDN correspondant au sens d'ouverture (true = turn=on). "
        "Convention validée terrain = true."
    ),
    "cimier.motor_shelly.motor_on_relay_state": (
        "État du relais MOT qui met le moteur EN MARCHE. Convention validée terrain "
        "= false (le moteur tourne quand le relais est sur turn=off)."
    ),
    "cimier.motor_shelly.api": (
        "Protocole d'accès aux Shelly MOT/UPDN : « legacy » (Gen 1 /relay) ou « rpc »."
    ),
    "cimier.motor_shelly.timer_safety_sec": (
        "Minuterie de sécurité (secondes) côté Shelly coupant le moteur même si "
        "l'arrêt logiciel échoue."
    ),
    # --- boot_calibration ---
    "boot_calibration.fallback_sweep_deg": (
        "Amplitude (degrés) du balayage de calibration au boot autour de la position "
        "courante (séquence -sweep puis +2×sweep). Ex. 7."
    ),
    "boot_calibration.timeout_sec": (
        "Délai maximal (secondes) de la routine de calibration au boot avant passage "
        "en état dégradé."
    ),
    "boot_calibration.poll_interval_sec": (
        "Période (secondes) de scrutation du microswitch 45° pendant la calibration au boot."
    ),
}


def _infer_type(value) -> str:
    # bool AVANT int : isinstance(True, int) is True.
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    return "str"


def _collect_fields(node: dict, prefix: str, group: str | None, out: list[dict]) -> None:
    """Collecte récursivement les feuilles éditables (hors clés _-préfixées)."""
    for key, value in node.items():
        if key.startswith("_"):
            continue
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            _collect_fields(value, path, key, out)
        else:
            out.append(
                {
                    "path": path,
                    "key": key,
                    "label": key,
                    "group": group,
                    "type": _infer_type(value),
                    "help": node.get(f"_{key}_comment") or HELP_REGISTRY.get(path, ""),
                    "enum": ENUM_REGISTRY.get(path),
                }
            )


def build_config_schema(template: dict) -> list[dict]:
    """Produit la liste des sections (accordéon) depuis le squelette du template.

    Les scalaires de premier niveau (ex. `simulation`) sont regroupés sous une
    section synthétique « Général » (`key="_general"`).
    """
    sections: list[dict] = []
    general_fields: list[dict] = []

    for key, value in template.items():
        if key.startswith("_"):
            continue
        if isinstance(value, dict):
            fields: list[dict] = []
            _collect_fields(value, key, None, fields)
            sections.append(
                {
                    "key": key,
                    "label": key,
                    "help": value.get("_comment", ""),
                    "advanced": key in ADVANCED_SECTIONS,
                    "fields": fields,
                }
            )
        else:
            general_fields.append(
                {
                    "path": key,
                    "key": key,
                    "label": key,
                    "group": None,
                    "type": _infer_type(value),
                    "help": template.get(f"_{key}_comment") or HELP_REGISTRY.get(key, ""),
                    "enum": ENUM_REGISTRY.get(key),
                }
            )

    if general_fields:
        sections.insert(
            0,
            {
                "key": "_general",
                "label": "Général",
                "help": "",
                "advanced": False,
                "fields": general_fields,
            },
        )
    return sections


class ConfigValidationError(ValueError):
    """Type incohérent pour une clé lors d'une sauvegarde UI."""

    def __init__(self, path: str, message: str = "") -> None:
        self.path = path
        super().__init__(message or f"Type invalide pour « {path} »")


def validate_and_coerce(values: dict, template: dict, prefix: str = "") -> dict:
    """Vérifie/coerce les feuilles de `values` selon le type des feuilles du template.

    Ne valide que les chemins présents des deux côtés (le merge structurel gère le
    reste). Lève ConfigValidationError(path) au premier type incohérent.
    """
    out: dict = {}
    for key, val in values.items():
        if key.startswith("_"):
            continue
        path = f"{prefix}.{key}" if prefix else key
        if key not in template:
            continue  # clé inconnue : ignorée ici, retirée par le merge
        tmpl_val = template[key]
        if isinstance(tmpl_val, dict) and isinstance(val, dict):
            out[key] = validate_and_coerce(val, tmpl_val, path)
            continue
        expected = _infer_type(tmpl_val)
        if expected == "bool":
            if not isinstance(val, bool):
                raise ConfigValidationError(path)
            out[key] = val
        elif expected == "int":
            if isinstance(val, bool) or not isinstance(val, int):
                raise ConfigValidationError(path)
            out[key] = val
        elif expected == "float":
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                raise ConfigValidationError(path)
            out[key] = float(val)
        else:  # str
            if not isinstance(val, str):
                raise ConfigValidationError(path)
            out[key] = val
    return out


def _atomic_write_json(path: Path, data: dict) -> None:
    """Écrit `data` en JSON de façon atomique (tmp unique par process + os.replace)."""
    tmp = path.parent / f"{path.name}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def _collect_leaf_paths(value, prefix: str, out: list[str]) -> None:
    """Ajoute à `out` tous les chemins de feuilles sous `value`."""
    if isinstance(value, dict) and value:
        for k, v in value.items():
            _collect_leaf_paths(v, f"{prefix}.{k}" if prefix else k, out)
    else:
        out.append(prefix)


def _structural_merge(
    user: dict, template: dict, prefix: str = ""
) -> tuple[dict, list[str], list[str]]:
    """Merge la STRUCTURE du template dans `user`, en préservant les VALEURS user.

    Retourne (merged, added_paths, removed_paths).
    - clé des deux côtés, dicts → récursion ; sinon → valeur user gardée (Option 1)
    - clé template seule → défaut du template (added)
    - clé user seule → retirée (removed)
    """
    added: list[str] = []
    removed: list[str] = []
    merged: dict = {}
    for key, tmpl_val in template.items():
        path = f"{prefix}.{key}" if prefix else key
        if key in user:
            user_val = user[key]
            if isinstance(tmpl_val, dict) and isinstance(user_val, dict):
                sub, sub_add, sub_rem = _structural_merge(user_val, tmpl_val, path)
                merged[key] = sub
                added.extend(sub_add)
                removed.extend(sub_rem)
            else:
                merged[key] = user_val  # valeur user sacrée
        else:
            merged[key] = tmpl_val
            if not key.startswith("_"):
                _collect_leaf_paths(tmpl_val, path, added)
    for key in user:
        if key not in template and not key.startswith("_"):
            removed.append(f"{prefix}.{key}" if prefix else key)
    return merged, added, removed


@dataclass
class ConfigReport:
    status: str
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    backup_timestamp: str | None = None
    message: str = ""


_REPORT_CACHE: dict[str, ConfigReport] = {}


def _load_json_or_none(path: Path) -> dict | None:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _backup_mtime_iso(path: Path) -> str | None:
    if not path.exists():
        return None
    import datetime

    ts = path.stat().st_mtime
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).isoformat()


def _run_ensure(config_path: Path, template_path: Path, backup_path: Path) -> ConfigReport:
    template = _load_json_or_none(template_path)
    if template is None:
        raise RuntimeError(f"Template introuvable ou invalide : {template_path}")

    backup_ts = _backup_mtime_iso(backup_path)

    # 1. Déterminer la config de base + le statut primaire.
    if not config_path.exists():
        backup = _load_json_or_none(backup_path)
        if backup is not None:
            user, status = backup, "restored_from_backup"
        else:
            user, status = dict(template), "bootstrapped_from_template"
    else:
        parsed = _load_json_or_none(config_path)
        if parsed is not None:
            user, status = parsed, "unchanged"
        else:
            backup = _load_json_or_none(backup_path)
            if backup is not None:
                user, status = backup, "recovered_corruption"
            else:
                user, status = dict(template), "corruption_no_backup"

    # 2. Merge structurel vs template.
    merged, added, removed = _structural_merge(user, template)

    # 3. Décider d'écrire config.json.
    structural_change = bool(added or removed)
    if status == "unchanged":
        if structural_change:
            status = "migrated"
            _atomic_write_json(config_path, merged)
        # sinon : on ne réécrit rien (intact au bit près)
    else:
        _atomic_write_json(config_path, merged)

    # 4. lastgood = config valide finale.
    _atomic_write_json(backup_path, merged)

    return ConfigReport(
        status=status,
        added=added,
        removed=removed,
        backup_timestamp=backup_ts,
        message=_message_for(status, added, removed, backup_ts),
    )


def _message_for(status, added, removed, backup_ts) -> str:
    if status == "saved":
        return "Configuration enregistrée. Redémarre les services pour l'appliquer."
    if status == "unchanged":
        return "Configuration inchangée."
    if status == "migrated":
        return (
            f"Configuration migrée : {len(added)} paramètre(s) ajouté(s) "
            f"à leur valeur par défaut. Tes réglages ont été conservés."
        )
    if status == "restored_from_backup":
        return f"config.json absent — restauré depuis la sauvegarde du {backup_ts}."
    if status == "recovered_corruption":
        return f"config.json illisible — restauré depuis la sauvegarde du {backup_ts}."
    if status == "bootstrapped_from_template":
        return "Première config générée depuis le gabarit — à renseigner."
    if status == "corruption_no_backup":
        return (
            "config.json corrompu et aucune sauvegarde — valeurs par défaut "
            "chargées, reconfiguration requise."
        )
    return ""


def write_user_config(
    values: dict,
    config_path: Path = DEFAULT_CONFIG_PATH,
    template_path: Path = DEFAULT_TEMPLATE_PATH,
    backup_path: Path = DEFAULT_BACKUP_PATH,
) -> ConfigReport:
    """Persiste les valeurs éditées par l'UI, à travers le noyau A.

    Valide les types vs template, merge la structure (réinjecte les _comment et
    écarte toute clé inconnue), écrit atomiquement, rafraîchit lastgood, invalide
    la mémoïsation. Lève ConfigValidationError(path) si un type est incohérent.
    """
    template = _load_json_or_none(template_path)
    if template is None:
        raise RuntimeError(f"Template introuvable ou invalide : {template_path}")

    coerced = validate_and_coerce(values, template)
    merged, added, removed = _structural_merge(coerced, template)

    _atomic_write_json(config_path, merged)
    _atomic_write_json(backup_path, merged)
    _REPORT_CACHE.pop(str(config_path), None)

    return ConfigReport(
        status="saved",
        added=added,
        removed=removed,
        backup_timestamp=_backup_mtime_iso(backup_path),
        message=_message_for("saved", added, removed, None),
    )


def ensure_config_ready(
    config_path: Path = DEFAULT_CONFIG_PATH,
    template_path: Path = DEFAULT_TEMPLATE_PATH,
    backup_path: Path = DEFAULT_BACKUP_PATH,
    *,
    force: bool = False,
) -> ConfigReport:
    """Garantit un config.json valide et à jour structurellement. Mémoïsé par process."""
    key = str(config_path)
    if not force and key in _REPORT_CACHE:
        return _REPORT_CACHE[key]
    report = _run_ensure(config_path, template_path, backup_path)
    _REPORT_CACHE[key] = report
    return report
