from __future__ import annotations
import hashlib
import json
import math
import os
import re
import shutil
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import soundfile as sf

from .catalog import BY_ID, validate
from .engine import ROOT, FFMPEG, VIDEO, Runner, Settings, analyze, spectral, ai_process, available, engine_python
from .session import Asset, AudioVersion


@dataclass
class Result:
    tool_id: str
    folder: Path
    original: Path
    tracks: dict
    before: dict
    after: dict
    params: dict
    selection: tuple | None = None
    time_changed: bool = False
    data: dict = field(default_factory=dict)
    image: Path | None = None
    exported: bool = False
    exported_tracks: set = field(default_factory=set)


def read_streams(source, runner):
    log = runner.ff(['-i', source, '-map', '0:a', '-t', '0', '-f', 'null', '-'])
    log = log.split('Output #')[0]
    streams = []
    for line in log.splitlines():
        if re.search(r'Stream #0:\d+.*Audio:', line): streams.append(line.strip())
    if not streams: raise ValueError('文件中没有可读取的音轨。')
    return streams


def decode_audio(source, target, runner, stream=0, selection=None):
    args = []
    if selection:
        start, end = selection
        if start < 0 or end <= start: raise ValueError('片段起止时间无效。')
        args += ['-ss', str(start)]
    args += ['-i', source]
    if selection: args += ['-t', str(end-start)]
    runner.ff([*args, '-map', f'0:a:{stream}', '-vn', '-ar', '48000', '-ac', '2', '-c:a', 'pcm_f32le', target])
    info = analyze(target)
    if info['seconds'] < .02: raise ValueError('该范围没有足够的音频。')
    return info


def import_asset(session, source, runner, stream=0):
    source = Path(source).resolve()
    if not source.is_file(): raise ValueError('素材文件不存在。')
    folder = session.new_folder('asset')
    try:
        streams = read_streams(source, runner)
        if not 0 <= stream < len(streams): raise ValueError('音轨索引不存在。')
        dest = folder / 'input.wav'
        info = decode_audio(source, dest, runner, stream)
        asset = Asset(folder.name, source, folder, streams, [AudioVersion(dest, '原始素材', info)], stream=stream)
        session.assets[asset.id] = asset
        return asset
    except Exception:
        shutil.rmtree(folder, ignore_errors=True); raise


def measure_loudness(path, runner):
    log = runner.ff(['-i', path, '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json', '-f', 'null', '-'])
    matches = re.findall(r'\{\s*"input_i".*?\}', log, re.S)
    if not matches: raise RuntimeError('未获得响度测量结果。')
    return json.loads(matches[-1])


def normalize(path, dest, lufs, peak, runner):
    m = measure_loudness(path, runner)
    if not all(math.isfinite(float(m[k])) for k in ('input_i','input_tp','input_lra','input_thresh','target_offset')):
        shutil.copyfile(path, dest); return
    # target_offset depends on target. Re-measure using the actual requested target.
    log = runner.ff(['-i', path, '-af', f'loudnorm=I={lufs}:TP={peak}:LRA=11:print_format=json', '-f', 'null', '-'])
    m = json.loads(re.findall(r'\{\s*"input_i".*?\}', log, re.S)[-1])
    filt = (f'loudnorm=I={lufs}:TP={peak}:LRA=11:linear=true:measured_I={m["input_i"]}:'
            f'measured_TP={m["input_tp"]}:measured_LRA={m["input_lra"]}:measured_thresh={m["input_thresh"]}:offset={m["target_offset"]}')
    filter_audio(path, dest, filt, runner)


def filter_audio(source, dest, filters, runner):
    runner.ff(['-i', source, '-af', filters, '-ar', '48000', '-c:a', 'pcm_f32le', dest])


def silence_intervals(path, runner, threshold=-40, minimum=.4):
    log = runner.ff(['-i', path, '-af', f'silencedetect=noise={threshold}dB:d={minimum}', '-f', 'null', '-'])
    intervals = []; start = None
    for match in re.finditer(r'silence_(start|end):\s*([\d.eE+-]+)', log):
        if match[1] == 'start': start = float(match[2])
        elif start is not None: intervals.append({'start': start, 'end': float(match[2])}); start = None
    if start is not None: intervals.append({'start': start, 'end': sf.info(path).duration})
    return intervals


def copy_regions(source, dest, regions, runner):
    with sf.SoundFile(source) as src, sf.SoundFile(dest, 'w', samplerate=src.samplerate, channels=src.channels, subtype='FLOAT') as out:
        for a, b in regions:
            first, last = round(a*src.samplerate), min(len(src), round(b*src.samplerate))
            src.seek(first)
            remaining = last-first
            while remaining > 0:
                runner.check(); x = src.read(min(remaining, 48000*5), always_2d=True, dtype='float32')
                out.write(x); remaining -= len(x)


def run_ai(kind, source, folder, params, runner):
    env = 'separator' if kind in ('vocals','stems','dereverb') else 'speech'
    if not available(env): raise RuntimeError(f'请先在「引擎管理」安装 {env}。')
    binary = ROOT / 'bin' / ('ffmpeg.exe' if os.name == 'nt' else 'ffmpeg')
    if not binary.exists(): binary.parent.mkdir(exist_ok=True); shutil.copyfile(FFMPEG, binary)
    config = folder / 'request.json'; config.write_text(json.dumps(params), encoding='utf-8')
    manifest = folder / 'manifest.json'
    runner.run([engine_python(env), ROOT / 'audioworkbench' / 'tool_worker.py', kind, source, folder, config], folder / 'engine.log')
    if not manifest.exists(): raise RuntimeError('引擎未生成结果清单。')
    return json.loads(manifest.read_text(encoding='utf-8'))


def db(value): return 10 ** (value / 20)


def dsp_filter(tool_id, p, duration):
    filters = {
        'hum': lambda: ','.join(f'bandreject=f={p["frequency"]*i}:t=q:w={p["q"]}' for i in range(1, int(p['harmonics'])+1)),
        'rumble': lambda: f'highpass=f={p["cutoff"]}:p=2',
        'declick': lambda: f'adeclick=t={p["threshold"]}',
        'declip': lambda: f'adeclip=t={p["threshold"]}',
        'dc': lambda: 'highpass=f=10:p=2',
        'eq': lambda: ','.join(f'equalizer=f={p[k+"_hz"]}:t=q:w=0.8:g={p[k+"_gain"]}' for k in ('low','mid','high')),
        'filters': lambda: f'highpass=f={p["highpass"]},lowpass=f={p["lowpass"]}',
        'deess': lambda: f'deesser=i={p["amount"]/100}',
        'compress': lambda: f'acompressor=threshold={db(p["threshold"])}:ratio={p["ratio"]}:attack={p["attack"]}:release={p["release"]}:makeup={db(p["makeup"])}',
        'limit': lambda: f'alimiter=limit={db(p["ceiling"])}:level=false:latency=true',
        'gate': lambda: f'agate=threshold={db(p["threshold"])}:ratio={p["ratio"]}:release={p["release"]}',
        'gain': lambda: f'volume={p["gain"]}dB' + (',alimiter=limit=0.891250938:level=false:latency=true' if p['protect'] else ''),
        'stereo': lambda: f'stereotools=slev={p["width"]/100}:balance_out={p["balance"]/100}',
        'fade': lambda: f'afade=t=in:d={min(p["fade_in"],duration):.6f},afade=t=out:st={max(0,duration-p["fade_out"]):.6f}:d={min(p["fade_out"],duration):.6f}',
        'trim': lambda: f'silenceremove=start_periods=1:start_duration=0.05:start_threshold={p["threshold"]}dB,areverse,silenceremove=start_periods=1:start_duration=0.05:start_threshold={p["threshold"]}dB,areverse',
        'speed': lambda: f'rubberband=tempo={p["speed"]}',
        'pitch': lambda: f'rubberband=pitch={2**(p["semitones"]/12)}',
        'reverse': lambda: 'areverse',
        'channels': lambda: {'mono':'pan=mono|c0=0.5*c0+0.5*c1', 'left':'pan=mono|c0=c0', 'right':'pan=mono|c0=c1', 'swap':'pan=stereo|c0=c1|c1=c0', 'invert':'pan=stereo|c0=c0|c1=-1*c1'}[p['mode']],
    }
    return filters[tool_id]() if tool_id in filters else None


def process_tool(asset, tool_id, params, runner=None, selection=None, assets=None, input_path=None, depth=0):
    runner = runner or Runner(); runner.check()
    if depth > 1: raise ValueError('处理链不允许嵌套。')
    p = validate(tool_id, params); tool = BY_ID[tool_id]
    source = Path(input_path or asset.current.path)
    stat=source.stat()
    identity={'path':str(source),'size':stat.st_size,'mtime':stat.st_mtime_ns,'tool':tool_id,'params':p,
              'selection':selection,'time_changed':asset.current.time_changed,'revision':2}
    if tool_id=='concat': identity['sources']=[str(a.current.path) for a in (assets or [asset])]
    cache_key=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
    cached=asset.cache.get(cache_key)
    if cached and cached.original.exists() and all(path.exists() for path in cached.tracks.values()):
        runner.progress(100,'已复用本次会话的临时结果')
        return cached
    folder = asset.folder / ('result-' + uuid.uuid4().hex); folder.mkdir()
    try:
        duration = sf.info(source).duration
        if selection:
            start, end = selection
            if start < 0 or end <= start or end > duration+.05: raise ValueError('选区超出当前音频范围。')
        original = folder / 'original.wav'
        runner.progress(5, '准备临时音频')
        before = decode_audio(source, original, runner, selection=selection)
        dest = folder / 'processed.wav'; tracks = {}; data = {}; image = None
        changed = tool.changes_time or asset.current.time_changed
        filt = dsp_filter(tool_id, p, before['seconds'])
        runner.progress(20, tool.title)
        if filt:
            if tool_id == 'filters' and p['highpass'] >= p['lowpass']: raise ValueError('高通截止必须低于低通截止。')
            filter_audio(original, dest, filt, runner)
        elif tool_id in ('convert','extract','crop'):
            shutil.copyfile(original, dest)
        elif tool_id in ('denoise','podcast'):
            current = original
            if p.get('dereverb'):
                m = run_ai('dereverb', current, folder, {'model':'Reverb_HQ_By_FoxJoy.onnx','device':'cpu'}, runner)
                current = Path(next(iter(m['tracks'].values())))
            clean = folder / 'clean.wav'
            if p['engine'] == 'deepfilter': ai_process('deepfilter', current, clean, Settings(strength=p['strength']/100), runner)
            else: spectral(current, clean, p['strength']/100, runner)
            if tool_id == 'podcast':
                current = clean
                if p['polish']:
                    current = folder / 'polished.wav'
                    filter_audio(clean, current, 'highpass=f=70,equalizer=f=3000:t=q:w=0.8:g=1.5,deesser=i=0.15,acompressor=threshold=0.125:ratio=2:attack=15:release=150', runner)
                normalize(current, dest, p['lufs'], -1.5, runner)
            else: shutil.copyfile(clean, dest)
        elif tool_id == 'loudness': normalize(original, dest, p['lufs'], p['peak'], runner)
        elif tool_id in ('vocals','stems','dereverb'):
            manifest = run_ai(tool_id, original, folder, p, runner)
            tracks = {k: Path(v) for k,v in manifest['tracks'].items()}
            if not tracks: raise RuntimeError('分离引擎没有返回音轨。')
        elif tool_id == 'split':
            if math.ceil(before['seconds']/p['seconds']) > 1000: raise ValueError('分段数量超过 1000，请增加每段时长。')
            for i, start in enumerate(np.arange(0, before['seconds'], p['seconds'])):
                runner.check(); part = folder / f'part-{i+1:03d}.wav'
                copy_regions(original, part, [(float(start), min(float(start+p['seconds']),before['seconds']))], runner)
                tracks[f'片段 {i+1:03d}'] = part
        elif tool_id == 'concat':
            if selection: raise ValueError('音频拼接请使用完整音频模式。')
            entries = assets or [asset]
            if len(entries) < 2: raise ValueError('拼接至少需要两个素材，按左侧顺序处理。')
            with sf.SoundFile(dest, 'w', samplerate=48000, channels=2, subtype='FLOAT') as out:
                for i, a in enumerate(entries):
                    normalized = folder / f'concat-{i}.wav'
                    decode_audio(a.current.path, normalized, runner)
                    if i and p['gap']: out.write(np.zeros((round(48000*p['gap']),2), dtype='float32'))
                    for x in sf.blocks(normalized, blocksize=48000*5, always_2d=True, dtype='float32'):
                        runner.check(); out.write(x)
        elif tool_id == 'pauses':
            if p['keep'] >= p['minimum']: raise ValueError('保留长度必须短于长停顿阈值。')
            intervals = silence_intervals(original, runner, p['threshold'], p['minimum'])
            cursor = 0.; regions = []
            for seg in intervals:
                middle = seg['start'] + p['keep']/2
                regions.append((cursor, middle)); cursor = max(middle, seg['end']-p['keep']/2)
            regions.append((cursor, before['seconds']))
            copy_regions(original, dest, regions, runner); data['removed_pauses'] = intervals
        elif tool_id == 'analysis':
            data['loudness'] = measure_loudness(original, runner)
            clipped = 0; samples = 0
            for x in sf.blocks(original, blocksize=480000, dtype='float32'):
                runner.check(); clipped += int(np.count_nonzero(np.abs(x) >= .999)); samples += x.size
            data['clipped_samples'] = clipped; data['clipped_percent'] = round(100*clipped/max(samples,1),4)
        elif tool_id == 'spectrum':
            image = folder / 'spectrum.png'
            runner.ff(['-i', original, '-lavfi', 'showspectrumpic=s=1400x600:legend=1:scale=log:color=viridis', '-frames:v','1',image])
        elif tool_id == 'silence': data['segments'] = silence_intervals(original, runner, p['threshold'], p['minimum'])
        elif tool_id in ('vad','transcribe'):
            data = run_ai(tool_id, original, folder, p, runner)
        elif tool_id == 'chain':
            steps = p.get('steps', [])
            if not steps: raise ValueError('请先添加处理步骤。')
            if len(steps)>16: raise ValueError('最多支持 16 个步骤。')
            current = original; data['steps'] = []
            for i, step in enumerate(steps):
                key = step['tool']
                if key not in CHAIN_TOOLS: raise ValueError('该功能不能用于单轨处理链。')
                runner.progress(int(15+70*i/len(steps)), f'{i+1}/{len(steps)} · {BY_ID[key].title}')
                result = process_tool(asset,key,step['params'],runner,input_path=current,depth=depth+1)
                current = next(iter(result.tracks.values())); changed |= result.time_changed
                data['steps'].append({'tool':key,'params':step['params']})
            shutil.copyfile(current,dest)
        else: raise ValueError('未实现的工具：' + tool_id)
        runner.check()
        if not tracks and not tool.analysis: tracks['处理结果'] = dest
        after = {}
        for name, path in tracks.items():
            info = analyze(path)
            if info['seconds'] < .02: raise ValueError('处理后没有剩余音频，请降低裁剪强度。')
            if not tool.changes_time and tool_id != 'chain' and abs(info['seconds']-before['seconds'])>.1:
                raise ValueError('处理时长出现异常变化，已拒绝结果。')
            after[name] = info
        runner.progress(100, '临时结果已就绪，尚未导出')
        result=Result(tool_id,folder,original,tracks,before,after,p,selection,changed,data,image)
        if not tool.analysis: asset.cache[cache_key]=result
        return result
    except Exception:
        # Failed processing is never a persistent output. Keep nothing outside this session.
        shutil.rmtree(folder,ignore_errors=True); raise


CHAIN_TOOLS = [k for k,t in BY_ID.items() if not t.analysis and k not in ('chain','vocals','stems','split','concat','crop','extract','convert')]


def subtitle_text(segments, fmt):
    if fmt == 'txt': return '\n'.join(s['text'] for s in segments)
    def timestamp(s):
        ms = round(s*1000); seconds, ms = divmod(ms,1000); minutes, seconds = divmod(seconds,60); hours,minutes=divmod(minutes,60)
        return f'{hours:02}:{minutes:02}:{seconds:02},{ms:03}'
    lines = []
    for i, seg in enumerate(segments):
        if not math.isfinite(float(seg['start'])) or not math.isfinite(float(seg['end'])) or seg['start'] < 0 or seg['end'] <= seg['start']:
            raise ValueError(f'第 {i+1} 行时间戳无效。')
        lines.append(f'{i+1}\n{timestamp(seg["start"])} --> {timestamp(seg["end"])}\n{seg["text"].strip()}\n')
    return '\n'.join(lines)


def export_result(asset, result, destination, fmt, runner=None, track=None, sample_rate=48000, bit_depth=24, overwrite=False):
    """Explicit user action only. Atomic single-file commit, including multi-track ZIP."""
    runner = runner or Runner(); destination = Path(destination).resolve()
    if destination == asset.source.resolve(): raise ValueError('不能覆盖原始素材。')
    if destination.exists() and not overwrite: raise FileExistsError('目标文件已存在。')
    if sample_rate not in (16000,22050,44100,48000,96000) or bit_depth not in (16,24,32): raise ValueError('导出采样参数无效。')
    if not destination.parent.is_dir(): raise ValueError('导出目录不存在。')
    temporary = destination.parent / ('.awb-export-' + uuid.uuid4().hex + '.' + fmt)
    try:
        if fmt in ('srt','txt'):
            if result.tool_id != 'transcribe': raise ValueError('当前结果不是转写。')
            temporary.write_text(subtitle_text(result.data['segments'],fmt),encoding='utf-8-sig')
        elif fmt == 'json':
            payload = {'tool':result.tool_id,'source':str(asset.source),'selection':result.selection,'params':result.params,
                       'before':{k:v for k,v in result.before.items() if k!='envelope'},'data':result.data}
            temporary.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
        elif fmt == 'png':
            if not result.image: raise ValueError('没有频谱图。')
            shutil.copyfile(result.image,temporary)
        elif fmt == 'zip':
            if not result.tracks: raise ValueError('没有可导出的音轨。')
            with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED) as archive:
                for i,(name,path) in enumerate(result.tracks.items()):
                    runner.check()
                    encoded = result.folder / f'export-{i}.wav'
                    runner.ff(['-i',path,'-ar',str(sample_rate),'-c:a',f'pcm_s{bit_depth}le' if bit_depth!=32 else 'pcm_f32le',encoded])
                    safe = re.sub(r'[<>:"/\\|?*]','_',name)
                    archive.write(encoded,f'{i+1:02d}-{safe}.wav'); encoded.unlink()
        elif fmt == 'mkv':
            if result.selection or result.time_changed: raise ValueError('片段或已改变时间轴的结果不能直接替换视频音轨。')
            if asset.source.suffix.lower() not in VIDEO: raise ValueError('原素材不是视频。')
            path = result.tracks.get(track)
            if not path: raise ValueError('请选择要导出的音轨。')
            runner.ff(['-i',asset.source,'-i',path,'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k',temporary])
        elif fmt in ('wav','flac','mp3','m4a','ogg'):
            path = result.tracks.get(track)
            if not path: raise ValueError('请选择要导出的音轨。')
            codecs = {'wav':['-c:a',f'pcm_s{bit_depth}le' if bit_depth!=32 else 'pcm_f32le'],
                      'flac':['-c:a','flac','-sample_fmt','s16' if bit_depth==16 else 's32'],
                      'mp3':['-c:a','libmp3lame','-b:a','192k'], 'm4a':['-c:a','aac','-b:a','192k'],
                      'ogg':['-c:a','libvorbis','-q:a','5']}
            runner.ff(['-i',path,'-ar',str(sample_rate),*codecs[fmt],temporary])
        else: raise ValueError('不支持的导出格式。')
        runner.check()
        if overwrite: os.replace(temporary,destination)
        elif os.name == 'nt': os.rename(temporary,destination)
        else:
            os.link(temporary,destination); temporary.unlink()
        if fmt=='zip': result.exported_tracks.update(result.tracks)
        elif fmt in ('wav','flac','mp3','m4a','ogg','mkv') and track:
            result.exported_tracks.add(track)
        result.exported = (set(result.tracks).issubset(result.exported_tracks) if result.tracks else True)
        return destination
    finally:
        temporary.unlink(missing_ok=True)
