#!/usr/bin/env python3
"""Прогресс сборки Wine и остановка всех компиляторов перед сохранением кэша."""
import argparse
import os
from pathlib import Path
import signal
import subprocess
import time


def stop_group(process):
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    # Даже если make уже вышел, в группе могут оставаться его компиляторы.
    time.sleep(2)
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def run(command, timeout_seconds, interval=60):
    interrupted = []
    previous_handlers = {}
    for sig in (signal.SIGINT, signal.SIGTERM):
        previous_handlers[sig] = signal.signal(sig, lambda signum, frame: interrupted.append(signum))
    progress = Path('build/winecx-progress.log')
    progress.parent.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(command, start_new_session=True)
    started = time.monotonic()
    next_report = started
    try:
        with progress.open('w') as log:
            while process.poll() is None:
                now = time.monotonic()
                if interrupted or now - started >= timeout_seconds:
                    message = 'Остановка сборки: сигнал отмены или внутренний лимит времени.'
                    print(message, flush=True)
                    log.write(message + '\n')
                    return 128 + interrupted[0] if interrupted else 124
                if now >= next_report:
                    objects = sum(1 for _ in Path('build/winecx-objects').rglob('*.o'))
                    message = f'Прогресс Wine: {(now - started) / 60:.1f} мин, объектных файлов: {objects}'
                    print(message, flush=True)
                    log.write(message + '\n')
                    log.flush()
                    next_report = now + interval
                time.sleep(1)
        return process.returncode
    finally:
        stop_group(process)
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeout-minutes', type=int, default=110)
    args = parser.parse_args()
    if args.timeout_minutes <= 0:
        parser.error('Лимит времени должен быть положительным')
    command = ['arch', '-x86_64', '/bin/bash', '-c',
               'export PATH="/usr/local/bin:/usr/local/sbin:$PATH"; exec /bin/bash tools/build_winecx.sh']
    raise SystemExit(run(command, args.timeout_minutes * 60))
