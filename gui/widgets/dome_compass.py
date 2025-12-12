"""
Widget boussole affichant la position de la coupole.
- Cercle gris représentant la coupole vue de dessus
- Arc rouge sur le pourtour (position actuelle - 70cm sur périmètre π×200cm ≈ 40°)
- Trait noir au centre exact de la trappe pour comparaison visuelle
- Tube de télescope au centre orienté vers la cible
- Flèche bleue sortant du tube et indiquant la position cible
"""

from kivy.uix.widget import Widget
from kivy.uix.label import Label
from kivy.graphics import Color, Ellipse, Line, Triangle, PushMatrix, PopMatrix, Rotate
from kivy.properties import NumericProperty
from math import cos, sin, radians, pi


class DomeCompass(Widget):
    """
    Afficheur circulaire de position de coupole.

    - Arc rouge : position actuelle (largeur 40° ≈ 70cm sur périmètre π×200cm)
    - Flèche bleue : position cible (sort d'un tube de télescope au centre)
    - Trait noir au centre de la trappe pour marquer le centre exact
    - Angles en degrés astronomiques (0° = Nord)
    """

    # Position actuelle de la coupole (degrés)
    position_actuelle = NumericProperty(0)

    # Position cible de la coupole (degrés)
    position_cible = NumericProperty(0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Permettre au widget de s'adapter à son conteneur
        self.size_hint = (1, 1)

        # Créer les labels cardinaux (N, E, S, O)
        self._cardinal_labels = {}
        for direction in ['N', 'E', 'S', 'O']:
            label = Label(
                text=direction,
                font_size='12sp',
                color=(0.7, 0.7, 0.7, 1),
                bold=True,
                size_hint=(None, None),
                halign='center',
                valign='middle'
            )
            label.bind(texture_size=label.setter('size'))
            self._cardinal_labels[direction] = label
            self.add_widget(label)

        # Bind pour redessiner quand les positions changent
        self.bind(pos=self._update_canvas, size=self._update_canvas)
        self.bind(position_actuelle=self._update_canvas)
        self.bind(position_cible=self._update_canvas)

    def _update_canvas(self, *args):
        """Redessine la boussole."""
        # Utiliser canvas.before pour dessiner sous les labels (enfants)
        self.canvas.before.clear()

        if self.size[0] == 0 or self.size[1] == 0:
            return

        # Centre du widget
        center_x = self.pos[0] + self.width / 2
        center_y = self.pos[1] + self.height / 2

        # Marge pour les labels cardinaux (adapter la taille de police selon l'espace)
        min_dimension = min(self.width, self.height)
        label_margin = max(12, min_dimension * 0.12)  # 12% de marge minimum 12px

        # Adapter la taille de police selon l'espace disponible
        font_size = max(9, min(14, min_dimension * 0.08))
        for label in self._cardinal_labels.values():
            label.font_size = f'{int(font_size)}sp'

        # Rayon de la coupole (réduit pour laisser place aux labels)
        radius = min_dimension / 2 - label_margin

        # Positionner les labels cardinaux
        self._position_cardinal_labels(center_x, center_y, radius, label_margin)

        with self.canvas.before:
            # 1. CERCLE DE FOND (coupole vue de dessus - gris foncé)
            Color(0.25, 0.27, 0.3, 1)
            Ellipse(
                pos=(center_x - radius, center_y - radius),
                size=(radius * 2, radius * 2)
            )

            # 2. MARQUEURS CARDINAUX (petits traits)
            self._draw_cardinal_marks(center_x, center_y, radius)

            # 3. POSITION ACTUELLE - ARC ROUGE (ouverture 70cm sur périmètre)
            # 70cm sur périmètre π×200cm ≈ 11.14% du périmètre
            # Angle d'ouverture ≈ 40.1°
            self._draw_dome_opening(center_x, center_y, radius, self.position_actuelle)

            # 4. POSITION CIBLE - FLÈCHE BLEUE
            self._draw_target_arrow(center_x, center_y, radius, self.position_cible)

            # 5. TEXTE CENTRAL - Afficher l'angle actuel
            self._draw_center_text(center_x, center_y, self.position_actuelle)

    def _position_cardinal_labels(self, cx, cy, radius, margin):
        """Positionne les labels N, E, S, O autour de la coupole."""
        # Distance du centre aux labels (juste après le cercle)
        label_dist = radius + margin / 2

        # Positions : N=haut, E=droite, S=bas, O=gauche
        positions = {
            'N': (cx, cy + label_dist),      # 12h (haut)
            'E': (cx + label_dist, cy),      # 3h (droite)
            'S': (cx, cy - label_dist),      # 6h (bas)
            'O': (cx - label_dist, cy),      # 9h (gauche)
        }

        for direction, (lx, ly) in positions.items():
            label = self._cardinal_labels[direction]
            # Centrer le label sur la position
            label.center_x = lx
            label.center_y = ly

    def _draw_cardinal_marks(self, cx, cy, radius):
        """Dessine les marqueurs cardinaux N, E, S, W."""
        # Points cardinaux : N=0°, E=90°, S=180°, W=270°
        # En coordonnées Kivy, 0° = droite, on doit donc convertir

        Color(0.5, 0.5, 0.5, 0.8)
        mark_length = 8

        for angle_astro, label in [(0, 'N'), (90, 'E'), (180, 'S'), (270, 'W')]:
            # Conversion angle astronomique → angle Kivy
            # Astro: 0°=Nord (haut), sens horaire
            # Kivy: 0°=Est (droite), sens anti-horaire
            angle_kivy = 90 - angle_astro
            angle_rad = radians(angle_kivy)

            # Point extérieur
            x_out = cx + radius * cos(angle_rad)
            y_out = cy + radius * sin(angle_rad)

            # Point intérieur
            x_in = cx + (radius - mark_length) * cos(angle_rad)
            y_in = cy + (radius - mark_length) * sin(angle_rad)

            # Trait
            Line(points=[x_in, y_in, x_out, y_out], width=1.5)

    def _draw_dome_opening(self, cx, cy, radius, angle_center):
        """
        Dessine la coupole avec son ouverture (trappe).

        Le rouge représente la partie fermée de la coupole.
        L'absence de rouge = la trappe (ouverture).
        Un trait noir marque le centre exact de la trappe.

        Args:
            cx, cy: Centre du cercle
            radius: Rayon
            angle_center: Angle central de l'ouverture (degrés astro)
        """
        # Largeur de l'ouverture : 70cm sur périmètre π×200cm
        # Angle = (70 / (π × 200)) × 360° ≈ 40.1°
        import math
        opening_angle = (70.0 / (math.pi * 200.0)) * 360.0  # ≈ 40.1°
        half_opening = opening_angle / 2

        # Angles de début et fin de la trappe (en degrés astro)
        trappe_start = angle_center - half_opening
        trappe_end = angle_center + half_opening

        # Normaliser les angles
        trappe_start = trappe_start % 360
        trappe_end = trappe_end % 360

        # Dessiner la partie FERMÉE de la coupole (tout sauf la trappe)
        # Arc rouge de la fin de la trappe jusqu'au début de la trappe (en passant par l'autre côté)
        Color(0.9, 0.2, 0.2, 1)  # Rouge vif

        # Si la trappe ne chevauche pas 0°, on dessine un seul arc
        # Sinon on dessine deux arcs
        if trappe_end > trappe_start:
            # Cas normal : dessiner de trappe_end à trappe_start (sens horaire, passant par 360°)
            Line(
                circle=(cx, cy, radius - 2, trappe_end, trappe_start + 360),
                width=4
            )
        else:
            # La trappe chevauche 0° : dessiner de trappe_end à trappe_start directement
            Line(
                circle=(cx, cy, radius - 2, trappe_end, trappe_start),
                width=4
            )

        # TRAIT NOIR AU CENTRE EXACT DE LA TRAPPE
        # Pour visualiser facilement le centre de l'ouverture (court pour ne pas toucher la flèche)
        angle_center_for_trig = 90 - angle_center
        angle_rad = radians(angle_center_for_trig)

        center_line_inner = radius - 8   # Début du trait (vers l'intérieur, plus court)
        center_line_outer = radius + 2   # Fin du trait (légèrement au-delà du cercle)

        inner_x = cx + center_line_inner * cos(angle_rad)
        inner_y = cy + center_line_inner * sin(angle_rad)
        outer_x = cx + center_line_outer * cos(angle_rad)
        outer_y = cy + center_line_outer * sin(angle_rad)

        Color(0, 0, 0, 1)  # Noir
        Line(points=[inner_x, inner_y, outer_x, outer_y], width=2)

    def _draw_target_arrow(self, cx, cy, radius, angle_target):
        """
        Dessine un tube de télescope au centre et une flèche bleue indiquant la position cible.

        Args:
            cx, cy: Centre du cercle
            radius: Rayon
            angle_target: Angle cible (degrés astro)
        """
        # Conversion angle astro → Kivy
        angle_kivy = 90 - angle_target
        angle_rad = radians(angle_kivy)

        # ====== TUBE DE TÉLESCOPE AU CENTRE ======
        # Proportions réelles : tube 90cm long × 30cm diamètre, trappe 70cm
        # Ratio longueur/trappe = 90/70 ≈ 1.286
        # Ratio diamètre/trappe = 30/70 ≈ 0.429
        # La trappe fait ~40° d'arc, donc on calcule en proportion du rayon
        import math
        opening_angle_rad = (70.0 / (math.pi * 200.0)) * 2 * math.pi  # ~0.7 rad
        trappe_width_px = 2 * radius * math.sin(opening_angle_rad / 2)  # Largeur trappe en pixels

        tube_length = trappe_width_px * (90.0 / 70.0)  # 90cm vs 70cm trappe
        tube_width = trappe_width_px * (30.0 / 70.0)   # 30cm vs 70cm trappe

        # Le tube est orienté vers l'angle cible
        # Point de rotation au 1er tiers du tube (30cm sur 90cm)
        # Le centre de la boussole correspond au point de pivot du télescope
        perp_angle = angle_rad + pi / 2

        # Distance du pivot vers l'arrière (1/3 du tube)
        pivot_to_back = tube_length / 3.0
        # Distance du pivot vers l'avant (2/3 du tube)
        pivot_to_front = tube_length * 2.0 / 3.0

        # Coins du tube
        half_width = tube_width / 2

        # Point arrière du tube (derrière le pivot/centre)
        back_cx = cx - pivot_to_back * cos(angle_rad)
        back_cy = cy - pivot_to_back * sin(angle_rad)

        # Coin arrière gauche et droite
        back_left_x = back_cx + half_width * cos(perp_angle)
        back_left_y = back_cy + half_width * sin(perp_angle)
        back_right_x = back_cx - half_width * cos(perp_angle)
        back_right_y = back_cy - half_width * sin(perp_angle)

        # Point avant du tube (devant le pivot/centre)
        front_cx = cx + pivot_to_front * cos(angle_rad)
        front_cy = cy + pivot_to_front * sin(angle_rad)
        front_left_x = front_cx + half_width * cos(perp_angle)
        front_left_y = front_cy + half_width * sin(perp_angle)
        front_right_x = front_cx - half_width * cos(perp_angle)
        front_right_y = front_cy - half_width * sin(perp_angle)

        # Corps du tube (gris foncé avec contour)
        Color(0.15, 0.18, 0.22, 1)  # Gris très foncé (corps)
        # Dessiner comme deux triangles pour former un rectangle
        Triangle(points=[back_left_x, back_left_y, back_right_x, back_right_y, front_left_x, front_left_y])
        Triangle(points=[back_right_x, back_right_y, front_right_x, front_right_y, front_left_x, front_left_y])

        # Contour du tube (bleu foncé) - les 4 côtés du rectangle
        Color(0.2, 0.3, 0.5, 1)
        Line(points=[back_left_x, back_left_y, front_left_x, front_left_y], width=1.2)
        Line(points=[back_right_x, back_right_y, front_right_x, front_right_y], width=1.2)
        Line(points=[back_left_x, back_left_y, back_right_x, back_right_y], width=1.2)
        Line(points=[front_left_x, front_left_y, front_right_x, front_right_y], width=1.2)

        # ====== FLÈCHE SORTANT DU TUBE ======
        # Point de départ de la flèche (sort de l'avant du tube)
        arrow_start_dist = pivot_to_front + 2
        start_x = cx + arrow_start_dist * cos(angle_rad)
        start_y = cy + arrow_start_dist * sin(angle_rad)

        # Point d'arrivée (sur le cercle intérieur)
        arrow_radius = radius - 16
        end_x = cx + arrow_radius * cos(angle_rad)
        end_y = cy + arrow_radius * sin(angle_rad)

        # Ligne de la flèche
        Color(0.3, 0.6, 1, 1)  # Bleu clair
        Line(points=[start_x, start_y, end_x, end_y], width=2)

        # Tête de flèche (triangle)
        arrow_size = 8

        # Pointe de la flèche
        tip_x = end_x
        tip_y = end_y

        # Base de la flèche (vers le tube)
        base_dist = arrow_radius - arrow_size
        base_cx = cx + base_dist * cos(angle_rad)
        base_cy = cy + base_dist * sin(angle_rad)

        # Perpendiculaire
        base_width = 5
        base_x1 = base_cx + base_width * cos(perp_angle)
        base_y1 = base_cy + base_width * sin(perp_angle)
        base_x2 = base_cx - base_width * cos(perp_angle)
        base_y2 = base_cy - base_width * sin(perp_angle)

        Color(0.2, 0.5, 0.9, 1)  # Bleu plus foncé
        Triangle(points=[tip_x, tip_y, base_x1, base_y1, base_x2, base_y2])

    def _draw_center_text(self, cx, cy, angle):
        """
        Dessine l'angle au centre (optionnel).
        Note: Pour le texte, on utilise un Label dans le parent.
        """
        # Le texte sera géré par un Label superposé dans le widget parent
        pass

    def update_position(self, actuelle, cible=None):
        """
        Met à jour les positions affichées.

        Args:
            actuelle: Position actuelle de la coupole (degrés)
            cible: Position cible (optionnel)
        """
        self.position_actuelle = actuelle
        if cible is not None:
            self.position_cible = cible
