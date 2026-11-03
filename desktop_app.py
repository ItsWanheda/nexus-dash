"""Backward-compatible desktop launcher for NEXUS-DASH.

The desktop implementation lives in :mod:`nexus_dash.desktop.app`.
"""
from __future__ import annotations

import sys

from nexus_dash.desktop import app as _desktop_app

if __name__ == "__main__":
    try:
        raise SystemExit(_desktop_app.main())
    except Exception as exc:
        print(f"NEXUS-DASH desktop startup failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
else:
    sys.modules[__name__] = _desktop_app
