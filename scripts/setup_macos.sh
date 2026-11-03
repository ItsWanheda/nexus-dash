#!/usr/bin/env bash
set -Eeuo pipefail

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/Library/Application Support}"
BIN_HOME="${XDG_BIN_HOME:-$HOME/.local/bin}"
APP_DIR="$DATA_HOME/NEXUS-DASH"
VENV="$APP_DIR/.venv"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This installer is for macOS only." >&2
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3.10+ is required. Install Python from python.org or Homebrew first." >&2
  exit 1
fi
PYTHON_VERSION="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' || {
  echo "Python 3.10 or newer is required (found $PYTHON_VERSION)." >&2
  exit 1
}

mkdir -p "$APP_DIR" "$BIN_HOME" "$HOME/Applications"
if [[ "$SOURCE_DIR" != "$APP_DIR" ]]; then
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete --exclude='.git' --exclude='.venv' "$SOURCE_DIR/" "$APP_DIR/"
  else
    find "$APP_DIR" -mindepth 1 -maxdepth 1 ! -name '.venv' -exec rm -rf {} +
    cp -a "$SOURCE_DIR/." "$APP_DIR/"
    rm -rf "$APP_DIR/.git"
  fi
fi

python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install -r "$APP_DIR/requirements-desktop.txt"

cat > "$BIN_HOME/nexus-dash" <<EOF
#!/usr/bin/env bash
exec "$VENV/bin/python" "$APP_DIR/desktop_app.py" "\$@"
EOF
chmod 755 "$BIN_HOME/nexus-dash"

cat > "$HOME/Applications/NEXUS-DASH.command" <<EOF
#!/bin/bash
"$BIN_HOME/nexus-dash"
EOF
mkdir -p "$HOME/Applications"
chmod 755 "$HOME/Applications/NEXUS-DASH.command"

echo
echo "NEXUS-DASH is installed."
echo "Launch from Terminal with: $BIN_HOME/nexus-dash"
echo "Or double-click: $HOME/Applications/NEXUS-DASH.command"
if [[ ":$PATH:" != *":$BIN_HOME:"* ]]; then
  echo "Tip: add $BIN_HOME to PATH to run 'nexus-dash' from any terminal."
fi
