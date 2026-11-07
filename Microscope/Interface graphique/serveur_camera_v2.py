"""Serveur Raspberry Pi (ou --simulation sur Windows). Réseau local de confiance uniquement.
Démarrer: python3 serveur_camera.py --host 0.0.0.0 --token MON_SECRET
Tester Windows: py serveur_camera.py --simulation --host 127.0.0.1 --token test
"""
import argparse
import json
import math
import re
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

BASE=Path(__file__).resolve().parent
FILMS=BASE/'films_acquis'
state={'phase':'pret','error':None,'files':[],'progress':0,'mode':'simulation'}
lock=threading.Lock()
stop_event=threading.Event()

def validate(c):
    dt=1/float(c['fps_requested']);exp=float(c['exposure_ms'])/1000;duration=float(c['duration_s'])
    if not all(math.isfinite(x) for x in (dt,exp,duration)) or not (0<exp<=dt and 0<duration<=120 and 0<dt<=10):
        raise ValueError('Paramètres invalides : exposition <= intervalle, durée <= 120 s.')
    if round(duration/dt)>450:raise ValueError('Maximum 450 images par acquisition (protection mémoire du Raspberry Pi).')
    return dt,exp,duration

def record(config,simulate):
    from types import SimpleNamespace
    import acquisition_interface as acq
    dt,exp,duration=validate(config)
    FILMS.mkdir(exist_ok=True)
    with lock:state.update(phase='acquisition',error=None,files=[],progress=0)
    try:
        if simulate:
            import numpy as np
            from PIL import Image
            n=max(2,round(duration/dt)); frames=[];ts=[]
            for i in range(n):
                if stop_event.is_set():break
                a=np.zeros((120,160),dtype=np.uint8)
                x=40+(i%60);y=60
                a[y-2:y+3,x-2:x+3]=220
                frames.append(Image.fromarray(a));ts.append(i*dt)
                with lock:state['progress']=int(100*(i+1)/n)
                time.sleep(min(dt,0.03))
            if not frames:raise RuntimeError('Acquisition annulée avant la première image')
            number=acq.prochain_numero(FILMS,'simulation')
            name=acq.nom_de_base('simulation',number,dt,exp,0.155)
            tif=FILMS/(name+'.tif');js=FILMS/(name+'.json')
            frames[0].save(tif,save_all=True,append_images=frames[1:])
            js.write_text(json.dumps({'simulation':True,'n_images':len(frames),'dt_demande_s':dt,'exposition_demandee_s':exp,'pixel_um':0.155,'calibration_confirmee':False,'arret_anticipe':stop_event.is_set()},indent=2),encoding='utf-8')
        else:
            # Exécution de l'acquisition sur le Pi uniquement. Le module est importé sans picamera2 sur Windows.
            args=SimpleNamespace(dt=dt,exp=exp,duree=duration,gain=1.0,nom='film',objectif=20,na=0.45,pixel=0.155)
            acq.DOSSIER_FILMS=FILMS
            camera=acq.configurer_camera(args)
            try:
                camera.start();time.sleep(1)
                number=acq.prochain_numero(FILMS,args.nom)
                def progress(value):
                    with lock: state['progress'] = value
                tif=acq.enregistrer_film(camera,args,number,'Interface V8',stop_event=stop_event,progress_callback=progress)
            finally:
                camera.stop();camera.close()
            if tif is None:raise RuntimeError('Acquisition impossible (espace disque insuffisant ou arrêt)')
            js=tif.with_suffix('.json')
        with lock:state.update(phase='termine',files=[tif.name,js.name],progress=100)
    except Exception as exc:
        traceback.print_exc()
        with lock:state.update(phase='erreur',error=str(exc))
    finally:stop_event.clear()

def handler_factory(token,simulation):
    class Handler(BaseHTTPRequestHandler):
        def send_json(self,obj,status=200):
            data=json.dumps(obj,ensure_ascii=False).encode('utf-8')
            self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        def authorized(self):
            if self.headers.get('X-Camera-Token','')!=token:
                self.send_json({'error':'Jeton de connexion incorrect'},403);return False
            return True
        def do_GET(self):
            if not self.authorized():return
            if self.path=='/status':
                with lock:data=state.copy()
                return self.send_json(data)
            if self.path.startswith('/download/'):
                name=unquote(self.path[len('/download/'):])
                if not re.fullmatch(r'[A-Za-z0-9_.-]+\.(?:tif|json)',name) or name.startswith('.'):
                    return self.send_json({'error':'Nom de fichier interdit'},400)
                file=FILMS/name
                with lock:allowed=name in state['files']
                if not allowed or not file.is_file():return self.send_json({'error':'Fichier indisponible'},404)
                self.send_response(200);self.send_header('Content-Type','application/octet-stream');self.send_header('Content-Length',str(file.stat().st_size));self.end_headers()
                try:
                    with file.open('rb') as f:
                        while chunk:=f.read(1024*1024):self.wfile.write(chunk)
                except (BrokenPipeError,ConnectionResetError):pass
                return
            self.send_json({'error':'Route inconnue'},404)
        def do_POST(self):
            if not self.authorized():return
            try:
                length=int(self.headers.get('Content-Length','0'))
                if length>4096:raise ValueError('Requête trop grande')
                data=json.loads(self.rfile.read(length) or b'{}')
                if self.path=='/start':
                    validate(data)
                    with lock:
                        if state['phase']=='acquisition':return self.send_json({'error':'Acquisition déjà en cours'},409)
                        state.update(phase='demarrage',files=[],error=None,progress=0)
                        stop_event.clear()
                    threading.Thread(target=record,args=(data,simulation),daemon=True).start()
                    return self.send_json({'ok':True})
                if self.path=='/stop':
                    with lock:phase=state['phase']
                    if phase in ('acquisition','demarrage'):stop_event.set()
                    return self.send_json({'ok':True,'message':'Arrêt demandé; sauvegarde des images déjà capturées si possible'})
                return self.send_json({'error':'Route inconnue'},404)
            except (ValueError,KeyError,TypeError,ZeroDivisionError) as e:self.send_json({'error':str(e)},400)
    return Handler

def main():
    p=argparse.ArgumentParser();p.add_argument('--simulation',action='store_true');p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,default=8765);p.add_argument('--token',required=True)
    a=p.parse_args()
    if len(a.token)<4: p.error('Choisissez un jeton de 4 caractères minimum')
    state['mode']='simulation' if a.simulation else 'camera_reelle'
    if a.host=='0.0.0.0':print('ATTENTION : protocole HTTP non chiffré. Utiliser uniquement un réseau local de confiance.')
    print(f'Serveur {state["mode"]} sur {a.host}:{a.port}')
    ThreadingHTTPServer((a.host,a.port),handler_factory(a.token,a.simulation)).serve_forever()
if __name__=='__main__':main()
