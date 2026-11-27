"""Interface visuelle du spectromètre PHS3910 — prototype autonome.
Lancement : python3 interface_spectrometre_v5.py
Dépendances : Tkinter et Pillow (aperçus des images). Capture locale JPEG + DNG via libcamera/rpicam. Calibration et traitement à intégrer.
"""
import tkinter as tk
import json
from pathlib import Path
import shutil
import subprocess
import time
from tkinter import ttk, messagebox, filedialog

BG = '#0B0B0E'
PANEL = '#17171C'
PANEL2 = '#202027'
RED = '#E63946'
RED_DARK = '#A91E2C'
TEXT = '#F5F5F7'
MUTED = '#A9A9B2'


# Conversion visuelle fournie sur Moodle (adaptée du code de Dan Bruton).
# Ne sert ni à la calibration ni à la mesure d'intensité.
def wavelength_to_rgb(wavelength, gamma=0.8):
    w = float(wavelength)
    if 380 <= w <= 440:
        a = 0.3 + 0.7*(w-380)/60
        r,g,b = (440-w)/60*a,0,a
    elif 440 < w <= 490: r,g,b = 0,(w-440)/50,1
    elif 490 < w <= 510: r,g,b = 0,1,(510-w)/20
    elif 510 < w <= 580: r,g,b = (w-510)/70,1,0
    elif 580 < w <= 645: r,g,b = 1,(645-w)/65,0
    elif 645 < w <= 750: r,g,b = 0.3+0.7*(750-w)/105,0,0
    else: r,g,b = 0,0,0
    return tuple(int(255*c**gamma) for c in (r,g,b))

def spectral_color(w):
    return '#%02x%02x%02x' % wavelength_to_rgb(w)

def spectral_band(parent):
    tk.Label(parent,text='Repère visuel des longueurs d’onde (nm)',bg=PANEL,fg=MUTED).pack(anchor='w',pady=(8,0))
    c=tk.Canvas(parent,height=43,bg=PANEL,highlightthickness=0)
    c.pack(fill='x')
    def draw(event=None):
        c.delete('all'); width=c.winfo_width()-36
        if width<10: return
        for i in range(width):
            x=18+i
            c.create_line(x,3,x,21,fill=spectral_color(400+300*i/max(1,width-1)))
        for nm in range(400,701,50):
            x=18+width*(nm-400)/300
            c.create_text(x,33,text=str(nm),fill=TEXT,font=('Arial',8))
    c.bind('<Configure>',draw)
    return c

root = tk.Tk()
root.title('Spectromètre PHS3910 | Interface')
root.geometry('1200x850')
root.minsize(880, 620)
root.configure(bg=BG)

style = ttk.Style(root)
style.theme_use('clam')
style.configure('TNotebook', background=BG, borderwidth=0)
style.configure('TNotebook.Tab', background=PANEL2, foreground=MUTED,
                font=('Arial', 12, 'bold'), padding=(26, 13), borderwidth=0)
style.map('TNotebook.Tab', background=[('selected', RED_DARK)],
          foreground=[('selected', TEXT)])
style.configure('TFrame', background=BG)

header = tk.Frame(root, bg=BG, padx=26, pady=20)
header.pack(fill='x')
tk.Label(header, text='◉  SPECTROMÈTRE', bg=BG, fg=TEXT,
         font=('Arial', 23, 'bold')).pack(side='left')
tk.Label(header, text='PHS3910  •  Prototype de laboratoire', bg=BG,
         fg=MUTED, font=('Arial', 11)).pack(side='right')
tk.Frame(root, bg=RED, height=3).pack(fill='x')

notebook = ttk.Notebook(root)
notebook.pack(fill='both', expand=True, padx=18, pady=16)

status = tk.StringVar(value='Interface prête — calculs scientifiques à intégrer')

def panel(parent, title, subtitle=None):
    frame = tk.Frame(parent, bg=PANEL, padx=19, pady=17,
                     highlightbackground='#303039', highlightthickness=1)
    tk.Label(frame, text=title, bg=PANEL, fg=TEXT,
             font=('Arial', 15, 'bold')).pack(anchor='w')
    if subtitle:
        tk.Label(frame, text=subtitle, bg=PANEL, fg=MUTED,
                 font=('Arial', 10), wraplength=650, justify='left').pack(anchor='w', pady=(5, 13))
    return frame

def button(parent, label, command=None, accent=False):
    return tk.Button(parent, text=label, command=command or (lambda: pending(label)),
                     bg=RED if accent else PANEL2, fg=TEXT,
                     activebackground=RED_DARK, activeforeground=TEXT,
                     relief='flat', bd=0, padx=14, pady=10,
                     cursor='hand2', font=('Arial', 10, 'bold'))

def pending(action):
    status.set(f'« {action} » : fonction à connecter au module correspondant')
    messagebox.showinfo('Prototype visuel',
                        f'Le bouton « {action} » est prêt visuellement.\n'
                        'La fonction caméra/calibration/traitement sera ajoutée lors de l’intégration.')

def placeholder(parent, text, height=220):
    canvas = tk.Canvas(parent, bg='#101015', height=height, highlightthickness=1,
                       highlightbackground='#35353D')
    canvas.pack(fill='both', expand=True, pady=(10, 0))
    canvas.create_text(350, height//2, text=text, fill=MUTED,
                       font=('Arial', 12), width=600, justify='center')
    return canvas

# 1. ACQUISITION — paramètres et fichiers partagés
acq = ttk.Frame(notebook)
notebook.add(acq, text='01   Acquisition')
acq.columnconfigure(0, weight=2); acq.columnconfigure(1, weight=1)
acq.rowconfigure(0, weight=1)
cam = panel(acq, 'CAMÉRA', 'Aperçu natif sur le Pi ; dernière image dans cette fenêtre.')
cam.grid(row=0,column=0,sticky='nsew',padx=5,pady=5)
view = tk.Label(cam,bg='#101015',fg=MUTED,text='Aucune image',height=8)
view.pack(fill='both',expand=True)
settings = panel(acq,'PARAMÈTRES CAMÉRA')
settings.grid(row=0,column=1,sticky='nsew',padx=5,pady=5)
params = {}
entries = []
for key,label,default in [('exposure_us','Exposition (µs)','10000'),('gain','Gain analogique','1'),('awb_r','Balance rouge','1'),('awb_b','Balance bleue','1'),('frames','Nombre d’images','1')]:
    r=tk.Frame(settings,bg=PANEL); r.pack(fill='x',pady=3)
    tk.Label(r,text=label,bg=PANEL,fg=TEXT).pack(side='left')
    v=tk.StringVar(value=default); params[key]=v
    e=tk.Entry(r,textvariable=v,width=9); e.pack(side='right'); entries.append(e)
locked=None
records={}
preview_process=None
session=Path.home()/'spectrometre_mesures'/time.strftime('%Y%m%d_%H%M%S')
def read_settings():
    d={k:float(v.get()) for k,v in params.items()}
    for k in ('exposure_us','frames'):
        if not d[k].is_integer(): raise ValueError('Exposition et nombre d’images : entiers requis')
        d[k]=int(d[k])
    if not (0<d['exposure_us'] and 1<=d['frames']<=20 and d['gain']>=1 and d['awb_r']>0 and d['awb_b']>0): raise ValueError('Paramètres invalides (1 à 20 images, gain ≥ 1).')
    return d
def lock_settings():
    global locked
    try: locked=read_settings()
    except Exception as e: messagebox.showerror('Réglages',str(e)); return
    for e in entries: e.configure(state='disabled')
    status.set('Réglages verrouillés pour les trois mesures')
def unlock_settings():
    global locked
    locked=None
    for e in entries: e.configure(state='normal')
    status.set('Réglages libres ; refaire les trois mesures si modifiés')
def command(kind):
    for prefix in ('libcamera','rpicam'):
        exe=shutil.which(prefix+'-'+kind)
        if exe: return exe
    raise RuntimeError('Commande caméra absente : utiliser le Raspberry Pi ou importer une image.')
def camera_args(d):
    return ['--shutter',str(d['exposure_us']),'--gain',str(d['gain']),'--awbgains',f"{d['awb_r']},{d['awb_b']}"]
def stop_preview():
    global preview_process
    if preview_process and preview_process.poll() is None:
        preview_process.terminate()
        try: preview_process.wait(timeout=3)
        except subprocess.TimeoutExpired: preview_process.kill(); preview_process.wait()
    preview_process=None

def start_preview():
    global preview_process
    try:
        stop_preview(); preview_process=subprocess.Popen([command('hello'),'-t','0']+camera_args(locked or read_settings()))
        status.set('Aperçu natif caméra ouvert (fenêtre séparée)')
    except Exception as e: messagebox.showerror('Caméra',str(e))
def show_image(widget,path,size=(480,180)):
    from PIL import Image, ImageTk
    with Image.open(path) as im:
        im=im.convert('RGB'); im.thumbnail(size); photo=ImageTk.PhotoImage(im)
    widget.configure(image=photo,text='',height=0); widget.image=photo

def capture_files(name,d):
    stop_preview(); session.mkdir(parents=True,exist_ok=True)
    folder=session/(name+'_'+str(time.time_ns())); folder.mkdir()
    files=[]
    for i in range(d['frames']):
        path=folder/f'{i+1:02d}.jpg'
        subprocess.run([command('still'),'--nopreview','--raw','-t','1000','-o',str(path)]+camera_args(d),check=True,timeout=max(30,d['exposure_us']/1e6+20))
        raw=path.with_suffix('.dng')
        if not raw.exists(): raise RuntimeError('DNG non trouvé : vérifier la version de libcamera.')
        files.append({'preview':str(path),'raw':str(raw)})
    return files
button(settings,'Verrouiller',lock_settings,True).pack(fill='x',pady=4)
button(settings,'Déverrouiller',unlock_settings).pack(fill='x',pady=4)
tk.Label(settings,text='Gain ≈ sensibilité ISO ; balance fixe.\nJPEG : aperçu uniquement ; DNG : traitement.',bg=PANEL,fg=MUTED,justify='left').pack(anchor='w')
controls=tk.Frame(cam,bg=PANEL); controls.pack(fill='x')
button(controls,'Démarrer',start_preview,True).pack(side='left'); button(controls,'Arrêter',stop_preview).pack(side='left',padx=5)
cards=tk.Frame(acq,bg=BG); cards.grid(row=1,column=0,columnspan=2,sticky='ew')
acq_states={}
def acquire(name,widget,state,importing=False):
    try:
        if importing:
            path=filedialog.askopenfilename(filetypes=[('Images','*.jpg *.jpeg *.png *.tif *.tiff')]);
            if not path: return
            files=[{'preview':path,'raw':None}]; d=None
        else:
            if locked is None: raise ValueError('Verrouiller les réglages avant les acquisitions.')
            d=dict(locked); files=capture_files(name,d)
        show_image(widget,files[0]['preview'],(220,90)); show_image(view,files[0]['preview'])
        records[name]={'files':files,'settings':d}; session.mkdir(parents=True,exist_ok=True)
        (session/'acquisitions.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
        state.set('Importé — paramètres inconnus' if importing else f"Acquis : {len(files)} DNG")
        status.set(f'{name} : image disponible ; vérifier saturation et signal')
    except Exception as e: messagebox.showerror('Acquisition',str(e))
for name,desc in [('noir','Lumière bloquée'),('reference','Sans filtre'),('filtre','Avec filtre')]:
    c=panel(cards,name.upper(),desc); c.pack(side='left',fill='both',expand=True,padx=4)
    v=tk.Label(c,text='Aucune image',bg='#101015',fg=MUTED,height=3); v.pack(fill='x')
    st=tk.StringVar(value='Non acquis'); acq_states[name]=st
    tk.Label(c,textvariable=st,bg=PANEL,fg=TEXT).pack()
    r=tk.Frame(c,bg=PANEL); r.pack()
    button(r,'Acquérir',lambda n=name,w=v,t=st:acquire(n,w,t),True).pack(side='left')
    button(r,'Importer',lambda n=name,w=v,t=st:acquire(n,w,t,True)).pack(side='left')

# 2. CALIBRATION
cal = ttk.Frame(notebook)
notebook.add(cal, text='02   Calibration')
cal.grid_columnconfigure(0, weight=1)
cal.grid_columnconfigure(1, weight=2)
cal.grid_rowconfigure(0, weight=1)
left = panel(cal, 'RAIES LASER', 'Importer les trois images et renseigner les longueurs d’onde connues.')
left.grid(row=0, column=0, sticky='nsew', padx=(0, 10), pady=12)
right = panel(cal, 'CALIBRATION', 'Images originales et correspondance pixels → nm')
right.grid(row=0, column=1, sticky='nsew', pady=12)
previews = tk.Frame(right, bg=PANEL)
previews.pack(fill='x', pady=(0, 8))
plot = tk.Canvas(right, bg='#101015', height=230, highlightthickness=0)
plot.pack(fill='both', expand=True)
cal_state = tk.StringVar(value='État : non calibré')
equation = tk.StringVar(value='Équation : —   |   Incertitude : — nm')
tk.Label(right, textvariable=equation, bg=PANEL, fg=TEXT, wraplength=500).pack(anchor='w', pady=5)
tk.Label(right, textvariable=cal_state, bg=PANEL, fg=RED).pack(anchor='w')
lasers = []
points = []

def draw_calibration(event=None):
    plot.delete('all')
    w, h = plot.winfo_width(), plot.winfo_height()
    if w < 100 or h < 100: return
    x0, x1, y0, y1 = 60, w-20, h-45, 20
    plot.create_line(x0,y1,x0,y0,x1,y0,fill=MUTED,width=2)
    plot.create_text(12, (y0+y1)/2, text='λ (nm)', fill=TEXT, angle=90)
    plot.create_text((x0+x1)/2,h-12,text='Position x (pixels)',fill=TEXT)
    if not points:
        plot.create_text((x0+x1)/2,(y0+y1)/2,text='En attente des données de calibration',fill=MUTED,width=max(80,w-100))
        return
    xs, ys = zip(*points)
    lo, hi = min(xs), max(xs)
    low, high = min(ys), max(ys)
    def xy(x,y): return x0+(x-lo)/(hi-lo)*(x1-x0), y0-(y-low)/(high-low)*(y0-y1)
    for i in range(5):
        x=lo+(hi-lo)*i/4; y=low+(high-low)*i/4
        px,py=xy(x,y)
        plot.create_line(x0,py,x1,py,fill='#303039')
        plot.create_text(x0-7,py,text=f'{y:.0f}',anchor='e',fill=MUTED)
        plot.create_text(px,y0+12,text=f'{x:.0f}',fill=MUTED)
    for x,y in points:
        px,py=xy(x,y)
        plot.create_oval(px-4,py-4,px+4,py+4,fill=RED,outline=TEXT)
    # La courbe définitive sera fournie par calibration.py.
plot.bind('<Configure>', draw_calibration)

laser_scroll=tk.Frame(left,bg=PANEL); laser_scroll.pack(fill='both',expand=True)
laser_canvas=tk.Canvas(laser_scroll,bg=PANEL,highlightthickness=0,width=315,height=260)
laser_bar=ttk.Scrollbar(laser_scroll,orient='vertical',command=laser_canvas.yview)
laser_bar.pack(side='right',fill='y'); laser_canvas.pack(side='left',fill='both',expand=True)
laser_canvas.configure(yscrollcommand=laser_bar.set)
laser_list=tk.Frame(laser_canvas,bg=PANEL)
laser_window=laser_canvas.create_window((0,0),window=laser_list,anchor='nw')
laser_list.bind('<Configure>',lambda e:laser_canvas.configure(scrollregion=laser_canvas.bbox('all')))
laser_canvas.bind('<Configure>',lambda e:laser_canvas.itemconfigure(laser_window,width=e.width))

def add_laser():
    if len(lasers)>=4:
        messagebox.showinfo('Calibration','Cette maquette accepte quatre lasers au maximum.'); return
    idx=len(lasers)+1
    row=tk.Frame(laser_list,bg=PANEL)
    row.pack(fill='x',pady=3)
    top=tk.Frame(row,bg=PANEL); top.pack(fill='x')
    tk.Label(top,text=f'Laser {idx} (nm)',bg=PANEL,fg=TEXT).pack(side='left')
    wave=tk.StringVar()
    entry=tk.Entry(top,textvariable=wave,bg=PANEL2,fg=TEXT,insertbackground=TEXT,width=10,relief='flat'); entry.pack(side='right',ipady=4)
    swatch=tk.Label(top,bg=PANEL2,width=3); swatch.pack(side='right',padx=5)
    def update_color(*args):
        try: swatch.configure(bg=spectral_color(float(wave.get().replace(',','.'))))
        except ValueError: swatch.configure(bg=PANEL2)
    wave.trace_add('write',update_color)
    meta=tk.Frame(row,bg=PANEL); meta.pack(fill='x',pady=2)
    tk.Label(meta,text='Source / modèle',bg=PANEL,fg=MUTED).pack(side='left')
    model=tk.Entry(meta,width=19); model.pack(side='right')
    uncrow=tk.Frame(row,bg=PANEL); uncrow.pack(fill='x',pady=2)
    tk.Label(uncrow,text='Incertitude u(λ) (nm)',bg=PANEL,fg=MUTED).pack(side='left')
    uncertainty=tk.Entry(uncrow,width=10); uncertainty.pack(side='right')
    card=tk.Frame(previews,bg=PANEL2); card.pack(side='left',fill='both',expand=True,padx=3)
    preview=tk.Label(card,text=f'Laser {idx}\nAucune image',bg='#101015',fg=MUTED,height=5); preview.pack(fill='both',expand=True)
    pos=tk.StringVar(value='Position : — px')
    tk.Label(card,textvariable=pos,bg=PANEL2,fg=TEXT).pack()
    record={'entry':entry,'path':None,'preview':preview,'position':pos,'model':model,'uncertainty':uncertainty,'wavelength_var':wave}
    lasers.append(record)
    def load():
        path=filedialog.askopenfilename(filetypes=[('Images','*.jpg *.jpeg *.png *.tif *.tiff *.bmp'),('Tous les fichiers','*')])
        if not path: return
        try:
            from PIL import Image, ImageTk
            with Image.open(path) as im:
                im=im.convert('RGB'); im.thumbnail((125,80)); photo=ImageTk.PhotoImage(im)
            preview.configure(image=photo,text='',height=0); preview.image=photo
            record['path']=path
            record['raw']=None
            record['settings']=None
            pos.set('Position : — px')
            cal_state.set('État : images importées, calibration à effectuer')
            status.set(f'Image laser {idx} importée')
        except Exception as exc:
            messagebox.showerror('Importation',f'Impossible de lire l’image : {exc}\nInstaller Pillow si nécessaire.')
    actions=tk.Frame(row,bg=PANEL); actions.pack(fill='x',pady=3)
    button(actions,'Importer',load).pack(side='left',padx=(0,5))
    def capture_laser():
        try:
            d=read_settings(); d['frames']=1
            files=capture_files(f'laser{idx}',d)
            show_image(preview,files[0]['preview'],(125,80))
            record['path']=files[0]['preview']; record['raw']=files[0]['raw']; record['settings']=d
            cal_state.set('État : calibration à effectuer')
        except Exception as e: messagebox.showerror('Laser',str(e))
    button(actions,'Capturer',capture_laser).pack(side='left')

def export_laser_inputs():
    try:
        data=[]
        for i,r in enumerate(lasers,1):
            nm=float(r['entry'].get().replace(',','.'))
            u=r['uncertainty'].get().strip().replace(',','.')
            u=float(u) if u else None
            if not 380 <= nm <= 750 or (u is not None and not 0 <= u < float('inf')):
                raise ValueError(f'Laser {i} : longueur d’onde ou incertitude invalide.')
            if not r['path']: raise ValueError(f'Laser {i} : image manquante.')
            data.append(dict(wavelength_nm=nm,uncertainty_nm=u,model=r['model'].get(),preview=r['path'],raw=r.get('raw'),settings=r.get('settings')))
        path=filedialog.asksaveasfilename(defaultextension='.json',initialfile='lasers_reference.json',filetypes=[('JSON','*.json')])
        if path:
            Path(path).write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
            status.set('Données des lasers exportées pour le module de calibration')
    except Exception as e: messagebox.showerror('Données laser',str(e))

for _ in range(3): add_laser()
button(left,'+ Ajouter un laser',add_laser).pack(fill='x',pady=5)
button(left,'Exporter les données laser',export_laser_inputs).pack(fill='x',pady=3)
button(left,'Lancer la calibration',accent=True).pack(fill='x',pady=5)
button(left,'Sauvegarder la calibration').pack(fill='x',pady=3)
button(left,'Charger une calibration').pack(fill='x',pady=3)
tk.Label(right,text='Plage calibrée : — nm | Résidus : — | Modèle : à définir',bg=PANEL,fg=MUTED).pack(anchor='w')

# 3. ANALYSE
ana = ttk.Frame(notebook)
notebook.add(ana, text='03   Analyse')
ana.grid_columnconfigure(0, weight=1)
ana.grid_columnconfigure(1, weight=1)
ana.grid_rowconfigure(0, weight=1)
intensity = panel(ana, 'SPECTRE D’INTENSITÉ', 'I(x) avant calibration, I(λ) après calibration')
intensity.grid(row=0, column=0, sticky='nsew', padx=(0, 10), pady=12)
placeholder(intensity, 'Graphique du spectre\nEn attente du traitement', 275)
spectral_band(intensity)
trans = panel(ana, 'TRANSMISSION DU FILTRE', 'Transmission (%) en fonction de la longueur d’onde (nm)')
trans.grid(row=0, column=1, sticky='nsew', pady=12)
placeholder(trans, 'Graphique de transmission\nEn attente du traitement', 275)
spectral_band(trans)
results = panel(ana, 'LONGUEURS D’ONDE DE COUPURE', 'Résultats et incertitudes calculés par le module de traitement')
results.grid(row=1, column=0, columnspan=2, sticky='ew', pady=(0, 12))
row = tk.Frame(results, bg=PANEL)
row.pack(fill='x', pady=(10, 0))
for label in ('Coupure inférieure : — ± — nm', 'Coupure supérieure : — ± — nm', 'Largeur : — nm'):
    tk.Label(row, text=label, bg=PANEL, fg=TEXT,
             font=('Arial', 11)).pack(side='left', padx=(0, 35))
options=tk.Frame(results,bg=PANEL); options.pack(fill='x',pady=5)
analysis_params={}
for key,label,default in [('type','Type','Inconnu'),('threshold','Seuil (% max.)','50'),('roi_y0','ROI y début','0'),('roi_y1','ROI y fin','')]:
    tk.Label(options,text=label,bg=PANEL,fg=TEXT).pack(side='left',padx=4)
    v=tk.StringVar(value=default); analysis_params[key]=v
    if key=='type': ttk.Combobox(options,textvariable=v,values=['Inconnu','Passe-bande','Passe-long','Passe-court'],state='readonly',width=12).pack(side='left')
    else: tk.Entry(options,textvariable=v,width=7).pack(side='left')
summary=tk.StringVar(value='Paramètres utilisés : en attente de l’analyse')
tk.Label(results,textvariable=summary,bg=PANEL,fg=MUTED,wraplength=950,justify='left').pack(anchor='w')
def refresh_analysis(event=None):
    summary.set('Acquisitions : '+ ' | '.join(n+': '+acq_states[n].get() for n in acq_states)+'\n'+cal_state.get()+' | Réglages enregistrés : '+str({n:r['settings'] for n,r in records.items()})+'\nTraitement : non exécuté ; paramètres proposés ci-dessus.')
notebook.bind('<<NotebookTabChanged>>',refresh_analysis)
buttons = tk.Frame(results, bg=PANEL)
buttons.pack(fill='x', pady=(15, 0))
button(buttons, 'Calculer la transmission', accent=True).pack(side='left', padx=(0, 10))
button(buttons, 'Exporter les résultats').pack(side='left')

footer = tk.Frame(root, bg=BG, padx=22, pady=9)
footer.pack(fill='x')
tk.Label(footer, textvariable=status, bg=BG, fg=MUTED,
         font=('Arial', 10)).pack(anchor='w')
root.protocol('WM_DELETE_WINDOW',lambda:(stop_preview(),root.destroy()))
root.mainloop()
