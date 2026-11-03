"""Desktop shell platform-selection tests."""

import pytest

from nexus_dash.desktop.app import desktop_gui_backend


def test_desktop_gui_backend_selects_native_backend():
    assert desktop_gui_backend("Windows") == "edgechromium"
    assert desktop_gui_backend("Linux") == "gtk"
    assert desktop_gui_backend("Darwin") == "cocoa"


def test_desktop_gui_backend_rejects_unsupported_platform():
    with pytest.raises(RuntimeError, match="not supported"):
        desktop_gui_backend("FreeBSD")
