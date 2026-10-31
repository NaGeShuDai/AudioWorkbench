"""Regression coverage for feature ownership, local animation, and dual seeking."""
import sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import soundfile as sf
from PySide6.QtWidgets import QApplication,QToolButton
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from audioworkbench.desktop import MainWindow
from audioworkbench.ui_components import FeaturePanel
app=QApplication([]); app.setStyle('Fusion'); w=MainWindow(); w.show()
def until(fn):
    end=time.monotonic()+30
    while not fn() and time.monotonic()<end: QTest.qWait(25)
    assert fn()
with tempfile.TemporaryDirectory() as temp:
    p=Path(temp)/'tone.wav'; sf.write(p,np.sin(np.arange(48000*6)*2*np.pi*220/48000)*.1,48000)
    w.add_paths([str(p)]); until(lambda:not w.busy)
    panel=FeaturePanel(w)
    assert all(tile.parentWidget()==panel.container and not tile.isWindow() for _,tile in panel.tiles)
    for _ in range(3):
        panel.show(); QTest.qWait(30)
        for query in ('去噪','invalid',''):
            panel.search.setText(query); QTest.qWait(10)
            assert not any(isinstance(t,QToolButton) for t in app.topLevelWidgets())
        panel.hide()
    w.set_busy(True); phase=w.busy_indicator.phase; QTest.qWait(180)
    assert w.busy_indicator.phase!=phase and w.busy_indicator.isVisible()
    w.set_busy(False); assert not w.busy_indicator.timer.isActive()
    w.choose_tool('gain'); w.selected_range(1,5); w.run_tool(); until(lambda:not w.busy)
    until(lambda:w.player.duration()>0)
    def drag(bar,ratio):
        slider=bar.slider; slider.setValue(0); QTest.mousePress(slider,Qt.LeftButton,pos=QPoint(6,slider.height()//2))
        QTest.mouseMove(slider,QPoint(int((slider.width()-12)*ratio+6),slider.height()//2),30)
        QTest.mouseRelease(slider,Qt.LeftButton,pos=QPoint(int((slider.width()-12)*ratio+6),slider.height()//2)); QTest.qWait(250)
    drag(w.original_bar,.5)
    assert w.player_kind=='original' and w.playing_full_source
    assert abs(w.player.position()-3000)<180,w.player.position()
    drag(w.processed_bar,.75)
    assert w.player_kind=='processed' and abs(w.player.position()-3000)<180,w.player.position()
    assert w.original_bar.duration==6 and w.processed_bar.duration==4
    w.toggle_play(); QTest.qWait(100); drag(w.original_bar,.3)
    assert w.player.playbackState()==w.player.PlaybackState.PlayingState
    w.player.pause(); w._closing=True; w.close(); panel.close()
print('PASS: no top-level tiles, repeated filtering, animation start/stop, real dual slider drags, preview durations, preserve playback')
