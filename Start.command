#!/bin/bash
set -euo pipefail
project_root="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
venv_python="$project_root/.venv/bin/python"
requirements="$project_root/requirements.txt"
marker="$project_root/.venv/studio-requirements.sha256"

if [ ! -x "$venv_python" ]; then
    if ! command -v python3 >/dev/null 2>&1; then
        echo "Python 3.10+ bulunamadi. Python kurup yeniden deneyin." >&2
        exit 1
    fi
    python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else "Python 3.10+ gerekli.")'
    python3 -m venv "$project_root/.venv"
fi
"$venv_python" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else "Proje .venv ortami Python 3.10+ ile olusturulmali.")'
requirements_hash="$("$venv_python" -c 'import hashlib, pathlib, sys; print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())' "$requirements")"
installed_hash=""
if [ -f "$marker" ]; then installed_hash="$(cat "$marker")"; fi
if [ "$installed_hash" != "$requirements_hash" ] || ! "$venv_python" -c 'import PySide6, serial' >/dev/null 2>&1; then
    "$venv_python" -m pip install --disable-pip-version-check -r "$requirements"
    printf '%s' "$requirements_hash" > "$marker"
fi
cd "$project_root"
exec "$venv_python" "$project_root/studio.py" "$@"
