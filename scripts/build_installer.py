"""Compile the per-user Windows installer using Inno Setup 7 or newer."""
import os,sys,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
candidates=[os.environ.get('ISCC'),shutil.which('ISCC'),str(ROOT/'test-artifacts/innosetup/ISCC.exe')]
for base in ('PROGRAMFILES','PROGRAMFILES(X86)','LOCALAPPDATA'):
    for folder in ('Inno Setup 7','Inno Setup 6','Programs/Inno Setup 7','Programs/Inno Setup 6'):
        candidates.append(str(Path(os.environ.get(base,''))/folder/'ISCC.exe'))
compiler=next((p for p in candidates if p and Path(p).is_file()),None)
if not compiler: raise SystemExit('Install Inno Setup 7+ or set ISCC to ISCC.exe')
if not (ROOT/'dist/AudioWorkbench/AudioWorkbench.exe').is_file(): raise SystemExit('Build the portable app first')
subprocess.run([compiler,str(ROOT/'scripts/installer.iss')],cwd=ROOT,check=True)
