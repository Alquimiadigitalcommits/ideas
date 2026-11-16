"""`python -m app` → inicia el servidor local y abre el navegador."""
import threading
import webbrowser

import uvicorn

from . import config


def main() -> None:
    url = f"http://{config.HOST}:{config.PORT}"
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    print(f"Smart Video Editor en {url}  (workspace: {config.WORKSPACE})")
    uvicorn.run("app.main:app", host=config.HOST, port=config.PORT, log_level="info")


if __name__ == "__main__":
    main()
