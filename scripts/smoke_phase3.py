"""Local-only Vite/Uvicorn smoke without environment files or live services."""
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import dotenv
import httpx
import uvicorn


def forbidden(*args, **kwargs):
    raise AssertionError('Environment-file and external HTTP access forbidden in smoke')


dotenv.load_dotenv = forbidden
dotenv.dotenv_values = forbidden
httpx.HTTPTransport.handle_request = forbidden

from api.main import app


def main():
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]})
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            if not thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError('Local backend failed to start')
            time.sleep(0.05)
        result = subprocess.run(
            ['node', 'web/tests/smoke-phase3.mjs', str(port)],
            cwd=Path(__file__).resolve().parents[1], timeout=90,
            capture_output=True, text=True, encoding='utf-8',
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
        )
        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        return result.returncode
    finally:
        server.should_exit = True
        thread.join(10)
        listener.close()
        if thread.is_alive():
            raise RuntimeError('Local backend did not stop cleanly')


if __name__ == '__main__':
    raise SystemExit(main())
