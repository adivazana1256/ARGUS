"""ASGI entrypoint (M0 spec §4.1): ``uvicorn argus.main:app``.

The module-level ``app`` is the one deliberate factory call for the server to
import; all other construction goes through :func:`argus.api.app.create_app`.
"""

from argus.api.app import create_app

app = create_app()
