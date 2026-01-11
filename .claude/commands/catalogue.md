---
description: Recherche et gestion du catalogue d'objets celestes
category: utilities-debugging
argument-hint: [optionnel] nom d'objet ou commande (search, list, visible, info)
---

# Catalogue DriftApp

Recherche d'objets celestes et verification de visibilite.

## Instructions

Tu vas explorer le catalogue astronomique : **$ARGUMENTS**

### 1. Recherche d'un Objet

```python
import sys
sys.path.insert(0, '.')
from core.observatoire.catalogue import GestionnaireCatalogue

catalogue = GestionnaireCatalogue()

# Rechercher un objet
objet = "$ARGUMENTS" or "M31"
result = catalogue.rechercher(objet)

if result:
    print(f"=== {result['nom']} ===")
    print(f"Type: {result.get('type', 'N/A')}")
    print(f"Constellation: {result.get('constellation', 'N/A')}")
    print(f"Magnitude: {result.get('magnitude', 'N/A')}")
    print(f"RA (J2000): {result['ra_deg']:.4f}° ({result['ra_deg']/15:.2f}h)")
    print(f"DEC (J2000): {result['dec_deg']:.4f}°")
else:
    print(f"Objet '{objet}' non trouve dans le catalogue")
    print("\nRecherche partielle:")
    # Recherche partielle
    matches = [o for o in catalogue.get_objets_disponibles()
               if objet.lower() in o.lower()][:10]
    for m in matches:
        print(f"  - {m}")
```

### 2. Liste des Objets Disponibles

```python
import sys
sys.path.insert(0, '.')
from core.observatoire.catalogue import GestionnaireCatalogue

catalogue = GestionnaireCatalogue()
objets = catalogue.get_objets_disponibles()

# Grouper par type/prefixe
messier = [o for o in objets if o.startswith('M')]
ngc = [o for o in objets if o.startswith('NGC')]
etoiles = [o for o in objets if not o.startswith(('M', 'NGC', 'IC'))]

print(f"=== CATALOGUE DRIFTAPP ===")
print(f"Total: {len(objets)} objets")
print(f"\nMessier: {len(messier)}")
print(f"NGC: {len(ngc)}")
print(f"Etoiles/Autres: {len(etoiles)}")

print(f"\n=== OBJETS MESSIER ({len(messier)}) ===")
for i, obj in enumerate(sorted(messier)):
    print(f"  {obj}", end="")
    if (i + 1) % 10 == 0:
        print()
print()

print(f"\n=== ETOILES PRINCIPALES ===")
for obj in sorted(etoiles)[:20]:
    print(f"  {obj}")
```

### 3. Objets Visibles Maintenant

```python
import sys
sys.path.insert(0, '.')
from datetime import datetime, timezone
from core.observatoire.catalogue import GestionnaireCatalogue
from core.observatoire.calculations import AstronomicalCalculations
from core.config.config import get_site_config

# Config
lat, lon, _, _, _ = get_site_config()
calc = AstronomicalCalculations(lat, lon)
catalogue = GestionnaireCatalogue()
now = datetime.now(timezone.utc)

print(f"=== OBJETS VISIBLES ===")
print(f"Date/Heure: {now.strftime('%Y-%m-%d %H:%M UTC')}")
print(f"Site: {lat}°N, {lon}°E")
print()

visible = []
for nom in catalogue.get_objets_disponibles():
    obj = catalogue.rechercher(nom)
    if obj:
        az, alt = calc.calculer_coords_horizontales(
            obj['ra_deg'], obj['dec_deg'], now
        )
        if alt > 15:  # Au-dessus de 15°
            visible.append({
                'nom': nom,
                'alt': alt,
                'az': az,
                'mag': obj.get('magnitude', 99)
            })

# Trier par altitude (plus haut = mieux)
visible.sort(key=lambda x: x['alt'], reverse=True)

print(f"{'Objet':<15} {'Alt':>6} {'Az':>6} {'Mag':>5}")
print("-" * 35)
for obj in visible[:30]:
    mag_str = f"{obj['mag']:.1f}" if obj['mag'] < 99 else "N/A"
    print(f"{obj['nom']:<15} {obj['alt']:>5.1f}° {obj['az']:>5.1f}° {mag_str:>5}")

print(f"\nTotal visible (>15°): {len(visible)} objets")
```

### 4. Planetes Visibles

```python
import sys
sys.path.insert(0, '.')
from datetime import datetime, timezone
from core.observatoire.ephemerides import PlanetaryEphemerides
from core.config.config import get_site_config

# Config
lat, lon, _, _, _ = get_site_config()
now = datetime.now(timezone.utc)
eph = PlanetaryEphemerides()

planets = ['Mercury', 'Venus', 'Mars', 'Jupiter', 'Saturn', 'Uranus', 'Neptune']

print(f"=== PLANETES ===")
print(f"Date/Heure: {now.strftime('%Y-%m-%d %H:%M UTC')}")
print()

print(f"{'Planete':<10} {'Alt':>6} {'Az':>6} {'Visible':<10}")
print("-" * 35)

for planet in planets:
    try:
        az, alt = eph.get_planet_position(planet, now, lat, lon)
        if alt > 0:
            status = "OUI" if alt > 15 else "Basse"
        else:
            status = "Non"
        print(f"{planet:<10} {alt:>5.1f}° {az:>5.1f}° {status:<10}")
    except Exception as e:
        print(f"{planet:<10} Erreur: {e}")
```

### 5. Information Detaillee sur un Objet

```python
import sys
sys.path.insert(0, '.')
from datetime import datetime, timezone, timedelta
from core.observatoire.catalogue import GestionnaireCatalogue
from core.observatoire.calculations import AstronomicalCalculations
from core.tracking.abaque_manager import AbaqueManager
from core.config.config import get_site_config

# Config
lat, lon, _, _, _ = get_site_config()
calc = AstronomicalCalculations(lat, lon)
catalogue = GestionnaireCatalogue()
abaque = AbaqueManager()
abaque.load_abaque()

objet = "$ARGUMENTS" or "M31"
result = catalogue.rechercher(objet)

if result:
    now = datetime.now(timezone.utc)
    az, alt = calc.calculer_coords_horizontales(
        result['ra_deg'], result['dec_deg'], now
    )

    print(f"=== {result['nom']} - DETAILS ===")
    print(f"\nCatalogue:")
    print(f"  Type: {result.get('type', 'N/A')}")
    print(f"  Constellation: {result.get('constellation', 'N/A')}")
    print(f"  Magnitude: {result.get('magnitude', 'N/A')}")
    print(f"  RA (J2000): {result['ra_deg']:.4f}°")
    print(f"  DEC (J2000): {result['dec_deg']:.4f}°")

    print(f"\nPosition actuelle ({now.strftime('%H:%M UTC')}):")
    print(f"  Azimut: {az:.1f}°")
    print(f"  Altitude: {alt:.1f}°")

    if alt > 0:
        print(f"  Status: VISIBLE")

        # Position coupole
        pos_coupole, _ = abaque.get_dome_position(alt, az)
        print(f"  Position coupole: {pos_coupole:.1f}°")

        # Mode adaptatif
        if alt >= 75:
            mode = "CONTINUOUS"
        elif alt >= 68:
            mode = "CRITICAL"
        else:
            mode = "NORMAL"
        print(f"  Mode adaptatif: {mode}")
    else:
        print(f"  Status: SOUS L'HORIZON")

    # Evolution sur 6h
    print(f"\nEvolution (prochaines 6h):")
    print(f"  {'Heure':<8} {'Alt':>6} {'Az':>6} {'Status':<12}")
    print("  " + "-" * 35)
    for h in range(0, 7):
        future = now + timedelta(hours=h)
        az_f, alt_f = calc.calculer_coords_horizontales(
            result['ra_deg'], result['dec_deg'], future
        )
        if alt_f > 15:
            status = "Optimal" if alt_f < 75 else "Zenith"
        elif alt_f > 0:
            status = "Basse"
        else:
            status = "Invisible"
        print(f"  +{h}h      {alt_f:>5.1f}° {az_f:>5.1f}° {status:<12}")
else:
    print(f"Objet '{objet}' non trouve")
```

### 6. Meilleurs Objets pour ce Soir

```python
import sys
sys.path.insert(0, '.')
from datetime import datetime, timezone, timedelta
from core.observatoire.catalogue import GestionnaireCatalogue
from core.observatoire.calculations import AstronomicalCalculations
from core.config.config import get_site_config

lat, lon, _, _, _ = get_site_config()
calc = AstronomicalCalculations(lat, lon)
catalogue = GestionnaireCatalogue()

# Calculer pour 22h ce soir
now = datetime.now(timezone.utc)
tonight = now.replace(hour=21, minute=0, second=0, microsecond=0)
if tonight < now:
    tonight += timedelta(days=1)

print(f"=== SUGGESTIONS POUR CE SOIR ===")
print(f"Heure de reference: {tonight.strftime('%Y-%m-%d %H:%M UTC')}")
print()

candidates = []
for nom in catalogue.get_objets_disponibles():
    obj = catalogue.rechercher(nom)
    if obj:
        az, alt = calc.calculer_coords_horizontales(
            obj['ra_deg'], obj['dec_deg'], tonight
        )
        if 30 < alt < 70:  # Zone optimale
            mag = obj.get('magnitude', 99)
            candidates.append({
                'nom': nom,
                'alt': alt,
                'az': az,
                'mag': mag,
                'type': obj.get('type', 'N/A')
            })

# Trier par magnitude (plus brillant = mieux)
candidates.sort(key=lambda x: x['mag'])

print(f"{'Objet':<15} {'Type':<12} {'Alt':>5} {'Az':>5} {'Mag':>4}")
print("-" * 45)
for obj in candidates[:20]:
    mag_str = f"{obj['mag']:.1f}" if obj['mag'] < 99 else "?"
    print(f"{obj['nom']:<15} {obj['type']:<12} {obj['alt']:>4.0f}° {obj['az']:>4.0f}° {mag_str:>4}")

print(f"\nTotal dans zone optimale (30-70°): {len(candidates)}")
```

### 7. Recherche par Constellation

```python
import sys
sys.path.insert(0, '.')
from core.observatoire.catalogue import GestionnaireCatalogue

catalogue = GestionnaireCatalogue()
constellation = "$ARGUMENTS" or "Orion"

print(f"=== OBJETS DANS {constellation.upper()} ===")

objets_const = []
for nom in catalogue.get_objets_disponibles():
    obj = catalogue.rechercher(nom)
    if obj and obj.get('constellation', '').lower() == constellation.lower():
        objets_const.append(obj)

if objets_const:
    objets_const.sort(key=lambda x: x.get('magnitude', 99))
    for obj in objets_const:
        mag = obj.get('magnitude', 'N/A')
        print(f"  {obj['nom']:<15} Mag: {mag}")
else:
    print(f"Aucun objet trouve dans {constellation}")
    print("\nConstellations disponibles:")
    consts = set()
    for nom in catalogue.get_objets_disponibles():
        obj = catalogue.rechercher(nom)
        if obj and obj.get('constellation'):
            consts.add(obj['constellation'])
    for c in sorted(consts):
        print(f"  - {c}")
```

### 8. Export Liste pour Observation

```python
import sys
import json
sys.path.insert(0, '.')
from datetime import datetime, timezone
from core.observatoire.catalogue import GestionnaireCatalogue
from core.observatoire.calculations import AstronomicalCalculations
from core.config.config import get_site_config

lat, lon, _, _, _ = get_site_config()
calc = AstronomicalCalculations(lat, lon)
catalogue = GestionnaireCatalogue()
now = datetime.now(timezone.utc)

# Generer liste d'observation
observation_list = []
for nom in catalogue.get_objets_disponibles():
    obj = catalogue.rechercher(nom)
    if obj:
        az, alt = calc.calculer_coords_horizontales(
            obj['ra_deg'], obj['dec_deg'], now
        )
        if alt > 20:
            observation_list.append({
                'nom': nom,
                'ra_deg': obj['ra_deg'],
                'dec_deg': obj['dec_deg'],
                'altitude': round(alt, 1),
                'azimut': round(az, 1),
                'magnitude': obj.get('magnitude'),
                'type': obj.get('type'),
                'constellation': obj.get('constellation')
            })

# Sauvegarder
output_file = f"logs/observation_list_{now.strftime('%Y%m%d_%H%M')}.json"
with open(output_file, 'w') as f:
    json.dump(observation_list, f, indent=2)

print(f"Liste exportee: {output_file}")
print(f"Objets: {len(observation_list)}")
```

### Resume

```
=== COMMANDES CATALOGUE ===

Recherche:
  /catalogue M31          # Info sur M31
  /catalogue Vega         # Info sur Vega
  /catalogue Jupiter      # Position planete

Listes:
  /catalogue list         # Tous les objets
  /catalogue visible      # Visibles maintenant
  /catalogue tonight      # Suggestions ce soir

Filtres:
  /catalogue Orion        # Objets dans Orion
  /catalogue planets      # Planetes visibles

Export:
  /catalogue export       # JSON pour observation
```
