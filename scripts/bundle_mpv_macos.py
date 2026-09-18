#!/usr/bin/env python3
"""Collect mpv and its non-system libraries into one self-contained directory.

macOS has no static mpv build, so the Homebrew binary has to be shipped together
with its dylibs. Those dylibs are referenced through absolute /opt/homebrew
paths, which do not exist on a machine without Homebrew, so every reference is
rewritten to @executable_path/@loader_path and the files are signed again.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess


def run(*args: str) -> str:
    """Run a command, raising with its stderr when it fails."""
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"{args[0]} failed for {args[-1]}:\n{result.stderr}")
    return result.stdout


def dependencies(path: str) -> list[str]:
    """Non-system libraries the given Mach-O file links against."""
    found = []
    for line in run("otool", "-L", path).splitlines()[1:]:
        linked = line.strip().split(" (")[0].strip()
        if not linked.startswith("/"):
            continue
        if linked.startswith("/usr/lib/") or linked.startswith("/System/"):
            continue
        found.append(linked)
    return found


def collect(root_binary: str) -> dict[str, str]:
    """Walk the dependency graph, keyed by real path so the /opt and /Cellar
    aliases of the same library collapse into one entry."""
    found: dict[str, str] = {}
    pending = [os.path.realpath(root_binary)]
    while pending:
        current = pending.pop()
        if current in found or not os.path.exists(current):
            continue
        found[current] = os.path.basename(current)
        pending.extend(os.path.realpath(dep) for dep in dependencies(current))
    return found


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mpv", required=True, help="path to the mpv binary")
    parser.add_argument("--output", required=True, help="staging directory")
    args = parser.parse_args()

    mpv_real = os.path.realpath(args.mpv)
    if not os.path.isfile(mpv_real):
        raise SystemExit(f"mpv not found: {args.mpv}")

    libraries = collect(mpv_real)

    names: dict[str, str] = {}
    for real, name in libraries.items():
        if name in names:
            raise SystemExit(f"two libraries share the name {name}")
        names[name] = real

    output = os.path.abspath(args.output)
    shutil.rmtree(output, ignore_errors=True)
    os.makedirs(output)

    # Everything is flattened into one directory so the rewritten references can
    # be resolved against the loader's own location.
    staged: list[str] = []
    for name, real in sorted(names.items()):
        # collect() starts from mpv itself, so leave it out here: it is staged
        # below with @executable_path references rather than @loader_path ones.
        if real == mpv_real:
            continue
        target = os.path.join(output, name)
        shutil.copy2(real, target)
        os.chmod(target, 0o755)
        staged.append(target)

    mpv_target = os.path.join(output, os.path.basename(mpv_real))
    shutil.copy2(mpv_real, mpv_target)
    os.chmod(mpv_target, 0o755)

    # A library's own install name has to match how the others refer to it.
    for target in staged:
        run("install_name_tool", "-id",
            f"@loader_path/{os.path.basename(target)}", target)

    for target in staged:
        for linked in dependencies(target):
            run("install_name_tool", "-change", linked,
                f"@loader_path/{os.path.basename(os.path.realpath(linked))}",
                target)

    for linked in dependencies(mpv_target):
        run("install_name_tool", "-change", linked,
            f"@executable_path/{os.path.basename(os.path.realpath(linked))}",
            mpv_target)

    # Editing load commands invalidates the signature, and arm64 refuses to run
    # code without a valid one, so every file is signed again ad hoc.
    for target in staged + [mpv_target]:
        run("codesign", "--force", "--sign", "-", target)

    print(f"staged mpv and {len(staged)} libraries into {output}")


if __name__ == "__main__":
    main()
