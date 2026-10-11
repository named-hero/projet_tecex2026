"""
affichage.py : interface visuelle du piano acoustique (PHS3910).

    python affichage.py --demo   -> teste l'interface sans plaque ni piezo
    python affichage.py          -> ecoute les resultats UDP envoyes par
                                    AcquisitionEtCorrelation.py (127.0.0.1:5005)

PRINCIPE
--------
- La plaque est dessinee comme sur la photo : 12 rectangles colores (N1..N12),
  2 points de mesure par rectangle, le piezo en haut (PIEZO_EN_HAUT, plus bas).
- Chaque rectangle = UNE note. Quand une note est reconnue, son rectangle
  s'illumine (ambre) ET la touche correspondante du clavier s'illumine.
- Panneau de correlation : carte 7 x 7 de la plaque (une case par point, couleur = correlation,
  legende a droite, cadre par note, trous et piezo). Si la matrice recue n'a pas ce format,
  retour a l'affichage d'origine (barres par rectangle ou carte grise).
- Temps de reponse affiche = duree_traitement_ms recue (impact -> envoi).
- Les sons sont generes automatiquement dans notes/ s'ils n'existent pas.

Ce fichier ne fait PAS la correlation : il affiche ce qu'il recoit.
Installation : pip install PyQt6 numpy
"""

import sys
import time
import wave
from pathlib import Path

import numpy as np
from PyQt6 import QtCore, QtGui, QtNetwork, QtWidgets

try:
    from PyQt6 import QtMultimedia
except ImportError:          # son facultatif
    QtMultimedia = None

import Protocole_et_Communication as protocole

DOSSIER = Path(__file__).resolve().parent
NOTES_DIR = DOSSIER / "notes"

DUREE_ALLUMAGE_MS = 700      # duree d'illumination apres une note
AMBRE = "#ffb000"            # couleur "actif" (rectangle ET touche)

NOTES = ["C4", "C#4", "D4", "D#4", "E4", "F4", "F#4", "G4", "G#4", "A4", "A#4", "B4"]
NOMS = {"C": "Do", "D": "Ré", "E": "Mi", "F": "Fa", "G": "Sol", "A": "La", "B": "Si"}

# ----------------------------------------------------------------------
# DISPOSITION DE LA PLAQUE (coordonnees de la photo, y vers le bas)
# Chaque zone : (rectangle x0, y0, x1, y1, couleur, [(no_point, cx, cy, contour_gras), ...])
# Pour changer une position ou une couleur, modifier ce tableau seulement.
# ----------------------------------------------------------------------
ZONES = {
    "N1":  ((33, 817, 315, 948),  "#5b88bd", [(1, 105, 882, False),  (5, 248, 882, False)]),
    "N2":  ((33, 670, 315, 805),  "#c5d3ee", [(2, 105, 735, False),  (6, 248, 735, False)]),
    "N3":  ((33, 378, 315, 514),  "#ee9d4c", [(3, 105, 442, False),  (8, 248, 442, False)]),
    "N4":  ((325, 670, 606, 805), "#f6cc94", [(11, 398, 735, False), (18, 540, 735, True)]),
    "N5":  ((325, 234, 606, 368), "#6aae5c", [(14, 398, 299, True),  (21, 540, 299, True)]),
    "N6":  ((325, 89, 606, 222),  "#b9e3a5", [(15, 390, 157, True),  (22, 540, 157, False)]),
    "N7":  ((470, 817, 750, 948), "#d0524f", [(17, 540, 882, True),  (23, 685, 882, False)]),
    "N8":  ((470, 378, 750, 514), "#eba8a9", [(20, 540, 442, False), (26, 685, 442, True)]),
    "N9":  ((616, 89, 896, 222),  "#a587cc", [(28, 688, 157, True),  (34, 830, 157, False)]),
    "N10": ((760, 378, 1040, 514), "#cbbce0", [(32, 830, 442, False), (39, 975, 442, False)]),
    "N11": ((760, 670, 1040, 805), "#9a6e66", [(30, 830, 735, False), (37, 975, 735, False)]),
    "N12": ((760, 234, 1040, 368), "#c8a9a0", [(33, 830, 299, False), (40, 975, 299, False)]),
}

# Quelle note joue chaque rectangle. Par defaut N1 = Do, N2 = Do#, ... N12 = Si.
# Modifier ici si l'equipe a assigne les notes autrement.
NOTE_PAR_ZONE = dict(zip(ZONES.keys(), NOTES))
ZONE_PAR_NOTE = {n: z for z, n in NOTE_PAR_ZONE.items()}

# Positions non utilisees de la photo (cercles hachures) et position du piezo : decor.
POINTS_INUTILISES = [(830, 882), (975, 882), (248, 299), (685, 299), (398, 442),
                     (248, 590), (398, 590), (540, 590), (685, 590), (830, 590),
                     (975, 590), (685, 735), (398, 882), (248, 1025), (540, 1025),
                     (975, 1025)]
POINTS_VIDES = [(105, 590), (398, 1025), (830, 1025)]
PIEZO = (653, 993, 717, 1058)

# Fenetre "monde" affichee (en coordonnees de la photo)
MONDE = QtCore.QRectF(0, 60, 1070, 1030)

# Orientation : la photo a le piezo en bas. Avec PIEZO_EN_HAUT = True, la plaque est tournee de 180 degres
# (rectangles, points, trous, piezo), comme la carte de correlation. Mettre False pour revenir a la photo.
PIEZO_EN_HAUT = True
if PIEZO_EN_HAUT:
    def _px(x):
        return MONDE.left() + MONDE.right() - x

    def _py(y):
        return MONDE.top() + MONDE.bottom() - y

    ZONES = {z: ((_px(x1), _py(y1), _px(x0), _py(y0)), c, [(pid, _px(cx), _py(cy), g) for pid, cx, cy, g in pts])
             for z, ((x0, y0, x1, y1), c, pts) in ZONES.items()}
    POINTS_INUTILISES = [(_px(x), _py(y)) for x, y in POINTS_INUTILISES]
    POINTS_VIDES = [(_px(x), _py(y)) for x, y in POINTS_VIDES]
    PIEZO = (_px(PIEZO[2]), _py(PIEZO[3]), _px(PIEZO[0]), _py(PIEZO[1]))

# --- Carte de correlation : une case par position de la plaque (grille 7 x 7) ---
# Le traitement envoie une matrice 7 x 7 (AcquisitionEtCorrelation.carte_de_correlation) rangee comme la
# plaque affichee : ligne = de haut en bas, colonne = de gauche a droite, valeur = score du point a cet endroit.
FORME_CARTE = (7, 7)
_XS = sorted(_px(x) if PIEZO_EN_HAUT else x for x in (105, 248, 398, 540, 685, 830, 975))
_YS = sorted(_py(y) if PIEZO_EN_HAUT else y for y in (157, 299, 442, 590, 735, 882, 1025))


def case_de(cx, cy):
    """Position (ligne, colonne) de la grille 7 x 7 la plus proche d'un point de la plaque."""
    return (min(range(7), key=lambda i: abs(_YS[i] - cy)), min(range(7), key=lambda j: abs(_XS[j] - cx)))


CASES_POINTS = {pid: case_de(cx, cy) for _, (_, _, pts) in ZONES.items() for pid, cx, cy, _ in pts}
CASES_MORTES = [case_de(x, y) for x, y in POINTS_INUTILISES]
CASES_TROUS = [case_de(x, y) for x, y in POINTS_VIDES]
CASE_PIEZO = case_de((PIEZO[0] + PIEZO[2]) / 2, (PIEZO[1] + PIEZO[3]) / 2)

# Table de couleurs (viridis, 0 = violet fonce, 1 = jaune)
_VIRIDIS = [(0.0, "#440154"), (0.125, "#482878"), (0.25, "#3e4989"), (0.375, "#31688e"), (0.5, "#26828e"),
            (0.625, "#1f9e89"), (0.75, "#35b779"), (0.875, "#6ece58"), (1.0, "#fde725")]


def couleur_correlation(v):
    v = max(0.0, min(1.0, float(v)))
    for (a, ca), (b, cb) in zip(_VIRIDIS, _VIRIDIS[1:]):
        if v <= b:
            t = (v - a) / (b - a)
            c1, c2 = QtGui.QColor(ca), QtGui.QColor(cb)
            return QtGui.QColor(int(c1.red() + t * (c2.red() - c1.red())),
                                int(c1.green() + t * (c2.green() - c1.green())),
                                int(c1.blue() + t * (c2.blue() - c1.blue())))
    return QtGui.QColor(_VIRIDIS[-1][1])


# Pour l'affichage de la correlation : si la matrice recue contient 24 valeurs,
# on suppose qu'elles suivent les points tries par numero (1,2,3,5,6,8,11,...) ;
# 12 valeurs = une par rectangle (N1..N12) ; 40 valeurs = indexees par numero de point.
IDS_BANQUE = sorted(pid for _, _, pts in ZONES.values() for pid, _, _, _ in pts)
ZONE_DU_POINT = {pid: z for z, (_, _, pts) in ZONES.items() for pid, _, _, _ in pts}


def note_nom(note):
    if not note:
        return "—"
    dieze = "♯" if "#" in note else ""
    return f"{NOMS.get(note[0], note[0])}{dieze} {note[-1]} ({note})"


def scores_par_zone(matrice):
    """Transforme la matrice recue en {zone: score}. Dictionnaire vide si taille inconnue."""
    if matrice is None:
        return {}
    v = np.asarray(matrice, dtype=float).ravel()
    zones = list(ZONES.keys())
    sc = {}
    if v.size == len(IDS_BANQUE):
        for pid, val in zip(IDS_BANQUE, v):
            z = ZONE_DU_POINT[pid]
            sc[z] = max(sc.get(z, 0.0), float(val))
    elif v.size == len(zones):
        sc = {z: float(val) for z, val in zip(zones, v)}
    elif v.size == 40:
        for pid, z in ZONE_DU_POINT.items():
            sc[z] = max(sc.get(z, 0.0), float(v[pid - 1]))
    return sc


def couleur_texte(hex_fond):
    c = QtGui.QColor(hex_fond)
    lum = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
    return QtGui.QColor("#ffffff" if lum < 140 else "#1c2730")


# ----------------------------------------------------------------------
# Sons : generes une seule fois dans notes/ (pseudo-piano : harmoniques + decroissance)
# ----------------------------------------------------------------------
def nom_fichier_son(note):
    return NOTES_DIR / f"{note.replace('#', '-')}.wav"


def generer_sons_si_absents():
    fs = 44100
    t = np.arange(int(1.6 * fs)) / fs
    NOTES_DIR.mkdir(exist_ok=True)
    for i, note in enumerate(NOTES):
        chemin = nom_fichier_son(note)
        if chemin.exists():
            continue
        f0 = 261.6256 * 2 ** (i / 12)
        s = sum(a * np.sin(2 * np.pi * f0 * k * t) for k, a in enumerate([1.0, 0.5, 0.25, 0.12], 1))
        s = s * np.exp(-3.0 * t) * np.minimum(1.0, t / 0.004)
        s = (0.8 * s / np.max(np.abs(s)) * 32767).astype("<i2")
        with wave.open(str(chemin), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(fs)
            w.writeframes(s.tobytes())


# ----------------------------------------------------------------------
# Widget : la plaque avec ses rectangles
# ----------------------------------------------------------------------
class Plaque(QtWidgets.QWidget):
    zoneCliquee = QtCore.pyqtSignal(str)

    def __init__(self, fenetre):
        super().__init__()
        self.fenetre = fenetre
        self.setMinimumSize(520, 520)

    def _echelle(self):
        s = min(self.width() / MONDE.width(), self.height() / MONDE.height())
        ox = (self.width() - s * MONDE.width()) / 2
        oy = (self.height() - s * MONDE.height()) / 2
        return s, ox, oy

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QtGui.QColor("#f7f8fa"))
        s, ox, oy = self._echelle()
        p.translate(ox, oy)
        p.scale(s, s)
        p.translate(-MONDE.x(), -MONDE.y())

        # Decor : positions non utilisees, vides, piezo
        p.setPen(QtGui.QPen(QtGui.QColor("#9aa3aa"), 2))
        p.setBrush(QtGui.QBrush(QtGui.QColor("#b5bcc2"), QtCore.Qt.BrushStyle.BDiagPattern))
        for x, y in POINTS_INUTILISES:
            p.drawEllipse(QtCore.QPointF(x, y), 24, 24)
        p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        pen = QtGui.QPen(QtGui.QColor("#9aa3aa"), 2, QtCore.Qt.PenStyle.DotLine)
        p.setPen(pen)
        for x, y in POINTS_VIDES:
            p.drawEllipse(QtCore.QPointF(x, y), 24, 24)
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QColor("#000000"))
        r = QtCore.QRectF(PIEZO[0], PIEZO[1], PIEZO[2] - PIEZO[0], PIEZO[3] - PIEZO[1])
        p.drawRect(r)
        p.setPen(QtGui.QColor("#ffffff"))
        f = QtGui.QFont("Arial")
        f.setPixelSize(20)
        p.setFont(f)
        p.drawText(r, QtCore.Qt.AlignmentFlag.AlignCenter, "piézo")

        actives = self.fenetre.zones_actives()

        # Rectangles
        for zid, ((x0, y0, x1, y1), couleur, pts) in ZONES.items():
            rect = QtCore.QRectF(x0, y0, x1 - x0, y1 - y0)
            actif = zid in actives
            if actif:
                p.setPen(QtCore.Qt.PenStyle.NoPen)
                p.setBrush(QtGui.QColor(255, 176, 0, 90))
                p.drawRect(rect.adjusted(-14, -14, 14, 14))      # halo
                fond, bord, ep = AMBRE, "#7a4a00", 6
            else:
                fond, bord, ep = couleur, "#333d45", 3
            p.setPen(QtGui.QPen(QtGui.QColor(bord), ep))
            p.setBrush(QtGui.QColor(fond))
            p.drawRect(rect)

            f = QtGui.QFont("Arial")
            f.setPixelSize(26)
            f.setBold(True)
            p.setFont(f)
            p.setPen(couleur_texte(fond))
            p.drawText(rect.adjusted(10, 5, -8, -4),
                       QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignLeft,
                       f"{zid} · {NOTE_PAR_ZONE[zid]}")

            # Points de mesure
            for pid, cx, cy, gras in pts:
                p.setPen(QtGui.QPen(QtGui.QColor("#111111"), 5 if gras else 2))
                p.setBrush(QtGui.QColor("#ffffff"))
                p.drawEllipse(QtCore.QPointF(cx, cy + 8), 24, 24)
                f.setPixelSize(22)
                p.setFont(f)
                p.setPen(QtGui.QColor("#111111"))
                p.drawText(QtCore.QRectF(cx - 24, cy - 16, 48, 48),
                           QtCore.Qt.AlignmentFlag.AlignCenter, str(pid))
        p.end()

    def mousePressEvent(self, event):
        if not self.fenetre.demo:
            return
        s, ox, oy = self._echelle()
        x = (event.position().x() - ox) / s + MONDE.x()
        y = (event.position().y() - oy) / s + MONDE.y()
        for zid, ((x0, y0, x1, y1), _, _) in ZONES.items():
            if x0 <= x <= x1 and y0 <= y <= y1:
                self.zoneCliquee.emit(zid)
                return


# ----------------------------------------------------------------------
# Widget : le clavier (1 octave : Do4 a Si4)
# ----------------------------------------------------------------------
class Clavier(QtWidgets.QWidget):
    BLANCHES = ["C4", "D4", "E4", "F4", "G4", "A4", "B4"]
    NOIRES = {"C#4": 1, "D#4": 2, "F#4": 4, "G#4": 5, "A#4": 6}
    noteCliquee = QtCore.pyqtSignal(str)

    def __init__(self, fenetre):
        super().__init__()
        self.fenetre = fenetre
        self.setMinimumHeight(130)
        self.setMaximumHeight(170)
        self._touches = []

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QtGui.QColor("#eef2f5"))
        x0, y0 = 8.0, 5.0
        w = (self.width() - 16) / 7
        h = self.height() - 10
        actives = self.fenetre.notes_actives
        self._touches = []
        f = QtGui.QFont("Arial", 9, QtGui.QFont.Weight.Bold)
        p.setFont(f)

        for i, note in enumerate(self.BLANCHES):
            r = QtCore.QRectF(x0 + i * w, y0, w, h)
            self._touches.append((note, r, False))
            p.setPen(QtGui.QPen(QtGui.QColor("#273642"), 1))
            p.setBrush(QtGui.QColor(AMBRE if note in actives else "#ffffff"))
            p.drawRect(r)
            p.setPen(QtGui.QColor("#17232c"))
            p.drawText(QtCore.QRectF(r.x(), r.bottom() - 28, r.width(), 22),
                       QtCore.Qt.AlignmentFlag.AlignCenter, note)

        nw, nh = w * 0.56, h * 0.60
        noires = []
        for note, sep in self.NOIRES.items():
            r = QtCore.QRectF(x0 + sep * w - nw / 2, y0, nw, nh)
            noires.append((note, r, True))
            p.setPen(QtGui.QPen(QtGui.QColor("#121b22"), 1))
            p.setBrush(QtGui.QColor(AMBRE if note in actives else "#121b22"))
            p.drawRect(r)
            p.setPen(QtGui.QColor("#17232c" if note in actives else "#ffffff"))
            p.drawText(r.adjusted(0, 0, 0, -4),
                       QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignBottom,
                       note)
        self._touches = noires + self._touches   # noires testees en premier au clic
        p.end()

    def mousePressEvent(self, event):
        if not self.fenetre.demo:
            return
        pos = event.position()
        for note, r, _ in self._touches:
            if r.contains(pos):
                self.noteCliquee.emit(note)
                return


# ----------------------------------------------------------------------
# Widget : correlation (barres par rectangle, ou carte grise si format inconnu)
# ----------------------------------------------------------------------
class Correlations(QtWidgets.QWidget):
    def __init__(self, fenetre):
        super().__init__()
        self.fenetre = fenetre
        self.setMinimumHeight(380)

    def _dessiner_carte(self, p, mat):
        """Carte de la plaque : une case par point, couleur = correlation (legende a droite)."""
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        marge_legende = 78
        c = min((self.width() - marge_legende - 10) / 7, (self.height() - 10) / 7)
        ox = 6 + max(0.0, (self.width() - marge_legende - 10 - 7 * c) / 2)
        oy = 5 + max(0.0, (self.height() - 10 - 7 * c) / 2)

        def centre(i, j):
            return QtCore.QPointF(ox + (j + 0.5) * c, oy + (i + 0.5) * c)

        police = QtGui.QFont("Arial")
        # Trous : cercle vide ; piezo : carre noir
        p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        p.setPen(QtGui.QPen(QtGui.QColor("#8a949b"), 2, QtCore.Qt.PenStyle.DotLine))
        for i, j in CASES_TROUS:
            p.drawEllipse(centre(i, j), c * 0.32, c * 0.32)
        i, j = CASE_PIEZO
        r = QtCore.QRectF(centre(i, j).x() - c * 0.36, centre(i, j).y() - c * 0.36, c * 0.72, c * 0.72)
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QColor("#000000"))
        p.drawRect(r)
        police.setPixelSize(max(8, int(c * 0.16)))
        p.setFont(police)
        p.setPen(QtGui.QColor("#ffffff"))
        p.drawText(r, QtCore.Qt.AlignmentFlag.AlignCenter, "piézo")

        # Zones mortes : score montre, couleur attenuee (aucune note jouee)
        for i, j in CASES_MORTES:
            v = float(mat[i, j])
            col = couleur_correlation(v)
            col.setAlpha(80)
            p.setPen(QtGui.QPen(QtGui.QColor("#c3c9ce"), 1))
            p.setBrush(col)
            p.drawRect(QtCore.QRectF(ox + j * c, oy + i * c, c, c))
            p.setPen(QtGui.QColor("#8a949b"))
            p.drawText(QtCore.QRectF(ox + j * c, oy + i * c, c, c), QtCore.Qt.AlignmentFlag.AlignCenter, f"{v:.2f}")

        # Points des notes, puis un cadre par rectangle (nom de la note et meilleur score)
        actives = self.fenetre.zones_actives()
        for zid, (_, _, pts) in ZONES.items():
            cases = [CASES_POINTS[pid] for pid, _, _, _ in pts]
            valeurs = [float(mat[i, j]) for i, j in cases]
            for (i, j), v in zip(cases, valeurs):
                p.setPen(QtGui.QPen(QtGui.QColor("#ffffff"), 1))
                p.setBrush(couleur_correlation(v))
                p.drawRect(QtCore.QRectF(ox + j * c, oy + i * c, c, c))
                lum = couleur_correlation(v).lightness()
                p.setPen(QtGui.QColor("#ffffff" if lum < 140 else "#17232c"))
                police.setPixelSize(max(9, int(c * 0.22)))
                police.setBold(True)
                p.setFont(police)
                p.drawText(QtCore.QRectF(ox + j * c, oy + i * c, c, c), QtCore.Qt.AlignmentFlag.AlignCenter, f"{v:.2f}")
            i0, i1 = min(i for i, _ in cases), max(i for i, _ in cases)
            j0, j1 = min(j for _, j in cases), max(j for _, j in cases)
            cadre = QtCore.QRectF(ox + j0 * c, oy + i0 * c, (j1 - j0 + 1) * c, (i1 - i0 + 1) * c)
            actif = zid in actives
            p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            p.setPen(QtGui.QPen(QtGui.QColor(AMBRE if actif else "#17232c"), 6 if actif else 3))
            p.drawRect(cadre.adjusted(2, 2, -2, -2))
            police.setPixelSize(max(9, int(c * 0.17)))
            p.setFont(police)
            etiquette = f"{zid} {NOTE_PAR_ZONE[zid]}"
            largeur = p.fontMetrics().horizontalAdvance(etiquette) + 8
            p.setPen(QtCore.Qt.PenStyle.NoPen)
            p.setBrush(QtGui.QColor(0, 0, 0, 170))
            fond = QtCore.QRectF(cadre.x() + 4, cadre.y() + 4, largeur, p.fontMetrics().height() + 2)
            p.drawRect(fond)
            p.setPen(QtGui.QColor("#ffffff"))
            p.drawText(fond, QtCore.Qt.AlignmentFlag.AlignCenter, etiquette)

        # Legende : barre de couleur 1 (haut) -> 0 (bas)
        bx, by, bw, bh = self.width() - marge_legende + 14, oy, 20, 7 * c
        degrade = QtGui.QLinearGradient(0, by, 0, by + bh)
        for pos, col in _VIRIDIS:
            degrade.setColorAt(1.0 - pos, QtGui.QColor(col))
        p.setPen(QtGui.QPen(QtGui.QColor("#17232c"), 1))
        p.setBrush(QtGui.QBrush(degrade))
        p.drawRect(QtCore.QRectF(bx, by, bw, bh))
        police.setPixelSize(12)
        police.setBold(False)
        p.setFont(police)
        for k in range(6):
            v = k / 5
            y = by + bh * (1 - v)
            p.drawLine(QtCore.QPointF(bx + bw, y), QtCore.QPointF(bx + bw + 4, y))
            p.drawText(QtCore.QRectF(bx + bw + 6, y - 8, 36, 16), QtCore.Qt.AlignmentFlag.AlignVCenter, f"{v:.1f}")
        p.save()
        p.translate(bx - 6, by + bh / 2)
        p.rotate(-90)
        p.drawText(QtCore.QRectF(-60, -14, 120, 14), QtCore.Qt.AlignmentFlag.AlignCenter, "Corrélation")
        p.restore()

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.fillRect(self.rect(), QtGui.QColor("#f5f7f9"))
        p.setPen(QtGui.QColor("#182630"))
        sc = self.fenetre.scores_zone
        mat = self.fenetre.matrice

        if mat is not None and mat.shape == FORME_CARTE:
            self._dessiner_carte(p, mat)
        elif sc:
            n = len(ZONES)
            h = max(18, (self.height() - 16) / n)
            larg = max(80, self.width() - 140)
            for i, zid in enumerate(ZONES):
                y = 8 + i * h
                v = max(0.0, min(1.0, sc.get(zid, 0.0)))
                actif = zid in self.fenetre.zones_actives()
                p.setPen(QtGui.QColor("#182630"))
                p.drawText(QtCore.QRectF(6, y, 82, h), QtCore.Qt.AlignmentFlag.AlignVCenter,
                           f"{zid} {NOTE_PAR_ZONE[zid]}")
                p.fillRect(QtCore.QRectF(92, y + 4, larg, h - 8), QtGui.QColor("#dce4ea"))
                p.fillRect(QtCore.QRectF(92, y + 4, larg * v, h - 8),
                           QtGui.QColor(AMBRE if actif else "#4d8eb9"))
                p.drawText(QtCore.QRectF(98 + larg, y, 40, h),
                           QtCore.Qt.AlignmentFlag.AlignVCenter, f"{v:.2f}")
        elif mat is not None and mat.size:
            m, n = mat.shape
            lo, hi = float(mat.min()), float(mat.max())
            cw, ch = (self.width() - 20) / n, (self.height() - 30) / m
            for i in range(m):
                for j in range(n):
                    v = (mat[i, j] - lo) / (hi - lo) if hi > lo else 0.0
                    g = int(255 * (1 - v))                    # noir = correlation max
                    p.fillRect(QtCore.QRectF(10 + j * cw, 10 + i * ch, cw, ch), QtGui.QColor(g, g, g))
            p.setPen(QtGui.QColor("#182630"))
            p.drawText(QtCore.QRectF(0, self.height() - 20, self.width(), 18),
                       QtCore.Qt.AlignmentFlag.AlignCenter,
                       f"Matrice {m}×{n} (format non associe aux rectangles)")
        else:
            p.drawText(self.rect(), QtCore.Qt.AlignmentFlag.AlignCenter, "En attente des coefficients…")
        p.end()


# ----------------------------------------------------------------------
# Fenetre principale
# ----------------------------------------------------------------------
class Fenetre(QtWidgets.QMainWindow):
    def __init__(self, demo=False):
        super().__init__()
        self.demo = demo
        self.notes_actives = set()
        self.points_actifs = set()      # optionnel : si un jour le protocole envoie "points"
        self.scores_zone = {}
        self.matrice = None
        self.sons = {}
        self.rng = np.random.default_rng()
        self.setWindowTitle("Piano acoustique — localisation et note reconnue")
        self.resize(1300, 880)

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        main = QtWidgets.QVBoxLayout(central)
        main.setContentsMargins(10, 8, 10, 8)

        barre = QtWidgets.QHBoxLayout()
        main.addLayout(barre)
        self.son = QtWidgets.QCheckBox("Jouer le son")
        self.son.setChecked(True)
        barre.addWidget(self.son)
        if self.demo:
            barre.addWidget(QtWidgets.QLabel("   MODE DÉMO — clique un rectangle ou une touche, ou accord :"))
            self.combo = QtWidgets.QComboBox()
            self.combo.addItems(["Do-Mi-Sol (C4,E4,G4)", "Ré-Fa-La (D4,F4,A4)"])
            barre.addWidget(self.combo)
            btn = QtWidgets.QPushButton("Jouer l'accord")
            btn.clicked.connect(self.accord_demo)
            barre.addWidget(btn)
        barre.addStretch()

        contenu = QtWidgets.QHBoxLayout()
        main.addLayout(contenu, 1)
        self.plaque = Plaque(self)
        contenu.addWidget(self.plaque, 3)

        droite = QtWidgets.QVBoxLayout()
        contenu.addLayout(droite, 2)
        titre = QtWidgets.QLabel("Corrélation avec chaque point de la plaque · échelle 0 à 1")
        titre.setStyleSheet("font-size:16px; font-weight:bold;")
        droite.addWidget(titre)
        self.correlation = Correlations(self)
        droite.addWidget(self.correlation, 1)
        self.table = QtWidgets.QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Heure", "Note", "Réponse (ms)"])
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setMaximumHeight(170)
        droite.addWidget(self.table)

        self.clavier = Clavier(self)
        main.addWidget(self.clavier)

        bas = QtWidgets.QHBoxLayout()
        main.addLayout(bas)
        self.note_label = QtWidgets.QLabel("Note jouée : —")
        self.note_label.setStyleSheet("font-size:24px; font-weight:bold; padding:4px;")
        bas.addWidget(self.note_label, 3)
        self.temps_label = QtWidgets.QLabel("Temps de réponse : — ms")
        self.temps_label.setStyleSheet("font-size:20px; padding:4px;")
        bas.addWidget(self.temps_label, 2)
        self.status = QtWidgets.QLabel()
        self.status.setWordWrap(True)
        main.addWidget(self.status)

        self.timer = QtCore.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.eteindre)

        self.plaque.zoneCliquee.connect(lambda z: self.simuler([NOTE_PAR_ZONE[z]]))
        self.clavier.noteCliquee.connect(lambda n: self.simuler([n]))

        self.charger_sons()
        if self.demo:
            self.status.setText("MODE DÉMO : aucune mesure réelle, aucun temps de réponse réel.")
        else:
            self.ouvrir_udp()

    # --- etat visuel ---
    def zones_actives(self):
        return {ZONE_PAR_NOTE[n] for n in self.notes_actives if n in ZONE_PAR_NOTE}

    def eteindre(self):
        self.notes_actives.clear()
        self.update_tout()

    def update_tout(self):
        self.plaque.update()
        self.clavier.update()
        self.correlation.update()

    # --- sons ---
    def charger_sons(self):
        if QtMultimedia is None:
            return
        try:
            generer_sons_si_absents()
        except Exception as exc:
            print("Generation des sons impossible :", exc)
        for note in NOTES:
            chemin = nom_fichier_son(note)
            if chemin.exists():
                effet = QtMultimedia.QSoundEffect(self)
                effet.setSource(QtCore.QUrl.fromLocalFile(str(chemin)))
                effet.setVolume(0.7)
                self.sons[note] = effet

    # --- UDP ---
    def ouvrir_udp(self):
        self.socket = QtNetwork.QUdpSocket(self)
        if not self.socket.bind(QtNetwork.QHostAddress(protocole.HOTE), protocole.PORT):
            raise RuntimeError(f"Impossible d'utiliser UDP {protocole.HOTE}:{protocole.PORT}. "
                               "Le port est peut-être déjà utilisé (une autre fenêtre ouverte ?).")
        self.socket.readyRead.connect(self.lire_udp)
        self.status.setText(f"MODE RÉEL : en attente des résultats sur UDP {protocole.HOTE}:{protocole.PORT}.")

    def lire_udp(self):
        while self.socket.hasPendingDatagrams():
            data = self.socket.receiveDatagram().data()
            try:
                self.recevoir(protocole.decoder(bytes(data)), simulation=False)
            except Exception as exc:
                self.status.setText(f"Message UDP ignoré : {exc}")

    # --- traitement d'un resultat (reel ou simule) ---
    def recevoir(self, message, simulation=False):
        notes = [n for n in message.get("notes", []) if n in ZONE_PAR_NOTE]
        self.notes_actives = set(notes)
        self.points_actifs = {str(p) for p in message.get("points", [])}
        mat = message.get("matrice_de_convolution")
        self.matrice = np.atleast_2d(np.asarray(mat, dtype=float)) if mat is not None else None
        self.scores_zone = scores_par_zone(self.matrice)
        duree = float(message.get("duree_traitement_ms", 0.0))

        self.note_label.setText("Note jouée : " + (", ".join(note_nom(n) for n in notes) if notes else "—"))
        if simulation:
            self.temps_label.setText("Temps de réponse : (démo)")
        else:
            self.temps_label.setText(f"Temps de réponse : {duree:.0f} ms")
            self.status.setText("Résultat reçu en temps réel. Ambre = note reconnue (rectangle + touche).")

        if notes:
            self.table.insertRow(0)
            for j, txt in enumerate([time.strftime("%H:%M:%S"), ", ".join(notes),
                                     "—" if simulation else f"{duree:.0f}"]):
                self.table.setItem(0, j, QtWidgets.QTableWidgetItem(txt))
            while self.table.rowCount() > 8:
                self.table.removeRow(self.table.rowCount() - 1)

        self.update_tout()
        self.timer.start(DUREE_ALLUMAGE_MS)
        if self.son.isChecked():
            for n in notes:
                if n in self.sons:
                    self.sons[n].play()

    # --- demo ---
    def simuler(self, notes):
        if not self.demo:
            return
        carte = np.zeros(FORME_CARTE)
        for pid, (i, j) in CASES_POINTS.items():
            carte[i, j] = self.rng.uniform(0.10, 0.40)
        for i, j in CASES_MORTES:
            carte[i, j] = self.rng.uniform(0.10, 0.40)
        for n in notes:
            for pid, _, _, _ in ZONES[ZONE_PAR_NOTE[n]][2]:
                carte[CASES_POINTS[pid]] = self.rng.uniform(0.85, 0.98)
        self.recevoir({"notes": notes, "matrice_de_convolution": carte,
                       "duree_traitement_ms": 0.0}, simulation=True)

    def accord_demo(self):
        self.simuler(["C4", "E4", "G4"] if self.combo.currentIndex() == 0 else ["D4", "F4", "A4"])


def main():
    app = QtWidgets.QApplication(sys.argv)
    try:
        fenetre = Fenetre(demo="--demo" in sys.argv)
    except Exception as exc:
        QtWidgets.QMessageBox.critical(None, "Démarrage impossible", str(exc))
        return 1
    fenetre.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
