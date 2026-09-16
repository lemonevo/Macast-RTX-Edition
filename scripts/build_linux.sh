#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != Linux ]]; then
    echo 'This build script must run on Linux.' >&2
    exit 1
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${PYTHON:-python3}"
version="$(<"$repo_root/macast/.version")"
arch="$(uname -m)"
output_root="${1:-$repo_root/.build/linux-v$version-$arch}"

if [[ -e "$output_root" ]]; then
    echo "Refusing to overwrite $output_root" >&2
    exit 1
fi

"$python_bin" -c 'import PyInstaller, babel' || {
    echo 'Install requirements/build-linux.txt in the build environment first.' >&2
    exit 1
}
"$python_bin" -c 'import gi; gi.require_version("Gtk", "3.0"); from gi.repository import Gtk; import pystray; assert pystray.Icon.__module__ == "pystray._appindicator"' || {
    echo 'The build Python must see system python3-gi and AppIndicator; create its venv with --system-site-packages.' >&2
    exit 1
}
command -v mpv >/dev/null || {
    echo 'Install the system mpv player first.' >&2
    exit 1
}

mkdir -p "$output_root/i18n" "$output_root/dist"
"$python_bin" "$repo_root/scripts/compile_translations.py" \
    --source "$repo_root/i18n" --output "$output_root/i18n"

name="Macast-RTX-Edition-v$version-linux-$arch"
"$python_bin" -m PyInstaller --onefile --noconfirm \
    --name "$name" \
    --workpath "$output_root/work" \
    --distpath "$output_root/dist" \
    --specpath "$output_root" \
    --additional-hooks-dir "$repo_root" \
    --add-data "$repo_root/macast/.version:." \
    --add-data "$repo_root/macast/xml:macast/xml" \
    --add-data "$repo_root/macast/assets:macast/assets" \
    --add-data "$repo_root/macast/scripts:macast/scripts" \
    --add-data "$output_root/i18n:i18n" \
    "$repo_root/Macast.py"

(cd "$output_root/dist" && sha256sum "$name" > SHA256SUMS.txt)
echo "Built $output_root/dist/$name"
echo 'The target machine also needs mpv and a supported desktop tray backend.'
