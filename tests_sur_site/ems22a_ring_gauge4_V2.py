#!/usr/bin/env python3
# ems22a_ring_gauge_fixed.py
# Version relue : importations et indentation corrigées

import time
import math
import json
import atexit
import tkinter as tk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
import matplotlib.animation as animation

# spidev est optionnel (peut ne pas être installé sur la machine de test)
try:
    import spidev
    SPIDEV_AVAILABLE = True
except Exception:
    SPIDEV_AVAILABLE = False

# =====================
# --- CONSTANTES ---
# =====================
CALIBRATION_FACTOR = 0.01077/0.9925   # calibration d'origine conservée
REFRESH_RATE_HZ = 200           # fréquence d’échantillonnage (Hz)
ANGLE_FILE = "last_angle.json"
TEST_MODE = False               # True pour simulation sans SPI

# =====================
# --- SPI setup ---
# =====================
if SPIDEV_AVAILABLE and not TEST_MODE:
    spi = spidev.SpiDev()
    spi.open(0, 0)
    spi.max_speed_hz = 1000000
    spi.mode = 0
else:
    spi = None

# =====================
# --- VARIABLES ---
# =====================
prev_value = 0
total_counts = 0
last_angle_display = 0.0
rotation_sign = -1  # 1 = horaire

# =====================
# --- LECTURE EMS22A ---
# =====================
def read_raw10():
    """Lecture 10 bits correcte pour EMS22A"""
    if TEST_MODE:
        t = time.time()
        return int(((t * 50) % 1024))  # simulation
    if not spi:
        raise RuntimeError("SPI non initialisé.")
    resp = spi.xfer2([0x00, 0x00])
    # lecture correcte : bits [13:4] -> ((high & 0x3F) << 4) | (low >> 4)
    raw = ((resp[0] & 0x3F) << 4) | (resp[1] >> 4)
    return raw

# =====================
# --- CALCUL ANGLES ---
# =====================
def update_counts():
    global prev_value, total_counts
    cur = read_raw10()
    diff = cur - prev_value
    if diff > 512:
        diff -= 1024
    elif diff < -512:
        diff += 1024
    total_counts += diff
    prev_value = cur
    return total_counts

def get_ring_angle_deg():
    counts = update_counts()
    wheel_degrees = (counts / 1024.0) * 360.0
    ring_degrees = wheel_degrees * CALIBRATION_FACTOR * rotation_sign
    return ring_degrees % 360.0

# =====================
# --- SAUVEGARDE ---
# =====================
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

# =====================
# --- INTERFACE ---
# =====================
root = tk.Tk()
root.title("Mesure angulaire de la couronne")

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

# Graduations tous les 45°, texte à l'intérieur
for angle in range(0, 360, 45):
    rad = math.radians(90 - angle)
    x1, y1 = math.cos(rad), math.sin(rad)
    ax.plot([0.92 * x1, 1.0 * x1], [0.92 * y1, 1.0 * y1], color="black", lw=1)
    ax.text(0.80 * x1, 0.80 * y1, f"{angle}°", ha="center", va="center", fontsize=9)

# Aiguille
needle, = ax.plot([0, 0], [0, 1], 'r-', lw=4)

# Texte angle
angle_text = ax.text(0, -1.35, "", fontsize=16, color="blue", ha="center", fontweight="bold")

# Bouton Reset
def reset_angle():
    global total_counts, prev_value, last_angle_display
    prev_value = read_raw10() if (spi or TEST_MODE) else 0
    total_counts = 0
    last_angle_display = 0.0
    save_angle()

button = tk.Button(root, text="Reset angle", command=reset_angle)
canvas = FigureCanvasTkAgg(fig, master=root)
canvas.get_tk_widget().pack(fill=tk.BOTH, expand=1)
button.pack(pady=6)

last_angle_display = load_angle()

# =====================
# --- ANIMATION ---
# =====================
def animate(_):
    global last_angle_display
    try:
        angle_display = get_ring_angle_deg()
    except Exception as e:
        angle_display = 0.0
        print("SPI/read error:", e)

    last_angle_display = angle_display % 360.0

    # Mapping so that 0° -> top, angles increase clockwise:
    rad = math.radians(last_angle_display)
    x = math.sin(rad)
    y = math.cos(rad)

    needle.set_data([0, x], [0, y])
    angle_text.set_text(f"Angle couronne = {last_angle_display:0.1f}°")
    return needle, angle_text

ani = animation.FuncAnimation(fig, animate, interval=1000 / REFRESH_RATE_HZ, blit=False)

# =====================
# --- LANCEMENT ---
# =====================
try:
    root.mainloop()
finally:
    if spi:
        try:
            spi.close()
        except Exception:
            pass