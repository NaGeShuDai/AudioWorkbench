from __future__ import annotations
import os
import math
from functools import lru_cache
import sys
from pathlib import Path
import numpy as np
from PySide6.QtCore import Qt, Signal, QSize, QRectF, QProcess, QProcessEnvironment, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QIcon
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (QWidget,QLabel,QPushButton,QVBoxLayout,QHBoxLayout,QGridLayout,QFormLayout,
    QFrame,QDialog,QScrollArea,QLineEdit,QComboBox,QDoubleSpinBox,QCheckBox,QListWidget,
    QPlainTextEdit,QMessageBox,QDialogButtonBox,QToolButton,QSizePolicy,QAbstractSpinBox,QSlider)
from .engine import ROOT, available
from .catalog import TOOLS, BY_ID, GROUPS, COMMON

STYLE = '''
* { font-family:"Microsoft YaHei UI"; font-size:12px; color:#263b3a; }
QMainWindow, QDialog { background:#f5f7f6; }
QWidget#canvas { background:#f5f7f6; }
QFrame#card { background:#ffffff; border:1px solid #e3eae6; border-radius:14px; }
QFrame#sidebar { background:#edf3ef; border:0; border-radius:14px; }
QLabel { background:transparent; }
QLabel#title { font-size:25px; font-weight:600; letter-spacing:-.5px; }
QLabel#heading { font-size:18px; font-weight:600; }
QLabel#section { font-size:13px; font-weight:600; }
QLabel#muted { color:#7b8d86; font-size:11px; }
QLabel#eyebrow { color:#649080; font-size:10px; letter-spacing:2px; font-weight:600; }
QLabel#badge { color:#317963; background:#eaf4ef; border-radius:5px; padding:5px 9px; }
QPushButton { background:#fff; border:1px solid #dee7e1; border-radius:8px; padding:9px 12px; }
QPushButton:hover { background:#f0f6f2; border-color:#a7c7b9; }
QPushButton:checked { background:#e3efe7; color:#216c53; border-color:#b3d0bf; }
QPushButton:disabled { color:#a5b3ac; background:#f4f6f4; border-color:#e9efeb; }
QPushButton#primary { background:#246b53; color:white; border:1px solid #246b53; font-weight:600; }
QPushButton#primary:hover { background:#1b5843; }
QPushButton#primary:disabled { background:#bdd2c5; border-color:#bdd2c5; }
QPushButton#nav { text-align:left; background:transparent; border:0; padding:10px 12px; }
QPushButton#nav:checked { background:#dcebe1; color:#195c42; font-weight:600; }
QPushButton#nav:hover { background:#e2ede5; }
QToolButton#tile { background:#fff; border:1px solid #e1e9e3; border-radius:12px; font-size:13px; padding:14px; }
QToolButton#tile:hover { background:#edf5ef; border-color:#9abcaa; }
QLineEdit, QComboBox, QDoubleSpinBox { background:#fafcfb; border:1px solid #dfe7e2; border-radius:7px; padding:8px; selection-background-color:#bfdacb; color:#263b3a; }
QDoubleSpinBox { min-height:20px; }
QDoubleSpinBox QLineEdit { padding:0; border:0; background:transparent; color:#263b3a; }
QDoubleSpinBox::up-button { subcontrol-origin:border; subcontrol-position:top right; width:20px; border:0; background:transparent; }
QDoubleSpinBox::down-button { subcontrol-origin:border; subcontrol-position:bottom right; width:20px; border:0; background:transparent; }
QWidget#params { background:#ffffff; }
QComboBox::drop-down { border:0; width:22px; }
QComboBox QAbstractItemView { background:white; selection-background-color:#dceee2; }
QCheckBox { spacing:8px; padding:5px 0; }
QCheckBox::indicator { width:15px; height:15px; border-radius:4px; border:1px solid #b6c8bd; background:white; }
QCheckBox::indicator:checked { background:#2c775a; border:1px solid #2c775a; }
QListWidget { background:transparent; border:0; outline:none; }
QListWidget::item { padding:10px 7px; border-radius:6px; }
QListWidget::item:selected { background:#dcebe1; color:#216b50; }
QListWidget::item:hover { background:#e7f0ea; }
QScrollArea { background:transparent; border:0; }
QScrollBar:vertical { width:6px; background:transparent; margin:0; }
QScrollBar::handle:vertical { min-height:25px; border-radius:3px; background:#c5d5cb; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
QProgressBar { border:0; background:#e1ebe4; border-radius:3px; height:5px; max-height:5px; color:transparent; }
QProgressBar::chunk { background:#3a8466; border-radius:3px; }
QPlainTextEdit, QTableWidget { background:#fafcfb; border:1px solid #e0e8e3; border-radius:8px; padding:6px; }
QHeaderView::section { background:#edf4ef; border:0; padding:7px; }
QTabWidget::pane { border:0; }
QTabBar::tab { background:transparent; padding:10px 15px; color:#7a8c83; }
QTabBar::tab:selected { color:#216b50; border-bottom:2px solid #216b50; }
QSplitter::handle { background:transparent; width:12px; }
QToolTip { background:#263b32; color:white; border:0; padding:7px; }
'''
STYLE += ('QDoubleSpinBox::up-arrow { image:url("'+(ROOT/'assets/icons/arrow-up.svg').as_posix()+'"); width:10px; height:10px; }'
          'QDoubleSpinBox::down-arrow { image:url("'+(ROOT/'assets/icons/arrow-down.svg').as_posix()+'"); width:10px; height:10px; }')


@lru_cache(maxsize=256)
def icon(name, color='#38785e', size=24):
    path=ROOT/'assets'/'icons'/f'{name}.svg'
    if not path.exists(): path=ROOT/'assets'/'icons'/'audio-lines.svg'
    raw=path.read_text(encoding='utf-8').replace('currentColor',color)
    renderer=QSvgRenderer(raw.encode()); pix=QPixmap(size*2,size*2); pix.fill(Qt.transparent)
    painter=QPainter(pix); renderer.render(painter); painter.end(); pix.setDevicePixelRatio(2)
    return QIcon(pix)


def label(text, name=None):
    w=QLabel(text)
    if name: w.setObjectName(name)
    return w


def btn(text, fn=None, glyph=None, primary=False):
    b=QPushButton(text)
    if glyph: b.setIcon(icon(glyph,'#ffffff' if primary else '#38785e',18)); b.setIconSize(QSize(18,18))
    if primary: b.setObjectName('primary')
    if fn: b.clicked.connect(fn)
    return b


def card(name='card', margins=20):
    w=QFrame(); w.setObjectName(name); l=QVBoxLayout(w)
    l.setContentsMargins(margins,margins,margins,margins); l.setSpacing(12)
    return w,l


class ParamForm(QWidget):
    changed=Signal()
    def __init__(self,tool_id,values=None):
        super().__init__(); self.setObjectName('params'); self.tool_id=tool_id; self.controls={}
        form=QVBoxLayout(self); form.setContentsMargins(0,0,0,0); form.setSpacing(13)
        values=values or BY_ID[tool_id].defaults()
        for p in BY_ID[tool_id].params:
            if p.kind=='bool':
                w=QCheckBox(p.title); w.setChecked(values.get(p.key,p.default)); w.toggled.connect(self.changed)
            else:
                form.addWidget(label(p.title,'muted'))
                if p.kind=='choice':
                    w=QComboBox()
                    for title,value in p.options: w.addItem(title,value)
                    w.setCurrentIndex(max(0,w.findData(values.get(p.key,p.default))))
                    w.currentIndexChanged.connect(self.changed)
                    w.setMinimumWidth(0); w.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon); w.setMinimumContentsLength(8)
                elif p.kind=='path':
                    w=QLineEdit(str(values.get(p.key,p.default))); w.setPlaceholderText('留空使用所选在线模型'); w.textChanged.connect(self.changed)
                else:
                    w=QDoubleSpinBox(); w.setRange(p.low,p.high); w.setSingleStep(p.step)
                    w.setDecimals(0 if p.step>=1 else 2); w.setValue(values.get(p.key,p.default)); w.setSuffix(p.unit)
                    w.setButtonSymbols(QAbstractSpinBox.UpDownArrows); w.valueChanged.connect(self.changed)
            self.controls[p.key]=w; form.addWidget(w)
        if not self.controls:
            note=label('此工具无需额外参数。\n在工作区选择范围后运行。','muted'); note.setWordWrap(True); form.addWidget(note)
        form.addStretch()

    def values(self):
        result={}
        for p in BY_ID[self.tool_id].params:
            w=self.controls[p.key]
            result[p.key]=w.isChecked() if p.kind=='bool' else w.currentData() if p.kind=='choice' else w.text().strip() if p.kind=='path' else w.value()
        return result


class FeaturePanel(QDialog):
    selected=Signal(str)
    def __init__(self,parent=None):
        super().__init__(parent); self.setWindowTitle('完整功能'); self.resize(970,760); self.setMinimumSize(800,600)
        layout=QVBoxLayout(self); layout.setContentsMargins(28,25,28,24); layout.setSpacing(16)
        top=QHBoxLayout(); titles=QVBoxLayout(); titles.addWidget(label('AUDIO TOOLBOX','eyebrow'))
        titles.addWidget(label('完整功能','title')); top.addLayout(titles); top.addStretch()
        count=label(f'{len(TOOLS)} 项工具','badge'); count.setMaximumHeight(30); top.addWidget(count); layout.addLayout(top)
        self.search=QLineEdit(); self.search.setPlaceholderText('搜索功能，例如：去噪、字幕、剪辑…')
        self.search.addAction(icon('search'),QLineEdit.LeadingPosition); self.search.textChanged.connect(self.filter); layout.addWidget(self.search)
        categories=QHBoxLayout(); self.category='全部'; self.tabs=[]
        for title in ['全部']+GROUPS:
            b=btn(title,lambda checked=False,t=title:self.set_category(t)); b.setCheckable(True); b.setChecked(title=='全部')
            categories.addWidget(b); self.tabs.append(b)
        layout.addLayout(categories)
        scroll=QScrollArea(); scroll.setWidgetResizable(True); self.container=QWidget(); self.container.setObjectName('canvas')
        self.grid=QGridLayout(self.container); self.grid.setContentsMargins(0,0,5,0); self.grid.setSpacing(12)
        scroll.setWidget(self.container); layout.addWidget(scroll,1)
        self.tiles=[]
        for t in TOOLS:
            tile=QToolButton(self.container); tile.setObjectName('tile'); tile.setText(t.title); tile.setIcon(icon(t.icon,size=30)); tile.setIconSize(QSize(30,30))
            tile.setToolButtonStyle(Qt.ToolButtonTextUnderIcon); tile.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed); tile.setFixedHeight(108)
            tile.setToolTip(t.description+'\n引擎：'+t.engine); tile.clicked.connect(lambda checked=False,key=t.id:self.choose(key)); self.tiles.append((t,tile))
        self.empty=label('没有匹配的工具，试试其他关键词。','muted'); layout.addWidget(self.empty)
        footer=QHBoxLayout(); footer.addWidget(label('统一操作 · 临时预览 · 确认后导出','muted')); footer.addStretch(); footer.addWidget(btn('关闭',self.reject))
        layout.addLayout(footer); self.filter()

    def set_category(self,title):
        self.category=title
        for b in self.tabs: b.setChecked(b.text()==title)
        self.filter()

    def filter(self):
        self.container.setUpdatesEnabled(False)
        for row in range(self.grid.rowCount()): self.grid.setRowStretch(row,0)
        while self.grid.count(): self.grid.takeAt(0)
        query=self.search.text().lower().strip(); count=0
        for tool,tile in self.tiles:
            visible=(self.category=='全部' or tool.group==self.category) and (not query or query in (tool.title+tool.description+tool.engine).lower())
            tile.setVisible(visible)
            if visible: self.grid.addWidget(tile,count//4,count%4); count+=1
        for col in range(4): self.grid.setColumnStretch(col,1)
        self.grid.setRowStretch((count+3)//4,1); self.empty.setVisible(not count)
        self.container.setUpdatesEnabled(True)

    def choose(self,key): self.selected.emit(key); self.accept()


class Waveform(QWidget):
    selected=Signal(float,float)
    seek=Signal(float)
    def __init__(self,interactive=True):
        super().__init__(); self.setMinimumHeight(45); self.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
        self.values=[]; self.duration=0.; self.a=0.; self.b=0.; self.cursor=0.; self.drag=None; self.interactive=interactive
        self.setCursor(Qt.CrossCursor if interactive else Qt.PointingHandCursor)

    def set_audio(self,info):
        self.values=info.get('envelope',[]); self.duration=info.get('seconds',0); self.cursor=0.; self.update()

    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing); p.setClipRect(self.rect())
        w,h=self.width(),self.height(); p.fillRect(self.rect(),QColor('#f8fbf9'))
        p.setPen(QPen(QColor('#e7efe9'),1))
        for i in range(1,8): p.drawLine(int(w*i/8),0,int(w*i/8),h)
        p.drawLine(0,h//2,w,h//2)
        if self.interactive and self.duration>0 and self.b>self.a:
            x1=w*self.a/self.duration; x2=w*self.b/self.duration
            p.fillRect(QRectF(x1,0,x2-x1,h),QColor(68,137,94,28))
            p.setPen(QPen(QColor('#6a9e7a'),1)); p.drawLine(int(x1),0,int(x1),h); p.drawLine(int(x2),0,int(x2),h)
        if not self.values:
            p.setPen(QColor('#94a99b')); p.drawText(self.rect(),Qt.AlignCenter,'导入音频或视频，开始处理'); return
        n=max(1,w//3); values=np.interp(np.linspace(0,len(self.values)-1,n),np.arange(len(self.values)),self.values)
        scale=max(.06,max(self.values)); p.setPen(QPen(QColor('#65a184'),2))
        for i,v in enumerate(values):
            a=max(1,min(1,float(v)/scale)*h*.37); p.drawLine(i*3,int(h/2-a),i*3,int(h/2+a))
        p.setPen(QPen(QColor('#24523c'),1)); x=int(w*self.cursor); p.drawLine(x,0,x,h)

    def mousePressEvent(self,event):
        self.drag=max(0.,min(1.,event.position().x()/max(self.width(),1)))

    def mouseMoveEvent(self,event):
        if self.drag is None or not self.interactive: return
        end=max(0.,min(1.,event.position().x()/max(self.width(),1)))
        self.a=min(self.drag,end)*self.duration; self.b=max(self.drag,end)*self.duration; self.update()

    def mouseReleaseEvent(self,event):
        if self.drag is None: return
        end=max(0.,min(1.,event.position().x()/max(self.width(),1)))
        if self.interactive and abs(end-self.drag)>.01:
            self.a=min(self.drag,end)*self.duration; self.b=max(self.drag,end)*self.duration
            self.selected.emit(self.a,self.b)
        else: self.seek.emit(end)
        self.drag=None; self.update()


class ChainEditor(QWidget):
    changed=Signal()
    def __init__(self,steps=None):
        super().__init__(); self.setObjectName('params'); self.steps=list(steps or [])
        from .toolbox import CHAIN_TOOLS
        layout=QVBoxLayout(self); layout.setContentsMargins(0,0,0,0); layout.setSpacing(8)
        self.combo=QComboBox()
        for key in CHAIN_TOOLS: self.combo.addItem(BY_ID[key].title,key)
        layout.addWidget(self.combo); layout.addWidget(btn('添加步骤',self.add,'plus'))
        self.list=QListWidget(); self.list.setMinimumHeight(180); self.list.itemDoubleClicked.connect(self.edit); layout.addWidget(self.list,1)
        row=QHBoxLayout()
        for text,fn in [('↑',lambda:self.move(-1)),('↓',lambda:self.move(1)),('设置',self.edit),('移除',self.remove)]: row.addWidget(btn(text,fn))
        layout.addLayout(row); layout.addWidget(label('双击步骤可编辑参数；按顺序执行。','muted')); self.refresh()
    def refresh(self):
        row=self.list.currentRow(); self.list.clear()
        for i,s in enumerate(self.steps): self.list.addItem(f'{i+1:02d}   {BY_ID[s["tool"]].title}')
        self.list.setCurrentRow(min(max(row,0),len(self.steps)-1))
    def add(self):
        if len(self.steps)>=16: return
        key=self.combo.currentData(); self.steps.append({'tool':key,'params':BY_ID[key].defaults()}); self.refresh(); self.changed.emit()
    def remove(self):
        row=self.list.currentRow()
        if row>=0: self.steps.pop(row); self.refresh(); self.changed.emit()
    def move(self,delta):
        row=self.list.currentRow(); other=row+delta
        if 0<=row<len(self.steps) and 0<=other<len(self.steps):
            self.steps[row],self.steps[other]=self.steps[other],self.steps[row]; self.refresh(); self.list.setCurrentRow(other); self.changed.emit()
    def edit(self,*args):
        row=self.list.currentRow()
        if row<0: return
        step=self.steps[row]; dialog=QDialog(self); dialog.setWindowTitle(BY_ID[step['tool']].title); dialog.resize(340,430)
        layout=QVBoxLayout(dialog); form=ParamForm(step['tool'],step['params']); layout.addWidget(form)
        layout.addWidget(btn('应用设置',dialog.accept,primary=True))
        if dialog.exec(): step['params']=form.values(); self.changed.emit()
    def values(self):
        import copy
        return {'steps':copy.deepcopy(self.steps)}


class ModelsDialog(QDialog):
    def __init__(self,parent):
        super().__init__(parent); self.setWindowTitle('引擎管理'); self.resize(720,540); self.proc=None
        l=QVBoxLayout(self); l.setContentsMargins(24,24,24,24); l.setSpacing(15)
        l.addWidget(label('开源处理引擎','heading'))
        note=label('基础工具内置。AI 依赖与模型按需下载，音频始终在本机处理。\n“已安装”仅表示依赖就绪，具体模型首次运行时下载。','muted'); note.setWordWrap(True); l.addWidget(note)
        self.buttons=[]
        for key,title in [('deepfilter','DeepFilterNet3 · 语音去噪'),('separator','Audio Separator · MDX / RoFormer / Demucs'),('speech','faster-whisper + Silero VAD · 转写与语音检测')]:
            row=QHBoxLayout(); row.addWidget(label(title)); row.addStretch()
            b=btn('已安装 · 检查' if available(key) else '安装',lambda checked=False,k=key:self.install(k))
            row.addWidget(b); l.addLayout(row); self.buttons.append((key,b))
        self.log=QPlainTextEdit(); self.log.setReadOnly(True); l.addWidget(self.log,1)
        note=label('模型权重和代码的许可分别适用。Resemble / 实时 AEC 未纳入本版。','muted'); note.setWordWrap(True); l.addWidget(note)
        l.addWidget(btn('关闭',self.reject))
    def install(self,key):
        if self.proc and self.proc.state()!=QProcess.NotRunning: return
        for _,b in self.buttons: b.setEnabled(False)
        self.log.setPlainText('正在检查 / 安装依赖，请稍候…')
        self.proc=QProcess(self); self.proc.setProcessChannelMode(QProcess.MergedChannels)
        env=QProcessEnvironment.systemEnvironment(); env.insert('PYTHONUTF8','1'); self.proc.setProcessEnvironment(env)
        self.proc.readyReadStandardOutput.connect(lambda:self.log.appendPlainText(bytes(self.proc.readAllStandardOutput()).decode('utf-8',errors='replace')))
        self.proc.errorOccurred.connect(lambda error:self.log.appendPlainText(self.proc.errorString()))
        self.proc.finished.connect(self.finished_install)
        if getattr(sys,'frozen',False):
            self.proc.start(str(ROOT/'uv.exe'),['run','--no-project','--python','3.11',str(ROOT/'audioworkbench'/'install_engine.py'),key])
        else: self.proc.start(sys.executable,['-u',str(ROOT/'audioworkbench'/'install_engine.py'),key])
    def finished_install(self,code,status):
        self.log.appendPlainText('依赖就绪。' if code==0 else '安装失败，请查看日志。')
        for key,b in self.buttons: b.setEnabled(True); b.setText('已安装 · 检查' if available(key) else '重试')
    def reject(self):
        if self.proc and self.proc.state()!=QProcess.NotRunning: return
        super().reject()
    def closeEvent(self,event):
        if self.proc and self.proc.state()!=QProcess.NotRunning: event.ignore()
        else: event.accept()


class ExportDialog(QDialog):
    def __init__(self,asset,result,parent=None):
        super().__init__(parent); self.setWindowTitle('确认导出'); self.resize(460,470)
        l=QVBoxLayout(self); l.setContentsMargins(24,24,24,24); l.setSpacing(14)
        l.addWidget(label('保存你确认的结果','heading'))
        scope=f'片段 {result.selection[0]:.2f}–{result.selection[1]:.2f} 秒' if result.selection else '完整音频'
        l.addWidget(label(f'{BY_ID[result.tool_id].title}  ·  {scope}','badge'))
        self.track=QComboBox()
        for name in result.tracks: self.track.addItem(name,name)
        l.addWidget(label('输出音轨','muted')); l.addWidget(self.track)
        self.format=QComboBox()
        formats=['wav','flac','mp3','m4a','ogg'] if result.tracks else []
        if len(result.tracks)>1: formats+=['zip']
        if result.tool_id=='transcribe': formats+=['srt','txt']
        if result.image: formats+=['png']
        if result.data or BY_ID[result.tool_id].analysis: formats+=['json']
        from .engine import VIDEO
        if result.tracks and asset.source.suffix.lower() in VIDEO and not result.selection and not result.time_changed: formats+=['mkv']
        titles={'zip':'ZIP · 所有音轨 / WAV','mkv':'MKV · 替换原视频音轨','json':'JSON · 分析报告'}
        for fmt in formats: self.format.addItem(titles.get(fmt,fmt.upper()),fmt)
        l.addWidget(label('格式','muted')); l.addWidget(self.format)
        row=QHBoxLayout(); self.rate=QComboBox(); self.depth=QComboBox()
        for rate in (16000,22050,44100,48000,96000): self.rate.addItem(f'{rate} Hz',rate)
        self.rate.setCurrentIndex(3)
        for depth in (16,24,32): self.depth.addItem(f'{depth} bit'+(' float' if depth==32 else ''),depth)
        self.depth.setCurrentIndex(1); row.addWidget(self.rate); row.addWidget(self.depth); l.addLayout(row)
        self.note=label('文件名和保存位置将在下一步选择。','muted'); self.note.setWordWrap(True); l.addWidget(self.note)
        l.addStretch(); buttons=QHBoxLayout(); buttons.addWidget(btn('返回试听',self.reject)); buttons.addWidget(btn('选择位置并导出',self.accept,'download',True)); l.addLayout(buttons)
        self.format.currentIndexChanged.connect(self.update_controls); self.update_controls()
    def update_controls(self):
        fmt=self.format.currentData(); audio=fmt in ('wav','flac','mp3','m4a','ogg','zip')
        self.rate.setEnabled(audio); self.depth.setEnabled(fmt in ('wav','flac','zip'))
        self.track.setEnabled(fmt in ('wav','flac','mp3','m4a','ogg','mkv'))
        self.note.setText('字幕时间从当前结果的 0 秒开始；可在工作区编辑。' if fmt in ('srt','txt') else
                         '仅保留第一条视频流与所选处理音轨，额外音轨和字幕不复制。' if fmt=='mkv' else
                         '所有音轨以 WAV 打包为一个 ZIP，不创建额外目录。' if fmt=='zip' else
                         '仅保存此处选择的文件，不附带中间音频或处理日志。')



class BusyIndicator(QWidget):
    """Small local repaint: keeps moving even while a worker reports no progress."""
    def __init__(self,parent=None):
        super().__init__(parent); self.setFixedSize(24,24); self.phase=0
        self.timer=QTimer(self); self.timer.setInterval(70); self.timer.timeout.connect(self.advance); self.hide()
    def advance(self): self.phase=(self.phase+1)%12; self.update()
    def set_running(self,running):
        self.setVisible(running)
        if running: self.timer.start()
        else: self.timer.stop()
    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing); p.setPen(Qt.NoPen)
        for i in range(12):
            c=QColor('#38785e'); c.setAlpha(40+int(215*((i-self.phase)%12)/11)); p.setBrush(c)
            a=i*math.pi/6; p.drawEllipse(QRectF(10+8*math.cos(a),10+8*math.sin(a),3,3))

class PlaybackBar(QWidget):
    seek=Signal(float)
    def __init__(self,title):
        super().__init__(); row=QHBoxLayout(self); row.setContentsMargins(0,0,0,0); row.setSpacing(9)
        row.addWidget(label(title,'muted')); self.slider=QSlider(Qt.Horizontal); self.slider.setRange(0,10000)
        self.slider.setStyleSheet('QSlider::groove:horizontal {height:4px;background:#dce8df;border-radius:2px;} QSlider::sub-page:horizontal {background:#438768;} QSlider::handle:horizontal {background:#246b53;width:12px;margin:-5px 0;border-radius:6px;}')
        row.addWidget(self.slider,1); self.time=label('00:00 / 00:00','muted'); row.addWidget(self.time); self.duration=0
        self.slider.sliderReleased.connect(lambda:self.seek.emit(self.slider.value()/10000))
        self.slider.sliderMoved.connect(lambda v:self.update_time(v/10000*self.duration))
        self.slider.actionTriggered.connect(self.keyboard_seek)
        self.setEnabled(False)
    def keyboard_seek(self,action):
        if not self.slider.isSliderDown(): self.seek.emit(self.slider.sliderPosition()/10000)
    def update_time(self,pos):
        def fmt(s):
            s=max(0,int(s)); return f'{s//60:02d}:{s%60:02d}'
        self.time.setText(f'{fmt(pos)} / {fmt(self.duration)}')
    def update_position(self,pos,duration):
        self.duration=duration
        if not self.slider.isSliderDown():
            self.slider.setValue(round(max(0,min(1,pos/max(duration,.001)))*10000)); self.update_time(pos)
