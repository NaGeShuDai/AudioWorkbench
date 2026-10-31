import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
import numpy as np
import soundfile as sf

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from audioworkbench.catalog import BY_ID,validate
from audioworkbench.engine import Runner,Cancelled
from audioworkbench.session import Session
from audioworkbench.toolbox import import_asset,process_tool,export_result,subtitle_text


class ToolboxTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.session=Session(self.root/'sessions'); self.exports=self.root/'exports'; self.exports.mkdir()
        sr=48000; t=np.arange(sr*4)/sr; rng=np.random.default_rng(18)
        gate=((t>.5)&(t<1.7))|((t>2.6)&(t<3.6))
        x=(.2*np.sin(2*np.pi*180*t)+.04*np.sin(2*np.pi*360*t))*gate+rng.normal(0,.0001,len(t))
        self.source=self.root/'测试 sample.wav'; sf.write(self.source,np.column_stack([x,x*.7]),sr,subtype='FLOAT')
        self.source_hash=hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.asset=import_asset(self.session,self.source,Runner())
    def tearDown(self):
        self.session.close(); self.temp.cleanup()
    def run_tool(self,key,params=None,selection=None):
        p=BY_ID[key].defaults(); p.update(params or {})
        return process_tool(self.asset,key,p,selection=selection)

    def test_all_builtin_tools(self):
        ai={'denoise','podcast','dereverb','vocals','stems','transcribe','vad','chain','concat'}
        for key in BY_ID:
            if key in ai: continue
            with self.subTest(tool=key):
                result=self.run_tool(key,{'seconds':1} if key=='split' else None, (0.5,2) if key=='crop' else None)
                self.assertTrue(result.original.is_file())
                for name,path in result.tracks.items():
                    x,sr=sf.read(path)
                    self.assertTrue(np.isfinite(x).all()); self.assertGreater(len(x),0)
                    if not result.time_changed: self.assertAlmostEqual(result.after[name]['seconds'],4,delta=.1)
                if key=='speed': self.assertAlmostEqual(next(iter(result.after.values()))['seconds'],4/1.1,delta=.05)
                if key=='silence': self.assertGreater(len(result.data['segments']),0)
                if key=='spectrum': self.assertTrue(result.image.is_file())
        self.assertEqual(list(self.exports.iterdir()),[])
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(),self.source_hash)

    def test_pipeline_chain_and_concat(self):
        for key in ('denoise','podcast'):
            result=self.run_tool(key,{'engine':'spectral'})
            self.assertEqual(len(result.tracks),1)
        result=self.run_tool('chain',{'steps':[{'tool':'gain','params':{'gain':-3,'protect':True}}, {'tool':'loudness','params':{'lufs':-18,'peak':-2}}]})
        self.assertEqual(len(result.data['steps']),2)
        other=import_asset(self.session,self.source,Runner())
        joined=process_tool(self.asset,'concat',{'gap':.5},assets=[self.asset,other])
        self.assertAlmostEqual(next(iter(joined.after.values()))['seconds'],8.5,places=2)

    def test_export_atomic_and_no_accidental_save(self):
        result=self.run_tool('gain',{'gain':-3})
        self.assertEqual(list(self.exports.iterdir()),[])
        track=next(iter(result.tracks))
        for fmt in ('wav','flac','mp3','m4a','ogg','zip'):
            output=self.exports/('final.'+fmt)
            export_result(self.asset,result,output,fmt,track=track)
            self.assertTrue(output.is_file())
            with self.assertRaises(FileExistsError): export_result(self.asset,result,output,fmt,track=track)
        self.assertEqual(len(list(self.exports.iterdir())),6)
        with self.assertRaises(ValueError): export_result(self.asset,result,self.source,'wav',track=track,overwrite=True)
        cancel=threading.Event(); cancel.set()
        with self.assertRaises(Cancelled): export_result(self.asset,result,self.exports/'cancelled.wav','wav',Runner(cancel),track)
        self.assertFalse((self.exports/'cancelled.wav').exists()); self.assertFalse(list(self.exports.glob('.awb-*')))

    def test_video_stream_selection_and_timeline_guard(self):
        video=self.root/'source.mkv'
        Runner().ff(['-f','lavfi','-i','color=c=gray:s=160x90:r=10:d=4','-i',self.source,'-f','lavfi','-i','sine=frequency=900:duration=4',
                     '-map','0:v','-map','1:a','-map','2:a','-c:v','libx264','-c:a','pcm_s16le',video])
        asset=import_asset(self.session,video,Runner(),stream=1); self.assertEqual(len(asset.streams),2)
        result=process_tool(asset,'gain',BY_ID['gain'].defaults()); track=next(iter(result.tracks))
        export_result(asset,result,self.exports/'video.mkv','mkv',track=track)
        cropped=process_tool(asset,'crop',{},selection=(1,2))
        with self.assertRaises(ValueError): export_result(asset,cropped,self.exports/'bad.mkv','mkv',track=next(iter(cropped.tracks)))

    def test_validation_and_subtitle(self):
        for key,p in [('gain',{'gain':100}),('speed',{'speed':float('nan')})]:
            with self.assertRaises(ValueError): validate(key,p)
        with self.assertRaises(ValueError): self.run_tool('gain',selection=(3,5))
        with self.assertRaises(ValueError): self.run_tool('filters',{'highpass':4000,'lowpass':1000})
        with self.assertRaises(ValueError): self.run_tool('chain',{'steps':[{'tool':'chain','params':{}}]})
        self.assertIn('00:00:01,250 --> 00:00:02,500',subtitle_text([{'start':1.25,'end':2.5,'text':'你好'}],'srt'))
        with self.assertRaises(ValueError): subtitle_text([{'start':2,'end':1,'text':'bad'}],'srt')

    def test_cache_and_partial_export(self):
        first=self.run_tool('gain',{'gain':-6}); second=self.run_tool('gain',{'gain':-6})
        self.assertEqual(first.folder,second.folder)
        result=self.run_tool('split',{'seconds':2})
        self.assertEqual(len(result.tracks),2)
        export_result(self.asset,result,self.exports/'first.wav','wav',track=next(iter(result.tracks)))
        self.assertFalse(result.exported,'one exported stem must not mark all stems as saved')
        export_result(self.asset,result,self.exports/'all.zip','zip')
        self.assertTrue(result.exported)

    def test_session_cleanup_and_live_lease(self):
        active=self.session.root; other=Session(self.root/'sessions')
        self.assertTrue(active.exists()); orphan=other.root; other.close(); self.assertFalse(orphan.exists())
        cmd=[sys.executable,'-c',"import sys,os;sys.path.insert(0,sys.argv[1]);from audioworkbench.session import Session;s=Session(sys.argv[2]);print(s.root,flush=True);os._exit(0)",str(Path(__file__).resolve().parents[1]),str(self.root/'sessions')]
        orphan=Path(subprocess.check_output(cmd,text=True).strip()); self.assertTrue(orphan.exists())
        self.session.cleanup_abandoned(); self.assertFalse(orphan.exists()); self.assertTrue(active.exists())
        self.session.close(); self.assertFalse(active.exists()); self.assertTrue(self.source.exists())


if __name__=='__main__': unittest.main(verbosity=2)
