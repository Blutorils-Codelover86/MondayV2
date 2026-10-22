"""Real offscreen QML controls and the authenticated backend, not a screenshot mock."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import pytest

@pytest.mark.parametrize('scenario',['layout','input','expressions'])
def test_real_qml_window(scenario):
    if importlib.util.find_spec('PySide6') is None:
        pytest.skip('Install the optional test-ui extra for offscreen Qt integration')
    root=Path(__file__).resolve().parents[1]
    result=subprocess.run([sys.executable,str(root/'scripts/qt_window_check.py'),scenario],cwd=root,
        env={**os.environ,'QT_QPA_PLATFORM':'offscreen','QT_QUICK_BACKEND':'software'},
        capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+'\n'+result.stderr
    assert 'QT_WINDOW_CHECK_OK: '+scenario in result.stdout
