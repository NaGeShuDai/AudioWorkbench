"""Executed inside an isolated model environment, never imported by the GUI."""
import json
import sys
from pathlib import Path


def main():
    # Use the OS trust store, including locally configured enterprise certificates.
    import truststore
    truststore.inject_into_ssl()
    kind, src, dest, config = sys.argv[1:]
    settings = json.loads(Path(config).read_text(encoding='utf-8'))
    if kind == 'deepfilter':
        from df.enhance import init_df, load_audio, enhance, save_audio
        model, state, _ = init_df()
        audio, _ = load_audio(src, sr=state.sr())
        result = enhance(model, state, audio)
        # Strength controls wet/dry mix for this engine.
        mix = settings['strength']
        result = result * mix + audio[..., :result.shape[-1]] * (1 - mix)
        save_audio(dest, result, state.sr())
    elif kind in ('vocals', 'dereverb'):
        from audio_separator.separator import Separator
        stem = 'Vocals' if kind == 'vocals' else 'No Reverb'
        model = settings['vocal_model' if kind == 'vocals' else 'reverb_model']
        separator = Separator(output_dir=str(Path(dest).parent / kind), output_format='WAV',
                              model_file_dir=str(Path(__file__).resolve().parent.parent / 'models'),
                              output_single_stem=stem)
        separator.load_model(model_filename=model)
        files = separator.separate(src)
        if len(files) != 1:
            raise RuntimeError(f'期望 {stem} 单音轨，模型返回 {files}；请检查模型的音轨类型。')
        result = Path(files[0])
        if not result.is_absolute(): result = Path(separator.output_dir) / result
        import shutil
        shutil.copyfile(result, dest)
    elif kind == 'enhance':
        import torch
        import torchaudio
        from resemble_enhance.enhancer.inference import enhance
        audio, sr = torchaudio.load(src)
        audio = audio.mean(dim=0)
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        result, rate = enhance(audio, sr, device, nfe=32, solver='midpoint', lambd=0.9, tau=0.5)
        torchaudio.save(dest, result.cpu().unsqueeze(0), rate)
    else:
        raise ValueError(kind)


if __name__ == '__main__':
    main()
