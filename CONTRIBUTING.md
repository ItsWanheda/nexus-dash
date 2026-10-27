# Contributing to NEXUS-DASH

Thanks for contributing to NEXUS-DASH. The project is a local-first system monitoring application; contributions should preserve its security boundary and cyberpunk visual identity.

## Development setup

    git clone https://github.com/ItsWanheda/nexus-dash.git
    cd nexus-dash
    python -m venv .venv

Activate the environment:

**Windows PowerShell**

    .\.venv\Scripts\Activate.ps1

**Linux / macOS**

    source .venv/bin/activate

Install runtime and test dependencies:

    python -m pip install -r requirements-dev.txt

Start the API and UI in two terminals:

    python server.py
    python -m http.server 5500 --bind 127.0.0.1

Then open http://127.0.0.1:5500.

## Engineering rules

- Keep the API on loopback and preserve origin/host checks. Do not add public network access or credentialed CORS.
- Never add arbitrary shell execution, shell command chaining, eval, or unrestricted process control.
- Treat hardware counters and OS event sources as best-effort; unsupported metrics/sources must be marked unavailable rather than fabricated.
- Diagnostic findings must expose evidence and limitations. Never label correlation as causation or infer a memory leak from one increasing RSS series.
- Bound process snapshots, historical storage, request inputs, and export sizes.
- Keep persistent telemetry privacy-conscious. Do not store hostnames, usernames, command lines, or executable paths in resource history without a separately reviewed design.
- Use accessible controls, keyboard focus states, reduced-motion support, and responsive layouts; preserve the dark/neon-green visual direction.
- Keep frontend JavaScript dependency-free unless a dependency is justified and documented.

## Validation

Run before opening a pull request:

    node --check src/static/app.js
    node --check src/static/flight-recorder.js
    node --check src/static/diagnostics.js
    python -m compileall -q server.py telemetry_store.py diagnostics.py tests
    python -m pytest -q

For UI changes, manually verify the relevant routes at desktop and mobile widths. For process features, test under a standard user account on supported operating systems and avoid terminating processes containing unsaved work.

## Pull request checklist

- [ ] Explain user-visible changes and security implications.
- [ ] Add or update automated tests.
- [ ] Update README.md, CHANGELOG.md, and relevant documentation.
- [ ] Confirm no secrets, local database files, exports, or generated artefacts are committed.
- [ ] Keep changes focused; do not combine unrelated refactors.
