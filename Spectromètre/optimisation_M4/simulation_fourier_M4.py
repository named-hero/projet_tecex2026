"""PHS3910 M4 - Modele d'optique de Fourier 1D (niveau 2), incidence oblique.
Dependances : numpy, matplotlib. Meme jeu de parametres que simulation_M4.py.

Chaine (axe de dispersion x, fente supposee longue, hauteur H sans effet sur le spectre) :
    1) fente            U0(x0) = rect(x0/l)
    2) L1 (f1)          U1(x1) = TF[U0](fx),  x1 = lambda*f1*fx            (plan du reseau)
    3) ouverture + reseau (ordre m) : le faisceau diffracte a pour coordonnee transverse
                        xb = r*x1, avec r = cos(beta)/cos(alpha)           (facteur anamorphique)
                        amplitude * sqrt(eta_blaze), ouverture |x1| <= Lb/2,
                        defocalisation d4 - f2 = delta : facteur exp(-i*pi*delta*xb^2/(lambda*f2^2))
    4) L2 (f2)          U2(x2') = TF[Ub](fx2),  x2' = lambda*f2*fx2/r      (x2' = x2 - x2c(lambda))
    5) camera           I(x2) = |U2(x2 - x2c(lambda))|^2, x2c = f2*tan(beta(lambda) - beta(lambda_c))
    6) source blanche   somme INCOHERENTE sur lambda (poids : eta(lambda)*S(lambda)*T_filtre(lambda)),
                        puis integration sur les pixels de 1,55 um.
Pour Lb infini, delta = 0 : la raie est un rectangle de largeur l*(f2/f1)*cos(alpha)/cos(beta),
ce qui est le terme rect de l'expression d'Olivier (un ordre n = m de la somme).
    7) image RGB        (section 3, configuration retenue ALPHA_RET, F1_RET, sans filtre : point iii du mandat)
                        chaque lambda ajoute sa couleur. COULEUR = "capteur" : sensibilite spectrale R, G, B de
                        la camera HQ (document Raspberry Pi RP-008148, fichier imx477_reponse_spectrale.csv)
                        multipliee par la transmission du filtre IR-cut, avec balance des blancs sur source plate ;
                        COULEUR = "mandat" : fonction wavelength_to_rgb fournie avec le mandat.
Focale d'entree : F1 = 60 mm dans ce script, comparee a 20, 40, 50 et 100 mm aux sections 1 et 2b (F1_LISTE). La section 1 ecrit
w90_defocalisation.csv, lu par incertitudes_M4.py et comparaison_f1_M4.py.
Hypotheses : scalaire, 1D, paraxial autour du rayon central de chaque ordre, sans chromatisme
des lentilles, source plate S(lambda) = 1. Le profil monochrome n'utilise aucune reponse de capteur.
Courbes du capteur : echantillonnees tous les 20 nm, lues sur les graphiques vectoriels du PDF ;
courbe IR-cut numerisee sur une image du PDF (precision d'environ 1 %).
"""
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parent

# ---------------- Parametres (SI), identiques a simulation_M4.py ----------------
TRAITS_MM = 600
PAS = 1e-3 / TRAITS_MM
LAMBDA_BLAZE = 500e-9
GAMMA = np.arcsin(LAMBDA_BLAZE / (2 * PAS))
ORDRE = 1
ALPHA = np.deg2rad(3.0)         # incidence candidate (Keira), a justifier
F1, F2 = 60e-3, 25e-3          # F1 retenue ; la comparaison avec 40 mm est faite par F1_LISTE
F1_LISTE = (20e-3, 40e-3, 50e-3, 60e-3, 100e-3)       # focales d'entree comparees (sections 1 et 2b)
FENTE = 50e-6                   # hypothese
ALPHA_RET = np.deg2rad(0.0)     # incidence retenue (4.1.2), utilisee seulement par l'image RGB (section 3)
F1_RET = 40e-3                  # focale d'entree retenue (4.1.4), utilisee seulement par l'image RGB (section 3)
LB = 2e-3                       # largeur du faisceau sur le reseau : valeur du code de depart (Keira), a confirmer ; 10 mm dans la v1 du brouillon
LB_NUM = 40e-3                  # fenetre numerique minimale en x1 (m) : sans elle, un Lb petit donne un pas sur le capteur trop grossier (4,7 um a Lb = 2 mm) ; W90 converge a 1 % pres (20 mm : ecart inferieur a 1 %), la largeur a mi-hauteur a +/- 1 um (franges)
DEFOCUS = 0.0                   # d4 - f2 (m)
PIXEL, N_PIX = 1.55e-6, 4056
W_CAPTEUR = N_PIX * PIXEL
LAM_MIN, LAM_MAX, LAM_C = 400e-9, 700e-9, 550e-9
LAM_COUPURE = 545e-9            # filtre passe-haut ideal (a remplacer par la courbe reelle)
LARGEUR_COUPURE = 2e-9          # largeur de la transition du filtre (hypothese)

COULEUR = "capteur"             # "capteur" : courbes R, G, B x IR-cut (Raspberry Pi) ; "mandat" : wavelength_to_rgb
EXPOSITION = 1.0                # image RGB : > 1 sature les canaux comme sur les photos reelles
AFFICHAGE_ROUGE_A_GAUCHE = True # comme sur les photos de la seance (rouge a gauche) ; ne change pas le calcul

# Echantillonnage numerique
N = 2 ** 14
                                 # pas de la fente : DX0 = LAM_MIN * f1 / (1.2 * LB), fenetre en x1 d'au moins Lb (voir grille())
SOUS_PIX = 5                     # sous-echantillons par pixel
D_LAM = 0.1e-9                   # pas de la somme sur lambda (< pixel en position)


# ---------------- Geometrie et reseau (comme simulation_M4.py) ----------------
def beta(lam, alpha):
    return np.arcsin(ORDRE * np.asarray(lam) / PAS - np.sin(alpha))

def x2c(lam, alpha, f2):
    return f2 * np.tan(beta(lam, alpha) - beta(LAM_C, alpha))

def eta_blaze(lam, alpha):
    b = beta(lam, alpha)
    u = (PAS * np.cos(GAMMA) / np.asarray(lam)) * (np.sin(alpha - GAMMA) + np.sin(b - GAMMA))
    return np.sinc(u) ** 2

def transmission_filtre(lam):
    return 0.5 * (1 + np.tanh((np.asarray(lam) - LAM_COUPURE) / LARGEUR_COUPURE))


def wavelength_to_rgb(wavelength, gamma=0.8):
    '''Fonction fournie avec le mandat (RGBtoWavelength.json), d'apres Dan Bruton.
    Longueur d'onde en nm (380 a 750). Retourne (R, G, B) entre 0 et 255.'''
    wavelength = float(wavelength)
    if wavelength >= 380 and wavelength <= 440:
        attenuation = 0.3 + 0.7 * (wavelength - 380) / (440 - 380)
        R = ((-(wavelength - 440) / (440 - 380)) * attenuation) ** gamma
        G = 0.0
        B = (1.0 * attenuation) ** gamma
    elif wavelength >= 440 and wavelength <= 490:
        R = 0.0
        G = ((wavelength - 440) / (490 - 440)) ** gamma
        B = 1.0
    elif wavelength >= 490 and wavelength <= 510:
        R = 0.0
        G = 1.0
        B = (-(wavelength - 510) / (510 - 490)) ** gamma
    elif wavelength >= 510 and wavelength <= 580:
        R = ((wavelength - 510) / (580 - 510)) ** gamma
        G = 1.0
        B = 0.0
    elif wavelength >= 580 and wavelength <= 645:
        R = 1.0
        G = (-(wavelength - 645) / (645 - 580)) ** gamma
        B = 0.0
    elif wavelength >= 645 and wavelength <= 750:
        attenuation = 0.3 + 0.7 * (750 - wavelength) / (750 - 645)
        R = (1.0 * attenuation) ** gamma
        G = 0.0
        B = 0.0
    else:
        R = 0.0
        G = 0.0
        B = 0.0
    return (int(R * 255), int(G * 255), int(B * 255))


# Reponse spectrale du capteur (R, G = moyenne de Green1 et Green2, B) et transmission du filtre IR-cut
_D = np.genfromtxt(OUT / "imx477_reponse_spectrale.csv", delimiter=",", names=True)

def reponse_capteur(lam_nm):
    return np.array([np.interp(lam_nm, _D["lambda_nm"], _D[c] * _D["T_IRcut"]) for c in "RGB"])

_LAM_WB = np.arange(380.0, 781.0)
_WB = 1.0 / np.sum([reponse_capteur(l) for l in _LAM_WB], axis=0)    # source plate -> R = G = B

def couleur_pixel(lam_nm):
    """Poids (R, G, B) d'une longueur d'onde dans l'image."""
    if COULEUR == "mandat":
        return np.array(wavelength_to_rgb(lam_nm)) / 255
    return reponse_capteur(lam_nm) * _WB


# ---------------- Optique de Fourier ----------------
def ft(u, dx):
    """TF centree, approximation de l'integrale de Fourier (pas dx)."""
    return np.fft.fftshift(np.fft.fft(np.fft.ifftshift(u))) * dx

_GRILLES = {}
def grille(f1):
    """Grille numerique de la fente pour la focale f1 (la fenetre en x1 depend de f1). Mise en cache."""
    if f1 not in _GRILLES:
        dx0 = LAM_MIN * f1 / (1.2 * max(LB, LB_NUM))   # fenetre en x1 : au moins Lb a toutes les longueurs d'onde, et au moins LB_NUM (pas de la grille sur le capteur)
        x0 = (np.arange(N) - N // 2) * dx0
        u0 = (np.abs(x0) <= FENTE / 2).astype(float)
        fx = np.fft.fftshift(np.fft.fftfreq(N, d=dx0))
        _GRILLES[f1] = (fx, fx[1] - fx[0], ft(u0, dx0))
    return _GRILLES[f1]

def ligne(lam, alpha=ALPHA, defoc=DEFOCUS, f1=F1):
    """Profil d'intensite d'une raie monochromatique, flux normalise a 1.
    Retourne (x2', I) avec x2' = x2 - x2c(lambda)."""
    fx, dfx, U1_moins = grille(f1)
    r = np.cos(beta(lam, alpha)) / np.cos(alpha)
    x1 = lam * f1 * fx
    dx1 = lam * f1 * dfx
    xb = r * x1
    Ub = U1_moins * (np.abs(x1) <= LB / 2) * np.exp(-1j * np.pi * defoc * xb ** 2 / (lam * F2 ** 2))
    U2 = ft(Ub, dx1)
    x2p = lam * F2 * np.fft.fftshift(np.fft.fftfreq(N, d=dx1)) / r
    I = np.abs(U2) ** 2
    dx2 = x2p[1] - x2p[0]
    return x2p, I / (I.sum() * dx2)

def fwhm(x, I):
    m = I >= I.max() / 2
    return (np.flatnonzero(m)[-1] - np.flatnonzero(m)[0] + 1) * (x[1] - x[0])

def w90(x, I):
    """Largeur contenant 90 % de l'energie (entre les quantiles 5 % et 95 %)."""
    c = np.cumsum(I) / I.sum()
    return np.interp(0.95, c, x) - np.interp(0.05, c, x)


# ---------------- 1) Validation : raie monochromatique et defocalisation, pour chaque focale f1 ----------------
DEFOC_LISTE = (0.0, 0.25e-3, 0.5e-3, 1e-3, 2e-3)
w90_tab = {}
for f1 in F1_LISTE:
    print(f"\n=== f1 = {f1*1e3:.0f} mm : Lambda = {PAS*1e6:.3f} um, alpha = {np.rad2deg(ALPHA):.1f} deg, f2 = {F2*1e3:.0f} mm, "
          f"fente = {FENTE*1e6:.0f} um, Lb = {LB*1e3:.1f} mm (hypothese)")
    print("Raie monochromatique (largeur a mi-hauteur) :  FFT  |  geometrique a*(f2/f1)*cos(a)/cos(b)")
    for lam in (450e-9, 550e-9, 650e-9):
        x2p, I = ligne(lam, f1=f1)
        geo = FENTE * (F2 / f1) * np.cos(ALPHA) / np.cos(beta(lam, ALPHA))
        disp = PAS * np.cos(beta(lam, ALPHA)) / (ORDRE * F2)     # dlambda/dx2
        print(f"  {lam*1e9:.0f} nm : {fwhm(x2p, I)*1e6:6.2f} um  |  {geo*1e6:6.2f} um   "
              f"(soit {fwhm(x2p, I)*disp*1e9:.2f} nm, pixel = {PIXEL*1e6:.2f} um)")
    print("Sensibilite a la defocalisation d4 - f2 (550 nm), illumination coherente de la fente :")
    w90_tab[f1] = []
    for d in DEFOC_LISTE:
        x2p, I = ligne(LAM_C, defoc=d, f1=f1)
        w90_tab[f1].append(w90(x2p, I) * 1e6)
        print(f"  d4 - f2 = {d*1e3:4.2f} mm : largeur a 90 % de l'energie {w90_tab[f1][-1]:6.2f} um")

# Table lue par incertitudes_M4.py et comparaison_f1_M4.py
with open(OUT / "w90_defocalisation.csv", "w", encoding="utf-8") as fh:
    fh.write("delta_mm," + ",".join(f"W90_um_f1_{f1*1e3:.0f}mm" for f1 in F1_LISTE) + "\n")
    for k, d in enumerate(DEFOC_LISTE):
        fh.write(f"{d*1e3:.2f}," + ",".join(f"{w90_tab[f1][k]:.2f}" for f1 in F1_LISTE) + "\n")
print("\nTable ecrite dans", OUT / "w90_defocalisation.csv")

# ---------------- 2) Image polychromatique, sans et avec filtre ----------------
pas_fin = PIXEL / SOUS_PIX
xf = (np.arange(N_PIX * SOUS_PIX) - N_PIX * SOUS_PIX / 2 + 0.5) * pas_fin
lams = np.arange(LAM_MIN - 10e-9, LAM_MAX + 10e-9, D_LAM)
sans = np.zeros_like(xf)
avec = np.zeros_like(xf)
for lam in lams:
    x2p, I = ligne(lam)
    profil = np.interp(xf - x2c(lam, ALPHA, F2), x2p, I, left=0, right=0)
    w = float(eta_blaze(lam, ALPHA))                      # source plate : S(lambda) = 1
    wf = w * float(transmission_filtre(lam))
    sans += w * profil
    avec += wf * profil
pix_sans = sans.reshape(-1, SOUS_PIX).sum(axis=1) * pas_fin
pix_avec = avec.reshape(-1, SOUS_PIX).sum(axis=1) * pas_fin
x_pix = (np.arange(N_PIX) - N_PIX / 2 + 0.5) * PIXEL

# Etalonnage lambda(x) par la relation du reseau (suppose connue), puis transmission mesuree
lam_grille = np.linspace(LAM_MIN, LAM_MAX, 2001)
lam_pix = np.interp(x_pix, x2c(lam_grille, ALPHA, F2), lam_grille)
ok = (x_pix > x2c(LAM_MIN, ALPHA, F2)) & (x_pix < x2c(LAM_MAX, ALPHA, F2)) & (pix_sans > 0.05 * pix_sans.max())
T_mes = np.where(ok, pix_avec / np.where(pix_sans > 0, pix_sans, 1), np.nan)

i50 = np.flatnonzero(ok & (T_mes >= 0.5))[0]
lam50 = np.interp(0.5, [T_mes[i50 - 1], T_mes[i50]], [lam_pix[i50 - 1], lam_pix[i50]])
def croise(niveau):
    """Longueur d'onde ou la transmission mesuree atteint `niveau` (interpolation entre pixels)."""
    i = np.flatnonzero(ok & (T_mes >= niveau))[0]
    return np.interp(niveau, [T_mes[i - 1], T_mes[i]], [lam_pix[i - 1], lam_pix[i]])
print(f"\nFiltre ideal a {LAM_COUPURE*1e9:.1f} nm : coupure retrouvee a {lam50*1e9:.2f} nm "
      f"(ecart {(lam50-LAM_COUPURE)*1e9:+.2f} nm)")
print(f"  Transition 10-90 % : {(croise(0.9)-croise(0.1))*1e9:.2f} nm "
      f"(transition propre du filtre : {LARGEUR_COUPURE*2.2*1e9:.1f} nm environ)")

# ---------------- 2b) Coupure retrouvee et transition 10-90 % selon f1 ----------------
def coupure(f1):
    """Filtre ideal : point a 50 % de avec/sans et largeur de la transition 10-90 %, pour la focale f1."""
    s_, a_ = np.zeros_like(xf), np.zeros_like(xf)
    for lam in lams:
        x2p, I = ligne(lam, f1=f1)
        profil = np.interp(xf - x2c(lam, ALPHA, F2), x2p, I, left=0, right=0)
        w = float(eta_blaze(lam, ALPHA))
        s_ += w * profil
        a_ += w * float(transmission_filtre(lam)) * profil
    ps = s_.reshape(-1, SOUS_PIX).sum(axis=1) * pas_fin
    pa = a_.reshape(-1, SOUS_PIX).sum(axis=1) * pas_fin
    ok_ = (x_pix > x2c(LAM_MIN, ALPHA, F2)) & (x_pix < x2c(LAM_MAX, ALPHA, F2)) & (ps > 0.05 * ps.max())
    T = np.where(ok_, pa / np.where(ps > 0, ps, 1), np.nan)
    def croise(niveau):
        i = np.flatnonzero(ok_ & (T >= niveau))[0]
        return np.interp(niveau, [T[i - 1], T[i]], [lam_pix[i - 1], lam_pix[i]])
    return croise(0.5), croise(0.9) - croise(0.1)

print(f"\nFiltre ideal a {LAM_COUPURE*1e9:.1f} nm, transition propre {LARGEUR_COUPURE*2.2*1e9:.1f} nm (10-90 %), selon f1 :")
print("f1 (mm) | coupure retrouvee (nm) | ecart (nm) | transition 10-90 % mesuree (nm) | elargissement (nm)")
for f1 in F1_LISTE:
    c50, t1090 = coupure(f1)
    print(f"{f1*1e3:7.0f} | {c50*1e9:22.2f} | {(c50-LAM_COUPURE)*1e9:+10.2f} | {t1090*1e9:31.2f} | {t1090*1e9-LARGEUR_COUPURE*2.2e9:+18.2f}")

# ---------------- Figures ----------------
fig, ax = plt.subplots(figsize=(9, 4.6))
for lam in (450e-9, 550e-9, 650e-9):
    x2p, I = ligne(lam)
    sel = np.abs(x2p) < 60e-6
    ax.plot(x2p[sel] * 1e6, I[sel] / I.max(), label=f"{lam*1e9:.0f} nm")
ax.axvspan(-PIXEL * 1e6 / 2, PIXEL * 1e6 / 2, color="gray", alpha=.25, label="1 pixel")
ax.set(xlabel="x2 - x2c(lambda) (um)", ylabel="Intensite normalisee",
       title="Raies monochromatiques au capteur (modele de Fourier)")
ax.legend(); ax.grid(alpha=.25); fig.tight_layout(); fig.savefig(OUT / "M4_04_raies_fourier.png", dpi=180)

fig, axes = plt.subplots(2, 1, figsize=(9, 7), sharex=True)
vis = (x_pix > x2c(LAM_MIN, ALPHA, F2)) & (x_pix < x2c(LAM_MAX, ALPHA, F2))
axes[0].plot(lam_pix[vis] * 1e9, pix_sans[vis], label="sans filtre")
axes[0].plot(lam_pix[vis] * 1e9, pix_avec[vis], label="avec filtre")
axes[0].set(ylabel="Signal par pixel (u.a.)", title="Profil sur le capteur, source plate, monochrome")
axes[0].legend(); axes[0].grid(alpha=.25)
axes[1].plot(lam_pix[vis] * 1e9, T_mes[vis], label="avec / sans (simule)")
axes[1].plot(lam_grille * 1e9, transmission_filtre(lam_grille), "--", label="filtre ideal")
axes[1].set(xlabel="Longueur d'onde (nm)", ylabel="Transmission")
axes[1].legend(); axes[1].grid(alpha=.25)
fig.tight_layout(); fig.savefig(OUT / "M4_05_filtre_fourier.png", dpi=180)

# ---------------- 3) Image RGB sans filtre, configuration retenue (point iii du mandat) ----------------
# Constantes ALPHA_RET et F1_RET propres a ce bloc : les sections 1 et 2 restent a ALPHA et F1.
rgb = np.zeros((xf.size, 3))
for lam in np.arange(360e-9, 740e-9, D_LAM):          # source plate sur 360-740 nm : pas de coupure franche dans l'image
    x2p, I = ligne(lam, alpha=ALPHA_RET, f1=F1_RET)
    profil = np.interp(xf - x2c(lam, ALPHA_RET, F2), x2p, I, left=0, right=0)
    rgb += (float(eta_blaze(lam, ALPHA_RET)) * profil)[:, None] * couleur_pixel(lam * 1e9)   # source plate : S(lambda) = 1
rgb = rgb.reshape(-1, SOUS_PIX, 3).sum(axis=1) * pas_fin
img_sans = np.clip(EXPOSITION * rgb / max(rgb.max(), 1e-30), 0, 1)

lam_ticks = np.arange(400, 701, 50)
i_orig = x2c(lam_ticks * 1e-9, ALPHA_RET, F2) / PIXEL + N_PIX / 2 - 0.5    # colonne de chaque longueur d'onde
print(f"\nImage RGB sans filtre (f1 = {F1_RET*1e3:.0f} mm, f2 = {F2*1e3:.0f} mm, theta_i = {np.rad2deg(ALPHA_RET):.0f} deg) : "
      f"400 nm a la colonne {i_orig[0]:.0f}, 700 nm a la colonne {i_orig[-1]:.0f} sur {N_PIX}")
print("lambda (nm) | colonne |    R     G     B   (signal normalise, maximum = 1)")
for l, c in zip(lam_ticks, i_orig):
    print(f"{l:11d} | {c:7.0f} | " + "  ".join(f"{v:5.2f}" for v in img_sans[int(round(c))]))

if AFFICHAGE_ROUGE_A_GAUCHE:
    img_aff, j_aff = img_sans[::-1], N_PIX - 1 - i_orig
else:
    img_aff, j_aff = img_sans, i_orig

fig, axes = plt.subplots(2, 1, figsize=(7.2, 3.4), sharex=True, gridspec_kw={"height_ratios": [1, 1.6]})
axes[0].imshow(np.tile(img_aff[None, :, :], (60, 1, 1)), aspect="auto", interpolation="nearest", extent=[0, N_PIX, 0, 1])
axes[0].set(yticks=[])
for k, (nom, c) in enumerate(zip("RGB", ("tab:red", "tab:green", "tab:blue"))):
    axes[1].plot(np.arange(N_PIX), img_aff[:, k], c, label=nom)
axes[1].set(xlabel="Colonne de pixels", ylabel="Signal normalisé", xlim=(0, N_PIX))
axes[1].legend(ncol=3, fontsize=8, loc="upper right"); axes[1].grid(alpha=.25)
ax_top = axes[0].twiny(); ax_top.set_xlim(0, N_PIX)                      # axe supplementaire : longueur d'onde
ax_top.set_xticks(j_aff + 0.5); ax_top.set_xticklabels([f"{l:d}" for l in lam_ticks])
ax_top.set_xlabel("Longueur d'onde (nm)")
fig.tight_layout(); fig.savefig(OUT / "M4_06_rgb.png", dpi=200)

plt.show()
