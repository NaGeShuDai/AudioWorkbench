"""Opt-in packaged-app self test. Media stays in a temporary directory."""
def run(app,report_path):
    import tempfile,time,json,traceback
    from pathlib import Path
    import numpy as np
    import soundfile as sf
    from .desktop import MainWindow
    from .ui_components import FeaturePanel
    from .engine import ROOT,Runner,FFMPEG
    from .toolbox import export_result
    result={'ok':False,'runtime':str(ROOT),'ffmpeg':FFMPEG}; w=None
    def until(fn):
        deadline=time.monotonic()+90
        while not fn() and time.monotonic()<deadline: app.processEvents(); time.sleep(.015)
        assert fn(),'Timed out'
    try:
        with tempfile.TemporaryDirectory() as temp:
            temp=Path(temp); sample=temp/'input.wav'; sf.write(sample,np.sin(np.arange(96000)*.04)*.1,48000)
            w=MainWindow(); errors=[]; w.error=lambda text:errors.append(text); w.show(); app.processEvents()
            w.add_paths([str(sample)]); until(lambda:not w.busy); assert w.asset and not errors,errors
            panel=FeaturePanel(w); panel.show(); app.processEvents()
            assert all(not tile.isWindow() for _,tile in panel.tiles); panel.close()
            w.choose_tool('gain'); w.range.setCurrentIndex(1); w.run_tool(); until(lambda:not w.busy); assert w.asset.result and not errors,errors
            w.seek_result(.5); until(lambda:w.player.duration()>0 and w.pending_seek is None)
            assert abs(w.player.position()-1000)<100
            result['audio_tracks']=list(w.asset.result.tracks)
            # Use the same exporter as the GUI's confirmed-export action.
            destination=temp/'confirmed.wav'
            export_result(w.asset,w.asset.result,destination,'wav',Runner(),next(iter(w.asset.result.tracks)),48000,24,False)
            assert destination.exists() and sf.info(destination).frames==96000
            result['export_verified']=True
            w.grab().save(str(Path(report_path).with_suffix('.png')))
            for tool in ('denoise','spectrum'):
                w.choose_tool(tool)
                if tool=='denoise': w.form.controls['engine'].setCurrentIndex(1)
                w.run_tool(); until(lambda:not w.busy); assert not errors,errors
                assert w.asset.result.tool_id==tool
            result['additional_tools']=['spectral denoise','spectrum']
            result['ok']=True
    except Exception: result['error']=traceback.format_exc()
    finally:
        if w: w._closing=True; w.close(); app.processEvents()
    Path(report_path).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if result['ok'] else 1
