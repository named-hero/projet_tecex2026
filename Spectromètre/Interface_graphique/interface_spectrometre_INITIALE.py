"""Interface visuelle du spectromètre PHS3910 — prototype autonome.
Lancement : python3 interface_spectrometre.py
Dépendance : python3-tk (Tkinter). Les acquisitions/calculs seront branchés plus tard.
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

BG = '#0B0B0E'
PANEL = '#17171C'
PANEL2 = '#202027'
RED = '#E63946'
RED_DARK = '#A91E2C'
TEXT = '#F5F5F7'
MUTED = '#A9A9B2'

root = tk.Tk()
root.title('Spectromètre PHS3910 | Interface')
root.geometry('1120x750')
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

status = tk.StringVar(value='Interface prête — acquisitions et analyses non connectées')

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

# 1. ACQUISITION
acq = ttk.Frame(notebook)
notebook.add(acq, text='01   Acquisition')
acq.grid_columnconfigure(0, weight=3)
acq.grid_columnconfigure(1, weight=2)
acq.grid_rowconfigure(0, weight=1)
cam = panel(acq, 'CAMÉRA EN DIRECT', 'Aperçu du spectre capté par la caméra Raspberry Pi HQ')
cam.grid(row=0, column=0, sticky='nsew', padx=(0, 10), pady=12)
placeholder(cam, 'APERÇU CAMÉRA\nÀ connecter au Raspberry Pi', 340)
controls = tk.Frame(cam, bg=PANEL)
controls.pack(fill='x', pady=(14, 0))
button(controls, '▶ Démarrer', accent=True).pack(side='left', padx=(0, 9))
button(controls, '■ Arrêter').pack(side='left')
right = panel(acq, 'ACQUISITIONS', 'Enregistrer les trois mesures dans les mêmes conditions de caméra.')
right.grid(row=0, column=1, sticky='nsew', pady=12)
for name, desc in [('Acquérir le noir', 'Source lumineuse bloquée'),
                   ('Acquérir la référence', 'Source sans filtre'),
                   ('Acquérir avec filtre', 'Source avec filtre')]:
    row = tk.Frame(right, bg=PANEL)
    row.pack(fill='x', pady=11)
    tk.Label(row, text=desc, bg=PANEL, fg=MUTED, font=('Arial', 10)).pack(anchor='w', pady=(0, 5))
    button(row, name).pack(fill='x')
button(right, 'Importer une image…').pack(fill='x', pady=(20, 0))

# 2. CALIBRATION
cal = ttk.Frame(notebook)
notebook.add(cal, text='02   Calibration')
cal.grid_columnconfigure(0, weight=1)
cal.grid_columnconfigure(1, weight=1)
left = panel(cal, 'RAIES LASER', 'Importer deux images de lasers de longueurs d’onde connues.')
left.grid(row=0, column=0, sticky='nsew', padx=(0, 10), pady=12)
for idx in (1, 2):
    tk.Label(left, text=f'Laser {idx} — longueur d’onde (nm)', bg=PANEL,
             fg=TEXT, font=('Arial', 11)).pack(anchor='w', pady=(18, 5))
    entry = tk.Entry(left, bg=PANEL2, fg=TEXT, insertbackground=TEXT,
                     relief='flat', font=('Arial', 12))
    entry.pack(fill='x', ipady=9)
    button(left, f'Importer image laser {idx}').pack(anchor='w', pady=(9, 4))
button(left, 'Lancer la calibration', accent=True).pack(fill='x', pady=(25, 0))
right = panel(cal, 'RÉSULTAT DE CALIBRATION', 'Correspondance entre les pixels du capteur et les longueurs d’onde.')
right.grid(row=0, column=1, sticky='nsew', pady=12)
placeholder(right, 'Graphique λ(x)\nEn attente des données de calibration', 310)
tk.Label(right, text='État : non calibré', bg=PANEL, fg=RED,
         font=('Arial', 12, 'bold')).pack(anchor='w', pady=15)

# 3. ANALYSE
ana = ttk.Frame(notebook)
notebook.add(ana, text='03   Analyse')
ana.grid_columnconfigure(0, weight=1)
ana.grid_columnconfigure(1, weight=1)
ana.grid_rowconfigure(0, weight=1)
intensity = panel(ana, 'SPECTRE D’INTENSITÉ', 'I(x) avant calibration, I(λ) après calibration')
intensity.grid(row=0, column=0, sticky='nsew', padx=(0, 10), pady=12)
placeholder(intensity, 'Graphique du spectre\nEn attente du traitement', 275)
trans = panel(ana, 'TRANSMISSION DU FILTRE', 'Transmission (%) en fonction de la longueur d’onde (nm)')
trans.grid(row=0, column=1, sticky='nsew', pady=12)
placeholder(trans, 'Graphique de transmission\nEn attente du traitement', 275)
results = panel(ana, 'LONGUEURS D’ONDE DE COUPURE', 'Résultats et incertitudes calculés par le module de traitement')
results.grid(row=1, column=0, columnspan=2, sticky='ew', pady=(0, 12))
row = tk.Frame(results, bg=PANEL)
row.pack(fill='x', pady=(10, 0))
for label in ('Coupure inférieure : — nm', 'Coupure supérieure : — nm', 'Incertitudes : — nm'):
    tk.Label(row, text=label, bg=PANEL, fg=TEXT,
             font=('Arial', 11)).pack(side='left', padx=(0, 35))
buttons = tk.Frame(results, bg=PANEL)
buttons.pack(fill='x', pady=(15, 0))
button(buttons, 'Calculer la transmission', accent=True).pack(side='left', padx=(0, 10))
button(buttons, 'Exporter les résultats').pack(side='left')

footer = tk.Frame(root, bg=BG, padx=22, pady=9)
footer.pack(fill='x')
tk.Label(footer, textvariable=status, bg=BG, fg=MUTED,
         font=('Arial', 10)).pack(anchor='w')
root.mainloop()
