"""Backward-compatible FastAPI entry point.

The application implementation lives in :mod:`nexus_dash.api.server`.
This module keeps the historical `server:app` ASGI target and `python server.py`
command working while the implementation uses the package layout.
"""
from __future__ import annotations

import sys

from nexus_dash.api import server as _server

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        _server.app,
        host="127.0.0.1",
        port=8000,
        reload=False,
        access_log=False,
        server_header=False,
    )
else:
    # Keep legacy imports (including access to underscored helpers) bound to the
    # implementation module rather than creating a second wrapper namespace.
    sys.modules[__name__] = _server
