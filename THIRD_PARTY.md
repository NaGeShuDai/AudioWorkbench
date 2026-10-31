# Third-party notices

AudioWorkbench original application code and icon: GPL-3.0-or-later, copyright 2026 AudioWorkbench contributors. Bundled third-party code retains its own license. No AI model weights or isolated AI environments are included in this release.

- PySide6 / Qt 6: LGPL-3.0 / GPL-3.0 and applicable module licenses. DLLs remain separate and replaceable in the portable directory. Source: https://download.qt.io/official_releases/QtForPython/ and https://code.qt.io/ .
- FFmpeg 7.1 essentials build by gyan.dev, as shipped by imageio-ffmpeg: GPL v3 enabled, with Rubber Band and other codec libraries. Source/rebuild information: https://www.gyan.dev/ffmpeg/builds/ , https://github.com/GyanD/codexffmpeg , https://ffmpeg.org/releases/ffmpeg-7.1.tar.xz . FFmpeg is an unmodified standalone subprocess executable. See its `-version` and `-buildconf` output for full configuration.
- imageio-ffmpeg: BSD-2-Clause wrapper, https://github.com/imageio/imageio-ffmpeg . FFmpeg has a separate license.
- uv: MIT / Apache-2.0, https://github.com/astral-sh/uv .
- Lucide 0.468.0: ISC, see assets/icons/LICENSE.
- NumPy, SciPy, SoundFile, noisereduce, matplotlib, Python and transitive libraries: their original licenses are copied under licenses/ in the portable distribution where supplied by installed packages.
- PyInstaller bootloader: GPL with the bootloader distribution exception, https://pyinstaller.org/ .

The portable folder must stay intact. The software is provided without warranty. Modified library builds may be substituted; do not remove the accompanying licenses. Optional models downloaded by users have separate upstream licenses; consult docs/OPEN_SOURCE.md and their model cards before redistribution.
