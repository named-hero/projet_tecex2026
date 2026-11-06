"""Contrat à transmettre aux collègues. Ne pas renommer en analyse_equipe.py
avant d'avoir remplacé cette fonction par le véritable algorithme."""

def analyser_video(video_path: str, pixel_um: float, dt_s: float, config: dict) -> dict:
    """Exécuter localisation, suivi, MSD et Stokes-Einstein.

    Entrées:
      video_path: chemin vers vidéo TIFF ou vidéo classique
      pixel_um: échelle vérifiée en µm/pixel
      dt_s: intervalle entre deux images en secondes
      config: informations supplémentaires (ex. objectif)

    Sortie attendue :
    {
      "trajectories": {
         "particule_1": [(0, 123.2, 44.1), (1, 123.7, 44.8)]
      },
      "results": {
         "particles": nombre_entier,
         "D_um2_s": diffusion_en_um2_par_s,
         "radius_nm": rayon_en_nm,
         "uncertainty_nm": incertitude_en_nm,
         "lag_s": [temps_en_secondes, ...],
         "msd_um2": [msd_en_um2, ...],
         "fit_msd_um2": [ajustement_en_um2, ...]  # facultatif
      }
    }
    """
    raise NotImplementedError("Intégrer ici les algorithmes validés de l'équipe.")
