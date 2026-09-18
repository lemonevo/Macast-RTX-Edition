"""Checks for the locally maintained NVA (bilibili) protocol plugin."""

import importlib.util
import json
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

PLUGIN_PATH = Path(__file__).resolve().parents[1] / 'plugins' / 'nirvana.py'


def load_plugin(setting_dir):
    """Load plugins/nirvana.py while pointing its config directory elsewhere."""
    import macast.utils

    with patch.object(macast.utils, 'SETTING_DIR', setting_dir):
        spec = importlib.util.spec_from_file_location('nva_plugin_under_test', PLUGIN_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class FakeRenderer:
    support_audio_file = False

    def __init__(self):
        self.texts = []
        self.subs = []
        self.urls = []
        self.audios = []

    def set_media_text(self, text, duration=1000):
        self.texts.append(text)

    def set_media_sub_file(self, data):
        self.subs.append(data)

    def set_media_sub_show(self, value):
        pass

    def set_media_url(self, url, start='0'):
        self.urls.append(url)

    def set_media_audio_file(self, url):
        self.audios.append(url)

    def set_media_title(self, title):
        pass

    def set_media_speed(self, speed):
        pass


class DashRenderer(FakeRenderer):
    """渲染器声明支持外挂音轨（例如 Macast 的 MPVRenderer）"""

    support_audio_file = True


class FakeProtocol:
    def __init__(self):
        self.subtitle = None
        self.speed = '1'

    def set_state_display_subtitle(self, value):
        self.subtitle = value

    def get_state_display_subtitle(self):
        return True

    def get_state_speed(self):
        return self.speed

    def get_state_position(self):
        return '00:00:10'

    def set_state_url(self, url):
        pass


class PluginNamespace(SimpleNamespace):
    """属性缺失时返回空字符串，避免测试与插件的字段列表强耦合"""

    def __getattr__(self, name):
        return ''


class NVAPluginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.plugin = load_plugin(cls.directory.name)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def handler(self, renderer_class=FakeRenderer, **overrides):
        handler = PluginNamespace(
            cid='100', oid='200', aid='', epid=0, access_key='', desire_qn=0,
            playurl_type=1, current_qn=0, qn={}, content_type=1, title='title',
            title_p='', danmaku_open=True, danmaku_cid='', audio_url='',
            danmaku_switch_save=True,
            sub=str(Path(self.directory.name) / 'macast.ass'),
            roomId=0, desire_speed=1)
        handler.__dict__.update(overrides)
        handler.renderer = renderer_class()
        handler.protocol = FakeProtocol()
        for name in ('get_video_url', 'request_play_url', 'send_play_cmd', 'load_danmaku',
                     'get_extra_info_thread', 'danmaku_file', 'notify_qn_downgrade',
                     'set_danmaku_visibility', 'update_play_state'):
            setattr(handler, name,
                    types.MethodType(getattr(self.plugin.NVAConectionHandler, name), handler))
        # 静态方法直接挂载：用 MethodType 绑定会多传一个 self
        for name in ('parse_qn', 'parse_speed'):
            setattr(handler, name, getattr(self.plugin.NVAConectionHandler, name))
        return handler

    @staticmethod
    def response(payload):
        return SimpleNamespace(text=json.dumps(payload), content=json.dumps(payload).encode())

    def serve(self, payload):
        return patch.object(self.plugin.NetworkManager, 'GET',
                            staticmethod(lambda *a, **k: self.response(payload)))

    def test_quality_list_falls_back_to_accept_quality(self):
        payload = {'code': 0, 'data': {
            'quality': 32, 'accept_quality': [80, 64, 32],
            'accept_description': ['1080P 高清', '720P 准高清', '480P 清晰'],
            'qn_extras': [], 'durl': [{'url': 'http://example.com/a.flv'}]}}
        with self.serve(payload):
            url, qn = self.handler().get_video_url()
        self.assertEqual(url, 'http://example.com/a.flv')
        self.assertEqual([item['quality'] for item in qn['supportQnList']], [80, 64, 32])
        self.assertEqual(qn['supportQnList'][1]['displayDesc'], '720P 准高清')

    def test_quality_downgrade_is_reported_to_the_user(self):
        payload = {'code': 0, 'data': {
            'quality': 64, 'accept_quality': [112, 80, 64],
            'accept_description': ['1080P+', '1080P', '720P'],
            'support_formats': [
                {'quality': 112, 'new_description': '1080P 高码率', 'display_desc': '1080P'},
                {'quality': 80, 'new_description': '1080P 高清', 'display_desc': '1080P'},
                {'quality': 64, 'new_description': '720P 准高清', 'display_desc': '720P'}],
            'qn_extras': [{'qn': 112, 'need_vip': True, 'need_login': True},
                          {'qn': 80, 'need_vip': False, 'need_login': True},
                          {'qn': 64, 'need_vip': False, 'need_login': False}],
            'durl': [{'url': 'http://example.com/b.flv'}]}}
        handler = self.handler(desire_qn=80)
        with self.serve(payload):
            handler.get_video_url()
        self.assertEqual(handler.current_qn, 64)
        self.assertTrue(any('需要登录' in text for text in handler.renderer.texts),
                        handler.renderer.texts)

    def test_dash_track_matches_the_requested_quality(self):
        payload = {'code': 0, 'data': {
            'quality': 64, 'accept_quality': [64, 32], 'accept_description': ['720P', '480P'],
            'support_formats': [], 'qn_extras': [],
            'dash': {'video': [{'id': 32, 'base_url': 'http://example.com/low.mp4'},
                               {'id': 64, 'base_url': 'http://example.com/high.mp4'}],
                     'audio': [{'id': 30216, 'base_url': 'http://example.com/audio.m4s'}]}}}
        with self.serve(payload):
            url, _ = self.handler(renderer_class=DashRenderer,
                                  desire_qn=64).get_video_url()
        self.assertEqual(url, 'http://example.com/high.mp4')

    def test_dash_without_audio_track_is_not_used(self):
        # 没有独立音轨的 DASH 会静音，这种情况必须回退合并流
        payload = {'code': 0, 'data': {
            'quality': 64, 'accept_quality': [80, 64], 'accept_description': ['1080P', '720P'],
            'support_formats': [], 'qn_extras': [],
            'durl': [{'url': 'http://example.com/merged.flv'}],
            'dash': {'video': [{'id': 80, 'base_url': 'http://example.com/1080.mp4'}]}}}
        handler = self.handler(renderer_class=DashRenderer, desire_qn=80)
        with self.serve(payload):
            url, _ = handler.get_video_url()
        self.assertEqual(url, 'http://example.com/merged.flv')
        self.assertEqual(handler.audio_url, '')

    def test_dash_is_used_for_high_quality_and_audio_is_attached(self):
        # B 站只通过 DASH 提供 1080P；音轨是独立文件，需要渲染器支持外挂音轨
        payload = {'code': 0, 'data': {
            'quality': 64, 'accept_quality': [80, 64], 'accept_description': ['1080P', '720P'],
            'support_formats': [], 'qn_extras': [],
            'dash': {'video': [{'id': 64, 'base_url': 'http://example.com/720.mp4'},
                               {'id': 80, 'base_url': 'http://example.com/1080.mp4'}],
                     'audio': [{'id': 30216, 'base_url': 'http://example.com/a64.m4s'},
                               {'id': 30280, 'base_url': 'http://example.com/a192.m4s'}]}}}
        handler = self.handler(renderer_class=DashRenderer, desire_qn=80)
        with self.serve(payload):
            url, qn = handler.get_video_url()
        self.assertEqual(url, 'http://example.com/1080.mp4')
        self.assertEqual(qn['curQn'], 80)
        self.assertEqual(handler.audio_url, 'http://example.com/a192.m4s')
        self.assertEqual(handler.renderer.texts, [])  # 没有降级

    def test_renderer_without_audio_support_keeps_the_merged_stream(self):
        payload = {'code': 0, 'data': {
            'quality': 64, 'accept_quality': [80, 64], 'accept_description': ['1080P', '720P'],
            'support_formats': [], 'qn_extras': [],
            'durl': [{'url': 'http://example.com/merged.flv'}],
            'dash': {'video': [{'id': 80, 'base_url': 'http://example.com/1080.mp4'}],
                     'audio': [{'id': 30280, 'base_url': 'http://example.com/a192.m4s'}]}}}
        handler = self.handler(desire_qn=80)  # FakeRenderer 不支持外挂音轨
        with self.serve(payload):
            url, qn = handler.get_video_url()
        self.assertEqual(url, 'http://example.com/merged.flv')
        self.assertEqual(handler.audio_url, '')
        self.assertEqual(qn['curQn'], 64)

    def test_falls_back_to_the_merged_stream_request(self):
        # 第一次请求（fnval=16）没有可用取流方式时，会用不带 fnval 的请求重试
        dash_only = {'code': 0, 'data': {
            'quality': 64, 'accept_quality': [64], 'accept_description': ['720P'],
            'support_formats': [], 'qn_extras': [], 'dash': {}}}
        merged = {'code': 0, 'data': {
            'quality': 64, 'accept_quality': [64], 'accept_description': ['720P'],
            'support_formats': [], 'qn_extras': [],
            'durl': [{'url': 'http://example.com/merged.flv'}]}}
        payloads = [self.response(dash_only), self.response(merged)]
        with patch.object(self.plugin.NetworkManager, 'GET',
                          staticmethod(lambda *a, **k: payloads.pop(0))):
            url, _ = self.handler().get_video_url()
        self.assertEqual(url, 'http://example.com/merged.flv')

    def test_send_play_cmd_attaches_the_dash_audio_track(self):
        handler = self.handler(cid='', content_type=2, audio_url='http://example.com/a.m4s')
        handler.send_play_cmd('http://example.com/video.m4s')
        self.assertEqual(handler.renderer.urls, ['http://example.com/video.m4s'])
        self.assertEqual(handler.renderer.audios, ['http://example.com/a.m4s'])

    def test_missing_play_url_does_not_reload_the_player(self):
        handler = self.handler()
        with self.serve({'code': -404, 'message': '啥都木有'}):
            url, qn = handler.get_video_url()
            self.assertIsNone(url)
            self.assertEqual(qn, {})
        handler.send_play_cmd(url)
        self.assertEqual(handler.renderer.urls, [])

    def test_dirty_danmaku_entries_do_not_break_the_subtitle_file(self):
        dirty = ('<?xml version="1.0" encoding="UTF-8"?><i>'
                 '<d p="1.0,1,25,16777215,1,0,abc,1">正常弹幕{花括号}\\反斜杠, 带逗号</d>'
                 '<d p="2.0,1,25,16777215,1,0,abc,2"></d>'
                 '<d p="3.0,1,25">字段不足</d>'
                 '<d p="bad,1,25,16777215,1,0,abc,4">时间戳异常</d>'
                 '<d p="5.0,1,25,16777215,1,0,abc,5">最后一条</d></i>')
        target = str(Path(self.directory.name) / 'dirty.ass')
        with patch.object(self.plugin.NetworkManager, 'GET',
                          staticmethod(lambda *a, **k: SimpleNamespace(content=dirty.encode('utf-8')))):
            result = self.plugin.DanmakuManager.get_danmaku('100', target)
        self.assertEqual(result, target)
        content = Path(target).read_text(encoding='utf-8')
        dialogues = [line for line in content.splitlines() if line.startswith('Dialogue:')]
        self.assertEqual(len(dialogues), 2, dialogues)
        self.assertNotIn('{花括号}', content)
        self.assertIn('（花括号）', content)
        self.assertIn('正常弹幕', content)

    def test_danmaku_switch_is_synced_to_the_protocol_layer(self):
        handler = self.handler()
        handler.set_danmaku_visibility(False)
        self.assertIs(handler.protocol.subtitle, False)
        handler.set_danmaku_visibility(True)
        self.assertIs(handler.protocol.subtitle, True)

    def test_danmaku_file_is_unique_per_video(self):
        handler = self.handler()
        self.assertTrue(handler.danmaku_file('137649199').endswith('macast-danmaku-137649199.ass'))
        self.assertNotIn('..', handler.danmaku_file('../../etc/passwd'))

    def test_string_quality_from_client_selects_the_right_track(self):
        # 客户端把画质传成字符串（'80'），修复前会静默退化成 B 站默认画质（720P）
        payload = {'code': 0, 'data': {
            'quality': 64, 'accept_quality': [80, 64], 'accept_description': ['1080P', '720P'],
            'support_formats': [], 'qn_extras': [],
            'dash': {'video': [{'id': 64, 'base_url': 'http://example.com/720.mp4'},
                               {'id': 80, 'base_url': 'http://example.com/1080.mp4'}],
                     'audio': [{'id': 30280, 'base_url': 'http://example.com/a.m4s'}]}}}
        handler = self.handler(renderer_class=DashRenderer, desire_qn='80')
        with self.serve(payload):
            url, qn = handler.get_video_url()
        self.assertEqual(url, 'http://example.com/1080.mp4')
        self.assertEqual(qn['curQn'], 80)
        self.assertEqual(qn['userDesireQn'], 80)

    def test_play_state_update_survives_missing_speed_state(self):
        # 播放速度状态还没写入时 float('') 会抛异常，修复前连弹幕线程都不会启动
        handler = self.handler()
        handler.protocol.speed = ''
        handler.update_play_state()

    def test_client_parameter_parsing_tolerates_strings(self):
        parse_qn = self.plugin.NVAConectionHandler.parse_qn
        parse_speed = self.plugin.NVAConectionHandler.parse_speed
        self.assertEqual(parse_qn('80'), 80)
        self.assertEqual(parse_qn(''), 0)
        self.assertEqual(parse_qn(None), 0)
        self.assertEqual(parse_speed('1.25'), 1.25)
        self.assertEqual(parse_speed(''), 1.0)
        self.assertEqual(parse_speed('-2'), 1.0)

    def test_closed_connection_drops_outgoing_data(self):        # 连接断开后 ping 线程不应再向 socket 写数据（原来会抛 AttributeError）
        send = self.plugin.NVAConectionBaseHandler.send
        handler = SimpleNamespace(terminated=False, sock=None, sock_lock=threading.Lock())
        send(handler, b'ping')  # socket 为 None：静默返回
        handler.sock = Mock()
        handler.terminated = True
        send(handler, b'ping')  # 已终止：丢弃
        handler.sock.sendall.assert_not_called()


if __name__ == '__main__':
    unittest.main()
