"""Client HTTP du Raspberry Pi. Aucun module caméra requis sur Windows."""
import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError

class CameraClient:
    def __init__(self, host, port=8765, token=""):
        self.base = f"http://{host}:{int(port)}"
        self.token = token

    def request(self, method, endpoint, data=None, timeout=10):
        body = json.dumps(data).encode('utf-8') if data is not None else None
        req = Request(self.base + endpoint, data=body, method=method,
                      headers={"Content-Type":"application/json", "X-Camera-Token":self.token})
        try:
            with urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except HTTPError as e:
            try: message=json.loads(e.read().decode('utf-8')).get('error',str(e))
            except Exception: message=str(e)
            raise RuntimeError(message) from e

    def status(self): return self.request('GET','/status')
    def start(self,config): return self.request('POST','/start',config)
    def stop(self): return self.request('POST','/stop',{})

    def download(self, name, destination):
        from pathlib import Path
        from urllib.parse import quote
        dest=Path(destination)
        req=Request(self.base+'/download/'+quote(name),headers={'X-Camera-Token':self.token})
        with urlopen(req,timeout=300) as response, dest.open('wb') as out:
            import shutil
            shutil.copyfileobj(response,out,1024*1024)
        return dest
