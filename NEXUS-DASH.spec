from PyInstaller.utils.hooks import collect_all

webview_datas, webview_binaries, webview_hidden = collect_all("webview")
tray_datas, tray_binaries, tray_hidden = collect_all("pystray")
pil_datas, pil_binaries, pil_hidden = collect_all("PIL")
try:
    adlx_datas, adlx_binaries, adlx_hidden = collect_all("adlx")
except Exception:
    adlx_datas, adlx_binaries, adlx_hidden = [], [], []
a = Analysis(
    ["desktop_app.py"], pathex=[],
    binaries=webview_binaries + tray_binaries + pil_binaries + adlx_binaries,
    datas=[("index.html", "."), ("src", "src")] + webview_datas + tray_datas + pil_datas + adlx_datas,
    hiddenimports=webview_hidden + tray_hidden + pil_hidden + adlx_hidden + [
        "uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto",
        "uvicorn.lifespan.on", "webview.platforms.edgechromium",
    ],
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=["tkinter"], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="NEXUS-DASH",
          debug=False, bootloader_ignore_signals=False, strip=False, upx=True,
          console=False, disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=True, upx_exclude=[], name="NEXUS-DASH")
