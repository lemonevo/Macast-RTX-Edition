"""Regression checks for discovery and local settings."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import cherrypy
from lxml import etree

from macast.protocol import DLNAHandler, DLNAProtocol
from macast.macast import Macast
from macast.gui import Platform
from macast.ssdp import SSDPServer
from macast.utils import Setting, SettingProperty, validate_settings
from macast_renderer.mpv import SettingProperty as MPVSettingProperty, get_player_setting
from macast_renderer.mpv import MPVRenderer


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


if __name__ == '__main__':
    unittest.main()
