"""PHS3910 - etude reproductible. Python: numpy matplotlib.
ATTENTION: modeles geometriques et RGB illustratif; efficacite et chromatisme non calibres.
Convention: alpha et beta signes de part et d'autre de la normale; separation physique |beta-alpha|.
"""
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
import csv
OUT=Path(__file__).resolve().parent
GROOVES=600; d=1e6/GROOVES # nm
P=0.00155 # mm/pixel
W=4056*P # mm
LAM=np.linspace(400,700,601)

def beta(lam,alpha,order=1,grooves=GROOVES):
    dd=1e6/grooves
    arg=order*np.asarray(lam)/dd-np.sin(np.deg2rad(alpha))
    return np.arcsin(np.clip(arg,-1,1))
def pos(lam,alpha,f2,order=1,grooves=GROOVES):
    b0=beta(550,alpha,order,grooves)
    return f2*np.tan(beta(lam,alpha,order,grooves)-b0)
def nm_per_px(alpha,f2):
    b=beta(550,alpha); return P*(d*np.cos(b))/(f2) # units: nm/mm * mm

def slit_nm(alpha,f1,a_um): return (a_um*1e-3)*d*np.cos(np.deg2rad(alpha))/f1

def rgb(w):
    # conversion approximative visible; ni CIE ni reponse du Bayer
    w=float(w)
    if w<380 or w>780: return np.zeros(3)
    if w<440: r,g,b=-(w-440)/60,0,1
    elif w<490:r,g,b=0,(w-440)/50,1
    elif w<510:r,g,b=0,1,-(w-510)/20
    elif w<580:r,g,b=(w-510)/70,1,0
    elif w<645:r,g,b=1,-(w-645)/65,0
    else:r,g,b=1,0,0
    atten=0.45+0.55*np.clip((w-380)/40,0,1) if w<420 else (0.45+0.55*np.clip((780-w)/80,0,1) if w>700 else 1)
    return np.clip(np.array([r,g,b])*atten,0,1)**0.8

# 1 - choix d'incidence: diffraction et separation CORRIGEE
fig,ax=plt.subplots(figsize=(9,5))
A=np.linspace(-3,16,400)
B=np.rad2deg(beta(550,A))
ax.plot(A,abs(B-A),label='Séparation physique |β−α| à 550 nm',lw=2)
ax.axvline(np.rad2deg(np.arcsin(500/(2*d))),ls='--',color='gray',label='Littrow à 500 nm')
ax.axhline(10,ls=':',color='black',label='Exemple de dégagement minimal : 10° (hypothèse)')
ax.set(xlabel='Incidence α (degrés)',ylabel='Séparation des axes optiques (degrés)',title='Angle de blaze ≠ séparation mécanique des bras')
ax.grid(alpha=.25);ax.legend(fontsize=9);fig.tight_layout();fig.savefig(OUT/'01_angles_et_separation.png',dpi=180);

# 2 - coverage by alpha/f2
fig,ax=plt.subplots(figsize=(9,5))
for f2 in [20,25,30,40]:
    ax.plot(LAM,pos(LAM,3,f2),label=f'f₂ = {f2} mm')
ax.axhline(W/2,color='black',ls='--');ax.axhline(-W/2,color='black',ls='--',label='Limites capteur')
ax.set(xlabel='Longueur d’onde (nm)',ylabel='Position sur le capteur (mm)',title='Couverture spectrale — incidence α = 3° (scénario de dégagement)')
ax.legend();ax.grid(alpha=.25);fig.tight_layout();fig.savefig(OUT/'02_couverture.png',dpi=180);

# 3 resolution vs slit
fig,ax=plt.subplots(figsize=(9,5))
for f1 in [25,40,60,75]:
    widths=np.linspace(10,150,141)
    ax.plot(widths,slit_nm(3,f1,widths),label=f'f₁ = {f1} mm')
ax.set(xlabel='Largeur de fente supposée (µm)',ylabel='Élargissement spectral géométrique (nm)',title='Compromis fente / focale d’entrée (m = 1)')
ax.legend();ax.grid(alpha=.25);fig.tight_layout();fig.savefig(OUT/'03_fente_et_resolution.png',dpi=180);

# 4 - grating pitch vs width and sampling
fig,ax=plt.subplots(figsize=(9,5))
for grooves in [300,600,900,1200]:
    dd=1e6/grooves
    vals=np.array([pos(LAM,3,25,1,grooves) if np.all(abs(LAM/dd-np.sin(np.deg2rad(3)))<=1) else np.full_like(LAM,np.nan)])[0]
    ax.plot(LAM,vals,label=f'{grooves} traits/mm')
ax.axhline(W/2,color='black',ls='--');ax.axhline(-W/2,color='black',ls='--')
ax.set(xlabel='Longueur d’onde (nm)',ylabel='Position (mm)',title='Influence du pas du réseau (comparaison théorique)')
ax.legend();ax.grid(alpha=.25);fig.tight_layout();fig.savefig(OUT/'04_pas_reseau.png',dpi=180);

# 5 simulated RGB image on sensor, idealized source continuous
fig,axes=plt.subplots(2,1,figsize=(10,4.6),sharex=True)
for ax,f2 in zip(axes,[40,25]):
    img=np.zeros((65,4056,3))
    xgrid=(np.arange(4056)-(4056-1)/2)*P
    wavelengths=np.linspace(400,700,1201)
    for w in wavelengths:
        xc=pos(w,3,f2)
        # hypothesized slit a=50um -> image width a*f2/f1, convolve gaussian
        sigma=max((0.05*f2/40)/2.355,0.015) # mm illustrative blur
        profile=np.exp(-.5*((xgrid-xc)/sigma)**2)
        img+=profile[None,:,None]*rgb(w)[None,None,:]
    img/=max(img.max(),1)
    ax.imshow(img,extent=[xgrid[0],xgrid[-1],0,1],aspect='auto',interpolation='nearest')
    ax.set_yticks([]);ax.set_ylabel(f'f₂={f2} mm')
axes[-1].set_xlabel('Position sur le capteur (mm)')
fig.suptitle('Image RGB illustrative sans filtre (source blanche idéale; non calibrée)')
fig.tight_layout();fig.savefig(OUT/'05_camera_RGB.png',dpi=180);

# comparison and best f2 for centered camera
rows=[]
for alpha in [0,2,3,5,8.6269,10,15]:
    b=np.rad2deg(beta(550,alpha))
    for f2 in [20,25,30,40]:
        low=float(pos(400,alpha,f2));high=float(pos(700,alpha,f2))
        fmax=min((W/2)/abs(float(pos(400,alpha,1))), (W/2)/abs(float(pos(700,alpha,1))))
        rows.append([alpha,b,abs(b-alpha),f2,low,high,abs(low)<=W/2 and abs(high)<=W/2,nm_per_px(alpha,f2),slit_nm(alpha,40,50),fmax])
with open(OUT/'tableau_comparatif.csv','w',newline='',encoding='utf-8-sig') as fh:
    wr=csv.writer(fh);wr.writerow(['alpha_deg','beta_550_deg','separation_physique_deg','f2_mm','x400_mm','x700_mm','couverture_400_700','nm_par_pixel_550','elargissement_fente_50um_nm','f2_max_sans_marge_mm']);wr.writerows(rows)
print('Fichiers créés dans',OUT)
for a in [3,8.6269]:
 b=np.rad2deg(beta(550,a));print(f'alpha={a:.3f}°, beta550={b:.3f}°, séparation={abs(b-a):.3f}°')
 for f2 in [25,40]:
  print(f' f2={f2}: x400={pos(400,a,f2):.3f} mm, x700={pos(700,a,f2):.3f} mm, nm/pixel={nm_per_px(a,f2):.3f}')


# Affiche les CINQ figures dans des fenetres interactives.
# Fermer les fenetres pour terminer le programme.
print("Ouverture des 5 graphiques. Ferme les fenetres pour terminer.")
plt.show(block=True)
