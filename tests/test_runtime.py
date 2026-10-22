import sys, threading, time
import pytest
from monday.runtime import Runtime, Cancelled

def test_stdout_stderr_exit(cfg):
    r=Runtime(cfg).run([sys.executable,'-c','import sys; print("ok"); print("bad",file=sys.stderr); sys.exit(7)'])
    assert r['stdout']=='ok\n' and r['stderr']=='bad\n' and r['exit_code']==7

def test_command_timeout(cfg):
    started=time.monotonic()
    with pytest.raises(TimeoutError): Runtime(cfg).run([sys.executable,'-c','import time; time.sleep(20)'],timeout=.1)
    assert time.monotonic()-started<2

def test_command_cancel(cfg):
    runtime=Runtime(cfg); timer=threading.Timer(.1,runtime.stop.set); timer.start()
    try:
        with pytest.raises(Cancelled): runtime.run([sys.executable,'-c','import time; time.sleep(20)'])
    finally: timer.cancel()

def test_command_output_bound(cfg):
    cfg.output_limit=128
    with pytest.raises(ValueError): Runtime(cfg).run([sys.executable,'-c','import os,time; os.write(1,b"x"*1000000); time.sleep(1)'])

def test_shell_not_interpreted(cfg):
    r=Runtime(cfg).run([sys.executable,'-c','import sys; print(sys.argv[1])','$(touch /tmp/monday-never); rm -rf /'])
    assert r['stdout'].strip()=='$(touch /tmp/monday-never); rm -rf /'

def test_truncated_output_is_disclosed(cfg):
    cfg.output_limit=10
    r=Runtime(cfg).run([sys.executable,'-c','print("x"*20)'])
    assert r['truncated'] and len(r['stdout'])==10
