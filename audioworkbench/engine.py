from __future__ import annotations

import sys
import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

import imageio_ffmpeg
import noisereduce as nr
import numpy as np
import soundfile as sf

ROOT = Path(sys.executable).resolve().parent if getattr(sys,"frozen",False) else Path(__file__).resolve().parent.parent
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
VIDEO = {'.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v'}


class Cancelled(Exception):
    pass


@dataclass
class Settings:
    denoise: bool = True
    strength: float = 0.55
    engine: str = 'spectral'
    separate: bool = False
    dereverb: bool = False
    enhance: bool = False
    polish: bool = True
    normalize: bool = True
    lufs: int = -16
    format: str = 'wav'
    video: bool = False
    trim: bool = False
    vocal_model: str = 'UVR-MDX-NET-Inst_HQ_3.onnx'
    reverb_model: str = 'Reverb_HQ_By_FoxJoy.onnx'


class Runner:
    def __init__(self, cancel=None, progress=None):
        self.cancel = cancel or threading.Event()
        self.progress = progress or (lambda p, s: None)

    def check(self):
        if self.cancel.is_set():
            raise Cancelled('已取消，原文件未改动')

    def run(self, args, logfile=None):
        self.check()
        import tempfile
        with (open(logfile, 'w+b') if logfile else tempfile.TemporaryFile()) as out:
            env = os.environ.copy()
            env['PATH'] = str(ROOT / 'bin') + os.pathsep + env.get('PATH', '')
            env['PYTHONUTF8'] = '1'
            # httpx / model hubs do not automatically discover Windows proxy settings.
            # Honor the user's existing OS proxy without printing its address or credentials.
            import urllib.request
            for scheme, proxy in urllib.request.getproxies().items():
                if scheme in ('http', 'https'):
                    env.setdefault(scheme.upper() + '_PROXY', proxy)
            p = subprocess.Popen([str(a) for a in args], stdout=out, stderr=out, env=env,
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            while p.poll() is None:
                if self.cancel.wait(0.15):
                    if os.name == 'nt':
                        subprocess.run(['taskkill', '/PID', str(p.pid), '/T', '/F'],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
                    else: p.terminate()
                    try:
                        p.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        p.kill(); p.wait()
                    raise Cancelled('已取消，原文件未改动')
            out.seek(0)
            text = out.read().decode('utf-8', errors='replace')
        if p.returncode:
            raise RuntimeError(text[-3500:] or f'进程退出：{p.returncode}')
        return text

    def ff(self, args):
        return self.run([FFMPEG, '-hide_banner', '-nostdin', '-y', *args])


def decode(source, dest, runner, start=0, duration=None):
    args = ['-ss', str(start), '-i', str(source)] if start else ['-i', str(source)]
    if duration:
        args += ['-t', str(duration)]
    runner.ff([*args, '-map', '0:a:0', '-vn', '-ar', '48000', '-ac', '2', '-c:a', 'pcm_f32le', str(dest)])


def analyze(path):
    info = sf.info(path)
    peak, energy, count, silent = 0., 0., 0, 0
    envelope = []
    for x in sf.blocks(path, blocksize=4800, dtype='float32', always_2d=True):
        if not np.isfinite(x).all():
            raise ValueError(f'音频包含无效采样值：{path}')
        peak = max(peak, float(np.max(np.abs(x))))
        energy += float(np.sum(x.astype('float64') ** 2)); count += x.size
        rms = float(np.sqrt(np.mean(x ** 2)))
        silent += len(x) if rms < .00316 else 0
        envelope.append(float(np.max(np.abs(x))))
    return {'seconds': info.duration, 'sample_rate': info.samplerate, 'channels': info.channels,
            'peak_dbfs': round(20 * np.log10(max(peak, 1e-9)), 2),
            'rms_dbfs': round(10 * np.log10(max(energy / max(count, 1), 1e-18)), 2),
            'silence_percent': round(100 * silent / max(info.frames, 1), 1), 'envelope': envelope}


def engine_python(name):
    return ROOT / '.engines' / name / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def available(name):
    return engine_python(name).exists() and (ROOT / '.engines' / name / 'ready.json').exists()


def ai_process(kind, source, output, settings, runner):
    env = {'deepfilter': 'deepfilter', 'vocals': 'separator', 'dereverb': 'separator', 'enhance': 'resemble'}[kind]
    if not available(env):
        raise RuntimeError(f'请先在「模型管理」安装 {env} 引擎。')
    binary = ROOT / 'bin' / ('ffmpeg.exe' if os.name == 'nt' else 'ffmpeg')
    if not binary.exists():
        binary.parent.mkdir(exist_ok=True); shutil.copyfile(FFMPEG, binary)
    config = output.with_suffix('.config.json')
    config.write_text(json.dumps(asdict(settings)), encoding='utf-8')
    runner.run([engine_python(env), ROOT / 'audioworkbench' / 'model_worker.py', kind, source, output, config],
               output.with_suffix('.log'))
    if not output.exists():
        raise RuntimeError(f'{kind} 未生成音频，请查看任务日志。')


def spectral(source, output, strength, runner):
    """Bounded-memory blocks with context; stereo channels retain original timing."""
    with sf.SoundFile(source) as src, sf.SoundFile(output, 'w', samplerate=src.samplerate,
            channels=src.channels, subtype='FLOAT') as dst:
        rate, total = src.samplerate, len(src)
        block, context = rate * 20, rate
        for start in range(0, total, block):
            runner.check()
            left, end = max(0, start - context), min(total, start + block + context)
            src.seek(left)
            x = src.read(end - left, dtype='float32', always_2d=True)
            y = np.zeros_like(x)
            for channel in range(x.shape[1]):
                if np.max(np.abs(x[:, channel])) > 1e-9:
                    y[:, channel] = nr.reduce_noise(y=x[:, channel], sr=rate, stationary=False,
                                                    prop_decrease=strength, n_jobs=1)
            if not np.isfinite(y).all():
                raise RuntimeError('去噪产生了无效采样值，已停止处理。')
            offset = start - left
            dst.write(y[offset:offset + min(block, total - start)])


def process(source, outdir, settings, runner=None, preview=None):
    runner = runner or Runner()
    source, outdir = Path(source).resolve(), Path(outdir).resolve()
    if settings.video and settings.trim:
        raise ValueError('替换视频音轨时不能裁剪静音，以免音画不同步。')
    for enabled, env in [(settings.separate or settings.dereverb, 'separator'),
                         (settings.enhance, 'resemble'),
                         (settings.denoise and settings.engine == 'deepfilter', 'deepfilter')]:
        if enabled and not available(env):
            raise RuntimeError(f'尚未安装 {env}，请打开模型管理完成安装。')
    job = outdir / (source.stem[:60] + '_' + time.strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:6])
    job.mkdir(parents=True)
    report = {'source': str(source.resolve()), 'settings': asdict(settings), 'preview': preview,
              'status': 'running', 'steps': [], 'started': time.strftime('%Y-%m-%d %H:%M:%S')}
    report['engines'] = {name: json.loads((ROOT / '.engines' / name / 'ready.json').read_text(encoding='utf-8'))
                         for name in ('deepfilter', 'separator', 'resemble') if available(name)}
    started = time.monotonic()
    def save():
        (job / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    save()
    try:
        runner.progress(5, '读取音轨')
        current = job / '00_original.wav'
        decode(source, current, runner, *(preview or (0, None)))
        report['before'] = analyze(current)
        if report['before']['seconds'] < .05:
            raise ValueError('所选片段没有足够的音频。')
        steps = []
        if settings.separate: steps.append(('vocals', '提取人声'))
        if settings.dereverb: steps.append(('dereverb', '减轻混响'))
        if settings.denoise: steps.append((settings.engine, '语音去噪'))
        if settings.enhance: steps.append(('enhance', '人声修复'))
        for i, (kind, label) in enumerate(steps):
            runner.check(); runner.progress(12 + int(48 * i / max(len(steps), 1)), label)
            dest = job / f'{i+1:02d}_{kind}.wav'
            then = time.monotonic()
            digest = hashlib.sha256()
            with open(current, 'rb') as stream:
                while chunk := stream.read(1024 * 1024):
                    runner.check(); digest.update(chunk)
            signature = {'revision': 1, 'kind': kind, 'strength': settings.strength,
                         'vocal_model': settings.vocal_model, 'reverb_model': settings.reverb_model}
            engine_name = {'deepfilter': 'deepfilter', 'vocals': 'separator', 'dereverb': 'separator', 'enhance': 'resemble'}.get(kind)
            if engine_name:
                signature['environment'] = (ROOT / '.engines' / engine_name / 'ready.json').read_text(encoding='utf-8')
            digest.update(json.dumps(signature, sort_keys=True).encode())
            cache = outdir / '.cache'; cache.mkdir(exist_ok=True)
            cached = cache / (digest.hexdigest() + '.wav')
            hit = cached.exists()
            if hit: shutil.copyfile(cached, dest)
            else:
                if kind == 'spectral': spectral(current, dest, settings.strength, runner)
                else: ai_process(kind, current, dest, settings, runner)
                temporary = cached.with_suffix('.' + uuid.uuid4().hex + '.tmp')
                shutil.copyfile(dest, temporary); temporary.replace(cached)
            current = dest
            report['steps'].append({'name': kind, 'cache_hit': hit, 'seconds': round(time.monotonic() - then, 2)})
            save()
        runner.progress(65, '音色与动态调整')
        filters = []
        if settings.polish:
            filters += ['highpass=f=70', 'equalizer=f=3000:t=q:w=0.8:g=1.5',
                        'deesser=i=0.15', 'acompressor=threshold=0.125:ratio=2:attack=15:release=150:makeup=1']
        if settings.trim:
            filters += ['silenceremove=start_periods=1:start_duration=0.08:start_threshold=-45dB',
                        'areverse', 'silenceremove=start_periods=1:start_duration=0.08:start_threshold=-45dB', 'areverse']
        if filters:
            dest = job / 'polished.wav'
            runner.ff(['-i', current, '-af', ','.join(filters), '-c:a', 'pcm_f32le', dest])
            current = dest
        loudfilter = None
        if settings.normalize:
            runner.progress(75, '测量并调整响度')
            import re
            log = runner.ff(['-i', current, '-af', f'loudnorm=I={settings.lufs}:TP=-1.5:LRA=11:print_format=json', '-f', 'null', '-'])
            matches = re.findall(r'\{\s*"input_i".*?\}', log, flags=re.S)
            if not matches: raise RuntimeError('响度分析没有返回测量值。')
            measured = json.loads(matches[-1]); report['loudness_input'] = measured
            if all(np.isfinite(float(measured[k])) for k in ('input_i', 'input_tp', 'input_lra', 'input_thresh', 'target_offset')):
                loudfilter = (f'loudnorm=I={settings.lufs}:TP=-1.5:LRA=11:linear=true:'
                              f'measured_I={measured["input_i"]}:measured_TP={measured["input_tp"]}:'
                              f'measured_LRA={measured["input_lra"]}:measured_thresh={measured["input_thresh"]}:'
                              f'offset={measured["target_offset"]}')
        runner.progress(88, '生成试听与导出文件')
        final = job / 'processed.wav'
        runner.ff(['-i', current, *(['-af', loudfilter] if loudfilter else []), '-ar', '48000', '-c:a', 'pcm_s24le', final])
        report['after'] = analyze(final)
        if not settings.trim and abs(report['after']['seconds'] - report['before']['seconds']) > .1:
            raise RuntimeError('处理后时长变化超过 100 ms，已停止导出，请检查模型输出。')
        exported = final
        if settings.format != 'wav':
            exported = job / ('processed.' + settings.format)
            codec = ['-c:a', 'libmp3lame', '-b:a', '192k'] if settings.format == 'mp3' else ['-c:a', 'flac']
            runner.ff(['-i', final, *codec, exported])
        if settings.video and source.suffix.lower() in VIDEO and not preview:
            exported = job / 'processed_video.mkv'
            runner.ff(['-i', source, '-i', final, '-map', '0:v:0', '-map', '1:a:0',
                       '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', exported])
        report.update(status='complete', output=str(exported), elapsed_seconds=round(time.monotonic() - started, 2))
        save(); runner.progress(100, '处理完成')
        return {'original': str(job / '00_original.wav'), 'processed': str(final),
                'output': str(exported), 'report': report, 'folder': str(job)}
    except Exception as exc:
        report.update(status='cancelled' if isinstance(exc, Cancelled) else 'failed', error=str(exc))
        save()
        raise
