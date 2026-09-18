"""Regression checks for discovery and local settings."""

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import cherrypy
from lxml import etree

from macast.protocol import DLNAHandler, DLNAProtocol
from macast.renderer import Renderer
from macast.macast import Macast
from macast.gui import Platform
from macast import plugin_store
from macast.plugin_store import PluginStoreError
from macast.ssdp import SSDPServer
from macast.utils import Setting, SettingProperty, validate_settings
from macast_renderer.mpv import SettingProperty as MPVSettingProperty, get_player_setting
from macast_renderer.mpv import MPVRenderer


class FakePluginResponse:
    """Minimal stand-in for a streamed requests response."""

    def __init__(self, text, status=200):
        self._payload = text.encode('utf-8')
        self.status_code = status
        self.headers = {'Content-Length': str(len(self._payload))}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def iter_content(self, size):
        yield self._payload


class RegressionTests(unittest.TestCase):
    def test_setting_write_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            path.write_text('{"CheckUpdate": 0}', encoding='utf-8')
            with patch.object(Setting, 'setting_path', str(path)), \
                    patch.object(Setting, 'setting', {}), \
                    patch.object(Setting, 'loaded', False):
                Setting.set(SettingProperty.StartAtLogin, 1)
                self.assertEqual(json.loads(path.read_text(encoding='utf-8')),
                                 {'CheckUpdate': 0, 'StartAtLogin': 1})

    def test_stop_does_not_wait_forever_after_failed_start(self):
        states = SimpleNamespace(STOPPED='stopped', STOPPING='stopping',
                                 EXITING='exiting', STARTING='starting',
                                 STARTED='started')
        engine = SimpleNamespace(states=states, state=states.STARTING, exit=Mock())

        def finish_startup(_):
            engine.state = states.STOPPED

        with patch('macast.utils.cherrypy.engine', engine), \
                patch('macast.utils.time.sleep', side_effect=finish_startup) as sleep:
            Setting.stop_service()
        sleep.assert_called_once()
        engine.exit.assert_not_called()

    def test_malformed_ssdp_does_not_raise(self):
        server = SSDPServer()
        for payload in (b'BROKEN\r\n\r\n',
                        b'M-SEARCH * HTTP/1.1\r\nMX: 1\r\n\r\n',
                        b'M-SEARCH * HTTP/1.1\r\nST: ssdp:all\r\nMX: nope\r\n\r\n',
                        b'\xff\xfe'):
            with self.subTest(payload=payload):
                server.datagram_received(payload, ('127.0.0.1', 12345))

    def test_ssdp_restart_closes_interface_sockets(self):
        server = SSDPServer()
        interface_socket = Mock()
        listener_socket = Mock()
        server.sock_list = [interface_socket]
        server.sock = listener_socket
        server.close_sockets()
        interface_socket.close.assert_called_once_with()
        listener_socket.close.assert_called_once_with()
        self.assertEqual(server.sock_list, [])
        self.assertIsNone(server.sock)

    def test_description_escapes_friendly_name_without_replacing_server(self):
        with patch.object(Setting, 'temp_friendly_name', 'A&B <screen>'), \
                patch.object(Setting, 'setting', {'USN': 'test-device'}), \
                patch.object(Setting, 'loaded', True):
            handler = DLNAHandler()
            httpserver = cherrypy.server.httpserver
            handler.reload()
            self.assertIs(cherrypy.server.httpserver, httpserver)
            root = etree.fromstring(handler.description)
            names = root.xpath('//*[local-name()="friendlyName"]')
            self.assertEqual(names[0].text, 'A&B <screen>')

    def test_bad_player_choice_falls_back_to_platform_default(self):
        with patch.object(Setting, 'get', return_value=999):
            self.assertIn(get_player_setting(MPVSettingProperty.PlayerSize), (1, 2))

    def test_settings_reject_values_that_break_startup(self):
        for setting in ({'PlayerSize': 999}, {'PlayerPosition': -1},
                        {'ApplicationPort': '1900'}, {'Blocked_Interfaces': 1},
                        {'PlayerHW': True}):
            with self.subTest(setting=setting), self.assertRaises(ValueError):
                validate_settings(setting)
        validate_settings({'ApplicationPort': 0, 'PlayerSize': 2,
                           'Blocked_Interfaces': ['eth0'], 'PluginSetting': {'x': 1}})

    def test_malformed_soap_is_client_error(self):
        protocol = DLNAProtocol()
        for payload in (b'', b'<broken/>'):
            with self.subTest(payload=payload), self.assertRaises(cherrypy.HTTPError) as error:
                protocol.call(payload)
            self.assertEqual(error.exception.status, 400)

    def test_automatic_update_does_not_open_browser(self):
        app = SimpleNamespace(platform=Platform.Others, dialog=Mock(),
                              open_browser=Mock())
        response = Mock()
        response.json.return_value = {'tag_name': 'v999.0'}
        with patch('macast.macast.requests.get', return_value=response), \
                patch.object(Setting, 'get_version', return_value='1.0'):
            Macast.check_update(app, verbose=False)
        app.open_browser.assert_not_called()
        app.dialog.assert_called_once()

    @staticmethod
    def renderer_stub(running=True, file_loaded=False):
        renderer = MPVRenderer(path='mpv')
        renderer.running = running
        renderer.file_loaded = file_loaded
        renderer.send_command = Mock()
        return renderer

    def test_mpv_defers_audio_and_subtitles_until_the_file_is_loaded(self):
        # 切换文件期间 mpv 会拒绝 audio-add / sub-add（否则切画质后弹幕消失、没声音）
        renderer = self.renderer_stub()
        with patch('macast_renderer.mpv.threading.Timer') as timer:
            MPVRenderer.set_media_audio_file(renderer, 'http://example.com/a.m4s')
            MPVRenderer.set_media_sub_file(renderer, {'url': '/tmp/danmaku.ass', 'title': '弹幕'})
        renderer.send_command.assert_not_called()
        self.assertEqual(sorted(renderer.deferred_actions), ['audio', 'subtitle'])
        timer.return_value.start.assert_called()

        MPVRenderer.update_state(renderer, json.dumps({'event': 'file-loaded'}))
        self.assertTrue(renderer.file_loaded)
        self.assertEqual(renderer.deferred_actions, {})
        commands = [call.args[0] for call in renderer.send_command.call_args_list]
        self.assertIn(['audio-add', 'http://example.com/a.m4s', 'select'], commands)
        self.assertIn(['sub-add', '/tmp/danmaku.ass', 'select', '弹幕'], commands)

    def test_mpv_attaches_subtitles_immediately_when_the_file_is_loaded(self):
        renderer = self.renderer_stub(file_loaded=True)
        MPVRenderer.set_media_sub_file(renderer, {'url': '/tmp/danmaku.ass', 'title': '弹幕'})
        renderer.send_command.assert_called_once_with(
            ['sub-add', '/tmp/danmaku.ass', 'select', '弹幕'])

    def test_mpv_deferred_actions_are_skipped_after_stop(self):
        renderer = self.renderer_stub(running=False)
        MPVRenderer.set_media_audio_file(renderer, 'http://example.com/a.m4s')
        MPVRenderer.apply_deferred_actions(renderer)
        renderer.send_command.assert_not_called()

    def test_renderer_declares_audio_track_support(self):
        self.assertFalse(Renderer.support_audio_file)
        self.assertTrue(MPVRenderer.support_audio_file)

    def test_failed_mpv_ipc_connection_closes_socket(self):
        ipc_socket = Mock()
        ipc_socket.connect.side_effect = OSError('not ready')
        alive = iter((True, False))
        renderer = SimpleNamespace(ipc_running=False, running=True,
                                   mpv_thread=SimpleNamespace(is_alive=lambda: next(alive)),
                                   mpv_sock='/tmp/test-macast-ipc', ipc_sock=None)
        with patch('macast_renderer.mpv.socket.socket', return_value=ipc_socket), \
                patch('macast_renderer.mpv.time.sleep'):
            MPVRenderer.start_ipc(renderer)
        ipc_socket.close.assert_called_once_with()
        self.assertIsNone(renderer.ipc_sock)


class PluginStoreTests(unittest.TestCase):
    PLUGIN_URL = ('https://raw.githubusercontent.com/lemonevo/Macast-RTX-Edition'
                  '/main/plugins/demo.py')
    UPSTREAM_PLUGIN_URL = ('https://raw.githubusercontent.com/xfangfang/Macast-plugins'
                           '/main/demo/demo.py')
    PLUGIN_SOURCE = (
        '# <macast.title>Demo</macast.title>\n'
        '# <macast.renderer>DemoRenderer</macast.renderer>\n'
        '# <macast.platform>darwin,linux,win32</macast.platform>\n'
        '# <macast.version>1.2</macast.version>\n')

    def setUp(self):
        plugin_store._repo_cache.update({'time': 0.0, 'data': None})

    @staticmethod
    def plugin_entry(**overrides):
        entry = {'type': 'renderer', 'url': PluginStoreTests.PLUGIN_URL,
                 'title': 'Demo', 'version': '1.2',
                 'platform': 'darwin,linux,win32'}
        entry.update(overrides)
        return entry

    def test_only_the_curated_repository_is_allowed(self):
        self.assertTrue(plugin_store.is_allowed_plugin_url(self.PLUGIN_URL))
        # 上游插件仓库仍然允许（用于回退安装）
        self.assertTrue(plugin_store.is_allowed_plugin_url(self.UPSTREAM_PLUGIN_URL))
        for url in ('http://raw.githubusercontent.com/lemonevo/Macast-RTX-Edition/main/plugins/demo.py',
                    'https://example.com/lemonevo/Macast-RTX-Edition/main/plugins/demo.py',
                    'https://raw.githubusercontent.com/attacker/evil/main/evil.py',
                    'https://raw.githubusercontent.com/lemonevo/Macast-RTX-Edition/main/plugins/../../evil.py',
                    'https://raw.githubusercontent.com/lemonevo/Macast-RTX-Edition/main/plugins/demo.txt',
                    'https://raw.githubusercontent.com/lemonevo/Macast-RTX-Edition/main/plugins/demo.py?raw=1',
                    ''):
            with self.subTest(url=url):
                self.assertFalse(plugin_store.is_allowed_plugin_url(url))

    def test_install_writes_only_inside_the_plugin_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('macast.plugin_store.requests.get',
                       return_value=FakePluginResponse(self.PLUGIN_SOURCE)):
                installed = plugin_store.install_plugin(
                    self.plugin_entry(), platform='darwin', setting_dir=directory)
            plugin_dir = Path(directory) / 'renderer'
            plugin_path = plugin_dir / 'demo.py'
            self.assertEqual(plugin_path.read_text(encoding='utf-8'), self.PLUGIN_SOURCE)
            self.assertEqual([item.name for item in plugin_dir.iterdir()], ['demo.py'])
            self.assertEqual(installed['title'], 'Demo')
            self.assertEqual(installed['version'], '1.2')
            self.assertFalse(installed['replaced'])

    def test_install_rejects_files_outside_the_trusted_slots(self):
        failures = (
            ({'type': 'renderer', 'url': 'https://example.com/evil.py'}, '外部地址'),
            (self.plugin_entry(type='protocol'), '缺少 <macast.protocol>'),
            (self.plugin_entry(url=self.PLUGIN_URL[:-3] + 'txt'), '非 .py'),
        )
        for entry, reason in failures:
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as directory:
                with patch('macast.plugin_store.requests.get',
                           return_value=FakePluginResponse(self.PLUGIN_SOURCE)):
                    with self.assertRaises(PluginStoreError):
                        plugin_store.install_plugin(entry, platform='darwin',
                                                    setting_dir=directory)
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_install_rejects_unsupported_platform(self):
        source = self.PLUGIN_SOURCE.replace('darwin,linux,win32', 'win32')
        with tempfile.TemporaryDirectory() as directory:
            with patch('macast.plugin_store.requests.get',
                       return_value=FakePluginResponse(source)):
                with self.assertRaises(PluginStoreError):
                    plugin_store.install_plugin(self.plugin_entry(), platform='darwin',
                                                setting_dir=directory)

    def test_install_rejects_oversized_downloads(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('macast.plugin_store.MAX_PLUGIN_BYTES', 8), \
                    patch('macast.plugin_store.requests.get',
                          return_value=FakePluginResponse(self.PLUGIN_SOURCE)):
                with self.assertRaises(PluginStoreError):
                    plugin_store.install_plugin(self.plugin_entry(), platform='darwin',
                                                setting_dir=directory)

    def test_repo_list_drops_untrusted_entries_and_is_cached(self):
        info = json.dumps({
            'repo_url': 'https://github.com/xfangfang/Macast-plugins',
            'plugin_v1': [self.plugin_entry(),
                          {'type': 'renderer', 'title': 'Evil',
                           'url': 'https://evil.example.com/evil.py'}],
        })
        with patch('macast.plugin_store.requests.get',
                   return_value=FakePluginResponse(info)) as request:
            data = plugin_store.load_repo_plugins()
            self.assertEqual([plugin['title'] for plugin in data['plugins']], ['Demo'])
            self.assertEqual(data['repo_url'],
                             'https://github.com/xfangfang/Macast-plugins')
            plugin_store.load_repo_plugins()
            self.assertEqual(request.call_count, 1)
            plugin_store.load_repo_plugins(force=True)
            self.assertEqual(request.call_count, 2)

    def test_repo_list_reports_transport_failure(self):
        with patch('macast.plugin_store.requests.get',
                   return_value=FakePluginResponse('missing', status=404)):
            with self.assertRaises(PluginStoreError):
                plugin_store.load_repo_plugins()

    def test_repo_list_falls_back_to_the_upstream_manifest(self):
        entry = self.plugin_entry(
            url='https://raw.githubusercontent.com/xfangfang/Macast-plugins/main/demo/demo.py')
        requested = []

        def fake_fetch(url, limit, timeout):
            requested.append(url)
            if len(requested) == 1:
                raise PluginStoreError('第一个清单源不可用')
            return json.dumps({'plugin_v1': [entry]})

        with patch('macast.plugin_store._fetch_text', side_effect=fake_fetch):
            data = plugin_store.load_repo_plugins()
        self.assertEqual(len(requested), 2)
        self.assertEqual(requested[0], plugin_store.PLUGIN_REPO_INFO_URLS[0])
        self.assertEqual([plugin['title'] for plugin in data['plugins']], ['Demo'])

    def test_uninstall_removes_only_the_plugin_file(self):
        with tempfile.TemporaryDirectory() as directory:
            plugin_dir = Path(directory) / 'renderer'
            plugin_dir.mkdir()
            plugin_path = plugin_dir / 'demo.py'
            plugin_path.write_text(self.PLUGIN_SOURCE, encoding='utf-8')
            keep = plugin_dir / '__init__.py'
            keep.write_text('', encoding='utf-8')
            cache_dir = plugin_dir / '__pycache__'
            cache_dir.mkdir()
            (cache_dir / 'demo.cpython-312.pyc').write_bytes(b'old')
            (cache_dir / 'other.cpython-312.pyc').write_bytes(b'other')

            removed = plugin_store.uninstall_plugin(
                self.plugin_entry(), setting_dir=directory)

            self.assertTrue(removed['removed'])
            self.assertEqual(removed['title'], 'Demo')
            self.assertEqual(sorted(item.name for item in plugin_dir.iterdir()),
                             ['__init__.py', '__pycache__'])
            self.assertEqual([item.name for item in cache_dir.iterdir()],
                             ['other.cpython-312.pyc'])
            with self.assertRaises(PluginStoreError):
                plugin_store.uninstall_plugin(self.plugin_entry(), setting_dir=directory)

    def test_uninstall_rejects_targets_outside_the_plugin_directory(self):
        entries = (
            self.plugin_entry(url='https://example.com/evil.py'),
            self.plugin_entry(type='plugin'),
            self.plugin_entry(url=self.PLUGIN_URL.replace('demo.py', '__init__.py')),
            self.plugin_entry(url='https://raw.githubusercontent.com/xfangfang'
                                  '/Macast-plugins/main/../../evil.py'),
        )
        for entry in entries:
            with self.subTest(entry=entry), tempfile.TemporaryDirectory() as directory:
                outside = Path(directory) / 'evil.py'
                outside.write_text('keep me', encoding='utf-8')
                with self.assertRaises(PluginStoreError):
                    plugin_store.uninstall_plugin(entry, setting_dir=directory)
                self.assertEqual([item.name for item in Path(directory).iterdir()],
                                 ['evil.py'])


class RestartTests(unittest.TestCase):
    def test_application_command_reuses_the_current_entry_point(self):
        executable, arguments = Setting.application_command()
        self.assertEqual(executable, sys.executable)
        self.assertEqual(arguments[0], sys.executable)
        self.assertEqual(arguments[0], executable)
        if getattr(sys, 'frozen', False):
            self.assertEqual(arguments[1:], sys.argv[1:])
        else:
            self.assertEqual(arguments[1:], sys.argv)

    def test_restart_replaces_the_process(self):
        with patch('macast.utils.os.execv') as execv:
            Setting._restart_application()
        executable, arguments = execv.call_args.args
        self.assertEqual(executable, sys.executable)
        self.assertEqual(arguments[0], sys.executable)

    def test_restart_falls_back_to_a_service_restart(self):
        with patch('macast.utils.os.execv', side_effect=OSError('cannot exec')), \
                patch('macast.utils.cherrypy.engine.restart') as restart:
            Setting._restart_application()
        restart.assert_called_once_with()

    def test_restart_application_is_delayed_until_the_response_is_sent(self):
        with patch('macast.utils.threading.Timer') as timer:
            Setting.restart_application()
        self.assertEqual(timer.call_args.args[1], Setting._restart_application)
        self.assertGreater(timer.call_args.args[0], 0)
        timer.return_value.start.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
