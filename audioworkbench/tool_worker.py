"""Runs in isolated separator/speech environments. All media output is temporary."""
import json
import os
import sys
from pathlib import Path


def main():
    import truststore
    truststore.inject_into_ssl()
    kind, src, folder, config = sys.argv[1:]
    folder = Path(folder); p = json.loads(Path(config).read_text(encoding='utf-8'))
    root = Path(__file__).resolve().parent.parent
    manifest = {}
    if kind in ('vocals','stems','dereverb'):
        import torch
        torch.set_num_threads(min(8, os.cpu_count() or 4))
        if p.get('device') == 'cuda' and not torch.cuda.is_available():
            raise RuntimeError('当前隔离环境没有可用 CUDA，请选择 CPU。')
        from audio_separator.separator import Separator
        separator = Separator(output_dir=str(folder / 'stems'), output_format='WAV',
                              model_file_dir=str(root / 'models'),
                              output_single_stem='No Reverb' if kind=='dereverb' else None,
                              use_soundfile=True, use_autocast=False)
        # CPU is explicit. Prevent auto-selection of a GPU when the user selected CPU.
        if p.get('device','cpu') == 'cpu':
            separator.torch_device = torch.device('cpu')
            separator.onnx_execution_provider = ['CPUExecutionProvider']
        separator.load_model(model_filename=p['model'])
        outputs = separator.separate(src)
        tracks = {}
        for filename in outputs:
            path = Path(filename)
            if not path.is_absolute(): path = Path(separator.output_dir) / path
            if not path.is_file(): raise RuntimeError('分离输出不存在：' + str(path))
            import re
            m = re.search(r'\(([^)]+)\)',path.stem)
            name = m[1] if m else path.stem
            tracks[name] = str(path.resolve())
        if kind == 'dereverb' and not any(n.lower()=='no reverb' for n in tracks):
            raise RuntimeError('模型没有返回 No Reverb 音轨。')
        manifest['tracks'] = tracks
    elif kind == 'transcribe':
        os.environ['HF_HUB_DISABLE_IMPLICIT_TOKEN']='1'
        os.environ['HF_HUB_DISABLE_XET']='1'
        if p.get('download_source')=='mirror': os.environ['HF_ENDPOINT']='https://hf-mirror.com'
        from faster_whisper import WhisperModel
        from faster_whisper.utils import download_model
        device = p.get('device','cpu')
        if p.get('model_path'):
            model_path=Path(p['model_path']).expanduser().resolve()
            if not (model_path/'model.bin').is_file(): raise ValueError('本地模型目录内没有 model.bin。')
            model_path=str(model_path)
        else:
            try:
                model_path=download_model(p['model'],cache_dir=str(root/'models'/'whisper'),local_files_only=True)
                if not all((Path(model_path)/name).is_file() for name in ('model.bin','config.json','tokenizer.json')):
                    raise FileNotFoundError('本地模型缓存尚未完整，继续下载。')
            except (OSError,ValueError):
                try: model_path=download_model(p['model'],cache_dir=str(root/'models'/'whisper'))
                except Exception as exc: raise RuntimeError('模型下载失败。可切换模型下载源，或填写已下载的本地模型目录。\n'+str(exc)) from exc
        model = WhisperModel(model_path, device=device, compute_type='int8' if device=='cpu' else 'float16')
        segments, info = model.transcribe(src, language=None if p['language']=='auto' else p['language'],
                                         task='translate' if p['translate'] else 'transcribe',
                                         vad_filter=p['vad'], beam_size=5, condition_on_previous_text=False)
        manifest = {'language':info.language,'language_probability':info.language_probability,
                    'segments':[{'start':s.start,'end':s.end,'text':s.text.strip()} for s in segments]}
    elif kind == 'vad':
        from faster_whisper.audio import decode_audio
        from faster_whisper.vad import get_speech_timestamps, VadOptions
        audio = decode_audio(src,sampling_rate=16000)
        segments = get_speech_timestamps(audio, VadOptions(threshold=p['threshold']))
        manifest = {'segments':[{'start':s['start']/16000,'end':s['end']/16000} for s in segments]}
    else: raise ValueError(kind)
    (folder/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__': main()
