"""PHS3910 M4 - Simulation niveau 1 (analytique), copie de travail.
Base : reproduire_optimisation_AVEC_GRAPHIQUES.py (Keira). Dependances : numpy, matplotlib.

Convention (Keira, type Thorlabs) : alpha et beta signes du meme cote de la normale,
Littrow a alpha = beta.
    sin(alpha) + sin(beta) = m*lambda/Lambda
Separation entre les bras optiques : |beta - alpha|.
Blaze : reflexion speculaire sur la facette, soit (alpha + beta)/2 = gamma.
Efficacite scalaire (sans ombrage) :
    eta = sinc^2( (Lambda*cos(gamma)/lambda) * ( sin(alpha - gamma) + sin(beta - gamma) ) )
avec sinc(u) = sin(pi*u)/(pi*u). Vaut 1 quand (alpha + beta)/2 = gamma.

Budget de resolution (largeurs spectrales en m, somme en quadrature) :
    fente       : a*Lambda*cos(alpha)/(m*f1)
    diffraction : lambda*Lambda*cos(alpha)/(m*Lb)
    pixel       : p*Lambda*cos(beta)/(m*f2)

Tableaux imprimes, repris dans la conception detaillee :
    1) ordres 0 a 3 (question 2)          2) separation selon l'incidence (question 1)
    3) largeurs de fente (question 5)     4) pas du reseau et pixels (question 6)
La comparaison des focales d'entree (40 contre 60 mm) est dans comparaison_f1_M4.py.
"""
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parent

# ---------------- Parametres (SI) ----------------
TRAITS_MM = 600                 # fiche technique (via Keira)
PAS = 1e-3 / TRAITS_MM          # Lambda (m)
LAMBDA_BLAZE = 500e-9           # fiche technique (via Keira)
GAMMA = np.arcsin(LAMBDA_BLAZE / (2 * PAS))   # angle de blaze (Littrow, m = 1), ~8,63 deg
ORDRE = 1

ALPHA_DEG = 3.0                 # incidence candidate (proposition de Keira), a justifier
F1 = 60e-3                      # focale d'entree retenue (m) ; repli a 40 mm, voir comparaison_f1_M4.py
F1_REPLI = 40e-3                # focale d'entree de repli (m)
F2 = 25e-3                      # focale de sortie (m)
FENTE = 50e-6                   # largeur de fente a (m), hypothese
H_FENTE = 5e-3                  # hauteur de fente h (m), HYPOTHESE (rapport fente/trou seulement)
LB = 2e-3                       # largeur du faisceau sur le reseau (m) : valeur du code de depart (Keira), a confirmer ; 10 mm dans la v1 du brouillon

PIXEL = 1.55e-6                 # IMX477
N_PIX = 4056
N_PIX_V = 3040                  # lignes du capteur (axe vertical, hauteur de la fente)
W_CAPTEUR = N_PIX * PIXEL       # 6,287 mm
H_CAPTEUR = N_PIX_V * PIXEL     # 4,712 mm
LAM_MIN, LAM_MAX, LAM_C = 400e-9, 700e-9, 550e-9
LAM = np.linspace(LAM_MIN, LAM_MAX, 601)


# ---------------- Modele ----------------
def beta(lam, alpha, m=ORDRE, pas=PAS):
    """Angle de diffraction (rad), meme convention que alpha (rad). NaN si l'ordre m n'existe pas."""
    with np.errstate(invalid="ignore"):
        return np.arcsin(m * np.asarray(lam) / pas - np.sin(alpha))

def x2(lam, alpha, f2, m=ORDRE, pas=PAS):
    """Position sur le capteur (m), origine a lambda_c."""
    return f2 * np.tan(beta(lam, alpha, m, pas) - beta(LAM_C, alpha, m, pas))

def eta_blaze(lam, alpha, m=ORDRE):
    b = beta(lam, alpha, m)
    u = (PAS * np.cos(GAMMA) / np.asarray(lam)) * (np.sin(alpha - GAMMA) + np.sin(b - GAMMA))
    return np.sinc(u) ** 2

def budget(lam, alpha, f1, f2, fente, lb, pas=PAS):
    b = beta(lam, alpha, ORDRE, pas)
    d_fente = fente * pas * np.cos(alpha) / (ORDRE * f1)
    d_diff = lam * pas * np.cos(alpha) / (ORDRE * lb)
    d_pix = PIXEL * pas * np.cos(b) / (ORDRE * f2)
    return d_fente, d_diff, d_pix, np.sqrt(d_fente**2 + d_diff**2 + d_pix**2)

def etendue(alpha, m=ORDRE, pas=PAS):
    """Etendue du spectre 400-700 nm sur le capteur, en unite de f2 (adimensionnel)."""
    return abs(float(x2(LAM_MAX, alpha, 1.0, m, pas) - x2(LAM_MIN, alpha, 1.0, m, pas)))

def f2_max(alpha, m=ORDRE, pas=PAS):
    """Focale de sortie maximale pour que 400-700 nm tienne sur le capteur (sans marge).
    Le spectre est suppose recentre sur le capteur (convention de la section 4.1.3 du brouillon)."""
    e = etendue(alpha, m, pas)
    return W_CAPTEUR / e if e > 0 else np.inf

def f(x, nd=2, suffixe=""):
    """Format d'une valeur, 'n.d.' si elle n'existe pas."""
    return f"{x:.{nd}f}{suffixe}" if np.isfinite(x) else "n.d."


# ---------------- Resume numerique ----------------
a0 = np.deg2rad(ALPHA_DEG)
b550 = float(beta(LAM_C, a0))
print(f"Lambda = {PAS*1e6:.3f} um, angle de blaze = {np.rad2deg(GAMMA):.2f} deg, capteur = {W_CAPTEUR*1e3:.3f} mm")
print("\nIncidence | beta(550) | separation | (a+b)/2 | eta(550) | f2 max (mm)")
for ad in (0, 3, 10, 20, 30, 40):
    a = np.deg2rad(ad)
    b = float(beta(LAM_C, a))
    print(f"{ad:8.1f}  | {np.rad2deg(b):8.2f}  | {abs(np.rad2deg(b)-ad):9.2f}  | "
          f"{(ad+np.rad2deg(b))/2:7.2f} | {float(eta_blaze(LAM_C, a)):7.3f}  | {f2_max(a)*1e3:7.1f}")

print(f"\nConfiguration choisie : alpha = {ALPHA_DEG} deg, f1 = {F1*1e3:.0f} mm, f2 = {F2*1e3:.0f} mm, fente = {FENTE*1e6:.0f} um, Lb = {LB*1e3:.1f} mm (hypothese)")
print(f"  x2(400) = {x2(LAM_MIN, a0, F2)*1e3:.3f} mm, x2(700) = {x2(LAM_MAX, a0, F2)*1e3:.3f} mm "
      f"(limites capteur : +/- {W_CAPTEUR/2*1e3:.3f} mm)")
ds, dd, dp, dt = budget(LAM_C, a0, F1, F2, FENTE, LB)
print(f"  Resolution a 550 nm : fente {ds*1e9:.2f} nm, diffraction {dd*1e9:.2f} nm, pixel {dp*1e9:.3f} nm, total {dt*1e9:.3f} nm")

# ---------------- 1) Ordres 0 a 3 (question 2) ----------------
print(f"\nOrdres de diffraction, alpha = {ALPHA_DEG} deg, f2 = {F2*1e3:.0f} mm (n.d. : l'ordre n'existe pas a cette longueur d'onde)")
print("ordre | beta(400) | beta(550) | beta(700) | etendue/f2 | f2 max (mm) | etendue a f2 (mm) | eta(550)")
for m in (0, 1, 2, 3):
    bs = [np.rad2deg(float(beta(l, a0, m))) for l in (LAM_MIN, LAM_C, LAM_MAX)]
    e = etendue(a0, m)
    print(f"{m:5d} | {f(bs[0]):>9s} | {f(bs[1]):>9s} | {f(bs[2]):>9s} | {f(e, 4):>10s} | "
          f"{f(f2_max(a0, m)*1e3 if e > 0 else np.nan, 1):>11s} | {f(e*F2*1e3 if e > 0 else np.nan):>17s} | {float(eta_blaze(LAM_C, a0, m)):7.3f}")
print(f"  Capteur : {W_CAPTEUR*1e3:.3f} mm. Recouvrements : l'ordre 1 de {LAM_MIN*1e9:.0f}-{LAM_MAX*1e9:.0f} nm coincide avec "
      f"l'ordre 2 de {LAM_MIN*1e9/2:.0f}-{LAM_MAX*1e9/2:.0f} nm (UV, absent) ;")
print(f"  l'ordre 2 de {LAM_MIN*1e9:.0f}-{LAM_MAX*1e9:.0f} nm coincide avec l'ordre 1 de {2*LAM_MIN*1e9:.0f}-{2*LAM_MAX*1e9:.0f} nm "
      f"(coupe par le filtre IR) et l'ordre 3 de {2*LAM_MIN*1e9/3:.0f}-{2*LAM_MAX*1e9/3:.0f} nm.")

# ---------------- 2) Separation selon l'incidence (question 1) ----------------
print(f"\nSeparation des bras |beta - alpha| selon l'incidence (m = {ORDRE})")
print("alpha | beta(400) | beta(550) | beta(700) | sep(400) | sep(550) | sep(700) | sep min 400-700 | eta(550)")
for ad in (0, 2, 3, 4, 5, 6, 8.63, 9.5, 10, 12, 15):
    a = np.deg2rad(ad)
    bs = [np.rad2deg(float(beta(l, a))) for l in (LAM_MIN, LAM_C, LAM_MAX)]
    sep_min = float(np.min(np.abs(np.rad2deg(beta(LAM, a)) - ad)))
    print(f"{ad:5.2f} | {bs[0]:9.2f} | {bs[1]:9.2f} | {bs[2]:9.2f} | {abs(bs[0]-ad):8.2f} | {abs(bs[1]-ad):8.2f} | "
          f"{abs(bs[2]-ad):8.2f} | {sep_min:15.2f} | {float(eta_blaze(LAM_C, a)):8.3f}")

# ---------------- 3) Largeurs de fente (question 5) ----------------
print(f"\nLargeur de fente a, f1 = {F1*1e3:.0f} mm, f2 = {F2*1e3:.0f} mm, alpha = {ALPHA_DEG} deg")
print("a (um) | d_lambda fente (nm) | image sur capteur (um) | (pixels)")
for a_um in (20, 50, 75, 100, 150):
    a = a_um * 1e-6
    d = a * PAS * np.cos(a0) / (ORDRE * F1)
    img = a * (F2 / F1) * np.cos(a0) / np.cos(b550)
    print(f"{a_um:6.0f} | {d*1e9:19.2f} | {img*1e6:22.1f} | {img/PIXEL:8.0f}")
print(f"  Hauteur maximale de fente : {H_CAPTEUR/(F2/F1)*1e3:.1f} mm (capteur {H_CAPTEUR*1e3:.2f} mm, grandissement vertical f2/f1 = {F2/F1:.3f})")
print(f"  Rapport des surfaces fente / trou (d = a) : 4h/(pi*a) = {4*H_FENTE/(np.pi*FENTE):.0f} pour h = {H_FENTE*1e3:.0f} mm, a = {FENTE*1e6:.0f} um (h hypothese)")
print(f"  Sans ouverture, source de 1 mm : d_lambda = {1e-3*PAS*np.cos(a0)/(ORDRE*F1)*1e9:.1f} nm")
img_unit = (F2 / F1) * np.cos(a0) / np.cos(b550)
print(f"  Bornes sur a : image >= 2 pixels : a >= {2*PIXEL/img_unit*1e6:.1f} um ; motif 2*lambda*f1/a <= Lb : "
      f"a >= {2*LAM_C*F1/LB*1e6:.1f} um (Lb = {LB*1e3:.0f} mm, hypothese)")
print(f"  Motif de diffraction de la fente sur le reseau 2*lambda*f1/a = {2*LAM_C*F1/FENTE*1e3:.2f} mm")

# ---------------- 4) Pas du reseau et pixels (question 6) ----------------
print(f"\nPas du reseau, f1 = {F1*1e3:.0f} mm, a = {FENTE*1e6:.0f} um, alpha = {ALPHA_DEG} deg, m = {ORDRE}")
print("traits/mm | Lambda (um) | d_lambda fente (nm) | etendue/f2 | f2 max (mm) | beta(700) (deg)")
for tr in (300, 600, 900, 1200):
    pas = 1e-3 / tr
    d = FENTE * pas * np.cos(a0) / (ORDRE * F1)
    print(f"{tr:9d} | {pas*1e6:11.3f} | {d*1e9:19.2f} | {etendue(a0, ORDRE, pas):10.3f} | {f2_max(a0, ORDRE, pas)*1e3:11.1f} | "
          f"{np.rad2deg(float(beta(LAM_MAX, a0, ORDRE, pas))):15.2f}")
print(f"\nPixels : echantillonnage {dp*1e9:.4f} nm/pixel a 550 nm, soit {ds/dp:.1f} pixels par element de resolution ({ds*1e9:.2f} nm)")
print("regroupement | nm par colonne | colonnes par element de resolution")
for k in (1, 2, 4):
    print(f"{k:12d} | {k*dp*1e9:14.3f} | {ds/(k*dp):.1f}")

# ---------------- Figures ----------------
# 1 - couverture spectrale selon f2
fig, ax = plt.subplots(figsize=(9, 5))
for f2 in (20e-3, 25e-3, 30e-3, 40e-3):
    ax.plot(LAM * 1e9, x2(LAM, a0, f2) * 1e3, label=f"f2 = {f2*1e3:.0f} mm")
ax.axhline(W_CAPTEUR / 2 * 1e3, color="k", ls="--"); ax.axhline(-W_CAPTEUR / 2 * 1e3, color="k", ls="--", label="limites capteur")
ax.set(xlabel="Longueur d'onde (nm)", ylabel="Position sur le capteur (mm)",
       title=f"Couverture spectrale, alpha = {ALPHA_DEG} deg, m = {ORDRE}")
ax.legend(); ax.grid(alpha=.25); fig.tight_layout(); fig.savefig(OUT / "M4_01_couverture.png", dpi=180)

# 2 - efficacite de blaze selon l'incidence
fig, ax = plt.subplots(figsize=(9, 5))
for ad in (0, 3, 10, 20, 30):
    ax.plot(LAM * 1e9, eta_blaze(LAM, np.deg2rad(ad)), label=f"alpha = {ad} deg")
ax.set(xlabel="Longueur d'onde (nm)", ylabel="Efficacite scalaire relative",
       title="Enveloppe de blaze (modele scalaire, sans ombrage)", ylim=(0, 1.02))
ax.legend(); ax.grid(alpha=.25); fig.tight_layout(); fig.savefig(OUT / "M4_02_blaze.png", dpi=180)

# 3 - budget de resolution : chaque terme selon son propre parametre (echelle log, meme axe vertical pour les trois panneaux)
SIG_A, SIG_F1_REL = 3e-6, 0.01              # HYPOTHESES de conception, comme dans incertitudes_M4.py
BLEU, ORANGE, GRIS, TEXTE2 = "#2a78d6", "#eb6834", "#6b6a66", "#52514e"
COUL = {F1: BLEU, F1_REPLI: ORANGE}
with plt.rc_context({"axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.alpha": .25,
                     "axes.edgecolor": TEXTE2, "axes.labelcolor": TEXTE2}):
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8), sharey=True)
    ds_nom = {f1: budget(LAM_C, a0, f1, F2, FENTE, LB)[0] * 1e9 for f1 in (F1, F1_REPLI)}
    dd_nom = budget(LAM_C, a0, F1, F2, FENTE, LB)[1] * 1e9
    dp_nom = budget(LAM_C, a0, F1, F2, FENTE, LB)[2] * 1e9

    # (a) selon la largeur de fente : terme de fente, diffraction, pixel, total, bande d'incertitude
    ax = axes[0]
    fentes = np.linspace(10e-6, 150e-6, 281)
    for f1 in (F1, F1_REPLI):
        ds_, dd_, dp_, dt_ = budget(LAM_C, a0, f1, F2, fentes, LB)
        u = dt_ * 0 + (ds_ / dt_) * ds_ * np.hypot(SIG_A / fentes, SIG_F1_REL)       # incertitude sur le total (nm)
        c = COUL[f1]
        ax.plot(fentes * 1e6, ds_ * 1e9, color=c, lw=1.2, label=f"fente, f1 = {f1*1e3:.0f} mm")
        ax.plot(fentes * 1e6, dt_ * 1e9, color=c, lw=2.4, ls="--", label=f"total (quadrature), f1 = {f1*1e3:.0f} mm")
        ax.fill_between(fentes * 1e6, (dt_ - u) * 1e9, (dt_ + u) * 1e9, color=c, alpha=.18, lw=0)
        tot = float(budget(LAM_C, a0, f1, F2, FENTE, LB)[3]) * 1e9
        ax.plot([FENTE * 1e6], [tot], "o", color=c, ms=8, mec="white", mew=2)
        ax.annotate(f"{tot:.2f} nm", (FENTE * 1e6, tot), textcoords="offset points", xytext=(-52, 6) if f1 == F1_REPLI else (8, -14),
                    color=TEXTE2, fontsize=9)
    ax.axhline(dd_nom, color=GRIS, lw=1.2, ls=":", label=f"diffraction, Lb = {LB*1e3:.0f} mm ({dd_nom:.2f} nm)")
    ax.axhline(dp_nom, color=GRIS, lw=1.2, ls="-.", label=f"pixel, f2 = {F2*1e3:.0f} mm ({dp_nom:.2f} nm)")
    ax.axvline(FENTE * 1e6, color=TEXTE2, lw=.8, ls=":")
    ax.set(xlabel="Largeur de fente a (µm)", ylabel="Largeur spectrale à 550 nm (nm)", yscale="log", ylim=(0.03, 8),
           title="Selon a (f2 et Lb fixés)")
    ax.legend(frameon=False, fontsize=7.5, loc="upper center", bbox_to_anchor=(0.5, -0.17), ncol=2)

    # (b) terme pixel selon f2, avec la limite de couverture du capteur
    ax = axes[1]
    f2s = np.linspace(10e-3, 40e-3, 241)
    dp_f2 = budget(LAM_C, a0, F1, f2s, FENTE, LB)[2] * 1e9
    ax.plot(f2s * 1e3, dp_f2, color=GRIS, lw=2, ls="-.", label="pixel")
    for f1 in (F1, F1_REPLI):
        ax.axhline(ds_nom[f1], color=COUL[f1], lw=1.2, label=f"fente, f1 = {f1*1e3:.0f} mm, a = {FENTE*1e6:.0f} µm")
    ax.plot([F2 * 1e3], [dp_nom], "o", color=GRIS, ms=8, mec="white", mew=2)
    ax.annotate(f"{dp_nom:.2f} nm", (F2 * 1e3, dp_nom), textcoords="offset points", xytext=(8, -14), color=TEXTE2, fontsize=9)
    ax.axvline(f2_max(a0) * 1e3, color=TEXTE2, lw=.9, ls=":")
    ax.text(f2_max(a0) * 1e3 - 0.4, 0.12, f"f2 max = {f2_max(a0)*1e3:.1f} mm", rotation=90, ha="right", va="bottom",
            color=TEXTE2, fontsize=8)
    ax.set(xlabel="Focale de sortie f2 (mm)", yscale="log", title="Terme pixel selon f2")
    ax.legend(frameon=False, fontsize=7.5, loc="upper right")

    # (c) terme de diffraction selon la largeur de faisceau sur le reseau Lb
    ax = axes[2]
    lbs = np.linspace(1e-3, 20e-3, 191)
    dd_lb = budget(LAM_C, a0, F1, F2, FENTE, lbs)[1] * 1e9
    ax.plot(lbs * 1e3, dd_lb, color=GRIS, lw=2, ls=":", label="diffraction")
    for f1 in (F1, F1_REPLI):
        ax.axhline(ds_nom[f1], color=COUL[f1], lw=1.2, label=f"fente, f1 = {f1*1e3:.0f} mm, a = {FENTE*1e6:.0f} µm")
    ax.plot([LB * 1e3], [dd_nom], "o", color=GRIS, ms=8, mec="white", mew=2)
    ax.annotate(f"{dd_nom:.2f} nm\n(Lb = {LB*1e3:.0f} mm, valeur retenue)", (LB * 1e3, dd_nom), textcoords="offset points", xytext=(8, 6), color=TEXTE2, fontsize=9)
    dd_10 = float(budget(LAM_C, a0, F1, F2, FENTE, 10e-3)[1]) * 1e9
    ax.plot([10], [dd_10], "o", color=GRIS, ms=8, mec="white", mew=2)
    ax.annotate(f"{dd_10:.2f} nm\n(Lb = 10 mm, v1 du brouillon)", (10, dd_10), textcoords="offset points", xytext=(8, 8), color=TEXTE2, fontsize=9)
    ax.set(xlabel="Largeur du faisceau sur le réseau Lb (mm)", yscale="log", title="Terme de diffraction selon Lb")
    ax.legend(frameon=False, fontsize=7.5, loc="upper right")

    fig.suptitle(f"Budget de résolution à 550 nm, θi = {ALPHA_DEG:.0f}°, m = {ORDRE} : trois termes sommés en quadrature", fontsize=11)
    fig.text(0.99, 0.005, "Bandes d'incertitude : σ(a) = 3 µm et σ(f1) = 1 % (hypothèses) ; points : valeurs nominales", ha="right",
             va="bottom", fontsize=8, color=TEXTE2)
    fig.tight_layout(rect=(0, 0.03, 1, 0.96)); fig.savefig(OUT / "M4_03_budget_resolution.png", dpi=180, bbox_inches="tight")

plt.show()
