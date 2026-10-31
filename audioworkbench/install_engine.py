import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def install(name):
    if name not in ('deepfilter', 'separator', 'resemble', 'speech'):
        raise ValueError(name)
    if name == 'resemble' and os.name == 'nt':
        raise RuntimeError('Resemble Enhance 的依赖不在本工具的原生 Windows 支持范围内。请使用基础去噪或 DeepFilterNet。')
    uv = str(ROOT/'uv.exe') if (ROOT/'uv.exe').exists() else shutil.which('uv')
    if not uv: raise RuntimeError('安装 AI 引擎需要 uv，请先安装 uv。')
    env = ROOT / '.engines' / name
    python = env / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    def run(args):
        subprocess.run([str(x) for x in args], check=True)
    (env / 'ready.json').unlink(missing_ok=True)
    run([uv, 'venv', '--allow-existing', '--python', '3.11', env])
    packages = {
        'deepfilter': ['numpy<2', 'torch==2.2.2', 'torchaudio==2.2.2', 'deepfilternet==0.5.6', 'soundfile'],
        'separator': ['audio-separator[cpu]', 'soundfile'],
        'resemble': ['resemble-enhance'],
        'speech': ['faster-whisper', 'onnxruntime', 'soundfile'],
    }[name]
    lockfile = ROOT / (name + '.lock.txt')
    if lockfile.exists():
        run([uv, 'pip', 'install', '--python', python, '-r', lockfile])
    else:
        run([uv, 'pip', 'install', '--python', python, 'truststore', *packages])
    imports = {'deepfilter': 'from df.enhance import init_df',
               'separator': 'from audio_separator.separator import Separator',
               'resemble': 'from resemble_enhance.enhancer.inference import enhance',
               'speech': 'from faster_whisper import WhisperModel; from faster_whisper.vad import get_speech_timestamps'}
    run([python, '-c', imports[name]])
    versions = subprocess.check_output([str(uv), 'pip', 'freeze', '--python', str(python)], text=True)
    (env / 'ready.json').write_text(json.dumps({'engine': name, 'packages': versions, 'verified': 'import only; weights downloaded on first use'}), encoding='utf-8')
    print('安装完成。首次处理将下载模型权重。', flush=True)


if __name__ == '__main__':
    install(sys.argv[1])
