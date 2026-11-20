"""PHS3910 — modèle scalaire 1D de spectromètre 4f, réseau blazé idéal.
Équations (6)-(9) du mandat : FFT de la fente, masque du réseau, FFT vers caméra.
Dépendances : numpy, matplotlib. Les valeurs sont des HYPOTHÈSES, pas une optimisation.
"""
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parent
# Paramètres modifiables (SI)
N = 32768
L0 = 0.100             # fenêtre numérique dans le plan de la fente (m)
f1, f2 = 40e-3, 25e-3 # focales (m)
a = 50e-6             # largeur de la fente (m)
traits_mm = 600
period = 1e-3 / traits_mm
lambda_blaze = 500e-9
largeur_reseau = 2e-3  # largeur utile supposée (m)
lambda_c = 550e-9
lambdas = [450e-9, 550e-9, 650e-9]

x0 = (np.arange(N) - N // 2) * (L0 / N)
dx0 = L0 / N
U0 = (np.abs(x0) <= a / 2).astype(float)

def ft(u, dx):
    """FFT centrée, approx. intégrale de Fourier avec espacement dx."""
    return np.fft.fftshift(np.fft.fft(np.fft.ifftshift(u))) * dx

def simuler(lam):
    # Équation (6) : champ dans le plan de Fourier de L1.
    freq0 = np.fft.fftshift(np.fft.fftfreq(N, d=dx0))
    x1 = lam * f1 * freq0
    dx1 = x1[1] - x1[0]
    U1_moins = ft(U0, dx0)

    # Équation (5) : réseau blazé idéal, facette = rampe de phase.
    # Phase de blaze proportionnelle à 1/lambda (hypothèse simplifiée).
    phase = 2 * np.pi * (lambda_blaze / lam) * np.mod(x1 / period, 1.0)
    M = np.exp(1j * phase) * (np.abs(x1) <= largeur_reseau / 2)
    U1_plus = U1_moins * M                         # Équation (7)

    # Équation (8) : seconde FFT vers le plan focal de L2.
    # Axe local de la caméra centré sur l'ordre +1 à lambda_c.
    # Retrait d'une pente de phase = changement d'axe angulaire (paraxial).
    freq_c = 1.0 / period * (lambda_c / lam)
    U1_local = U1_plus * np.exp(-2j * np.pi * freq_c * x1)
    U2 = ft(U1_local, dx1)
    freq1 = np.fft.fftshift(np.fft.fftfreq(N, d=dx1))
    x2 = lam * f2 * freq1
    I2 = np.abs(U2) ** 2
    I2 /= I2.max() if I2.max() > 0 else 1
    return x1, U1_moins, U1_plus, x2, I2

# Figure 1 : champ à l'entrée
fig, ax = plt.subplots(figsize=(8, 3.6))
sel = np.abs(x0) < 0.20e-3
ax.plot(x0[sel] * 1e6, U0[sel], lw=2)
ax.set(xlabel='Position dans la fente x₀ (µm)', ylabel='Amplitude normalisée',
       title=f'1 — Fente d’entrée : largeur a = {a*1e6:.0f} µm')
ax.grid(alpha=.25)
fig.tight_layout(); fig.savefig(OUT/'4f_01_fente.png', dpi=180)

# Figure 2 : champ dans le plan du réseau à 550 nm
x1, avant, apres, _, _ = simuler(lambda_c)
fig, ax = plt.subplots(figsize=(9, 4))
sel = np.abs(x1) <= 1.1e-3
ax.plot(x1[sel] * 1e3, np.abs(avant[sel])**2 / np.max(np.abs(avant)**2),
        label='Avant réseau : |U₁⁻|²', lw=1.8)
ax.plot(x1[sel] * 1e3, np.abs(apres[sel])**2 / np.max(np.abs(avant)**2),
        '--', label='Après réseau : |U₁⁺|²', lw=1.2)
ax.set(xlabel='Position dans le plan du réseau x₁ (mm)',
       ylabel='Intensité relative', title='2 — Plan de Fourier de L₁, λ = 550 nm')
ax.legend(); ax.grid(alpha=.25)
fig.tight_layout(); fig.savefig(OUT/'4f_02_plan_reseau.png', dpi=180)

# Figure 3 : raies à la caméra pour trois longueurs d'onde
fig, ax = plt.subplots(figsize=(9, 4.6))
for lam in lambdas:
    _, _, _, x2, intensity = simuler(lam)
    sel = np.abs(x2) < 4e-3
    ax.plot(x2[sel]*1e3, intensity[sel], label=f'{lam*1e9:.0f} nm', lw=1.6)
    near = np.abs(x2) < 3e-3
    idx = np.where(near)[0][np.argmax(intensity[near])]
    print(f'λ = {lam*1e9:.0f} nm : pic dominant vers x₂ = {x2[idx]*1e3:.3f} mm')
ax.axvline(-3.1435, ls=':', color='gray', alpha=.6)
ax.axvline(3.1435, ls=':', color='gray', alpha=.6)
ax.set(xlabel='Position x₂ sur la caméra (mm), axe centré à 550 nm',
       ylabel='Intensité normalisée (chaque λ)',
       title='3 — Sortie du système 4f : raies monochromatiques')
ax.legend(); ax.grid(alpha=.25)
fig.tight_layout(); fig.savefig(OUT/'4f_03_raies_camera.png', dpi=180)

print('\nHypothèses : réseau de phase idéal, 1D, propagation paraxiale, illumination uniforme,')
print('fente rectangulaire, ouverture finie du réseau, sans chromatisme ni réponse du capteur.')
print('IMPORTANT : modèle illustratif, pas une prédiction calibrée du montage réel.')
print('Figures enregistrées dans :', OUT)
plt.show()
