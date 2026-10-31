"""Real Qt workflow checks; audio lives only in TemporaryDirectory and Session."""
import os
import sys
import time
import tempfile
from pathlib import Path
import numpy as np
import soundfile as sf
from PySide6.QtCore import Qt,QPoint,QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QFileDialog

ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from audioworkbench.desktop import MainWindow
from audioworkbench.ui_components import FeaturePanel,ExportDialog
from audioworkbench.catalog import BY_ID,TOOLS


def wait(window,seconds=90):
    end=time.monotonic()+seconds
    while window.busy and time.monotonic()<end:
        app.processEvents(); QTest.qWait(20)
    assert not window.busy,'worker timed out'
    app.processEvents()


app=QApplication([]); app.setStyle('Fusion')
with tempfile.TemporaryDirectory() as temp:
    sample=Path(temp)/'Studio narration.wav'; sr=48000; t=np.arange(sr*8)/sr
    speech=.15*np.sin(2*np.pi*180*t)*(0.3+0.7*np.sin(2*np.pi*2*t)**2)*(np.sin(2*np.pi*.5*t)>-.65)
    sf.write(sample,speech+np.random.default_rng(9).normal(0,.006,len(t)),sr)
    w=MainWindow(); errors=[]; w.error=lambda text:errors.append(text); w.show(); app.processEvents()
    root=w.session.root; w.add_paths([str(sample)]); wait(w); assert not errors,errors
    assert w.files.count()==1
    # Every tool opens a real parameter form, without a blank placeholder page.
    for tool in TOOLS:
        w.choose_tool(tool.id); assert w.tool_title.text()==tool.title
        app.processEvents()
        for control in getattr(w.form,'controls',{}).values():
            if hasattr(control,'lineEdit') and control.lineEdit() is not None:
                assert control.lineEdit().width()>25,'numeric text is clipped'
    w.choose_tool('denoise'); w.form.controls['engine'].setCurrentIndex(1)
    w.selected_range(.5,3.5); w.run_tool(); wait(w)
    assert not errors,errors
    assert w.asset.result and w.export_btn.isEnabled()
    assert abs(w.asset.result.before['seconds']-3)<.01
    assert not (Path(temp)/'processed.wav').exists()
    QTest.mouseClick(w.processed_btn,Qt.LeftButton); QTest.mouseClick(w.play,Qt.LeftButton); QTest.qWait(700)
    assert w.player.position()>0,'playback did not advance'
    w.player.pause()
    # Parameter edits invalidate export until processing again.
    w.form.controls['strength'].setValue(60); assert not w.export_btn.isEnabled()
    w.form.controls['strength'].setValue(55); assert w.export_btn.isEnabled()
    # Full result, reversible history.
    w.range.setCurrentIndex(1); w.run_tool(); wait(w); w.apply_result(); assert w.asset.index==1
    w.history(-1); assert w.asset.index==0
    w.history(1); assert w.asset.index==1
    w.choose_tool('gain'); w.range.setCurrentIndex(1); w.form.controls['gain'].setValue(-2); w.run_tool(); wait(w)
    assert not errors,errors
    # Use real export dialog and application export action, selecting a deterministic temp path.
    export_path=Path(temp)/'confirmed.wav'
    original_get=QFileDialog.getSaveFileName
    QFileDialog.getSaveFileName=lambda *a,**k:(str(export_path),'WAV')
    def accept_export():
        dialog=app.activeModalWidget()
        if isinstance(dialog,ExportDialog): dialog.accept()
        else: QTimer.singleShot(25,accept_export)
    QTimer.singleShot(25,accept_export); w.export(); wait(w); QFileDialog.getSaveFileName=original_get
    assert export_path.exists(); assert len(list(Path(temp).glob('*.wav')))==2
    # Representative workspace and complete feature panel.
    w.choose_tool('podcast'); w.form.controls['engine'].setCurrentIndex(1); w.range.setCurrentIndex(0); w.start.setValue(0); w.end.setValue(5); w.run_tool(); wait(w)
    assert not errors,errors
    output=ROOT/'docs'; output.mkdir(exist_ok=True); QTest.qWait(200)
    assert w.result_wave.mapToGlobal(QPoint(0,w.result_wave.height())).y() <= w.play.mapToGlobal(QPoint(0,0)).y(), 'waveform overlaps playback controls'
    assert w.wave.mapToGlobal(QPoint(0,w.wave.height())).y() <= w.range.mapToGlobal(QPoint(0,0)).y(), 'waveform overlaps range controls'
    w.grab().save(str(output/'workspace.png'))
    panel=FeaturePanel(w); panel.show(); app.processEvents(); panel.grab().save(str(output/'features.png'))
    panel.search.setText('去噪'); app.processEvents(); assert any(tile.isVisible() and tool.id=='denoise' for tool,tile in panel.tiles)
    assert all(not tile.isVisible() or '去噪' in tool.title+tool.description+tool.engine for tool,tile in panel.tiles)
    panel.search.clear(); panel.set_category('音色动态'); app.processEvents(); assert all(not tile.isVisible() or tool.group=='音色动态' for tool,tile in panel.tiles)
    panel.selected.connect(w.choose_tool); panel.choose('eq'); assert w.tool_id=='eq'
    w.resize(1100,740); app.processEvents(); w.grab().save(str(output/'workspace-small.png'))
    # No unstaged edits survive a deliberate discard-close.
    w._closing=True; w.close(); app.processEvents(); assert not root.exists(),'session was not cleaned'
    assert export_path.exists() and sample.exists()
    print('PASS: catalog, parameters, preview, playback, invalidation, undo/redo, confirmed export, navigation, cleanup.',flush=True)
