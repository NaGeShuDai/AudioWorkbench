from __future__ import annotations
import threading
from pathlib import Path
from PySide6.QtCore import Qt,QThread,Signal,QUrl,QTimer
from PySide6.QtGui import QPixmap,QDesktopServices,QPalette,QColor
from PySide6.QtMultimedia import QAudioOutput,QMediaPlayer
from PySide6.QtWidgets import (QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QListWidget,QListWidgetItem,
    QSplitter,QComboBox,QDoubleSpinBox,QCheckBox,QProgressBar,QFileDialog,QMessageBox,QScrollArea,
    QStackedWidget,QPlainTextEdit,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QAbstractSpinBox,QApplication,QTabWidget)
from .catalog import BY_ID,COMMON
from .engine import Runner,Cancelled
from .session import Session
from .toolbox import import_asset,process_tool,export_result
from .ui_components import STYLE,icon,label,btn,card,ParamForm,ChainEditor,FeaturePanel,Waveform,ModelsDialog,ExportDialog,BusyIndicator,PlaybackBar


class Worker(QThread):
    progress=Signal(int,str)
    result=Signal(object)
    failed=Signal(str)
    def __init__(self,fn):
        super().__init__(); self.fn=fn; self.cancel=threading.Event()
    def run(self):
        try: self.result.emit(self.fn(Runner(self.cancel,lambda p,s:self.progress.emit(p,s))))
        except Cancelled: self.failed.emit('已取消')
        except Exception as exc: self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle('AudioWorkbench · 音频工具箱'); self.resize(1340,860); self.setMinimumSize(1100,740)
        palette=QPalette()
        for role,color in [(QPalette.Window,'#f5f7f6'),(QPalette.Base,'#ffffff'),(QPalette.AlternateBase,'#edf3ef'),(QPalette.Text,'#263b3a'),(QPalette.WindowText,'#263b3a'),(QPalette.Button,'#ffffff'),(QPalette.ButtonText,'#263b3a'),(QPalette.Highlight,'#c4dfce'),(QPalette.HighlightedText,'#164c36')]: palette.setColor(role,QColor(color))
        QApplication.instance().setPalette(palette)
        self.setStyleSheet(STYLE); self.setAcceptDrops(True); self.session=Session()
        self.asset_id=None; self.tool_id='podcast'; self.values={}; self.task=None; self.busy=False
        self.player_kind='original'; self.pending_seek=None; self._editing=False; self._range_guard=False; self._closing=False
        self.form=None; self.last_export=None; self.playing_full_source=False
        self.audio=QAudioOutput(self); self.player=QMediaPlayer(self); self.player.setAudioOutput(self.audio)
        self.player.positionChanged.connect(self.position_changed); self.player.mediaStatusChanged.connect(self.media_ready)
        self.player.durationChanged.connect(lambda _:self.position_changed(self.player.position()))
        self.player.playbackStateChanged.connect(self.play_state); self.player.errorOccurred.connect(lambda error,text:self.status.setText('播放：'+text))
        canvas=QWidget(); canvas.setObjectName('canvas'); self.setCentralWidget(canvas)
        outer=QVBoxLayout(canvas); outer.setContentsMargins(20,20,20,16); outer.setSpacing(17)
        header=QHBoxLayout(); logo=QLabel(); logo.setPixmap(icon('audio-lines',size=30).pixmap(30,30)); header.addWidget(logo)
        header.addWidget(label('AudioWorkbench','title')); header.addStretch(); header.addWidget(label('声音工具箱  /  本地处理','muted'))
        self.models_btn=btn('引擎管理',lambda:ModelsDialog(self).exec(),'package'); header.addWidget(self.models_btn); outer.addLayout(header)
        self.splitter=QSplitter(Qt.Horizontal); self.splitter.setChildrenCollapsible(False); outer.addWidget(self.splitter,1)
        sidebar,sl=card('sidebar',15); sidebar.setMinimumWidth(200); sidebar.setMaximumWidth(250); self.splitter.addWidget(sidebar)
        self.sidebar_tabs=QTabWidget(); self.sidebar_tabs.setDocumentMode(True); sl.addWidget(self.sidebar_tabs)
        material_page=QWidget(); ml=QVBoxLayout(material_page); ml.setContentsMargins(0,14,0,0); ml.setSpacing(12)
        self.sidebar_tabs.addTab(material_page,'导入素材')
        self.add_btn=btn('导入音频 / 视频',self.add_files,'plus'); ml.addWidget(self.add_btn)
        self.files=QListWidget(); self.files.setMinimumHeight(90); self.files.setDragDropMode(QAbstractItemView.InternalMove)
        self.files.currentItemChanged.connect(self.asset_changed); self.files.model().rowsMoved.connect(self.invalidate); ml.addWidget(self.files,1)
        row=QHBoxLayout(); self.file_count=label('拖入素材即可开始','muted'); row.addWidget(self.file_count); row.addStretch()
        self.remove_btn=btn('',self.remove_asset,'trash-2'); self.remove_btn.setToolTip('移除素材及临时结果'); row.addWidget(self.remove_btn); ml.addLayout(row)
        function_page=QWidget(); fl=QVBoxLayout(function_page); fl.setContentsMargins(0,14,0,0); fl.setSpacing(12)
        self.sidebar_tabs.addTab(function_page,'功能'); fl.addWidget(label('常用功能','section')); self.nav={}
        for key in COMMON:
            tool=BY_ID[key]; b=btn(tool.title,lambda checked=False,k=key:self.choose_tool(k),tool.icon); b.setObjectName('nav'); b.setCheckable(True); self.nav[key]=b; fl.addWidget(b)
        self.more_btn=btn('完整功能',self.show_features,'grid-2x2'); fl.addWidget(self.more_btn)
        self.extra_nav=btn('',self.show_features); self.extra_nav.setObjectName('nav'); self.extra_nav.hide(); fl.addWidget(self.extra_nav); fl.addStretch()
        center=QWidget(); cl=QVBoxLayout(center); cl.setContentsMargins(7,0,7,0); cl.setSpacing(12); self.splitter.addWidget(center)
        workspace,wl=card(margins=20); wl.setSpacing(8); cl.addWidget(workspace,1)
        heading=QHBoxLayout(); self.tool_title=label('','heading'); heading.addWidget(self.tool_title); heading.addStretch(); self.scope_badge=label('未导入素材','badge'); heading.addWidget(self.scope_badge); wl.addLayout(heading)
        self.description=label('','muted'); self.description.setWordWrap(True); wl.addWidget(self.description)
        line=QHBoxLayout(); self.filename=label('选择素材或拖入窗口','section'); line.addWidget(self.filename,1)
        self.undo_btn=btn('',lambda:self.history(-1),'undo-2'); self.undo_btn.setToolTip('撤销应用'); self.redo_btn=btn('',lambda:self.history(1),'redo-2'); self.redo_btn.setToolTip('重做应用'); line.addWidget(self.undo_btn); line.addWidget(self.redo_btn); wl.addLayout(line)
        self.stream=QComboBox(); self.stream.currentIndexChanged.connect(self.change_stream); wl.addWidget(self.stream); self.stream.hide()
        self.wave=Waveform(); self.wave.selected.connect(self.selected_range); self.wave.seek.connect(self.seek_original); wl.addWidget(self.wave,2)
        self.original_bar=PlaybackBar("原始 / 当前输入"); self.original_bar.seek.connect(self.seek_original); wl.addWidget(self.original_bar)
        range_row=QHBoxLayout(); self.range=QComboBox(); self.range.addItem('预览片段','selection'); self.range.addItem('完整音频','full'); self.range.currentIndexChanged.connect(self.range_changed); range_row.addWidget(self.range)
        self.start=QDoubleSpinBox(); self.end=QDoubleSpinBox()
        for box in (self.start,self.end):
            box.setRange(0,864000); box.setDecimals(2); box.setSuffix(' s'); box.setButtonSymbols(QAbstractSpinBox.UpDownArrows); box.setMinimumWidth(82); box.setMaximumWidth(110); box.valueChanged.connect(self.range_changed)
        range_row.addWidget(self.start); range_row.addWidget(label('—','muted')); range_row.addWidget(self.end); range_row.addStretch(); self.selection_hint=label('拖拽波形选择范围','muted'); range_row.addWidget(self.selection_hint); wl.addLayout(range_row)
        self.stack=QStackedWidget(); self.stack.setMinimumHeight(90); wl.addWidget(self.stack,2)
        empty=QWidget(); el=QVBoxLayout(empty); el.setAlignment(Qt.AlignCenter); image=QLabel(); image.setPixmap(icon('headphones','#a3c3af',40).pixmap(40,40)); image.setAlignment(Qt.AlignCenter); el.addWidget(image)
        text=label('先选一段试听，再处理完整音频。','muted'); text.setAlignment(Qt.AlignCenter); el.addWidget(text); self.stack.addWidget(empty)
        audio_page=QWidget(); ap=QVBoxLayout(audio_page); ap.setContentsMargins(0,0,0,0); ap.setSpacing(5)
        self.tracks=QComboBox(); self.tracks.currentIndexChanged.connect(self.track_changed); ap.addWidget(self.tracks); self.result_wave=Waveform(False); self.result_wave.seek.connect(self.seek_result); ap.addWidget(self.result_wave,1); self.stack.addWidget(audio_page)
        self.processed_bar=PlaybackBar("处理后"); self.processed_bar.seek.connect(self.seek_result); ap.addWidget(self.processed_bar)
        self.report=QPlainTextEdit(); self.report.setReadOnly(True); self.stack.addWidget(self.report)
        self.table=QTableWidget(0,3); self.table.setHorizontalHeaderLabels(['起点 / s','终点 / s','文字 / 类型']); self.table.horizontalHeader().setSectionResizeMode(2,QHeaderView.Stretch); self.table.setColumnWidth(0,85); self.table.setColumnWidth(1,85)
        self.table.cellChanged.connect(self.edit_segment); self.table.cellDoubleClicked.connect(self.seek_segment); self.stack.addWidget(self.table)
        self.spectrum=QLabel(); self.spectrum.setAlignment(Qt.AlignCenter); self.spectrum.setMinimumSize(1,1); self.stack.addWidget(self.spectrum)
        controls=QHBoxLayout(); self.play=btn('播放',self.toggle_play,'play'); controls.addWidget(self.play); self.time_label=label('00:00 / 00:00','muted'); controls.addWidget(self.time_label); controls.addStretch()
        self.original_btn=btn('原始',lambda:self.switch_audio('original')); self.processed_btn=btn('处理后',lambda:self.switch_audio('processed'))
        for b in (self.original_btn,self.processed_btn): b.setCheckable(True); controls.addWidget(b)
        wl.addLayout(controls); bottom=QHBoxLayout(); self.match=QCheckBox('A/B 音量匹配'); self.match.setChecked(True); self.match.setToolTip('按 RMS 近似匹配音量，仅影响试听'); self.match.toggled.connect(self.match_volume); bottom.addWidget(self.match); bottom.addStretch()
        self.metrics=label('','muted'); bottom.addWidget(self.metrics); wl.addLayout(bottom)
        history,hl=card(margins=12); hl.setSpacing(6); cl.addWidget(history); self.history_text=label('当前输入：原始素材','muted'); self.history_text.setWordWrap(True); hl.addWidget(self.history_text)
        actions=QHBoxLayout(); self.batch=QCheckBox('对全部素材运行'); actions.addWidget(self.batch); actions.addStretch(); self.apply_btn=btn('应用到下一步',self.apply_result,'layers'); actions.addWidget(self.apply_btn); self.run_btn=btn('运行处理',self.run_tool,'play',True); actions.addWidget(self.run_btn); hl.addLayout(actions)
        right,rl=card(margins=19); right.setMinimumWidth(260); right.setMaximumWidth(330); self.splitter.addWidget(right)
        row=QHBoxLayout(); row.addWidget(label('参数设置','section')); row.addStretch(); self.reset_btn=btn('',self.reset_params,'rotate-ccw'); self.reset_btn.setToolTip('恢复默认参数'); row.addWidget(self.reset_btn); rl.addLayout(row)
        self.engine_label=label('','muted'); self.engine_label.setWordWrap(True); rl.addWidget(self.engine_label); self.param_scroll=QScrollArea(); self.param_scroll.setWidgetResizable(True); self.param_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); rl.addWidget(self.param_scroll,1)
        self.result_state=label('暂无处理结果','muted'); self.result_state.setWordWrap(True); rl.addWidget(self.result_state); self.export_btn=btn('确认导出',self.export,'download',True); rl.addWidget(self.export_btn)
        self.open_btn=btn('打开导出位置',self.open_export,'folder-open'); self.open_btn.hide(); rl.addWidget(self.open_btn); self.splitter.setSizes([215,760,290])
        footer=QHBoxLayout(); self.busy_indicator=BusyIndicator(); footer.addWidget(self.busy_indicator); self.status=label('','muted'); footer.addWidget(self.status,1); self.cancel_btn=btn('取消',self.cancel_task,'x'); self.cancel_btn.setEnabled(False); footer.addWidget(self.cancel_btn); outer.addLayout(footer)
        self.progress=QProgressBar(); self.progress.setRange(0,100); self.progress.setValue(0); outer.addWidget(self.progress); self.choose_tool('podcast'); self.refresh_buttons()

    @property
    def asset(self): return self.session.assets.get(self.asset_id)
    def current_params(self): return self.form.values() if self.form else {}
    def selection(self): return (self.start.value(),self.end.value()) if self.range.currentData()=='selection' else None

    def choose_tool(self,key):
        if self.busy: return
        if self.form: self.values[self.tool_id]=self.form.values()
        self.tool_id=key; t=BY_ID[key]; self.tool_title.setText(t.title); self.description.setText(t.description); self.engine_label.setText('处理引擎\n'+t.engine)
        old=self.param_scroll.takeWidget()
        if old: old.deleteLater()
        self.form=ChainEditor(self.values.get(key,{}).get('steps',[])) if key=='chain' else ParamForm(key,self.values.get(key)); self.form.changed.connect(self.invalidate); self.param_scroll.setWidget(self.form)
        for k,b in self.nav.items(): b.setChecked(k==key)
        self.extra_nav.setVisible(key not in COMMON)
        if key not in COMMON: self.extra_nav.setText(t.title); self.extra_nav.setIcon(icon(t.icon)); self.extra_nav.setCheckable(True); self.extra_nav.setChecked(True)
        self.batch.setEnabled(key!='concat')
        if key=='concat': self.range.setCurrentIndex(1); self.batch.setChecked(False)
        if key=='crop': self.range.setCurrentIndex(0)
        self.show_result(); self.switch_audio('original',False); self.refresh_buttons()
    def show_features(self):
        if not hasattr(self,"feature_panel"):
            self.feature_panel=FeaturePanel(self); self.feature_panel.selected.connect(self.choose_tool)
        self.feature_panel.exec()
    def reset_params(self):
        self.values.pop(self.tool_id,None); self.form=None; self.choose_tool(self.tool_id); self.invalidate()
    def add_files(self):
        paths,_=QFileDialog.getOpenFileNames(self,'导入素材','','音频与视频 (*.wav *.mp3 *.flac *.m4a *.aac *.ogg *.opus *.aiff *.wma *.mp4 *.mov *.mkv *.avi *.webm *.m4v);;全部文件 (*)'); self.add_paths(paths)
    def add_paths(self,paths):
        if self.busy or not paths: return
        existing={str(a.source).casefold() for a in self.session.assets.values()}
        paths=list(dict.fromkeys(str(Path(p).resolve()) for p in paths if Path(p).is_file() and str(Path(p).resolve()).casefold() not in existing))
        if not paths: return
        def work(r):
            successes=[]; errors=[]
            for i,path in enumerate(paths):
                if r.cancel.is_set(): break
                r.progress(int(100*i/len(paths)),'导入 '+Path(path).name)
                try: successes.append(import_asset(self.session,path,r))
                except Cancelled: break
                except Exception as exc: errors.append(Path(path).name+': '+str(exc))
            return successes,errors
        def done(payload):
            assets,errors=payload
            for a in assets:
                item=QListWidgetItem(icon('file-audio'),a.source.name); item.setData(Qt.UserRole,a.id); item.setToolTip(str(a.source)); self.files.addItem(item)
            self.file_count.setText(f'{self.files.count()} 个素材')
            if self.files.currentRow()<0 and self.files.count(): self.files.setCurrentRow(0)
            if errors: self.error('\n\n'.join(errors))
        self.launch(work,done)
    def asset_changed(self,item,previous=None):
        self.release_player(); self.asset_id=item.data(Qt.UserRole) if item else None; a=self.asset
        self.filename.setText(a.source.name if a else '选择素材或拖入窗口'); self.filename.setToolTip(str(a.source) if a else '')
        self.stream.blockSignals(True); self.stream.clear()
        if a:
            for i,s in enumerate(a.streams): self.stream.addItem(f'音轨 {i+1} · '+s.split('Audio:')[-1][:70],i)
            self.stream.setCurrentIndex(a.stream)
        self.stream.setVisible(bool(a and len(a.streams)>1)); self.stream.blockSignals(False); self.update_input()
        if a and a.result and a.result.tool_id==self.tool_id:
            self._range_guard=True; self.range.setCurrentIndex(0 if a.result.selection else 1)
            if a.result.selection: self.start.setValue(a.result.selection[0]); self.end.setValue(a.result.selection[1])
            self._range_guard=False; self.range_changed()
        self.show_result(); self.switch_audio('original',False); self.refresh_buttons()
    def update_input(self):
        self._range_guard=True; a=self.asset; info=a.current.info if a else {}; self.wave.set_audio(info); self.original_bar.update_position(0,info.get("seconds",0))
        self.start.setMaximum(info.get('seconds',864000)); self.end.setMaximum(info.get('seconds',864000)); self.start.setValue(0); self.end.setValue(min(15,info.get('seconds',0)))
        self._range_guard=False; self.range_changed(); self.history_text.setText('当前输入：'+' → '.join(v.title for v in a.versions[:a.index+1]) if a else '当前输入：原始素材')
    def change_stream(self,index):
        a=self.asset
        if not a or self.busy or index<0 or index==a.stream: return
        if a.dirty and QMessageBox.question(self,'切换音轨','切换会丢弃此素材未导出的结果。继续？')!=QMessageBox.Yes:
            self.stream.blockSignals(True); self.stream.setCurrentIndex(a.stream); self.stream.blockSignals(False); return
        row=self.files.currentRow(); self.release_player()
        def done(new):
            self.session.remove(a.id); self.files.item(row).setData(Qt.UserRole,new.id); self.asset_changed(self.files.item(row))
        self.launch(lambda r:import_asset(self.session,a.source,r,index),done)
    def selected_range(self,a,b):
        self._range_guard=True; self.range.setCurrentIndex(0); self.start.setValue(a); self.end.setValue(b); self._range_guard=False; self.range_changed()
    def range_changed(self,*args):
        if self._range_guard: return
        selection=self.range.currentData()=='selection'; self.start.setEnabled(selection and not self.busy); self.end.setEnabled(selection and not self.busy)
        self.wave.a=self.start.value() if selection else 0; self.wave.b=self.end.value() if selection else 0; self.wave.update(); self.scope_badge.setText('片段预览' if selection else '完整音频'); self.invalidate()
    def invalidate(self,*args):
        if self.busy: return
        if self.asset and self.asset.result and self.asset.result.tool_id==self.tool_id: self.result_state.setText('参数 / 范围已改变，请重新运行。')
        self.refresh_buttons()
    def result_current(self):
        a=self.asset; r=a.result if a else None
        return bool(r and r.tool_id==self.tool_id and r.params==self.current_params() and r.selection==self.selection())
    def refresh_buttons(self):
        a=self.asset; valid=self.result_current() if self.form else False; r=a.result if a else None
        self.original_bar.setEnabled(bool(a) and not self.busy); self.processed_bar.setEnabled(bool(r and r.tracks and r.tool_id==self.tool_id) and not self.busy)
        self.run_btn.setEnabled(bool(a) and not self.busy); self.export_btn.setEnabled(valid and not self.busy); self.apply_btn.setEnabled(valid and bool(r.tracks if r else None) and not self.busy)
        self.original_btn.setEnabled(bool(a) and not self.busy); self.processed_btn.setEnabled(bool(r and r.tracks and r.tool_id==self.tool_id) and not self.busy)
        self.undo_btn.setEnabled(bool(a and a.index>0) and not self.busy); self.redo_btn.setEnabled(bool(a and a.index<len(a.versions)-1) and not self.busy); self.remove_btn.setEnabled(bool(a) and not self.busy); self.play.setEnabled(bool(a) and not self.busy)
    def run_tool(self):
        if self.busy or not self.asset: return
        selection=self.selection(); key=self.tool_id; params=self.current_params()
        if selection and selection[1]<=selection[0]: self.error('请选择有效的起止时间。'); return
        entries=[self.session.assets[self.files.item(i).data(Qt.UserRole)] for i in range(self.files.count())]
        targets=entries if self.batch.isChecked() and key!='concat' else [self.asset]; self.release_player()
        for a in targets: a.result=None
        self.show_result()
        def work(r):
            results=[]; errors=[]
            for i,a in enumerate(targets):
                if r.cancel.is_set(): break
                sub=Runner(r.cancel,lambda p,s,i=i:r.progress(int((100*i+p)/len(targets)),f'{i+1}/{len(targets)} · {s}'))
                try: results.append((a.id,process_tool(a,key,params,sub,selection,entries)))
                except Cancelled: break
                except Exception as exc: errors.append(a.source.name+': '+str(exc))
            return results,errors
        def done(payload):
            results,errors=payload
            for aid,result in results: self.session.assets[aid].result=result; self.session.assets[aid].dirty=True
            self.show_result(); self.switch_audio('processed' if self.asset and self.asset.result and self.asset.result.tracks else 'original',False)
            if errors: self.error('\n\n'.join(errors))
        self.launch(work,done)
    def show_result(self):
        a=self.asset; r=a.result if a else None; self.metrics.setText(''); self.result_state.setText('暂无处理结果'); self.tracks.blockSignals(True); self.tracks.clear()
        if not r or r.tool_id!=self.tool_id: self.stack.setCurrentIndex(0); self.tracks.blockSignals(False); self.refresh_buttons(); return
        scope=f'{r.selection[0]:.2f}–{r.selection[1]:.2f} 秒' if r.selection else '完整音频'; self.result_state.setText(('已导出' if r.exported else '临时结果 · 尚未导出')+'\n'+scope)
        if r.tracks:
            for name in r.tracks: self.tracks.addItem(name,name)
            self.stack.setCurrentIndex(1); self.tracks.blockSignals(False); self.track_changed()
        elif r.image: self.stack.setCurrentIndex(4); self.spectrum.setPixmap(QPixmap(str(r.image)).scaled(700,300,Qt.KeepAspectRatio,Qt.SmoothTransformation))
        elif 'segments' in r.data:
            self._editing=True; segments=r.data['segments']; self.table.setRowCount(len(segments)); editable=r.tool_id=='transcribe'
            self.table.setEditTriggers(QAbstractItemView.DoubleClicked|QAbstractItemView.EditKeyPressed if editable else QAbstractItemView.NoEditTriggers)
            for row,s in enumerate(segments):
                for col,value in enumerate((f'{s["start"]:.3f}',f'{s["end"]:.3f}',s.get('text','语音' if r.tool_id=='vad' else '静音'))): self.table.setItem(row,col,QTableWidgetItem(value))
            self._editing=False; self.stack.setCurrentIndex(3); self.result_state.setText(self.result_state.text()+f'\n{len(segments)} 个区间 · 从当前结果 0 秒起算')
        else:
            m=r.data.get('loudness',{}); b=r.before
            text=f'音频长度   {b["seconds"]:.2f} s\n采样率       {b["sample_rate"]} Hz\n声道数       {b["channels"]}\n采样峰值   {b["peak_dbfs"]} dBFS\nRMS             {b["rms_dbfs"]} dBFS\n低音量占比 {b["silence_percent"]}%\n'
            if m: text+=f'\n整体响度   {m["input_i"]} LUFS\n真峰值       {m["input_tp"]} dBTP\n响度范围   {m["input_lra"]} LU\n削波采样   {r.data["clipped_samples"]} ({r.data["clipped_percent"]}%)'
            self.report.setPlainText(text); self.stack.setCurrentIndex(2)
        self.tracks.blockSignals(False); self.refresh_buttons()
    def track_changed(self,*args):
        a=self.asset; r=a.result if a else None
        if not r or self.tracks.currentData() not in r.after: return
        info=r.after[self.tracks.currentData()]; self.result_wave.set_audio(info); self.processed_bar.update_position(0,info["seconds"]); self.metrics.setText(f'{info["seconds"]:.2f} s  ·  峰值 {info["peak_dbfs"]:.1f} dBFS')
        if self.player_kind=='processed': self.switch_audio('processed',False)
    def edit_segment(self,row,col):
        if self._editing or not self.asset or not self.asset.result: return
        r=self.asset.result
        if r.tool_id!='transcribe': return
        try:
            import math
            start=float(self.table.item(row,0).text()); end=float(self.table.item(row,1).text())
            if not all(math.isfinite(v) for v in (start,end)) or start<0 or end<=start or end>r.before['seconds']+.5: raise ValueError()
            r.data['segments'][row]={'start':start,'end':end,'text':self.table.item(row,2).text()}; r.exported=False; self.asset.dirty=True; self.result_state.setText('字幕已编辑 · 尚未导出')
        except ValueError: self.error('时间戳须满足 0 ≤ 起点 < 终点，且不超出当前片段。'); self.show_result()
    def seek_segment(self,row,col):
        if not self.asset or not self.asset.result: return
        r=self.asset.result; self.switch_audio('original',False); self.pending_seek=(int(r.data['segments'][row]['start']*1000),True)
        if self.player.mediaStatus() in (QMediaPlayer.LoadedMedia,QMediaPlayer.BufferedMedia): self.media_ready(self.player.mediaStatus())
    def apply_result(self):
        a=self.asset
        if not a or not self.result_current(): return
        r=a.result; track=self.tracks.currentData()
        if track not in r.tracks: return
        if r.selection and QMessageBox.question(self,'应用预览片段','应用后，下一步将只处理当前预览片段。继续？')!=QMessageBox.Yes: return
        self.release_player(); a.apply(r.tracks[track],BY_ID[r.tool_id].title,r.after[track],r.time_changed or bool(r.selection)); a.result=None; self.update_input(); self.show_result(); self.switch_audio('original',False); self.refresh_buttons()
    def history(self,delta):
        a=self.asset
        if not a or not 0<=a.index+delta<len(a.versions): return
        self.release_player(); a.index+=delta; a.result=None; a.dirty=True; self.update_input(); self.show_result(); self.switch_audio('original',False); self.refresh_buttons()
    def export(self):
        a=self.asset
        if not a or not self.result_current() or self.busy: return
        r=a.result; dialog=ExportDialog(a,r,self)
        if not dialog.exec(): return
        fmt=dialog.format.currentData(); suffix='_片段' if r.selection else ''; filename=a.source.stem+'_'+BY_ID[r.tool_id].title+suffix+'.'+fmt
        destination,_=QFileDialog.getSaveFileName(self,'保存已确认的结果',str(a.source.parent/filename),f'{fmt.upper()} (*.{fmt})',options=QFileDialog.DontConfirmOverwrite)
        if not destination: return
        if Path(destination).suffix.lower()!='.'+fmt: destination+='.'+fmt
        overwrite=Path(destination).exists()
        if overwrite and QMessageBox.question(self,'确认覆盖',f'将替换已有文件：\n{Path(destination).name}\n继续？')!=QMessageBox.Yes: return
        track=dialog.track.currentData(); rate=dialog.rate.currentData(); depth=dialog.depth.currentData()
        def done(path):
            a.dirty=not r.exported; self.last_export=Path(path); self.open_btn.show(); self.show_result(); self.status.setText('已导出：'+str(path))
        self.launch(lambda r:export_result(a,a.result,destination,fmt,r,track,rate,depth,overwrite),done)
    def open_export(self):
        if self.last_export: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_export.parent)))
    def remove_asset(self):
        a=self.asset
        if not a or self.busy: return
        if a.dirty and QMessageBox.question(self,'移除素材','此素材还有未导出的结果。丢弃并移除？')!=QMessageBox.Yes: return
        self.release_player(); row=self.files.currentRow(); self.files.takeItem(row); self.session.remove(a.id); self.file_count.setText(f'{self.files.count()} 个素材'); self.refresh_buttons()
    def release_player(self): self.player.stop(); self.player.setSource(QUrl()); self.pending_seek=None
    def switch_audio(self,kind,preserve=True):
        a=self.asset
        if not a: self.release_player(); return
        r=a.result if a.result and a.result.tool_id==self.tool_id else None
        if kind=='processed' and (not r or not r.tracks): return
        path=r.tracks.get(self.tracks.currentData()) if kind=='processed' else r.original if r else a.current.path
        if not path: return
        playing=self.player.playbackState()==QMediaPlayer.PlayingState; pos=self.player.position() if preserve else 0
        if self.playing_full_source and r and r.selection: pos=max(0,pos-int(r.selection[0]*1000))
        self.playing_full_source=not bool(r); self.player_kind=kind; self.original_btn.setChecked(kind=='original'); self.processed_btn.setChecked(kind=='processed')
        self.pending_seek=(pos,playing); self.player.setSource(QUrl.fromLocalFile(str(path))); self.match_volume()
    def media_ready(self,status):
        if status in (QMediaPlayer.LoadedMedia,QMediaPlayer.BufferedMedia) and self.pending_seek:
            pos,playing=self.pending_seek; self.pending_seek=None; self.player.setPosition(min(pos,self.player.duration()))
            if playing: self.player.play()
    def match_volume(self):
        gain=1.; a=self.asset; r=a.result if a else None
        if self.match.isChecked() and r and self.tracks.currentData() in r.after:
            before=r.before['rms_dbfs']; after=r.after[self.tracks.currentData()]['rms_dbfs']; current=before if self.player_kind=='original' else after; gain=10**((min(before,after)-current)/20)
        self.audio.setVolume(max(0.,min(1.,gain)))
    def toggle_play(self):
        if self.player.playbackState()==QMediaPlayer.PlayingState: self.player.pause()
        else:
            if self.player.source().isEmpty(): self.switch_audio('original',False)
            self.player.play()
    def play_state(self,state):
        playing=state==QMediaPlayer.PlayingState; self.play.setText('暂停' if playing else '播放'); self.play.setIcon(icon('pause' if playing else 'play',size=18))
    def position_changed(self,pos):
        duration=self.player.duration(); a=self.asset; r=a.result if a and a.result and a.result.tool_id==self.tool_id else None
        offset=r.selection[0] if r and r.selection and not self.playing_full_source else 0
        if self.player_kind=='original':
            self.wave.cursor=(pos/1000+offset)/max(self.wave.duration,.001); self.wave.update()
        else:
            self.result_wave.cursor=pos/max(duration,1); self.result_wave.update()
        def fmt(ms):
            s=int(ms/1000); return f'{s//60:02d}:{s%60:02d}'
        self.time_label.setText(f'{fmt(pos)} / {fmt(duration)}')
        if self.player_kind=='original': self.original_bar.update_position(pos/1000+offset,self.wave.duration)
        else: self.processed_bar.update_position(pos/1000,self.result_wave.duration)
    def seek_path(self,path,position,kind,full=False):
        if self.busy: return
        playing=self.player.playbackState()==QMediaPlayer.PlayingState
        self.player_kind=kind; self.playing_full_source=full
        self.original_btn.setChecked(kind=='original'); self.processed_btn.setChecked(kind=='processed')
        self.pending_seek=(position,playing)
        url=QUrl.fromLocalFile(str(path))
        if self.player.source()!=url: self.player.setSource(url)
        if self.player.mediaStatus() in (QMediaPlayer.LoadedMedia,QMediaPlayer.BufferedMedia,QMediaPlayer.EndOfMedia): self.media_ready(QMediaPlayer.LoadedMedia)
        self.match_volume()
    def seek_original(self,ratio):
        if self.asset: self.seek_path(self.asset.current.path,int(ratio*self.wave.duration*1000),'original',True)
    def seek_result(self,ratio):
        r=self.asset.result if self.asset else None
        if r and r.tool_id==self.tool_id and self.tracks.currentData() in r.tracks:
            self.seek_path(r.tracks[self.tracks.currentData()],int(ratio*self.result_wave.duration*1000),'processed')
    def launch(self,fn,done):
        self.set_busy(True); self.progress.setValue(0); self.status.setText('正在处理…'); self.task=Worker(fn)
        self.task.progress.connect(self.on_progress); self.task.result.connect(done); self.task.failed.connect(self.error); self.task.finished.connect(self.finished); self.task.start()
    def on_progress(self,p,text): self.progress.setValue(p); self.status.setText(text)
    def set_busy(self,value):
        self.busy=value; self.busy_indicator.set_running(value)
        if value: self.player.pause()
        for w in (self.files,self.add_btn,self.more_btn,self.extra_nav,self.models_btn,self.param_scroll,self.reset_btn,self.range,self.stream,self.table): w.setEnabled(not value)
        for b in self.nav.values(): b.setEnabled(not value)
        self.batch.setEnabled(not value and self.tool_id!='concat'); self.cancel_btn.setEnabled(value); self.start.setEnabled(not value and self.range.currentData()=='selection'); self.end.setEnabled(not value and self.range.currentData()=='selection'); self.wave.setEnabled(not value); self.refresh_buttons()
    def finished(self):
        cancelled=self.task.cancel.is_set(); self.set_busy(False)
        if cancelled: self.status.setText('已取消 · 未导出文件')
        elif self.progress.value()==100: self.status.setText('临时结果已就绪 · 确认导出后才保存')
        if self._closing: QTimer.singleShot(0,self.close)
    def cancel_task(self):
        if self.task and self.task.isRunning(): self.task.cancel.set(); self.status.setText('正在取消，等待当前步骤结束…'); self.cancel_btn.setEnabled(False)
    def error(self,message):
        self.status.setText(message.splitlines()[0][:130])
        if message=='已取消': return
        box=QMessageBox(self); box.setWindowTitle('处理提示'); box.setIcon(QMessageBox.Warning); box.setText(message.splitlines()[0][:220]); box.setDetailedText(message); box.exec()
    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls() and not self.busy: event.acceptProposedAction()
    def dropEvent(self,event): self.add_paths([u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()])
    def closeEvent(self,event):
        if self.busy:
            if QMessageBox.question(self,'任务正在运行','取消当前任务并关闭？')==QMessageBox.Yes: self._closing=True; self.cancel_task()
            event.ignore(); return
        if any(a.dirty for a in self.session.assets.values()) and not self._closing:
            box=QMessageBox(self); box.setWindowTitle('还有未导出的结果'); box.setText('关闭将清除本次会话的临时音频和编辑。')
            back=box.addButton('返回工作区',QMessageBox.RejectRole); discard=box.addButton('丢弃并退出',QMessageBox.DestructiveRole); box.setDefaultButton(back); box.exec()
            if box.clickedButton()!=discard: event.ignore(); return
        self.release_player(); self.session.close(); event.accept()
