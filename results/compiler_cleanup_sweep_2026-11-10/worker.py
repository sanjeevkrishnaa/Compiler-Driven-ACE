"""Run the existing physical benchmark worker with a read-only progress monitor."""
import json
from pathlib import Path
import runpy
import sys
import threading
import time

output = Path(sys.argv[sys.argv.index('--output') + 1])

def monitor():
    while True:
        time.sleep(20)
        frame = sys._current_frames().get(threading.main_thread().ident)
        while frame is not None:
            if frame.f_code.co_name == 'run_parallel_experiment':
                manager = frame.f_locals.get('request_manager')
                if manager is not None:
                    data = dict(completed=len(manager.request_end_times),
                                simulation_ms=manager.timeline.now() / 1e9,
                                updated=time.time())
                    temporary = output / 'progress.tmp'
                    temporary.write_text(json.dumps(data))
                    temporary.replace(output / 'progress.json')
                    break
            frame = frame.f_back

threading.Thread(target=monitor, daemon=True).start()
runpy.run_path(str(Path(__file__).resolve().parents[2] / 'tools/benchmark_matrix.py'), run_name='__main__')

