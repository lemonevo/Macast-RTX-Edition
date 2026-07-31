"""Compile gettext PO catalogs into a separate build directory."""

from __future__ import annotations

import argparse
from pathlib import Path

from babel.messages.mofile import write_mo
from babel.messages.pofile import read_po


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    for po_path in sorted(args.source.glob("*/LC_MESSAGES/macast.po")):
        locale_name = po_path.parents[1].name
        output_path = args.output / locale_name / "LC_MESSAGES" / "macast.mo"
        if output_path.exists():
            raise FileExistsError(f"Refusing to overwrite {output_path}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with po_path.open("r", encoding="utf-8") as source_file:
            catalog = read_po(source_file, locale=locale_name)
        with output_path.open("wb") as output_file:
            write_mo(output_file, catalog)
        print(output_path)


if __name__ == "__main__":
    main()
