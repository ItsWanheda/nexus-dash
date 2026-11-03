"""Cross-platform NEXUS-DASH desktop shell (PyWebView + optional tray)."""
from __future__ import annotations

import argparse
import http.client
import json
import os
import platform
import sys
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = Path(getattr(sys, "_MEIPASS", PROJECT_ROOT))


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        return


class LocalStaticServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False


def desktop_gui_backend(system: str | None = None) -> str:
    """Return the supported pywebview backend for the current operating system."""
    current = (system or platform.system()).casefold()
    backends = {"windows": "edgechromium", "linux": "gtk", "darwin": "cocoa"}
    try:
        return backends[current]
    except KeyError as exc:
        raise RuntimeError(f"Desktop mode is not supported on {system or platform.system()}.") from exc


def register_windows_startup(enabled: bool) -> None:
    if platform.system() != "Windows":
        raise RuntimeError("Automatic startup registration is supported on Windows only.")
    import winreg

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        if enabled:
            if getattr(sys, "frozen", False):
                command = f'"{Path(sys.executable).resolve()}" --minimized'
            else:
                command = f'"{Path(sys.executable).resolve()}" "{PROJECT_ROOT / "desktop_app.py"}" --minimized'
            winreg.SetValueEx(key, "NEXUS-DASH", 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, "NEXUS-DASH")
            except FileNotFoundError:
                pass


def _desktop_api_healthy() -> bool:
    connection = None
    try:
        connection = http.client.HTTPConnection("127.0.0.1", 8000, timeout=1)
        connection.request("GET", "/api/health")
        response = connection.getresponse()
        body = json.loads(response.read(4096).decode("utf-8"))
        return response.status == 200 and body.get("desktop_runtime") is True
    except (OSError, ValueError, http.client.HTTPException):
        return False
    finally:
        if connection:
            connection.close()


def _create_tray(window):
    """Create a tray icon when the platform backend supports it; otherwise return None."""
    try:
        import pystray
        from PIL import Image, ImageDraw

        image = Image.new("RGBA", (64, 64), (8, 12, 9, 255))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((5, 5, 59, 59), radius=12, outline=(95, 255, 145, 255), width=3)
        draw.text((19, 15), "N", fill=(95, 255, 145, 255))

        def show_window(icon=None, item=None):
            try:
                window.show()
                window.restore()
            except Exception:
                pass

        def quit_app(icon=None, item=None):
            try:
                icon.stop()
            except Exception:
                pass
            try:
                window.destroy()
            except Exception:
                pass

        return pystray.Icon(
            "NEXUS-DASH",
            image,
            "NEXUS-DASH",
            menu=pystray.Menu(
                pystray.MenuItem("Open NEXUS", show_window, default=True),
                pystray.MenuItem("Quit", quit_app),
            ),
        )
    except Exception:
        # A tray implementation is optional; the main desktop window must still work.
        return None


def run_desktop(minimized: bool = False) -> int:
    backend = desktop_gui_backend()
    os.environ["NEXUS_DESKTOP_RUNTIME"] = "1"

    import uvicorn
    import webview
    from nexus_dash.services.settings_store import SettingsStore
    from nexus_dash.api.server import app

    data_dir = Path(os.environ.get("NEXUS_DATA_DIR", Path.home() / ".nexus-dash")).expanduser()
    hide_on_start = minimized or bool(SettingsStore(data_dir).get().get("start_minimized"))
    static = LocalStaticServer(("127.0.0.1", 5500), partial(QuietHandler, directory=str(APP_ROOT)))
    static_thread = threading.Thread(target=static.serve_forever, name="nexus-static", daemon=True)
    static_thread.start()
    api = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="warning", access_log=False)
    )
    api_thread = threading.Thread(target=api.run, name="nexus-api", daemon=True)
    api_thread.start()
    icon = None
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and not api.started:
            if not api_thread.is_alive():
                raise RuntimeError("The NEXUS local API failed to start.")
            time.sleep(0.1)
        if not api.started or not _desktop_api_healthy():
            raise RuntimeError(
                "Could not verify the desktop API on 127.0.0.1:8000. "
                "Close another NEXUS/API instance."
            )
        window = webview.create_window(
            "NEXUS-DASH",
            "http://127.0.0.1:5500/",
            width=1440,
            height=920,
            min_size=(960, 640),
            background_color="#080c09",
            hidden=hide_on_start,
        )
        icon = _create_tray(window)
        if icon is not None:
            threading.Thread(target=icon.run, name="nexus-tray", daemon=True).start()

        def on_closing():
            if icon is None:
                return True
            try:
                window.hide()
                return False
            except Exception:
                return True

        window.events.closing += on_closing
        webview.start(debug=False, gui=backend)
    finally:
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass
        api.should_exit = True
        static.shutdown()
        static.server_close()
        api_thread.join(timeout=4)
        static_thread.join(timeout=2)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="NEXUS-DASH desktop application")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--register-startup", action="store_true")
    group.add_argument("--remove-startup", action="store_true")
    parser.add_argument("--minimized", action="store_true")
    args = parser.parse_args()
    if args.register_startup:
        register_windows_startup(True)
        return 0
    if args.remove_startup:
        register_windows_startup(False)
        return 0
    return run_desktop(args.minimized)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"NEXUS-DASH desktop startup failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
