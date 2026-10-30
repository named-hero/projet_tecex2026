from pathlib import Path
import tkinter as tk
from tkinter import filedialog
import tifffile
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

DOSSIER_FILMS = Path(__file__).resolve().parent / "films"

root = tk.Tk()
root.withdraw()
try:
    file = filedialog.askopenfilename(
        title="Sélectionner un film TIFF",
        initialdir=DOSSIER_FILMS,
        filetypes=[("Fichiers TIFF", "*.tif")],
    )
finally:
    root.destroy()

if not file:
    raise SystemExit("Aucun fichier sélectionné.")

with tifffile.TiffFile(file) as tif:
    frames = tif.asarray()

print("Number of frames:", len(frames))

fig, ax = plt.subplots()
img = ax.imshow(frames[0], cmap="gray")
ax.axis("off")

def update(i):
    img.set_data(frames[i])
    return [img]

ani = FuncAnimation(
    fig,
    update,
    frames=len(frames),
    interval=100,  # 100 ms = 10 FPS
    blit=True
)

plt.show()