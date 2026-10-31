"""Opt-in actual inference tests. Downloads only the requested models."""
import argparse
import base64
import json
import subprocess
import sys
import tempfile
from pathlib import Path
import numpy as np
import soundfile as sf
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from audioworkbench.engine import Runner
from audioworkbench.session import Session
from audioworkbench.toolbox import import_asset,process_tool
from audioworkbench.catalog import BY_ID

parser=argparse.ArgumentParser(); parser.add_argument('tools',nargs='*',default=['denoise','dereverb','vocals','vad','transcribe','stems']); parser.add_argument('--speech-model',default='tiny'); args=parser.parse_args()
with tempfile.TemporaryDirectory() as temp, Session() as session:
    source=Path(temp)/'speech.wav'
    script="$voice = New-Object -ComObject SAPI.SpVoice; $stream = New-Object -ComObject SAPI.SpFileStream; $stream.Open('"+str(source).replace("'","''")+"',3); $voice.AudioOutputStream = $stream; $voice.Speak('This is an audio processing test. Clear speech, quiet background, and natural sound.'); $stream.Close()"
    subprocess.run(['powershell','-NoProfile','-EncodedCommand',base64.b64encode(script.encode('utf-16le')).decode()],check=True,stdout=subprocess.DEVNULL)
    asset=import_asset(session,source,Runner()); results=[]
    for key in args.tools:
        print('RUN',key,flush=True); p=BY_ID[key].defaults()
        if key=='transcribe': p.update(model=args.speech_model,language='en',vad=True,download_source='mirror')
        try:
            result=process_tool(asset,key,p,selection=(0,min(4,asset.current.info['seconds'])))
            for path in result.tracks.values():
                x,sr=sf.read(path); assert np.isfinite(x).all() and len(x)>0
            if key=='transcribe': assert result.data['segments'],'no transcript'
            if key=='vad': assert result.data['segments'],'no speech detected'
            results.append({'tool':key,'status':'passed','tracks':list(result.tracks),'segments':result.data.get('segments',[])})
            print(json.dumps(results[-1],ensure_ascii=False),flush=True)
        except Exception as exc:
            results.append({'tool':key,'status':'failed','error':str(exc)})
            print(json.dumps(results[-1],ensure_ascii=False),flush=True)
    evidence=ROOT/'docs'/('ai-validation-'+'-'.join(args.tools)+(('-'+args.speech_model) if 'transcribe' in args.tools else '')+'.json')
    evidence.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    if any(r['status']=='failed' for r in results): sys.exit(1)
