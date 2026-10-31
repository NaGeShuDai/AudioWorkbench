"""Backward-compatible entry point for the current GUI validation."""
import runpy
from pathlib import Path
runpy.run_path(str(Path(__file__).with_name('gui_toolbox.py')), run_name='__main__')
