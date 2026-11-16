"""`python -m app` o el ejecutable empaquetado → inicia el servidor local y abre el navegador."""
import os
import socket
import threading
import webbrowser

import uvicorn

from . import config


def _free_port(preferred: int) -> int:
    with socket.socket() as s:
        try:
            s.bind((config.HOST, preferred))
            return preferred
        except OSError:
            s.bind((config.HOST, 0))
            return s.getsockname()[1]


def main() -> None:
    from .main import app   # import directo: funciona también dentro del ejecutable

    port = _free_port(config.PORT)
    url = f"http://{config.HOST}:{port}"
    if not os.environ.get("SVE_NO_BROWSER"):
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    print(f"Smart Video Editor en {url}  (workspace: {config.WORKSPACE}, ffmpeg: {config.FFMPEG})")
    uvicorn.run(app, host=config.HOST, port=port, log_level="info")


if __name__ == "__main__":
    main()
