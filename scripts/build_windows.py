"""Reproducible portable EXE build: run with the main virtual environment."""
import sys,shutil,subprocess,importlib.metadata
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
uv=shutil.which('uv')
if not uv: raise SystemExit('Install uv before building')
args=[sys.executable,'-m','PyInstaller','--noconfirm','--windowed','--onedir','--contents-directory','.', '--name','AudioWorkbench','--icon','assets/app.ico','--add-data','assets;assets','--add-data','audioworkbench/install_engine.py;audioworkbench','--add-data','audioworkbench/tool_worker.py;audioworkbench','--add-data','audioworkbench/model_worker.py;audioworkbench','--collect-all','imageio_ffmpeg','--copy-metadata','imageio-ffmpeg']
for name in ('deepfilter','separator','speech'): args+=['--add-data',name+'.lock.txt;.']
args+=['--add-binary',uv+';.','main.py']
subprocess.run(args,cwd=ROOT,check=True)
out=ROOT/'dist/AudioWorkbench'
for name in ('README.md','LICENSE','THIRD_PARTY.md'): shutil.copy2(ROOT/name,out/name)
licenses=out/'licenses'; licenses.mkdir(exist_ok=True)
for d in importlib.metadata.distributions():
    for file in d.files or []:
        if any(x in file.name.lower() for x in ('license','copying','notice')) and 'dist-info' in str(file):
            src=Path(d.locate_file(file))
            if src.is_file():
                dst=licenses/d.metadata['Name']/str(file).split('dist-info/',1)[-1]; dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,dst)
shutil.copytree(ROOT/'docs',out/'docs',dirs_exist_ok=True)
print('Built:',out/'AudioWorkbench.exe')
