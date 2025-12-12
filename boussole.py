#!/usr/bin/env python3
# ems22a_ring_gauge_daemon_client.py
# Version modifiée pour lire l'angle via le daemon EMS22A (fichier JSON)
# Utilise DaemonEncoderReader pour la lecture centralisée

import time
import math
import json
import atexit
import tkinter as tk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
import matplotlib.animation as animation

# Import du lecteur centralisé
from core.hardware.moteur import DaemonEncoderReader

# ==========================
# --- CONSTANTES ---
# ==========================
REFRESH_RATE_HZ = 60                           # 60 FPS suffisent
ANGLE_FILE = "last_angle.json"
TEST_MODE = False                              # Simulation si daemon absent

# ==========================
# --- VARIABLES ---
# ==========================
last_angle_display = 0.0
_daemon_reader = DaemonEncoderReader()


# ==========================
# --- LECTURE ANGLE VIA DAEMON ---
# ==========================
def get_daemon_angle():
    """
    Lit l'angle via DaemonEncoderReader.
    Si fichier indisponible → mode test.
    """
    try:
        return _daemon_reader.read_angle(timeout_ms=50)
    except RuntimeError:
        # Mode TEST si daemon non lancé
        if TEST_MODE:
            return (time.time() * 20) % 360.0
        else:
            return 0.0


# ==========================
# --- SAUVEGARDE ---
# ==========================
def save_angle():
    try:
        with open(ANGLE_FILE, "w") as f:
            json.dump({"angle": last_angle_display}, f)
    except Exception as e:
        print("Erreur sauvegarde:", e)

def load_angle():
    try:
        with open(ANGLE_FILE, "r") as f:
            data = json.load(f)
            return float(data.get("angle", 0.0))
    except Exception:
        return 0.0

atexit.register(save_angle)


# ==========================
# --- INTERFACE ---
# ==========================
root = tk.Tk()
root.title("Mesure angulaire (daemon EMS22A)")

fig, ax = plt.subplots(figsize=(5, 5))
ax.set_aspect('equal')
ax.axis('off')

# Cercle
circle = plt.Circle((0, 0), 1, fill=False, lw=2)
ax.add_artist(circle)

# Points cardinaux
cardinals = {'N': (0, 1.12), 'E': (1.12, 0), 'S': (0, -1.18), 'O': (-1.12, 0)}
for txt, (x, y) in cardinals.items():
    ax.text(x, y, txt, fontsize=14, fontweight='bold', ha='center', va='center')

# Graduations internes
for angle in range(0, 360, 45):
    rad = math.radians(90 - angle)
    x1, y1 = math.cos(rad), math.sin(rad)
    ax.plot([0.92 * x1, 1.0 * x1], [0.92 * y1, 1.0 * y1], color="black", lw=1)
    ax.text(0.80 * x1, 0.80 * y1, f"{angle}°", ha="center", va="center", fontsize=9)

# Aiguille
needle, = ax.plot([0, 0], [0, 1], 'r-', lw=4)

# Texte angle
angle_text = ax.text(0, -1.35, "", fontsize=16, color="blue",
                     ha="center", fontweight="bold")


# ==========================
# --- ANIMATION ---
# ==========================
def animate(_):
    global last_angle_display

    # Lecture angle via daemon
    # angle_display = get_daemon_angle() * rotation_sign
    angle_display = get_daemon_angle()
    angle_display %= 360.0

    last_angle_display = angle_display

    # Convertir en coordonnées
    rad = math.radians(angle_display)
    x = math.sin(rad)
    y = math.cos(rad)

    needle.set_data([0, x], [0, y])
    angle_text.set_text(f"Angle couronne = {angle_display:0.1f}°")

    return needle, angle_text


# ==========================
# --- LANCEMENT ---
# ==========================
try:
    last_angle_display = load_angle()
    canvas = FigureCanvasTkAgg(fig, master=root)
    canvas.get_tk_widget().pack(fill=tk.BOTH, expand=1)

    # Animation créée APRÈS intégration canvas (CRITIQUE!)
    ani = animation.FuncAnimation(fig, animate,
                                  interval=1000 / REFRESH_RATE_HZ,
                                  blit=False,
                                  cache_frame_data=False)

    root.mainloop()

finally:
    save_angle()