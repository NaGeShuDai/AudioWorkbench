import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audioworkbench.engine import Runner, Settings, Cancelled, process, decode


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        sr = 48000
        t = np.arange(sr * 4) / sr
        rng = np.random.default_rng(42)
        # Speech-like harmonics surrounded by stationary background noise.
        gate = ((t > 1) & (t < 3)).astype(float)
        signal = .15 * (np.sin(2*np.pi*170*t) + .4*np.sin(2*np.pi*340*t)) * gate
        noise = rng.normal(0, .018, len(t))
        cls.input = cls.root / 'sample.wav'
        sf.write(cls.input, np.column_stack([signal+noise, signal+noise]), sr, subtype='FLOAT')

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def test_denoise_and_loudness(self):
        result = process(self.input, self.root, Settings())
        x, sr = sf.read(result['processed'])
        self.assertEqual(sr, 48000)
        self.assertEqual(len(x), 4*sr)
        self.assertTrue(np.isfinite(x).all())
        self.assertLess(np.max(np.abs(x)), 1)
        self.assertEqual(result['report']['status'], 'complete')
        denoised, _ = sf.read(Path(result['folder']) / '01_spectral.wav')
        original, _ = sf.read(self.input)
        self.assertLess(np.mean(denoised[:sr//2]**2), np.mean(original[:sr//2]**2))
        self.assertTrue((Path(result['folder']) / 'report.json').exists())

    def test_preview_and_formats(self):
        for fmt in ('flac', 'mp3'):
            result = process(self.input, self.root, Settings(format=fmt, denoise=False), preview=(1, 2))
            self.assertAlmostEqual(result['report']['after']['seconds'], 2, places=2)
            self.assertTrue(Path(result['output']).is_file())

    def test_silence(self):
        path = self.root / 'silence.wav'; sf.write(path, np.zeros((48000, 2)), 48000)
        result = process(path, self.root, Settings())
        self.assertEqual(result['report']['status'], 'complete')
        samples, _ = sf.read(result['processed'])
        self.assertTrue(np.isfinite(samples).all())
        self.assertEqual(float(np.max(np.abs(samples))), 0.)

    def test_video_export(self):
        video = self.root / 'source.mp4'
        Runner().ff(['-f', 'lavfi', '-i', 'color=c=gray:s=160x90:r=10:d=4', '-i', self.input,
                     '-c:v', 'libx264', '-c:a', 'aac', '-shortest', video])
        result = process(video, self.root, Settings(video=True, denoise=False))
        self.assertEqual(Path(result['output']).suffix, '.mkv')
        decoded = self.root / 'video_audio.wav'; decode(result['output'], decoded, Runner())
        self.assertAlmostEqual(sf.info(decoded).duration, 4, delta=.1)

    def test_cancel_and_invalid(self):
        cancel = threading.Event(); cancel.set()
        with self.assertRaises(Cancelled): process(self.input, self.root, Settings(), Runner(cancel))
        with self.assertRaises(ValueError): process(self.input, self.root, Settings(video=True, trim=True))
        with self.assertRaises(RuntimeError): process(self.root / 'missing.wav', self.root, Settings())

    def test_cache_and_chunk_boundary(self):
        path = self.root / 'long.wav'
        rng = np.random.default_rng(5)
        sf.write(path, rng.normal(0, .015, (48000*21+137, 2)), 48000)
        first = process(path, self.root, Settings(polish=False, normalize=False))
        second = process(path, self.root, Settings(polish=False, normalize=False))
        self.assertTrue(second['report']['steps'][0]['cache_hit'])
        x, _ = sf.read(first['processed'])
        self.assertEqual(len(x), 48000*21+137)
        self.assertTrue(np.isfinite(x).all())

    def test_running_process_cancellation(self):
        cancel = threading.Event()
        timer = threading.Timer(.5, cancel.set); timer.start()
        start = time.monotonic()
        try:
            with self.assertRaises(Cancelled):
                Runner(cancel).run([sys.executable, '-c', 'import time; time.sleep(30)'])
        finally: timer.cancel()
        self.assertLess(time.monotonic() - start, 10)


if __name__ == '__main__': unittest.main(verbosity=2)
