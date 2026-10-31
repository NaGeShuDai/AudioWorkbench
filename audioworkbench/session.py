"""Private temporary sessions. Only export_result writes user deliverables."""
from __future__ import annotations
import json
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path


def _lock(file):
    file.seek(0)
    if os.name == 'nt':
        import msvcrt
        msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(file):
    file.seek(0)
    if os.name == 'nt':
        import msvcrt
        msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(file, fcntl.LOCK_UN)


@dataclass
class AudioVersion:
    path: Path
    title: str
    info: dict
    time_changed: bool = False


@dataclass
class Asset:
    id: str
    source: Path
    folder: Path
    streams: list
    versions: list
    index: int = 0
    stream: int = 0
    result: object = None
    dirty: bool = False
    cache: dict = field(default_factory=dict)

    @property
    def current(self): return self.versions[self.index]

    def apply(self, path, title, info, time_changed):
        self.versions = self.versions[:self.index+1]
        self.versions.append(AudioVersion(Path(path), title, info, time_changed or self.current.time_changed))
        self.index += 1
        self.dirty = True


class Session:
    def __init__(self, base=None):
        self.base = Path(base or Path(tempfile.gettempdir()) / 'AudioWorkbench-sessions-v2').resolve()
        self.base.mkdir(parents=True, exist_ok=True)
        self.cleanup_abandoned()
        self.root = self.base / ('session-' + uuid.uuid4().hex)
        self.root.mkdir()
        self.lease = open(self.root / '.lease', 'w+b')
        self.lease.write(b'1'); self.lease.flush(); _lock(self.lease)
        self.assets = {}

    def cleanup_abandoned(self):
        for folder in self.base.glob('session-*'):
            if not folder.is_dir() or folder.is_symlink() or folder.resolve().parent != self.base: continue
            lease = folder / '.lease'
            # A new process may be between mkdir and opening its lease.
            if not lease.exists(): continue
            try:
                with open(lease, 'r+b') as file:
                    _lock(file); _unlock(file)
                shutil.rmtree(folder)
            except (OSError, PermissionError): pass

    def new_folder(self, prefix='job'):
        folder = self.root / (prefix + '-' + uuid.uuid4().hex)
        folder.mkdir()
        return folder

    def remove(self, asset_id):
        asset = self.assets.pop(asset_id)
        if asset.folder.resolve().parent != self.root: raise ValueError('非法临时目录')
        shutil.rmtree(asset.folder, ignore_errors=True)

    def close(self):
        if not self.lease.closed:
            _unlock(self.lease); self.lease.close()
        # Only the uniquely owned session directory; never the source or export directory.
        if self.root.resolve().parent == self.base:
            shutil.rmtree(self.root, ignore_errors=True)

    def __enter__(self): return self
    def __exit__(self, *args): self.close()
