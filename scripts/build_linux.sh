#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
python -m pip install -e '.[build]'
python -m PyInstaller --clean --noconfirm campus_flow.spec
printf 'Aplicación generada en %s/dist/CampusFlow\n' "$project_dir"
