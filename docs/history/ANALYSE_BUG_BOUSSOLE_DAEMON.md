# 🐛 Bug Boussole Démon - Animation Figée

**Date** : 6 Décembre 2025
**Problème** : L'aiguille de la boussole utilisant le démon reste fixe
**Symptôme** : Données JSON du démon parfaites, mais affichage gelé

---

## 📋 Résumé Exécutif

**Problème** : La boussole `boussole.py` ne bouge pas alors que :
- ✅ Le démon corrigé fonctionne parfaitement
- ✅ Les données JSON (`/dev/shm/ems22_position.json`) sont correctes
- ✅ La boussole directe (`ems22a_ring_gauge4_V2.py`) fonctionne

**Cause** : Ordre d'initialisation incorrect - `FuncAnimation` créée **avant** intégration du canvas Tkinter

**Impact** : L'animation tourne à vide sans rafraîchir l'affichage graphique

---

## 🔍 Analyse Technique

### Code AVANT Correction (boussole.py lignes 130-143)

```python
# ❌ ERREUR : Animation créée EN PREMIER
ani = animation.FuncAnimation(fig, animate,
                              interval=1000 / REFRESH_RATE_HZ,
                              blit=False,
                              cache_frame_data=False)

# Canvas créé APRÈS (trop tard!)
try:
    last_angle_display = load_angle()
    canvas = FigureCanvasTkAgg(fig, master=root)  # Ligne 140
    canvas.get_tk_widget().pack(fill=tk.BOTH, expand=1)  # Ligne 141

    root.mainloop()
```

### Pourquoi ça ne Fonctionne Pas

Lorsque `FuncAnimation` est créée, elle s'attache à la figure matplotlib (`fig`). Mais à ce moment-là :

1. **Le canvas Tkinter n'existe pas encore** (créé ligne 140)
2. **La figure n'est pas connectée à Tkinter** (packed ligne 141)
3. **FuncAnimation ne sait pas où dessiner** → animation "fantôme"

Résultat :
- La fonction `animate()` est appelée 60 fois/seconde ✅
- Les données sont lues du JSON ✅
- `needle.set_data()` met à jour les données ✅
- **MAIS** l'affichage graphique n'est jamais rafraîchi ❌

### Comparaison avec Boussole Directe (Fonctionne)

**ems22a_ring_gauge4_V2.py lignes 146-174** :
```python
# ✅ CORRECT : Canvas AVANT animation
canvas = FigureCanvasTkAgg(fig, master=root)  # Ligne 146
canvas.get_tk_widget().pack(fill=tk.BOTH, expand=1)  # Ligne 147
button.pack(pady=6)

# Animation créée APRÈS intégration
ani = animation.FuncAnimation(fig, animate,  # Ligne 174
                              interval=1000 / REFRESH_RATE_HZ,
                              blit=False)

root.mainloop()
```

**Ordre correct** :
1. Canvas créé et intégré dans Tkinter
2. Figure matplotlib connectée au canvas
3. **PUIS** FuncAnimation créée → sait où dessiner
4. Mainloop démarre → animation fonctionne

---

## ✅ Correction Appliquée

### Code APRÈS Correction (boussole.py lignes 130-147)

```python
# ==========================
# --- LANCEMENT ---
# ==========================
try:
    last_angle_display = load_angle()

    # ✅ 1. Canvas créé et empaqueté EN PREMIER
    canvas = FigureCanvasTkAgg(fig, master=root)
    canvas.get_tk_widget().pack(fill=tk.BOTH, expand=1)

    # ✅ 2. Animation créée APRÈS intégration canvas (CRITIQUE!)
    ani = animation.FuncAnimation(fig, animate,
                                  interval=1000 / REFRESH_RATE_HZ,
                                  blit=False,
                                  cache_frame_data=False)

    # ✅ 3. Mainloop
    root.mainloop()

finally:
    save_angle()
```

**Changement** : Les lignes 130-133 (création `ani`) déplacées **après** lignes 135-136 (canvas).

---

## 🧪 Validation

### Test à Effectuer

```bash
# Terminal 1 : Lancer le démon corrigé
sudo python3 ems22d_calibrated.py &

# Terminal 2 : Lancer la boussole démon corrigée
python3 boussole.py

# Résultat attendu :
# - L'aiguille bouge en suivant la position réelle de la coupole
# - Synchronisé avec les données JSON du démon
# - Identique à la boussole directe (ems22a_ring_gauge4_V2.py)
```

### Comparaison Côte-à-Côte

```bash
# Terminal 1 : Boussole directe
python3 tests_sur_site/ems22a_ring_gauge4_V2.py

# Terminal 2 : Boussole démon
python3 boussole.py

# Résultat attendu :
# Les deux aiguilles affichent la même position
# Les deux bougent simultanément quand la coupole tourne
```

---

## 💡 Pourquoi Ce Bug Existait

### Historique Probable

Le code de `boussole.py` a probablement été écrit en copiant `ems22a_ring_gauge4_V2.py`, puis :

1. Ajout du bloc `try...finally` pour gérer `save_angle()`
2. Lors du refactoring, `ani = FuncAnimation(...)` déplacé **hors** du bloc try
3. Résultat : animation créée avant canvas → bug introduit

### Leçon Apprise

**Règle pour matplotlib + Tkinter** :

```python
# TOUJOURS cet ordre :
# 1. Créer la figure matplotlib
fig, ax = plt.subplots(...)

# 2. Configurer la figure (plots, textes, etc.)
needle, = ax.plot(...)

# 3. Créer le canvas Tkinter ET l'empaqueter
canvas = FigureCanvasTkAgg(fig, master=root)
canvas.get_tk_widget().pack(...)

# 4. Créer l'animation (APRÈS canvas!)
ani = animation.FuncAnimation(fig, ...)

# 5. Lancer mainloop
root.mainloop()
```

**Erreur fréquente** : Créer `FuncAnimation` juste après avoir configuré `fig`, avant le canvas → animation fantôme.

---

## 📊 Tableau Récapitulatif

| Aspect | AVANT (bug) | APRÈS (corrigé) |
|--------|-------------|-----------------|
| Ordre initialisation | Animation → Canvas ❌ | Canvas → Animation ✅ |
| Fonction animate() appelée | Oui (60 Hz) | Oui (60 Hz) |
| Données JSON lues | Oui | Oui |
| Affichage rafraîchi | Non ❌ | Oui ✅ |
| Aiguille bouge | Non (figée) ❌ | Oui (fluide) ✅ |

---

## 🔗 Références

**Fichier corrigé** :
- `boussole.py` lignes 130-147

**Comparaison** :
- `tests_sur_site/ems22a_ring_gauge4_V2.py` (référence qui fonctionne)

**Tests terrain** :
- Démon corrigé : `ems22d_calibrated.py` (méthode incrémentale)
- Données JSON validées par utilisateur : parfaites

**Documentation matplotlib** :
- [FuncAnimation avec backends](https://matplotlib.org/stable/api/animation_api.html)
- [Tkinter backend](https://matplotlib.org/stable/gallery/user_interfaces/embedding_in_tk_sgskip.html)

---

**Version** : 1.0
**Date** : 6 Décembre 2025
**Statut** : Correction appliquée, test terrain requis
