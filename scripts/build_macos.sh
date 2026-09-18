#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != Darwin ]]; then
    echo 'This build script must run on macOS.' >&2
    exit 1
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${PYTHON:-python3}"
version="$(<"$repo_root/macast/.version")"
arch="$(uname -m)"
output_root="${1:-$repo_root/.build/macos-v$version-$arch}"

# PyInstaller resolves the --add-data sources relative to the spec file, so a
# relative output root would be applied twice.
if [[ "$output_root" != /* ]]; then
    output_root="$PWD/$output_root"
fi

if [[ -e "$output_root" ]]; then
    echo "Refusing to overwrite $output_root" >&2
    exit 1
fi

"$python_bin" -c 'import PyInstaller, babel' || {
    echo 'Install requirements/build-macos.txt in the build environment first.' >&2
    exit 1
}
mpv_binary="$(command -v mpv || true)"
if [[ -z "$mpv_binary" ]]; then
    echo 'Install the mpv player first (brew install mpv).' >&2
    exit 1
fi

mkdir -p "$output_root/i18n" "$output_root/dist"
"$python_bin" "$repo_root/scripts/compile_translations.py" \
    --source "$repo_root/i18n" --output "$output_root/i18n"

# Homebrew ships no static mpv, so the binary is bundled together with its
# dylibs and every load command is rewritten to @executable_path/@loader_path.
# Without this the app only works when it can find mpv through PATH, which a
# bundle opened from Finder does not have.
mpv_staging="$output_root/mpv"
"$python_bin" "$repo_root/scripts/bundle_mpv_macos.py" \
    --mpv "$mpv_binary" --output "$mpv_staging"

app_name="Macast-RTX-Edition"
"$python_bin" -m PyInstaller --windowed --noconfirm \
    --name "$app_name" \
    --osx-bundle-identifier "cn.xfangfang.Macast" \
    --icon "$repo_root/macast/assets/icon.icns" \
    --workpath "$output_root/work" \
    --distpath "$output_root/dist" \
    --specpath "$output_root" \
    --add-data "$repo_root/macast/.version:." \
    --add-data "$repo_root/macast/xml:macast/xml" \
    --add-data "$repo_root/macast/assets:macast/assets" \
    --add-data "$repo_root/macast/scripts:macast/scripts" \
    --add-data "$output_root/i18n:i18n" \
    --add-data "$mpv_staging:bin/MacOS" \
    "$repo_root/Macast.py"

app_path="$output_root/dist/$app_name.app"
info_plist="$app_path/Contents/Info.plist"

# PyInstaller cannot set these from the command line. The menu bar app must set
# LSUIElement so it does not occupy a Dock slot, and the bundle version must
# match macast/.version instead of PyInstaller's 0.0.0 default.
plutil -replace CFBundleShortVersionString -string "$version" "$info_plist"
plutil -replace CFBundleVersion -string "$version" "$info_plist"
if ! plutil -insert LSUIElement -bool true "$info_plist" 2>/dev/null; then
    plutil -replace LSUIElement -bool true "$info_plist"
fi
if ! plutil -insert LSMinimumSystemVersion -string "11.0" "$info_plist" 2>/dev/null; then
    plutil -replace LSMinimumSystemVersion -string "11.0" "$info_plist"
fi

# Editing Info.plist invalidates the bundle signature, so sign it again. This
# also signs the bundled mpv and its dylibs that were rewritten above.
codesign --force --deep --sign - "$app_path"

name="Macast-RTX-Edition-v$version-macos-$arch"
dmg_root="$output_root/dmg"
mkdir -p "$dmg_root"
cp -R "$app_path" "$dmg_root/"
ln -s /Applications "$dmg_root/Applications"
hdiutil create -volname "$app_name" -srcfolder "$dmg_root" \
    -ov -format UDZO "$output_root/dist/$name.dmg" -quiet
(cd "$output_root/dist" && shasum -a 256 "$name.dmg" > SHA256SUMS-macos.txt)

echo "Built $output_root/dist/$name.dmg"
echo 'mpv is bundled, so the target machine does not need it installed.'
echo 'The bundle is ad-hoc signed only, so the first launch needs right-click > Open.'
