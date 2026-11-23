"""PHS3910 M4 - Incertitudes : sensibilite et Monte Carlo (formules analytiques du niveau 1).
Dependances : numpy, matplotlib. Meme convention d'angles que simulation_M4.py :
    sin(alpha) + sin(beta) = m*lambda/Lambda.

Partie 1 : sensibilite a un ecart-type de chaque parametre de conception (un parametre a la fois).
Partie 2 : Monte Carlo sur les parametres de conception (couverture du capteur, resolution).
    Les parties 1 et 2 sont faites pour la focale retenue f1 = 60 mm, puis pour le repli f1 = 40 mm ;
    la table d'elargissement par defocalisation vient de w90_defocalisation.csv (simulation_fourier_M4.py).
Partie 3 : Monte Carlo sur la mesure de la longueur d'onde de coupure d'un filtre :
    etalonnage de lambda(x) avec des lasers, puis position du point a 50 % du rapport avec/sans filtre.

ATTENTION : les ecarts-types de conception (SIGMA) sont des HYPOTHESES de travail, pas des tolerances mesurees.
Pour l'etalonnage par lasers, les longueurs d'onde viennent des spectres du dossier "Spectres des lasers-20261108"
(spectrometre de reference) ; seuls SIG_REF et la stabilite de chaque laser restent des hypotheses (voir LASERS_DEF).
"""
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parent
rng = np.random.default_rng(2026)          # graine fixe : resultats reproductibles
N_DESIGN = 20000
N_MESURE = 3000

ORDRE = 1
LAM_C, LAM_MIN, LAM_MAX = 550e-9, 400e-9, 700e-9
PIXEL, N_PIX = 1.55e-6, 4056
W_CAPTEUR = N_PIX * PIXEL
LB = 2e-3                                   # largeur du faisceau sur le reseau : valeur du code de depart (Keira), a confirmer

# ---------------- Valeurs nominales et ecarts-types (HYPOTHESES) ----------------
F1_LISTE = (60e-3, 40e-3)                   # focale retenue, puis focale de repli
NOM = dict(alpha=3.0, f1=F1_LISTE[0], f2=25e-3, fente=50e-6, pas=1e-3 / 600, defoc=0.0, decal=0.0)
SIGMA = dict(alpha=0.5,          # deg, reglage de l'incidence
             f1=0.6e-3,          # 1 % sur la focale (recalcule a 1 % de f1 dans etude())
             f2=0.25e-3,         # 1 % sur la focale
             fente=3e-6,         # reglage de la largeur de fente
             pas=1.7e-9,         # 0,1 % sur le pas du reseau
             defoc=0.3e-3,       # d4 - f2 : mise au point de la camera
             decal=0.3e-3)       # decalage lateral du spectre sur le capteur
LIBELLE = dict(alpha="incidence alpha (0,5 deg)", f1="focale f1 (1 %)", f2="focale f2 (1 %)",
               fente="largeur de fente a (3 um)", pas="pas du reseau (0,1 %)",
               defoc="defocalisation d4 - f2 (0,3 mm)", decal="decalage lateral du spectre (0,3 mm)")

# Elargissement de la raie avec la defocalisation : largeur a 90 % de l'energie (um) a 550 nm, table ecrite par
# simulation_fourier_M4.py (section 1) pour chaque focale f1 ; la relancer si les parametres changent.
_W = np.genfromtxt(OUT / "w90_defocalisation.csv", delimiter=",", names=True)
DEFOC_MM = _W["delta_mm"]
W90_UM = {40: _W["W90_um_f1_40mm"], 60: _W["W90_um_f1_60mm"]}      # um, selon f1 en mm

# Etalonnage et mesure de la coupure (HYPOTHESES)
LAM_COUPE = 545e-9
LARGEUR_1090 = 4.4e-9                       # transition 10-90 % du filtre seul
SIG_MES = dict(centroide=0.3,               # pixels, position du centre d'une raie laser
               laser=1.0,                   # facteur sur les ecarts-types de la table LASERS (1 = valeurs de la table)
               derive=1.0,                  # pixels, deplacement du spectre entre les images avec et sans filtre
               bruit=0.01)                  # ecart-type du bruit sur la transmission par colonne
SIG_REF = 0.3e-9                            # m, precision de la longueur d'onde du spectrometre de reference (HYPOTHESE :
                                            # aucune valeur dans la doc HR4000, voir le certificat d'etalonnage de l'appareil)


# ---------------- Modele ----------------
def beta(lam, alpha, pas):
    return np.arcsin(ORDRE * np.asarray(lam) / pas - np.sin(alpha))

def x2(lam, p):
    """Position sur le capteur (m), origine a lambda_c, plus le decalage lateral."""
    a = np.deg2rad(p["alpha"])
    return p["f2"] * np.tan(beta(lam, a, p["pas"]) - beta(LAM_C, a, p["pas"])) + p["decal"]

def sorties(p, w90):
    """Sorties du modele pour un jeu de parametres p ; w90 = largeurs a 90 % (um) de la table de defocalisation de la focale f1."""
    a = np.deg2rad(p["alpha"])
    b = float(beta(LAM_C, a, p["pas"]))
    nm_px = PIXEL * p["pas"] * np.cos(b) / (ORDRE * p["f2"])
    d_fente = p["fente"] * p["pas"] * np.cos(a) / (ORDRE * p["f1"])
    d_diff = LAM_C * p["pas"] * np.cos(a) / (ORDRE * LB)
    f_def = np.interp(abs(p["defoc"]) * 1e3, DEFOC_MM, w90) / w90[0]
    d_tot = np.sqrt((d_fente * f_def) ** 2 + d_diff ** 2 + nm_px ** 2)
    marge = W_CAPTEUR / 2 - max(abs(float(x2(LAM_MIN, p))), abs(float(x2(LAM_MAX, p))))
    return dict(marge=marge, nm_px=nm_px, d_tot=d_tot)


# ---------------- 1) Sensibilite et 2) Monte Carlo sur la conception, pour une focale f1 ----------------
def etude(f1_nom, figures):
    """Parties 1 et 2 pour la focale d'entree f1_nom ; figures=True trace M4_07 (sensibilite)."""
    nom = dict(NOM, f1=f1_nom)
    sigma = dict(SIGMA, f1=0.01 * f1_nom)
    w90 = W90_UM[int(round(f1_nom * 1e3))]
    rng_conc = np.random.default_rng(2026)      # meme tirages pour chaque focale
    ref = sorties(nom, w90)
    print(f"\n=============== f1 = {f1_nom*1e3:.0f} mm ===============")
    print(f"Nominal : marge de couverture = {ref['marge']*1e3:.3f} mm de chaque cote, "
          f"resolution totale = {ref['d_tot']*1e9:.3f} nm, echantillonnage = {ref['nm_px']*1e9:.4f} nm/px")
    print("\nSensibilite (effet de +1 sigma / -1 sigma) :")
    print(f"{'parametre':42s} {'marge (mm)':>20s} {'resolution (nm)':>22s}")
    effets = {}
    for k in nom:
        res = []
        for sg in (+1, -1):
            p = dict(nom); p[k] = nom[k] + sg * sigma[k]
            o = sorties(p, w90)
            res.append(((o["marge"] - ref["marge"]) * 1e3, (o["d_tot"] - ref["d_tot"]) * 1e9))
        effets[k] = res
        print(f"{LIBELLE[k]:42s} {res[0][0]:+9.3f} / {res[1][0]:+8.3f} {res[0][1]:+11.4f} / {res[1][1]:+8.4f}")

    if figures:
        ordre = sorted(nom, key=lambda k: max(abs(effets[k][0][1]), abs(effets[k][1][1])))
        fig, axes = plt.subplots(1, 2, figsize=(12, 4.6), sharey=True)
        for ax, idx, titre, unite in ((axes[0], 0, "Marge de couverture du capteur", "mm"),
                                       (axes[1], 1, "Resolution totale a 550 nm", "nm")):
            y = np.arange(len(ordre))
            ax.barh(y - 0.2, [effets[k][0][idx] for k in ordre], height=0.4, label="+1 sigma")
            ax.barh(y + 0.2, [effets[k][1][idx] for k in ordre], height=0.4, label="-1 sigma")
            ax.axvline(0, color="k", lw=0.8)
            ax.set(title=titre, xlabel=f"Variation ({unite})"); ax.grid(alpha=.25)
        axes[0].set_yticks(np.arange(len(ordre))); axes[0].set_yticklabels([LIBELLE[k] for k in ordre], fontsize=8)
        axes[1].legend()
        fig.suptitle(f"Sensibilite aux parametres de conception, f1 = {f1_nom*1e3:.0f} mm (ecarts-types hypothetiques)")
        fig.tight_layout(); fig.savefig(OUT / "M4_07_sensibilite.png", dpi=180)

    marges, d_tots, nm_pxs = [], [], []
    for _ in range(N_DESIGN):
        p = {k: nom[k] + sigma[k] * rng_conc.standard_normal() for k in nom}
        o = sorties(p, w90)
        marges.append(o["marge"]); d_tots.append(o["d_tot"]); nm_pxs.append(o["nm_px"])
    marges, d_tots, nm_pxs = np.array(marges), np.array(d_tots), np.array(nm_pxs)
    print(f"\nMonte Carlo conception ({N_DESIGN} tirages) :")
    print(f"  400-700 nm entierement sur le capteur : {np.mean(marges > 0)*100:.1f} % des tirages")
    print(f"  marge : mediane {np.median(marges)*1e3:.3f} mm, 5e percentile {np.percentile(marges, 5)*1e3:.3f} mm")
    print(f"  resolution totale : mediane {np.median(d_tots)*1e9:.2f} nm, 95e percentile {np.percentile(d_tots, 95)*1e9:.2f} nm")
    print(f"  echantillonnage : {np.median(nm_pxs)*1e9:.4f} nm/px (ecart-type {np.std(nm_pxs)*1e9:.4f})")
    return ref, marges, d_tots

etudes = {f1: etude(f1, figures=(f1 == F1_LISTE[0])) for f1 in F1_LISTE}
ref, marges, d_tots = etudes[F1_LISTE[0]]                  # focale retenue : sert a la partie 3
rng.standard_normal(N_DESIGN * len(NOM))                   # garde le flux aleatoire de la partie 3 identique a l'ancienne version

fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
axes[0].hist(marges * 1e3, bins=60, color="tab:blue")
axes[0].axvline(0, color="k", ls="--", label="limite du capteur")
axes[0].set(xlabel="Marge de couverture (mm, de chaque cote)", ylabel="Tirages",
            title=f"Spectre 400-700 nm sur le capteur : {np.mean(marges > 0)*100:.1f} %")
axes[0].legend()
bins = np.linspace(min(e[2].min() for e in etudes.values()) * 1e9, max(e[2].max() for e in etudes.values()) * 1e9, 70)
for f1, c in zip(F1_LISTE, ("tab:blue", "tab:orange")):
    d = etudes[f1][2] * 1e9
    axes[1].hist(d, bins=bins, color=c, alpha=.55,
                 label=f"f1 = {f1*1e3:.0f} mm : mediane {np.median(d):.2f} nm, 95e percentile {np.percentile(d, 95):.2f} nm")
axes[1].set(xlabel="Resolution totale a 550 nm (nm)", ylabel="Tirages", title="Resolution selon la focale d'entree")
axes[1].set_ylim(top=axes[1].get_ylim()[1] * 1.3)            # place pour la legende
axes[1].legend(fontsize=8, loc="upper right")
fig.tight_layout(); fig.savefig(OUT / "M4_08_monte_carlo_conception.png", dpi=180)


# ---------------- 3) Monte Carlo sur la mesure de la longueur d'onde de coupure ----------------
LAM_GRILLE = np.linspace(380e-9, 720e-9, 6801)
X_GRILLE = x2(LAM_GRILLE, NOM) / PIXEL                    # colonnes (croissant avec lambda)
def X_de_lam(lam): return np.interp(lam, LAM_GRILLE, X_GRILLE)
def lam_de_X(X): return np.interp(X, X_GRILLE, LAM_GRILLE)

def erf_np(x):
    """erf (Abramowitz et Stegun 7.1.26, erreur < 1,5e-7)."""
    s = np.sign(x); x = np.abs(x); t = 1.0 / (1.0 + 0.3275911 * x)
    y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * np.exp(-x * x)
    return s * y

SIG_FLOU = np.sqrt((LARGEUR_1090 / 2.563) ** 2 + (ref["d_tot"] / np.sqrt(12)) ** 2)   # filtre + fente (gaussienne equivalente)


# ---------------- Lasers d'etalonnage : longueurs d'onde mesurees avec le spectrometre de reference ----------------
DOSSIER_LASERS = OUT / "Spectres des lasers-20261108"
# nom : (fichier ou None, longueur d'onde nominale en nm, stabilite du laser en nm)
#  - CPS532 Thorlabs : pas de fichier texte, seulement le spectre typique (gif) : raies principales a 531,95 - 532,15 nm
#    selon la temperature (20 a 30 C), raies secondaires jusqu'a 532,7 nm. On retient 532,1 nm, etendue 0,75 nm, stabilite 0,1 nm.
#  - lasers a pile : stabilite 0,3 nm = HYPOTHESE (aucune donnee sur la derive avec la pile ou la temperature).
LASERS_DEF = {
    "CPS532 Thorlabs": (None, 532.0, 0.1),
    "532 pile":     ("532nm Laser (battery powered).txt", 532.0, 0.3),
    "555 pile":     ("555nm laser (battery powered).txt", 555.0, 0.3),
    "571 pile":     ("571nm laser (battery powered).txt", 571.0, 0.3),
    "593 pile":     ("593nm laser (battery powered).txt", 593.0, 0.3),
    "650 pointeur": ("650nm_laser_pointer_cat.txt", 650.0, 0.3),
    "650 ligne":    ("650nm_line_laser.txt", 650.0, 0.3),
}

def lire_raie(fichier):
    """Position de la raie (nm) selon 4 definitions : pic, milieu a mi-hauteur, centroide au-dessus de la
    mi-hauteur, centroide a +/-15 nm. La longueur d'onde retenue est le centroide au-dessus de la mi-hauteur
    (definition reproductible sur nos images) ; l'ecart entre definitions donne l'incertitude de definition."""
    lignes = (DOSSIER_LASERS / fichier).read_text(errors="ignore").splitlines()
    i0 = [k for k, l in enumerate(lignes) if "Begin Spectral Data" in l][0]
    d = np.array([[float(x) for x in l.split()[:2]] for l in lignes[i0 + 1:] if l.strip()])
    lam, s = d[:, 0], d[:, 1]
    ip = int(np.argmax(np.convolve(s, np.ones(5) / 5, "same"))); lp = lam[ip]
    y = s - np.median(s[abs(lam - lp) > 40])
    ys = np.convolve(y, np.ones(5) / 5, "same"); h = y[ip]
    a = ip
    while ys[a] > h / 2: a -= 1
    b = ip
    while ys[b] > h / 2: b += 1
    m = (lam >= lam[a]) & (lam <= lam[b])
    m15 = (abs(lam - lp) < 15) & (y > 0)
    defs = [lp, (lam[a] + lam[b]) / 2, np.sum(lam[m] * y[m]) / np.sum(y[m]), np.sum(lam[m15] * y[m15]) / np.sum(y[m15])]
    return dict(centroide=defs[2], etendue=max(defs) - min(defs), fwhm=lam[b] - lam[a], pas=float(np.median(np.diff(lam))))

RAIES = {nom: lire_raie(f) for nom, (f, _, _) in LASERS_DEF.items() if f is not None}

def construire(sig_ref):
    """Table des lasers : nominal, mesure (m) et ecart-type de la longueur d'onde reelle (m)."""
    L = {}
    for nom, (f, nominal, stab) in LASERS_DEF.items():
        if f is None:
            mes, s_def, s_pas, fwhm = 532.1, 0.75 / np.sqrt(12), 0.0, np.nan
        else:
            r = RAIES[nom]
            mes, s_def, s_pas, fwhm = r["centroide"], r["etendue"] / np.sqrt(12), r["pas"] / np.sqrt(12), r["fwhm"]
        sigma = np.sqrt((sig_ref * 1e9) ** 2 + s_def ** 2 + s_pas ** 2 + stab ** 2)
        L[nom] = dict(nominal=nominal * 1e-9, mesure=mes * 1e-9, sigma=sigma * 1e-9, s_def=s_def, fwhm=fwhm)
    return L

LASERS = construire(SIG_REF)
print(f"Lasers d'etalonnage (centroide au-dessus de la mi-hauteur, sigma total avec SIG_REF = {SIG_REF*1e9:.1f} nm) :")
print(f"  {'laser':16s} {'nominal':>8s} {'mesure':>8s} {'ecart':>7s} {'FWHM':>6s} {'s_def':>6s} {'sigma':>6s}   (nm)")
for nom, L in LASERS.items():
    print(f"  {nom:16s} {L['nominal']*1e9:8.1f} {L['mesure']*1e9:8.2f} {(L['mesure']-L['nominal'])*1e9:+7.2f} "
          f"{L['fwhm']:6.1f} {L['s_def']:6.2f} {L['sigma']*1e9:6.2f}")


def mc_coupure(calib, vrai, sig_las, sig, deg, n=N_MESURE):
    """Erreur (m) sur la longueur d'onde de coupure retrouvee, pour n tirages.
    calib : longueurs d'onde utilisees pour l'etalonnage ; vrai : valeurs moyennes reelles ; sig_las : leur ecart-type."""
    calib, vrai, sig_las = np.array(calib), np.array(vrai), np.array(sig_las)
    cols = X_de_lam(LAM_COUPE) + np.arange(-300, 301)
    lam_vrai = vrai[None, :] + sig["laser"] * sig_las[None, :] * rng.standard_normal((n, len(calib)))
    Xm = X_de_lam(lam_vrai) + sig["centroide"] * rng.standard_normal((n, len(calib)))
    derive = sig["derive"] * rng.standard_normal((n, 1))
    T = 0.5 * (1 + erf_np((lam_de_X(cols[None, :] - derive) - LAM_COUPE) / (np.sqrt(2) * SIG_FLOU)))
    T = T + sig["bruit"] * rng.standard_normal(T.shape)
    c = np.cumsum(np.pad(T, ((0, 0), (1, 0))), axis=1)
    Ts = (c[:, 9:] - c[:, :-9]) / 9                       # moyenne glissante sur 9 colonnes
    cs = cols[4:-4]
    i = np.argmax(Ts >= 0.5, axis=1); r = np.arange(n)
    x50 = cs[i - 1] + (0.5 - Ts[r, i - 1]) / (Ts[r, i] - Ts[r, i - 1])
    err = np.empty(n)
    for j in range(n):
        err[j] = np.polyval(np.polyfit(Xm[j], calib, deg), x50[j]) - LAM_COUPE
    return err

def resume(err):
    return err.mean() * 1e9, err.std() * 1e9, np.percentile(err, 2.5) * 1e9, np.percentile(err, 97.5) * 1e9

def cas(L, noms, valeurs, sig, deg):
    """valeurs = 'mesure' (etalonnage avec les longueurs d'onde mesurees) ou 'nominal' (avec les etiquettes des lasers)."""
    vrai = [L[k]["mesure"] for k in noms]
    calib = [L[k][valeurs] for k in noms]
    return mc_coupure(calib, vrai, [L[k]["sigma"] for k in noms], sig, deg)

SCHEMAS = {"2 lasers (CPS532, 650 pointeur), lineaire": (("CPS532 Thorlabs", "650 pointeur"), 1),
           "3 lasers (CPS532, 593, 650 pointeur), quadratique": (("CPS532 Thorlabs", "593 pile", "650 pointeur"), 2),
           "5 lasers (CPS532, 555, 571, 593, 650 pointeur), quadratique": (("CPS532 Thorlabs", "555 pile", "571 pile", "593 pile", "650 pointeur"), 2)}
ZERO = {k: 0.0 for k in SIG_MES}
print(f"\nMonte Carlo coupure d'un filtre ideal a {LAM_COUPE*1e9:.0f} nm ({N_MESURE} tirages par cas) :")
resultats = {}
for nom, (noms, deg) in SCHEMAS.items():
    print(f"  {nom}")
    e = cas(LASERS, noms, "mesure", SIG_MES, deg); resultats[nom] = e
    m, s, lo, hi = resume(e)
    print(f"    etalonnage avec les longueurs d'onde MESUREES : biais {m:+.3f} nm, ecart-type {s:.3f} nm, intervalle a 95 % [{lo:+.2f}, {hi:+.2f}] nm")
    for terme in SIG_MES:
        sig = dict(ZERO); sig[terme] = SIG_MES[terme]
        print(f"      {terme:10s} seul : ecart-type {resume(cas(LASERS, noms, 'mesure', sig, deg))[1]:.3f} nm")
    print(f"      non-linearite seule : biais {resume(cas(LASERS, noms, 'mesure', ZERO, deg))[0]:+.3f} nm")
    m, s, lo, hi = resume(cas(LASERS, noms, "nominal", SIG_MES, deg))
    print(f"    etalonnage avec les valeurs NOMINALES des etiquettes : biais {m:+.2f} nm, ecart-type {s:.2f} nm, intervalle a 95 % [{lo:+.1f}, {hi:+.1f}] nm")

noms3, deg3 = SCHEMAS["3 lasers (CPS532, 593, 650 pointeur), quadratique"]
print("\nEffet de SIG_REF (precision du spectrometre de reference), 3 lasers, valeurs mesurees :")
for sr in (0.1e-9, 0.3e-9, 0.5e-9, 1.0e-9):
    Lr = construire(sr)
    _, s, lo, hi = resume(cas(Lr, noms3, "mesure", SIG_MES, deg3))
    print(f"  SIG_REF {sr*1e9:.1f} nm : ecart-type {s:.3f} nm, intervalle a 95 % [{lo:+.2f}, {hi:+.2f}] nm")

print("\nEffet de la derive du spectre entre les deux images (3 lasers, valeurs mesurees, SIG_REF nominal) :")
for d in (0.0, 1.0, 5.0, 20.0):
    sig = dict(SIG_MES); sig["derive"] = d
    _, s, lo, hi = resume(cas(LASERS, noms3, "mesure", sig, deg3))
    print(f"  derive {d:5.1f} px (soit {d*ref['nm_px']*1e9:5.2f} nm) : ecart-type {s:.3f} nm, intervalle a 95 % [{lo:+.2f}, {hi:+.2f}] nm")

fig, ax = plt.subplots(figsize=(9, 4.6))
for nom, e in resultats.items():
    ax.hist(e * 1e9, bins=60, alpha=0.5, label=nom.split(" (")[0] + " mesures")
e_nom = cas(LASERS, noms3, "nominal", SIG_MES, deg3)
ax.hist(e_nom * 1e9, bins=60, alpha=0.5, color="gray", label="3 lasers, valeurs nominales (etiquettes)")
ax.axvline(0, color="k", ls="--")
ax.set(xlabel="Erreur sur la longueur d'onde de coupure (nm)", ylabel="Tirages",
       title=f"Mesure de la coupure d'un filtre a {LAM_COUPE*1e9:.0f} nm : erreur apres etalonnage")
ax.legend(fontsize=8); fig.tight_layout(); fig.savefig(OUT / "M4_09_monte_carlo_coupure.png", dpi=180)

plt.show()
