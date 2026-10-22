"""Bounded argv execution; no shell, finite output, stop and process-tree cleanup."""
import os, signal, subprocess, tempfile, threading, time
from pathlib import Path

class Cancelled(RuntimeError): pass

class Runtime:
    def __init__(self, cfg, stop=None):
        self.cfg, self.stop = cfg, stop or threading.Event()
        self.stop_file = cfg.data_dir / "STOP"

    def check(self):
        if self.stop.is_set() or self.stop_file.exists(): raise Cancelled("Emergency stop is active")

    def run(self, argv, cwd=None, timeout=None, input_text=None):
        self.check()
        if not argv or not all(isinstance(a, str) and "\x00" not in a for a in argv):
            raise ValueError("Invalid argv")
        # Anonymous files avoid pipe deadlocks; kill excessive output rather than filling disk.
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            env = {k:v for k,v in os.environ.items() if k not in ("LD_PRELOAD", "LD_LIBRARY_PATH", "PYTHONPATH", "BASH_ENV", "ENV")}
            env.update({"GIT_TERMINAL_PROMPT":"0", "GIT_CONFIG_NOSYSTEM":"1", "GIT_CONFIG_GLOBAL":"/dev/null"})
            with tempfile.TemporaryFile() as inp:
                if input_text is not None: inp.write(input_text.encode()); inp.seek(0)
                p = subprocess.Popen(argv, cwd=cwd, stdin=inp if input_text is not None else subprocess.DEVNULL,
                                     stdout=out, stderr=err, env=env, start_new_session=True)
                start = time.monotonic()
                try:
                    while p.poll() is None:
                        self.check()
                        if time.monotonic()-start > (timeout or self.cfg.command_timeout): raise TimeoutError("Command timed out")
                        if os.fstat(out.fileno()).st_size + os.fstat(err.fileno()).st_size > self.cfg.output_limit*8:
                            raise ValueError("Command output limit exceeded")
                        time.sleep(.03)
                finally:
                    # Stop descendants as well, including a build leaving background workers.
                    try: os.killpg(p.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                    p.wait()
            out.seek(0); err.seek(0)
            truncated = os.fstat(out.fileno()).st_size>self.cfg.output_limit or os.fstat(err.fileno()).st_size>self.cfg.output_limit
            return {"argv": argv, "truncated":truncated, "stdout":out.read(self.cfg.output_limit).decode(errors="replace"),
                    "stderr":err.read(self.cfg.output_limit).decode(errors="replace"), "exit_code":p.returncode}
