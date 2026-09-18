# Copyright (c) 2021 by xfangfang. All Rights Reserved.

import os
import sys
import uuid
import json
import time
import threading
import ctypes
import logging
import platform
import locale
import cherrypy
import subprocess
from enum import Enum
import netifaces as ni
from platformdirs import user_config_dir

if sys.platform == 'darwin':
    from AppKit import NSBundle
elif sys.platform == 'win32':
    import winreg

logger = logging.getLogger("Utils")
DEFAULT_PORT = 0
SETTING_DIR = user_config_dir("Macast-RTX-Edition", "ccjjxx99")
PROTOCOL_DIR = 'protocol'
RENDERER_DIR = 'renderer'


def validate_settings(settings):
    """Validate built-in settings before replacing the complete settings file.

    Unknown keys belong to plugins and are left untouched.
    """
    if not isinstance(settings, dict) or any(not isinstance(key, str) for key in settings):
        raise ValueError('Settings must be a JSON object with string keys')

    ranges = {
        'ApplicationPort': (0, 65535),
        'PlayerSize': (0, 4),
        'PlayerPosition': (0, 4),
        'PlayerHW': (0, 2),
        'PlayerOntop': (0, 1),
        'PlayerDefaultVolume': (0, 100),
        'RTXVideoVSR': (0, 1),
        'RTXVideoHDR': (0, 1),
        'StartAtLogin': (0, 1),
        'CheckUpdate': (0, 1),
        'MenubarIcon': (0, 1),
    }
    for key, (minimum, maximum) in ranges.items():
        if key in settings and (type(settings[key]) is not int or
                                not minimum <= settings[key] <= maximum):
            raise ValueError('Invalid ' + key)

    for key in ('Additional_Interfaces', 'Blocked_Interfaces'):
        if key in settings and (not isinstance(settings[key], list) or
                                any(not isinstance(item, str) for item in settings[key])):
            raise ValueError('Invalid ' + key)

    for key in ('USN', 'DLNA_FriendlyName', 'Macast_Renderer', 'Macast_Protocol'):
        if key in settings and (not isinstance(settings[key], str) or not settings[key]):
            raise ValueError('Invalid ' + key)

    if 'RTXVideoCapabilityState' in settings and settings['RTXVideoCapabilityState'] not in (
            'supported', 'unsupported', 'unknown'):
        raise ValueError('Invalid RTXVideoCapabilityState')


class SettingProperty(Enum):
    USN = 0
    CheckUpdate = 1
    StartAtLogin = 2
    MenubarIcon = 3
    ApplicationPort = 4
    DLNA_FriendlyName = 5
    Macast_Renderer = 6
    Macast_Protocol = 7
    Blocked_Interfaces = 8
    Additional_Interfaces = 9


class Setting:
    setting = {}
    loaded = False
    version = None
    setting_path = os.path.join(SETTING_DIR, "macast_setting.json")
    last_ip = None
    base_path = None
    friendly_name = "Macast RTX ({})".format(platform.node())
    temp_friendly_name = None
    mpv_default_path = 'mpv'

    @staticmethod
    def save():
        """Save user settings
        """
        if not os.path.exists(SETTING_DIR):
            os.makedirs(SETTING_DIR)
        with open(Setting.setting_path, "w", encoding="utf-8") as f:
            json.dump(obj=Setting.setting, fp=f, sort_keys=True, indent=4)

    @staticmethod
    def load():
        """Load user settings
        """
        logger.info("Load Setting")
        if Setting.version is None:
            try:
                with open(Setting.get_base_path('.version'), 'r', encoding="utf-8") as f:
                    Setting.version = f.read().strip()
            except FileNotFoundError as e:
                Setting.version = "0.0"
        if not Setting.loaded:
            if not os.path.exists(Setting.setting_path):
                Setting.setting = {}
            else:
                try:
                    with open(Setting.setting_path, "r", encoding="utf-8") as f:
                        Setting.setting = json.load(fp=f)
                    logger.error(Setting.setting)
                except Exception as e:
                    logger.error(e)
            Setting.loaded = True
        return Setting.setting

    @staticmethod
    def reload():
        Setting.setting = {}
        Setting.loaded = False
        Setting.load()

    @staticmethod
    def get_system_version():
        """Get system version
        """
        return str(platform.release())

    @staticmethod
    def get_system():
        """Get system name
        """
        return str(platform.system())

    @staticmethod
    def get_version():
        """Get application version
        """
        return Setting.version

    @staticmethod
    def get_friendly_name():
        """Get application friendly name
        This name will show in the device search list of the DLNA client
        and as player window default name.
        """
        if Setting.temp_friendly_name:
            return Setting.temp_friendly_name
        return Setting.get(SettingProperty.DLNA_FriendlyName, Setting.friendly_name)

    @staticmethod
    def set_temp_friendly_name(name):
        Setting.temp_friendly_name = name

    @staticmethod
    def get_usn(refresh=False):
        """Get device unique identification
        """
        dlna_id = str(uuid.uuid4())
        if not refresh:
            dlna_id_temp = Setting.get(SettingProperty.USN, dlna_id)
            if dlna_id == dlna_id_temp:
                Setting.set(SettingProperty.USN, dlna_id)
            return dlna_id_temp
        else:
            Setting.set(SettingProperty.USN, dlna_id)
            return dlna_id

    @staticmethod
    def is_ip_changed():
        if Setting.last_ip != Setting.get_ip():
            return True
        return False

    @staticmethod
    def get_ip():
        last_ip = []
        gateways = ni.gateways()  # {type: [{ip, interface, default},{},...], type: []}
        interfaces = set(Setting.get(SettingProperty.Additional_Interfaces, []))
        if sys.platform == 'linux':
            # Linux hosts commonly have Docker, VPN and tunnel interfaces.
            # Prefer the IPv4 default route. netifaces may omit it when an
            # IPv6 default route is present, so fall back to IPv4 gateway
            # interfaces rather than silently advertising on no interface.
            default_route = gateways.get('default', {}).get(ni.AF_INET)
            if default_route and len(default_route) > 1:
                interfaces.add(default_route[1])
            else:
                for route in gateways.get(ni.AF_INET, []):
                    if len(route) > 1:
                        interfaces.add(route[1])
        else:
            interface_type = [ni.AF_INET, ni.AF_LINK]
            for t in interface_type:
                if t in gateways:
                    for i in gateways[t]:
                        if len(i) > 1:
                            interfaces.add(i[1])
        for i in Setting.get(SettingProperty.Blocked_Interfaces, []):
            if i in interfaces:
                interfaces.remove(i)
        logger.debug(interfaces)
        for i in interfaces:
            try:
                iface = ni.ifaddresses(i)
            except ValueError as e:
                continue
            if ni.AF_INET in iface:
                for j in iface[ni.AF_INET]:
                    if 'addr' in j and 'netmask' in j:
                        last_ip.append((j['addr'], j['netmask']))
        Setting.last_ip = set(last_ip)
        logger.debug(Setting.last_ip)
        return Setting.last_ip

    @staticmethod
    def get_port():
        """Get application port
        """
        return Setting.get(SettingProperty.ApplicationPort, DEFAULT_PORT)

    @staticmethod
    def get_locale():
        """Get the language settings of the system
        Default: en_US
        """
        if sys.platform == 'darwin':
            lang = subprocess.check_output(
                ["osascript", "-e",
                 "user locale of (get system info)"]).decode().strip()
        elif sys.platform == 'win32':
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            get_language = kernel32.GetUserDefaultUILanguage
            get_language.restype = ctypes.c_ushort
            lang = locale.windows_locale.get(get_language(), "en_US")
        else:
            lang = os.environ.get('LANGUAGE')
            if lang is None:
                lang = os.environ.get('LANG', 'en_US')
            if lang is None:
                return 'en_US'
            lang = lang.split(':')[0].split('.')[0]
        return lang

    @staticmethod
    def get(property, default=1):
        """Get application settings
        """
        if not Setting.loaded:
            Setting.load()
        if property.name in Setting.setting:
            return Setting.setting[property.name]
        Setting.setting[property.name] = default
        return default

    @staticmethod
    def set(property, data):
        """Set application settings
        """
        if not Setting.loaded:
            Setting.load()
        Setting.setting[property.name] = data
        Setting.save()

    @staticmethod
    def system_shell(shell):
        result = subprocess.run(shell, stdout=subprocess.PIPE)
        return result.returncode, result.stdout.decode('UTF-8').strip()

    @staticmethod
    def set_start_at_login(launch):
        if sys.platform == 'darwin':
            app_path = NSBundle.mainBundle().bundlePath()
            if not app_path.startswith("/Applications"):
                return (1, "You need move Macast.app to Applications folder.")
            app_name = app_path.split("/")[-1].split(".")[0]
            res = Setting.system_shell(
                ['osascript',
                 '-e',
                 'tell application "System Events" ' +
                 'to get the name of every login item'])
            if res[0] == 1:
                return (1, "Cannot access System Events.")
            apps = list(map(lambda app: app.strip(), res[1].split(",")))
            # apps which start at login
            if launch:
                if app_name in apps:
                    return (0, "Macast is already in login items.")
                res = Setting.system_shell(
                    ['osascript',
                     '-e',
                     'tell application "System Events" ' +
                     'to make login item at end with properties ' +
                     '{{name: "{}",path:"{}", hidden:false}}'.format(
                         app_name, app_path)
                     ])
            else:
                if app_name not in apps:
                    return (0, "Macast is already not in login items.")
                res = Setting.system_shell(
                    ['osascript',
                     '-e',
                     'tell application "System Events" ' +
                     'to delete login item "{}"'.format(app_name)])
            return res
        elif sys.platform == 'win32':
            """Find the path of Macast.exe so as to create shortcut.
            """
            if "python" in os.path.basename(sys.executable).lower():
                return (1, "Not support to set start at login.")

            logger.info(sys.executable)
            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run",
                    0,
                    winreg.KEY_SET_VALUE,
                ) as key:
                    if launch:
                        winreg.SetValueEx(
                            key,
                            "Macast-RTX-Edition",
                            0,
                            winreg.REG_SZ,
                            sys.executable,
                        )
                    else:
                        try:
                            winreg.DeleteValue(key, "Macast-RTX-Edition")
                        except FileNotFoundError:
                            pass
            except OSError as exc:
                logger.error("Cannot update startup registration: %s", exc)
                return 1, str(exc)
            return 0, "success"
        elif sys.platform == 'linux':
            # Follow the freedesktop XDG autostart convention. This works for
            # GNOME, KDE, XFCE and other desktop environments without a
            # desktop-specific dependency.
            config_home = os.environ.get(
                'XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
            desktop_dir = os.path.join(config_home, 'autostart')
            desktop_file = os.path.join(desktop_dir, 'macast-rtx-edition.desktop')
            if not launch:
                try:
                    os.remove(desktop_file)
                except FileNotFoundError:
                    pass
                return (0, 'success')
            try:
                os.makedirs(desktop_dir, exist_ok=True)
                if getattr(sys, 'frozen', False):
                    argv = [sys.executable]
                else:
                    script = os.path.abspath(sys.argv[0])
                    if not os.path.isfile(script):
                        return (1, 'Cannot determine application path.')
                    argv = ([sys.executable, script]
                            if script.endswith('.py') else [script])
                # Desktop Entry Exec uses double quotes, not shell quoting.
                command = ' '.join('"{}"'.format(arg.replace('\\', '\\\\')
                                                   .replace('"', '\\"')
                                                   .replace('$', '\\$')
                                                   .replace('`', '\\`'))
                                   for arg in argv)
                with open(desktop_file, 'w', encoding='utf-8') as f:
                    f.write('[Desktop Entry]\nType=Application\nName=Macast RTX Edition\n'
                            'Comment=DLNA Media Renderer\nExec={}\n'
                            'Terminal=false\nCategories=AudioVideo;Player;\n'.format(command))
                return (0, 'success')
            except OSError as exc:
                logger.error('Cannot update XDG autostart: %s', exc)
                return (1, str(exc))
        else:
            return (1, 'Not support current platform.')

    @staticmethod
    def get_base_path(path="."):
        """PyInstaller creates a temp folder and stores path in _MEIPASS
            https://stackoverflow.com/a/13790741
            see also: https://pyinstaller.readthedocs.io/en/stable/\
                runtime-information.html#run-time-information
        """
        if Setting.base_path is not None:
            return os.path.join(Setting.base_path, path)
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            Setting.base_path = sys._MEIPASS
        else:
            Setting.base_path = os.path.join(os.path.dirname(__file__), '.')
        return os.path.join(Setting.base_path, path)

    @staticmethod
    def get_server_info():
        return '{}/{} UPnP/1.0 Macast/{}'.format(Setting.get_system(),
                                                 Setting.get_system_version(),
                                                 Setting.get_version())

    @staticmethod
    def get_system_env():
        # Get system env(for GNU/Linux and *BSD).
        # https://pyinstaller.readthedocs.io/en/stable/runtime-information.html#run-time-information
        env = dict(os.environ)
        logger.debug(env)
        lp_key = 'LD_LIBRARY_PATH'
        lp_orig = env.get(lp_key + '_ORIG')
        if lp_orig is not None:
            env[lp_key] = lp_orig
        else:
            env.pop(lp_key, None)
        return env

    @staticmethod
    def stop_service():
        """Stop all DLNA threads
        stop MPV
        stop DLNA HTTP Server
        stop SSDP
        stop SSDP notify thread
        """
        if cherrypy.engine.state in [cherrypy.engine.states.STOPPED,
                                     cherrypy.engine.states.STOPPING,
                                     cherrypy.engine.states.EXITING,
                                     ]:
            return
        while cherrypy.engine.state == cherrypy.engine.states.STARTING:
            time.sleep(0.5)
        if cherrypy.engine.state == cherrypy.engine.states.STARTED:
            cherrypy.engine.exit()

    @staticmethod
    def is_service_running():
        return cherrypy.engine.state in [cherrypy.engine.states.STARTING,
                                         cherrypy.engine.states.STARTED,
                                         ]

    @staticmethod
    def restart():
        if sys.platform == 'darwin' and sys.executable.endswith("Contents/MacOS/python"):
            # run from py2app build
            Setting.stop_service()
            executable = sys.executable[:-6] + 'Macast'
            os.execv(executable, [executable, executable])
        elif sys.platform == 'linux' and getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            # run from pyinstaller build on linux
            Setting.stop_service()
            env = Setting.get_system_env()
            executable = sys.executable
            os.execve(executable, [executable, executable], env)
        else:
            cherrypy.engine.restart()

    @staticmethod
    def application_command():
        """Return the executable and arguments that start Macast again."""
        executable = sys.executable
        if sys.platform == 'darwin' and executable.endswith("Contents/MacOS/python"):
            # run from py2app build: the app executable launches the interpreter
            app = executable[:-len('python')] + 'Macast'
            return app, [app, app]
        if getattr(sys, 'frozen', False):
            # run from a bundle: the executable is the entry point
            return executable, [executable] + sys.argv[1:]
        return executable, [executable, sys.argv[0]] + sys.argv[1:]

    @staticmethod
    def restart_application(delay=2.0):
        """Restart the whole application, for example after installing a plugin.

        Plugins are imported while Macast starts, so a plain service restart
        does not pick them up. The restart is delayed to let the HTTP response
        reach the settings page first. Current playback and DLNA sessions end.
        """
        threading.Timer(delay, Setting._restart_application).start()

    @staticmethod
    def _restart_application():
        """Replace the running process with a fresh one."""
        logger.info('Restarting Macast to load new components')
        executable, arguments = Setting.application_command()
        try:
            os.execv(executable, arguments)
        except OSError:
            logger.exception('Cannot restart Macast, restarting the service instead')
            cherrypy.engine.restart()


class XMLPath(Enum):
    BASE_PATH = os.path.dirname(__file__)
    DESCRIPTION = BASE_PATH + '/xml/Description.xml'
    AV_TRANSPORT = BASE_PATH + '/xml/AVTransport.xml'
    CONNECTION_MANAGER = BASE_PATH + '/xml/ConnectionManager.xml'
    RENDERING_CONTROL = BASE_PATH + '/xml/RenderingControl.xml'
    SETTING_PAGE = BASE_PATH + '/xml/settings_rtx.html'
    PROTOCOL_INFO = BASE_PATH + '/xml/SinkProtocolInfo.csv'


def load_xml(path):
    with open(path, encoding="utf-8") as f:
        xml = f.read()
    return xml


def notify_error(msg=None):
    """publish a notification when error occured
    """

    def wrapper_fun(fun):
        def wrapper(*args, **kwargs):
            nonlocal msg
            try:
                return fun(*args, **kwargs)
            except Exception as e:
                logger.error(str(e))
                if msg is None:
                    msg = str(e)
                else:
                    logger.error(msg)
                cherrypy.engine.publish('app_notify', 'Error', msg)

        return wrapper

    return wrapper_fun


def publish_method(func):
    def wrap(*args, **kwargs):
        func(*args, **kwargs)
        cherrypy.engine.publish(func.__name__, *args, **kwargs)

    return wrap


def format_class_name(instance):
    """
    eg1: DLNAHandler -> DLNA Handler
    eg2: AabcBabc -> Aabc Babc
    :param instance:
    :return:
    """
    name = instance.__class__.__name__
    res = name[0]
    for i in range(1, len(name) - 1):
        if 'A' <= name[i] <= 'Z' and 'a' <= name[i + 1] <= 'z':
            res += f' {name[i]}'
        else:
            res += name[i]
    res += name[-1]
    return res


def cherrypy_publish(method, default=None):
    res = cherrypy.engine.publish(method)
    if len(res) > 0:
        return res.pop()
    return default
