"""Reproducible measurements; no models or browser are started."""
import json, os, statistics, subprocess, sys, tempfile, time
from pathlib import Path
import psutil

def main():
    project=Path(__file__).resolve().parents[1]
    env=dict(os.environ); env['MONDAY_MODEL']=''; env['MONDAY_LAYA_PATH']=''
    rss=[]; startup=[]; latency=[]
    with tempfile.TemporaryDirectory(prefix='monday-bench-') as directory:
        env['MONDAY_DATA_DIR']=directory
        for _ in range(5):
            start=time.perf_counter()
            p=subprocess.Popen([sys.executable,'-m','monday'],cwd=project,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                prompt=p.stdout.read(8)
                if prompt!=b'monday> ': raise RuntimeError(p.stderr.read().decode())
                startup.append(time.perf_counter()-start)
                rss.append(psutil.Process(p.pid).memory_info().rss)
                if psutil.Process(p.pid).children(): raise RuntimeError('Unexpected idle children')
                p.communicate(b'quit\n',timeout=5)
            finally:
                if p.poll() is None: p.kill(); p.wait()
            start=time.perf_counter()
            r=subprocess.run([sys.executable,'-m','monday','check my ram'],cwd=project,env=env,capture_output=True,timeout=5)
            if r.returncode: raise RuntimeError(r.stderr.decode())
            latency.append(time.perf_counter()-start)
    result={'method':'5 fresh subprocesses; RSS after REPL prompt; no models or child services; wall clock includes Python startup',
            'python':sys.version.split()[0],'idle_rss_bytes':rss,'idle_rss_mib_median':statistics.median(rss)/2**20,
            'startup_seconds':startup,'startup_median_seconds':statistics.median(startup),
            'ram_task_seconds':latency,'ram_task_median_seconds':statistics.median(latency),
            'system_total_ram_bytes':psutil.virtual_memory().total}
    output=project/'docs'/'benchmarks.json'; output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__': main()
