"""Compatibility setup.py for editable/source installs."""

import sys
from setuptools import setup, find_packages

VERSION = "0.0.0"
with open("macast/.version", "r", encoding="utf-8") as f:
    VERSION = f.read().strip()
with open("README.md", "r", encoding="utf-8") as f:
    LONG_DESCRIPTION = f.read()
OPTIONS = {}
INSTALL = [
    "CherryPy==18.10.0",
    "lxml==6.1.1",
    "netifaces-plus==0.12.5",
    "packaging==26.2",
    "platformdirs==4.11.0",
    "requests==2.34.2",
]
PACKAGES = find_packages()

if sys.platform == "darwin":
    INSTALL += ["rumps>=0.4.0", "pyperclip==1.11.0"]
elif sys.platform == "win32":
    INSTALL += [
        "Pillow==12.3.0",
        "pyperclip==1.11.0",
        "pystray==0.19.5",
    ]
else:
    INSTALL += [
        "Pillow==12.3.0",
        "pyperclip==1.11.0",
        "pystray==0.19.5",
    ]

setup(
    name="macast-rtx-edition",
    version=VERSION,
    author="Macast contributors and ccjjxx99",
    description="A lightweight DLNA Media Renderer with NVIDIA RTX Video support",
    license="GPL-3.0-or-later",
    url="https://github.com/ccjjxx99/Macast-RTX-Edition",
    long_description=LONG_DESCRIPTION,
    long_description_content_type="text/markdown",
    classifiers=[
        "Topic :: Multimedia :: Sound/Audio",
        "Topic :: Multimedia :: Video",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: MacOS :: MacOS X",
        "Operating System :: Microsoft :: Windows :: Windows 10",
        "Operating System :: POSIX",
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
    ],
    platforms=["MacOS X", "Windows", "POSIX"],
    keywords=["mpv", "dlna", "renderer", "nvidia", "rtx", "vsr", "hdr"],
    options=OPTIONS,
    install_requires=INSTALL,
    packages=PACKAGES,
    include_package_data=True,
    entry_points={
        "console_scripts": [
            "macast-rtx-cli = macast.macast:cli",
            "macast-rtx-gui = macast.macast:gui",
        ]
    },
    python_requires=">=3.10",
)
