"""PHS3910 M4 - Comparaison des focales d'entree f1 = 20, 40, 50, 60 et 100 mm (question 4) et chromatisme (question 6).
Dependances : numpy, matplotlib. Lit w90_defocalisation.csv, ecrit par simulation_fourier_M4.py (section 1).

Contenu :
    1) tableau de comparaison de f1 : resolution de la fente, image, motif de diffraction, longueur du montage, flux
    2) effet de la defocalisation sur le terme de fente (table de Fourier, interpolation lineaire)
    3) chromatisme d'une lentille simple plan-convexe en N-BK7 pour L2 (la camera est reglee a 550 nm)
    4) figures M4_10 (comparaison, defocalisation) et M4_11 (chromatisme)

Hypotheses :
    - ecarts-types de conception (3 um sur a, 1 % sur f1) : HYPOTHESES de travail, comme dans incertitudes_M4.py
    - flux : lumiere collectee par L1 = etendue geometrique G = (a*h) * Omega, avec Omega = pi*(D1/2)^2/f1^2 l'angle solide
      sous lequel L1 voit la fente (source diffuse qui remplit la fente). h et D1 identiques pour toutes les focales
      (diametre de L1 non confirme). Les flux sont donnes relativement a f1 = 40 mm :
        . a egal (meme largeur de fente a)        : G proportionnel a 1/f1^2
        . a resolution egale (a proportionnel a f1, pour garder le meme terme de fente) : G proportionnel a 1/f1
        . a resolution egale ET h = h max (h max proportionnel a f1/f2) : G constant (le gain de hauteur compense)
    - chromatisme : lentille mince, f proportionnelle a 1/(n - 1) ; seul L2 est pris en compte (pas celui de L1) ;
      effet sur le terme de fente = rapport des largeurs a 90 % de la table de defocalisation (550 nm)
Verre : N-BK7, equation de Sellmeier (lambda en um) n^2 - 1 = somme B_i*lambda^2/(lambda^2 - C_i), coefficients de la page
    Wikipedia "Sellmeier equation" (BK7) ; verification : n_d calcule = 1,5168 pour 1,51680 sur la fiche SCHOTT N-BK7
    (https://edmundoptics.eu/document/download/521927).
"""
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parent

# ---------------- Parametres (SI), identiques a simulation_M4.py ----------------
PAS = 1e-3 / 600
ORDRE = 1
ALPHA = np.deg2rad(3.0)
F2 = 25e-3
FENTE = 50e-6
LB = 2e-3                       # valeur du code de depart (Keira), a confirmer ; 10 mm dans la v1 du brouillon
PIXEL, N_PIX, N_PIX_V = 1.55e-6, 4056, 3040
LAM_MIN, LAM_MAX, LAM_C = 400e-9, 700e-9, 550e-9
F1_REF = 40e-3                  # focale de reference pour les rapports de flux
F1_MM = (20, 40, 50, 60, 100)   # focales d'entree comparees (mm) ; doivent etre des colonnes de w90_defocalisation.csv
SIG_A, SIG_F1_REL = 3e-6, 0.01  # HYPOTHESES

B = (1.03961212, 0.231792344, 1.01046945)
C = (0.00600069867, 0.0200179144, 103.560653)       # um^2

def indice(lam_um):
    l2 = np.asarray(lam_um) ** 2
    return np.sqrt(1 + sum(b * l2 / (l2 - c) for b, c in zip(B, C)))

BETA_C = float(np.arcsin(LAM_C / PAS - np.sin(ALPHA)))
GRANDISSEMENT_ANGLE = np.cos(ALPHA) / np.cos(BETA_C)           # cos(alpha)/cos(beta) a 550 nm


def d_fente(a, f1):
    """Largeur spectrale due a la fente (m)."""
    return a * PAS * np.cos(ALPHA) / (ORDRE * f1)


# ---------------- 1) Comparaison des focales d'entree ----------------
def h_max(f1):
    """Hauteur maximale de la fente (m) : son image (grandissement vertical f2/f1) doit tenir dans la hauteur du capteur."""
    return N_PIX_V * PIXEL / (F2 / f1)

def flux_relatif(f1, a_egal=True, avec_hmax=False):
    """Etendue G = a*h/f1^2 (D1 fixe) relative a f1 = F1_REF ; a_egal=False : a proportionnel a f1 (meme terme de fente) ;
    avec_hmax=True : h = h max au lieu d'un h identique."""
    a = FENTE if a_egal else FENTE * f1 / F1_REF
    h = h_max(f1) if avec_hmax else h_max(F1_REF)
    a_ref, h_ref = FENTE, (h_max(F1_REF) if avec_hmax else h_max(F1_REF))
    return (a * h / f1**2) / (a_ref * h_ref / F1_REF**2)

print(f"Comparaison de f1, a = {FENTE*1e6:.0f} um, f2 = {F2*1e3:.0f} mm, alpha = 3 deg, m = {ORDRE}, Lb = {LB*1e3:.0f} mm")
print("f1 (mm) | d_lambda fente (nm) | image (um) | (pixels) | motif 2*lambda*f1/a (mm) | longueur 4f (mm) | "
      "h max (mm) | flux a a egal | flux a resolution egale | flux a resolution egale, h = h max | total (nm)")
for f1_mm in F1_MM:
    f1 = f1_mm * 1e-3
    d = d_fente(FENTE, f1)
    err = d * np.hypot(SIG_A / FENTE, SIG_F1_REL)
    img = FENTE * (F2 / f1) * GRANDISSEMENT_ANGLE
    motif = 2 * LAM_C * f1 / FENTE
    total = np.sqrt(d**2 + (LAM_C * PAS * np.cos(ALPHA) / (ORDRE * LB))**2 + (PIXEL * PAS * np.cos(BETA_C) / (ORDRE * F2))**2)
    print(f"{f1_mm:7d} | {d*1e9:6.2f} +/- {err*1e9:4.2f}      | {img*1e6:10.1f} | {img/PIXEL:8.0f} | {motif*1e3:24.2f} | "
          f"{2*(f1+F2)*1e3:16.0f} | {h_max(f1)*1e3:10.1f} | {flux_relatif(f1):13.2f} | {flux_relatif(f1, False):23.2f} | "
          f"{flux_relatif(f1, False, True):34.2f} | {total*1e9:9.3f}")
print(f"  Le motif de diffraction de la fente sur le reseau depasse Lb = {LB*1e3:.0f} mm pour f1 > {FENTE*LB/(2*LAM_C)*1e3:.0f} mm : "
      "le budget de resolution y est moins fiable.")
print("  a = 75 um a f1 = 60 mm : d_lambda fente = "
      f"{d_fente(75e-6, 60e-3)*1e9:.2f} nm (meme resolution que a = 50 um a 40 mm), surface de fente x1,5")

# ---------------- 2) Defocalisation ----------------
W = np.genfromtxt(OUT / "w90_defocalisation.csv", delimiter=",", names=True)
DELTA = W["delta_mm"]
W90 = {f1: W[f"W90_um_f1_{f1}mm"] for f1 in F1_MM}

def terme_fente(f1_mm, delta_mm):
    """Terme de fente (nm) pour un defaut de mise au point delta (mm) : d_lambda * W90(delta)/W90(0)."""
    w = W90[f1_mm]
    return d_fente(FENTE, f1_mm * 1e-3) * 1e9 * np.interp(np.abs(delta_mm), DELTA, w) / w[0]

print("\nDefocalisation (550 nm) : terme de fente effectif (nm)")
print("delta (mm) | " + " | ".join(f"f1 = {f1:3d} mm" for f1 in F1_MM))
for k, dl in enumerate(DELTA):
    print(f"{dl:10.2f} | " + " | ".join(f"{terme_fente(f1, dl):10.2f}" for f1 in F1_MM))
grille = np.linspace(0, DELTA.max(), 2001)
print("Defaut de mise au point a partir duquel le terme de fente de f1 depasse celui de 40 mm (interpolation lineaire sur 5 points) :")
CROISE = {}
for f1 in F1_MM:
    if f1 == 40:
        continue
    ecart = terme_fente(f1, grille) - terme_fente(40, grille)
    CROISE[f1] = grille[np.argmax(ecart > 0)] if np.any(ecart > 0) and ecart[0] <= 0 else np.nan
    if ecart[0] > 0:
        print(f"  f1 = {f1:3d} mm : toujours au-dessus de 40 mm (deja {ecart[0]:+.2f} nm a la mise au point exacte)")
    elif np.isfinite(CROISE[f1]):
        print(f"  f1 = {f1:3d} mm : a partir de delta = {CROISE[f1]:.2f} mm")
    else:
        print(f"  f1 = {f1:3d} mm : jamais sur 0 a {DELTA.max():.0f} mm")

# ---------------- 3) Chromatisme, lentille simple en N-BK7 ----------------
def focale(lam_nm, f550=F2 * 1e3):
    """Focale (mm) d'une lentille mince en N-BK7 de focale f550 a 550 nm."""
    return f550 * (indice(0.55) - 1) / (indice(np.asarray(lam_nm) * 1e-3) - 1)

print(f"\nN-BK7 : n_d (587,6 nm) calcule = {float(indice(0.5876)):.5f} (fiche SCHOTT : 1,51680)")
LAMS = np.arange(400, 701, 50)
f_min, f_max = float(focale(400)), float(focale(700))
f_comp = 0.5 * (f_min + f_max)                     # foyer de compromis sur 400-700 nm
print(f"Focale de L2 : {f_min:.2f} mm a 400 nm, {focale(550):.2f} mm a 550 nm, {f_max:.2f} mm a 700 nm "
      f"(variation {100*(f_max-f_min)/focale(550):.1f} %) ; foyer de compromis {f_comp:.2f} mm")
print("Terme de fente effectif (nm), camera reglee a 550 nm | avec le foyer de compromis")
print("lambda (nm) | f (mm) | defaut (mm) | " + " | ".join(f"{f1:3d} mm" for f1 in F1_MM) + "  ||  " + " | ".join(f"{f1:3d} mm" for f1 in F1_MM))
for lam in LAMS:
    d = float(focale(lam)) - F2 * 1e3
    dc = float(focale(lam)) - f_comp
    print(f"{lam:11d} | {float(focale(lam)):6.2f} | {d:+11.2f} | " + " | ".join(f"{terme_fente(f1, d):6.2f}" for f1 in F1_MM)
          + "  ||  " + " | ".join(f"{terme_fente(f1, dc):6.2f}" for f1 in F1_MM))
lam_fin = np.linspace(400, 700, 301)
print("Sur 400-700 nm :")
for f1 in F1_MM:
    t0 = terme_fente(f1, focale(lam_fin) - F2 * 1e3)
    tc = terme_fente(f1, focale(lam_fin) - f_comp)
    print(f"  f1 = {f1:3d} mm : camera a 550 nm : max {t0.max():.2f} nm, moyenne {t0.mean():.2f} nm ; "
          f"foyer de compromis : max {tc.max():.2f} nm, moyenne {tc.mean():.2f} nm ; "
          f"hausse a 400 nm : {100*(terme_fente(f1, float(focale(400)) - F2*1e3)/(d_fente(FENTE, f1*1e-3)*1e9) - 1):.0f} %")

# ---------------- 4) Figures ----------------
TEXTE, TEXTE2, GRILLE = "#0b0b0b", "#52514e", "#e4e3df"
plt.rcParams.update({"axes.edgecolor": TEXTE2, "axes.labelcolor": TEXTE2, "xtick.color": TEXTE2, "ytick.color": TEXTE2,
                     "text.color": TEXTE, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.color": GRILLE, "grid.linewidth": 0.8, "font.size": 10})
# f1 est une grandeur ordonnee : une seule teinte, du clair (f1 court) au fonce (f1 long)
COULEUR = dict(zip(F1_MM, ("#6baed6", "#4292c6", "#2171b5", "#08519c", "#08306b")))
MARQUEUR = dict(zip(F1_MM, ("o", "s", "^", "D", "v")))

# M4_10 : (gauche) terme de fente selon la largeur a ; (droite) terme de fente selon la defocalisation
fig, axes = plt.subplots(1, 2, figsize=(11, 4.6))
ax = axes[0]
a_um = np.linspace(10, 150, 281)
for f1 in F1_MM:
    ax.plot(a_um, d_fente(a_um * 1e-6, f1 * 1e-3) * 1e9, color=COULEUR[f1], lw=2, label=f"f1 = {f1} mm")
    ax.plot([50], [d_fente(FENTE, f1 * 1e-3) * 1e9], MARQUEUR[f1], color=COULEUR[f1], ms=8, mec="white", mew=1.5)
ax.axvline(50, color=TEXTE2, lw=0.8, ls=":")
ax.set(xlabel="Largeur de fente a (µm)", ylabel="Terme de fente δλ (nm), mise au point exacte",
       title="Résolution de la fente selon a et f1", ylim=(0, None))
ax.legend(frameon=False, loc="upper left")

ax = axes[1]
for f1 in F1_MM:
    ax.plot(DELTA, terme_fente(f1, DELTA), MARQUEUR[f1] + "-", color=COULEUR[f1], lw=2, ms=7, mec="white", mew=1.2, label=f"f1 = {f1} mm")
ax.set(xlabel="Défaut de mise au point δ = d4 − f2 (mm)", ylabel="Terme de fente effectif (nm)",
       title="Terme de fente et défocalisation", ylim=(0, None))
ax.legend(frameon=False, loc="upper left")
fig.text(0.99, 0.01, "a = 50 µm, θi = 3°, f2 = 25 mm ; défocalisation : modèle de Fourier à 550 nm, 5 points calculés reliés par des droites", ha="right", va="bottom",
         fontsize=8, color=TEXTE2)
fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.savefig(OUT / "M4_10_comparaison_f1.png", dpi=180)

# M4_11 : terme de fente selon la longueur d'onde, lentille simple en N-BK7 (gauche : camera a 550 nm ; droite : foyer de compromis)
fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), sharey=True)
for ax, ref, titre in ((axes[0], F2 * 1e3, "Caméra réglée à 550 nm"), (axes[1], f_comp, f"Foyer de compromis ({f_comp:.2f} mm)")):
    for f1 in F1_MM:
        ax.plot(lam_fin, terme_fente(f1, focale(lam_fin) - ref), color=COULEUR[f1], lw=2, label=f"f1 = {f1} mm")
    ax.set(xlabel="Longueur d'onde (nm)", title=titre, ylim=(0, None))
axes[0].set_ylabel("Terme de fente effectif (nm)")
h, l = axes[0].get_legend_handles_labels()
fig.legend(h, l, frameon=False, loc="lower center", ncol=len(F1_MM), bbox_to_anchor=(0.5, 0.03))
fig.suptitle("Chromatisme d'une lentille simple en N-BK7 (L2, f = 25 mm à 550 nm)", fontsize=11)
fig.text(0.99, 0.01, "Interpolation linéaire entre les 5 défauts de mise au point calculés (0 à 2 mm)", ha="right", va="bottom",
         fontsize=8, color=TEXTE2)
fig.tight_layout(rect=(0, 0.1, 1, 0.96)); fig.savefig(OUT / "M4_11_chromatisme.png", dpi=180)

# M4_12 : sensibilite du terme de fente a la defocalisation (figure du rapport), f1 = 20 a 100 mm
fig, ax = plt.subplots(figsize=(6.0, 3.2))
for f1 in F1_MM:
    ax.plot(DELTA, terme_fente(f1, DELTA), MARQUEUR[f1] + "-", color=COULEUR[f1], lw=2, ms=7, mec="white", mew=1.2, label=f"f1 = {f1} mm")
ax.set(xlabel="Défaut de mise au point δ = d4 − f2 (mm)", ylabel="Terme de fente effectif (nm)", ylim=(0, None))
ax.legend(frameon=False, loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=len(F1_MM), fontsize=8.5, handlelength=1.6, columnspacing=1.2)
fig.text(0.99, 0.01, "a = 50 µm, f2 = 25 mm, 550 nm ; points calculés (modèle de Fourier) reliés par des droites", ha="right", va="bottom",
         fontsize=7, color=TEXTE2)
fig.tight_layout(rect=(0, 0.04, 1, 1)); fig.savefig(OUT / "M4_12_sensibilite_defocalisation.png", dpi=200)

plt.show()
