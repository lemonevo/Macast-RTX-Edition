"""Setuptools build hooks and runtime dependencies for source installs."""

from pathlib import Path

from setuptools import find_packages, setup
from setuptools.command.build_py import build_py


class BuildWithTranslations(build_py):
    """Include compiled gettext catalogs in installed wheels."""

    def run(self):
        super().run()
        from babel.messages.mofile import write_mo
        from babel.messages.pofile import read_po

        source_root = Path(__file__).resolve().parent / "i18n"
        target_root = Path(self.build_lib) / "macast" / "i18n"
        for po_path in sorted(source_root.glob("*/LC_MESSAGES/macast.po")):
            locale_name = po_path.parents[1].name
            target = target_root / locale_name / "LC_MESSAGES" / "macast.mo"
            target.parent.mkdir(parents=True, exist_ok=True)
            with po_path.open("r", encoding="utf-8") as source_file:
                catalog = read_po(source_file, locale=locale_name)
            with target.open("wb") as output_file:
                write_mo(output_file, catalog)


INSTALL = [
    "CherryPy==18.10.0",
    "lxml==6.1.1",
    "netifaces-plus==0.12.5",
    "packaging==26.2",
    "platformdirs==4.11.0",
    "requests==2.34.2",
    "pyperclip==1.11.0",
    'rumps>=0.4.0; sys_platform == "darwin"',
    'Pillow==12.3.0; sys_platform != "darwin"',
    'pystray==0.19.5; sys_platform != "darwin"',
]

setup(
    install_requires=INSTALL,
    packages=find_packages(),
    include_package_data=True,
    package_data={"macast": ["i18n/*/LC_MESSAGES/*.mo"]},
    cmdclass={"build_py": BuildWithTranslations},
)
