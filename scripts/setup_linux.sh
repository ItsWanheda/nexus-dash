#!/usr/bin/env bash
set -Eeuo pipefail

APP_NAME="NEXUS-DASH"
SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
BIN_HOME="${XDG_BIN_HOME:-$HOME/.local/bin}"
APP_DIR="$DATA_HOME/nexus-dash"
VENV="$APP_DIR/.venv"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "This installer is for Linux only." >&2
  exit 1
fi
if ! command -v apt-get >/dev/null 2>&1; then
  echo "This setup currently supports Debian and Ubuntu (apt)." >&2
  exit 1
fi
if [[ "$EUID" -eq 0 ]]; then
  echo "Run this installer as your regular desktop user; it will use sudo only for apt packages." >&2
  exit 1
fi
if ! command -v sudo >/dev/null 2>&1; then
  echo "sudo is required to install GTK/WebKitGTK system dependencies." >&2
  exit 1
fi
SUDO=(sudo)

echo "Refreshing apt package indexes..."
"${SUDO[@]}" apt-get update

WEBKIT_VERSION=""
for version in 4.1 4.0; do
  if apt-cache show "libwebkit2gtk-$version-0" >/dev/null 2>&1 &&
     apt-cache show "gir1.2-webkit2-$version" >/dev/null 2>&1; then
    WEBKIT_VERSION="$version"
    break
  fi
done
if [[ -z "$WEBKIT_VERSION" ]]; then
  echo "Could not find WebKitGTK 4.1 or 4.0 packages in configured apt repositories." >&2
  exit 1
fi

echo "Installing GTK/WebKit system dependencies (WebKitGTK $WEBKIT_VERSION)..."
"${SUDO[@]}" apt-get install -y \
  python3 python3-venv python3-pip python3-gi python3-gi-cairo \
  gir1.2-gtk-3.0 "libwebkit2gtk-$WEBKIT_VERSION-0" "gir1.2-webkit2-$WEBKIT_VERSION"

mkdir -p "$APP_DIR" "$BIN_HOME"
if [[ "$SOURCE_DIR" != "$APP_DIR" ]]; then
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete --exclude='.git' --exclude='.venv' "$SOURCE_DIR/" "$APP_DIR/"
  else
    find "$APP_DIR" -mindepth 1 -maxdepth 1 ! -name '.venv' -exec rm -rf {} +
    cp -a "$SOURCE_DIR/." "$APP_DIR/"
    rm -rf "$APP_DIR/.git"
  fi
fi

python3 -m venv --system-site-packages "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install -r "$APP_DIR/requirements-desktop.txt"

cat > "$BIN_HOME/nexus-dash" <<EOF
#!/usr/bin/env bash
exec "$VENV/bin/python" "$APP_DIR/desktop_app.py" "\$@"
EOF
chmod 755 "$BIN_HOME/nexus-dash"

mkdir -p "$DATA_HOME/applications"
cat > "$DATA_HOME/applications/nexus-dash.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=NEXUS-DASH
Comment=Local-first system monitoring and diagnostics
Exec=$BIN_HOME/nexus-dash
Icon=utilities-system-monitor
Terminal=false
Categories=System;Monitor;
StartupNotify=true
EOF
chmod 644 "$DATA_HOME/applications/nexus-dash.desktop"

echo
echo "NEXUS-DASH is installed."
echo "Launch with: $BIN_HOME/nexus-dash"
if [[ ":$PATH:" != *":$BIN_HOME:"* ]]; then
  echo "Tip: add $BIN_HOME to PATH to run 'nexus-dash' from any terminal."
fi
