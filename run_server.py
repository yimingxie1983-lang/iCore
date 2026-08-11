

from __future__ import annotations

import os

def main() -> None:
    import uvicorn

    from cancer_claw.app import app
    from cancer_claw.config import settings

    host = os.environ.get("CANCER_CLAW_APP_HOST") or settings.app.host
    port = int(os.environ.get("CANCER_CLAW_APP_PORT") or settings.app.port)


    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="debug" if settings.app.debug else "info",
        reload=False,
    )

if __name__ == "__main__":
    main()
