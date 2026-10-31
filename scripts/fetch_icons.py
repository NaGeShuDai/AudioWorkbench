"""Vendor Lucide SVGs and upstream license. Network is only used during development."""
import concurrent.futures
import json
import sys
import urllib.request
from pathlib import Path
import truststore
truststore.inject_into_ssl()

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from audioworkbench.catalog import TOOLS
target=ROOT/'assets'/'icons'; target.mkdir(parents=True,exist_ok=True)
extra=['grid-2x2','folder-open','plus','x','play','pause','download','settings-2','search','chevron-right','undo-2','redo-2','trash-2','check','arrow-up','arrow-down','arrow-right','circle-help','layers','loader-circle','check-check','circle','circle-check','file-plus-2','package','folder','rotate-ccw','menu','square']
names=sorted(set([t.icon for t in TOOLS]+extra))
base='https://raw.githubusercontent.com/lucide-icons/lucide/0.468.0/'
def fetch(name):
    try:
        with urllib.request.urlopen(base+'icons/'+name+'.svg',timeout=35) as r: content=r.read()
        (target/(name+'.svg')).write_bytes(content)
        return name,True
    except Exception as e: return name,str(e)
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
    print(json.dumps(list(pool.map(fetch,names)),ensure_ascii=False))
with urllib.request.urlopen(base+'LICENSE',timeout=35) as r: (target/'LICENSE').write_bytes(r.read())
