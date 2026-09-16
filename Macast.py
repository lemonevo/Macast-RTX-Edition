"""Run Macast directly from a source checkout or a bundled application."""

from macast.macast import cli_entry, gui_entry


if __name__ == '__main__':
    gui_entry()
