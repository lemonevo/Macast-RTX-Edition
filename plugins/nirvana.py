# Copyright (c) 2021-2024 by xfangfang. All Rights Reserved.
#
# NVA protocol
#
# ============================================================================
# Macast RTX Edition 本地维护副本
#
# 上游文件: https://raw.githubusercontent.com/xfangfang/Macast-plugins/main/nirvana/nirvana.py
# 上游版本: 0.33（本副本版本号 0.34）
# 显示名称: 哔哩哔哩投屏（Bilibili 投屏），原来叫 "NVA Protocol"
# 上游声明: 仅供编程学习使用，禁止商用（原文见上游仓库）
#
# 本副本在上游 v0.33 基础上修复了以下问题（详见 plugins/README.md）：
#   1. 弹幕开关只在渲染层生效，协议层状态不同步 -> 再次投屏时弹幕被旧状态关闭
#   2. 弹幕文件固定同名，切集/切画质时互相覆盖
#   3. 弹幕脏数据（空文本/时间戳非法/字段不足）导致整份 ASS 生成失败，失败后仍加载空文件
#   4. Dialogue 行的 Name 字段使用未转义的弹幕文本，含逗号的弹幕会破坏 ASS 字段
#   5. support_formats 缺失时画质列表为空，客户端不显示画质菜单
#   6. 请求的画质被 B 站限制（未登录/非大会员）时静默回退，不说明原因
#   7. dash 分支盲取 video[0]；durl/dash/live 字段缺失时 KeyError 直接打断播放
#   8. 新增 nva-plugin.log 日志，便于排查协议交互问题
#   9. 1080P 拿不到：B 站的高画质只通过 DASH 提供，FLV 合并流上限 720P
#      -> 优先请求 DASH（fnval=16）并按画质选轨，音轨用 audio-add 单独挂载
#  10. 解析/发送异常用 print 输出、连接断开刷 AttributeError -> 统一写入 nva-plugin.log
# ============================================================================

# Macast Metadata
# <macast.title>哔哩哔哩投屏（Bilibili 投屏）</macast.title>
# <macast.protocol>NVAProtocol</macast.protocol>
# <macast.platform>darwin,win32,linux</macast.platform>
# <macast.version>0.34</macast.version>
# <macast.host_version>0.7</macast.host_version>
# <macast.author>xfangfang</macast.author>
# <macast.desc>哔哩哔哩投屏（Bilibili 投屏），在 B 站客户端里显示为「我的小电视(有弹幕)」，支持弹幕、倍速与 1080P 画质。</macast.desc>

# changelog
# v0.33: Fix video API error, Fix live stream error
# v0.32: Fix video API error

import re
import os
import urllib
import hashlib
import socket
import cheroot.server
import cherrypy
from cherrypy import _cpnative_server, Tool
import email.utils
import logging
import threading
import struct
import json
import time
from urllib import parse
import errno
import requests
from lxml import etree
import select

from macast.protocol import DLNAProtocol, DLNAHandler, Protocol
from macast.renderer import Renderer
from macast.utils import SETTING_DIR, XMLPath, load_xml, Setting

LF = b'\n'
CRLF = b'\r\n'
TAB = b'\t'
SPACE = b' '
COLON = b':'
SEMICOLON = b';'
EMPTY = b''
ASTERISK = b'*'
FORWARD_SLASH = b'/'
QUOTED_SLASH = b'%2F'
QUOTED_SLASH_REGEX = re.compile(b''.join((b'(?i)', QUOTED_SLASH)))

COMMAND = b'Command'
SEND_CMD = b'\xe0'
RET_CMD = b'\xc0'
PING = b'\xe4'

# https://github.com/SocialSisterYi/bilibili-API-collect/blob/master/docs/misc/sign/APPKey.md
APP_KEY = '4ebafd7c4951b366'
APP_SEC = '8cb98205e9b2ad3669aad0fce12a4c13'

NVA_SERVICE = """<?xml version="1.0" encoding="UTF-8"?>
<scpd xmlns="urn:schemas-upnp-org:service-1-0">
  <specVersion>
    <major>1</major>
    <minor>0</minor>
  </specVersion>
  <actionList>
    <action>
      <name>GetAppInfo</name>
      <argumentList>
        <argument>
          <name>PackageName</name>
          <direction>out</direction>
          <relatedStateVariable>A_ARG_TYPE_PackageName</relatedStateVariable>
        </argument>
        <argument>
          <name>AppKey</name>
          <direction>out</direction>
          <relatedStateVariable>A_ARG_TYPE_AppKey</relatedStateVariable>
        </argument>
        <argument>
          <name>Signature</name>
          <direction>out</direction>
          <relatedStateVariable>A_ARG_TYPE_Signature</relatedStateVariable>
        </argument>
        <argument>
          <name>CurrentSignedIn</name>
          <direction>out</direction>
          <relatedStateVariable>SignedIn</relatedStateVariable>
        </argument>
      </argumentList>
    </action>
    <action>
      <name>LoginWithCode</name>
      <argumentList>
        <argument>
          <name>Code</name>
          <direction>in</direction>
          <relatedStateVariable>A_ARG_TYPE_UnlimitedString</relatedStateVariable>
        </argument>
      </argumentList>
    </action>
    <action>
      <name>PrepareForMirrorProjection</name>
      <argumentList>
        <argument>
          <name>ScreenWidth</name>
          <direction>out</direction>
          <relatedStateVariable>A_ARG_TYPE_ScreenResolution</relatedStateVariable>
        </argument>
        <argument>
          <name>ScreenHeight</name>
          <direction>out</direction>
          <relatedStateVariable>A_ARG_TYPE_ScreenResolution</relatedStateVariable>
        </argument>
        <argument>
          <name>PushUrl</name>
          <direction>out</direction>
          <relatedStateVariable>A_ARG_TYPE_UnlimitedString</relatedStateVariable>
        </argument>
      </argumentList>
    </action>
    <action>
      <name>SetDanmakuSwitch</name>
      <argumentList>
        <argument>
          <name>DesiredSwitch</name>
          <direction>in</direction>
          <relatedStateVariable>DanmakuSwitch</relatedStateVariable>
        </argument>
      </argumentList>
    </action>
    <action>
      <name>AppendDanmaku</name>
      <argumentList>
        <argument>
          <name>Content</name>
          <direction>in</direction>
          <relatedStateVariable>A_ARG_TYPE_UnlimitedString</relatedStateVariable>
        </argument>
        <argument>
          <name>Size</name>
          <direction>in</direction>
          <relatedStateVariable>A_ARG_TYPE_UnlimitedInt</relatedStateVariable>
        </argument>
        <argument>
          <name>Type</name>
          <direction>in</direction>
          <relatedStateVariable>A_ARG_TYPE_UnlimitedInt</relatedStateVariable>
        </argument>
        <argument>
          <name>Color</name>
          <direction>in</direction>
          <relatedStateVariable>A_ARG_TYPE_UnlimitedInt</relatedStateVariable>
        </argument>
        <argument>
          <name>DanmakuId</name>
          <direction>in</direction>
          <relatedStateVariable>A_ARG_TYPE_UnlimitedString</relatedStateVariable>
        </argument>
        <argument>
          <name>Action</name>
          <direction>in</direction>
          <relatedStateVariable>A_ARG_TYPE_UnlimitedString</relatedStateVariable>
        </argument>
      </argumentList>
    </action>
    <action>
      <name>GetPlayInfo</name>
      <argumentList>
        <argument>
          <name>Params</name>
          <direction>in</direction>
          <relatedStateVariable>A_ARG_TYPE_UnlimitedString</relatedStateVariable>
        </argument>
        <argument>
          <name>Content</name>
          <direction>out</direction>
          <relatedStateVariable>A_ARG_TYPE_UnlimitedString</relatedStateVariable>
        </argument>
      </argumentList>
    </action>
    <action>
      <name>GetAccountInfo</name>
      <argumentList>
        <argument>
          <name>VipInfo</name>
          <direction>out</direction>
          <relatedStateVariable>A_ARG_TYPE_UnlimitedInt</relatedStateVariable>
        </argument>
      </argumentList>
    </action>
    <action>
      <name>SwitchQuality</name>
      <argumentList>
        <argument>
          <name>Qn</name>
          <direction>in</direction>
          <relatedStateVariable>A_ARG_TYPE_UnlimitedInt</relatedStateVariable>
        </argument>
      </argumentList>
    </action>
  </actionList>
  <serviceStateTable>
    <stateVariable sendEvents="no">
      <name>A_ARG_TYPE_UnlimitedString</name>
      <dataType>string</dataType>
    </stateVariable>
    <stateVariable sendEvents="no">
      <name>A_ARG_TYPE_PackageName</name>
      <dataType>string</dataType>
      <defaultValue>com.xiaodianshi.tv.yst</defaultValue>
    </stateVariable>
    <stateVariable sendEvents="no">
      <name>A_ARG_TYPE_AppKey</name>
      <dataType>string</dataType>
      <defaultValue>0000000000000000</defaultValue>
    </stateVariable>
    <stateVariable sendEvents="no">
      <name>A_ARG_TYPE_Signature</name>
      <dataType>string</dataType>
      <defaultValue>0000000000000000</defaultValue>
    </stateVariable>
    <stateVariable sendEvents="no">
      <name>A_ARG_TYPE_UnlimitedInt</name>
      <dataType>i4</dataType>
    </stateVariable>
    <stateVariable sendEvents="no">
      <name>A_ARG_TYPE_ScreenResolution</name>
      <dataType>ui4</dataType>
    </stateVariable>
    <stateVariable sendEvents="no">
      <name>SignedIn</name>
      <dataType>boolean</dataType>
      <defaultValue>1</defaultValue>
    </stateVariable>
    <stateVariable sendEvents="no">
      <name>DanmakuSwitch</name>
      <dataType>boolean</dataType>
    </stateVariable>
  </serviceStateTable>
</scpd>
""".encode()

logger = logging.getLogger("NVAPRotocol")
logger.setLevel(logging.INFO)
# NVA PATCH: 插件日志写入配置目录，方便排查弹幕/画质问题
try:
    _nva_log_path = os.path.join(SETTING_DIR, 'nva-plugin.log')
    if not any(getattr(h, 'baseFilename', '') == _nva_log_path for h in logger.handlers):
        _nva_handler = logging.FileHandler(_nva_log_path, encoding='utf-8')
        _nva_handler.setFormatter(
            logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        logger.addHandler(_nva_handler)
except Exception as _log_error:  # 日志初始化失败不影响插件运行
    print('nva plugin log setup failed:', _log_error)


# NVAHTTPServer 替换cherrypy中的 CPHTTPServer 负责适配NVA协议
# 主要适配代码位于 NVAHTTPRequest 中
# 主要修改的内容是，适配NVA的协议头：NVA/1.0（等同HTTP看待）


class NVAHTTPRequest(cheroot.server.HTTPRequest):
    def __init__(self, server, conn, proxy_mode=False, strict_mode=True):
        super(NVAHTTPRequest, self).__init__(server, conn, proxy_mode, strict_mode)
        # NVA PATCH: Add a variable indicating whether it is NVA protocol
        self.is_nva = False

    def read_request_line(self):
        """Read and parse first line of the HTTP request.

                Returns:
                    bool: True if the request line is valid or False if it's malformed.

                """
        # HTTP/1.1 connections are persistent by default. If a client
        # requests a page, then idles (leaves the connection open),
        # then rfile.readline() will raise socket.error("timed out").
        # Note that it does this based on the value given to settimeout(),
        # and doesn't need the client to request or acknowledge the close
        # (although your TCP stack might suffer for it: cf Apache's history
        # with FIN_WAIT_2).
        request_line = self.rfile.readline()

        # Set started_request to True so communicate() knows to send 408
        # from here on out.
        self.started_request = True
        if not request_line:
            return False

        if request_line == CRLF:
            # RFC 2616 sec 4.1: "...if the server is reading the protocol
            # stream at the beginning of a message and receives a CRLF
            # first, it should ignore the CRLF."
            # But only ignore one leading line! else we enable a DoS.
            request_line = self.rfile.readline()
            if not request_line:
                return False

        if not request_line.endswith(CRLF):
            self.simple_response(
                '400 Bad Request', 'HTTP requires CRLF terminators',
            )
            return False

        try:
            method, uri, req_protocol = request_line.strip().split(SPACE, 2)
            # NVA PATCH: Fit for NVA protocol
            if b'NVA' in req_protocol:
                req_protocol = req_protocol.replace(b'NVA/1.0', b'HTTP/1.0')
                self.is_nva = True
                # let the http server forget the socket when first request is done
                self.close_connection = True
                self.conn.linger = True

            if not req_protocol.startswith(b'HTTP/'):
                self.simple_response(
                    '400 Bad Request', 'Malformed Request-Line: bad protocol',
                )
                return False
            rp = req_protocol[5:].split(b'.', 1)
            if len(rp) != 2:
                self.simple_response(
                    '400 Bad Request', 'Malformed Request-Line: bad version',
                )
                return False
            rp = tuple(map(int, rp))  # Minor.Major must be threat as integers
            if rp > (1, 1):
                self.simple_response(
                    '505 HTTP Version Not Supported', 'Cannot fulfill request',
                )
                return False
        except (ValueError, IndexError):
            self.simple_response('400 Bad Request', 'Malformed Request-Line')
            return False

        self.uri = uri
        self.method = method.upper()

        if self.strict_mode and method != self.method:
            resp = (
                'Malformed method name: According to RFC 2616 '
                '(section 5.1.1) and its successors '
                'RFC 7230 (section 3.1.1) and RFC 7231 (section 4.1) '
                'method names are case-sensitive and uppercase.'
            )
            self.simple_response('400 Bad Request', resp)
            return False

        try:
            scheme, authority, path, qs, fragment = urllib.parse.urlsplit(uri)
        except UnicodeError:
            self.simple_response('400 Bad Request', 'Malformed Request-URI')
            return False

        uri_is_absolute_form = (scheme or authority)

        if self.method == b'OPTIONS':
            # TODO: cover this branch with tests
            path = (
                uri
                # https://tools.ietf.org/html/rfc7230#section-5.3.4
                if (self.proxy_mode and uri_is_absolute_form)
                else path
            )
        elif self.method == b'CONNECT':
            # TODO: cover this branch with tests
            if not self.proxy_mode:
                self.simple_response('405 Method Not Allowed')
                return False

            # `urlsplit()` above parses "example.com:3128" as path part of URI.
            # this is a workaround, which makes it detect netloc correctly
            uri_split = urllib.parse.urlsplit(b''.join((b'//', uri)))
            _scheme, _authority, _path, _qs, _fragment = uri_split
            _port = EMPTY
            try:
                _port = uri_split.port
            except ValueError:
                pass

            # FIXME: use third-party validation to make checks against RFC
            # the validation doesn't take into account, that urllib parses
            # invalid URIs without raising errors
            # https://tools.ietf.org/html/rfc7230#section-5.3.3
            invalid_path = (
                _authority != uri
                or not _port
                or any((_scheme, _path, _qs, _fragment))
            )
            if invalid_path:
                self.simple_response(
                    '400 Bad Request',
                    'Invalid path in Request-URI: request-'
                    'target must match authority-form.',
                )
                return False

            authority = path = _authority
            scheme = qs = fragment = EMPTY
        else:
            disallowed_absolute = (
                self.strict_mode
                and not self.proxy_mode
                and uri_is_absolute_form
            )
            if disallowed_absolute:
                # https://tools.ietf.org/html/rfc7230#section-5.3.2
                # (absolute form)
                """Absolute URI is only allowed within proxies."""
                self.simple_response(
                    '400 Bad Request',
                    'Absolute URI not allowed if server is not a proxy.',
                )
                return False

            invalid_path = (
                self.strict_mode
                and not uri.startswith(FORWARD_SLASH)
                and not uri_is_absolute_form
            )
            if invalid_path:
                # https://tools.ietf.org/html/rfc7230#section-5.3.1
                # (origin_form) and
                """Path should start with a forward slash."""
                resp = (
                    'Invalid path in Request-URI: request-target must contain '
                    'origin-form which starts with absolute-path (URI '
                    'starting with a slash "/").'
                )
                self.simple_response('400 Bad Request', resp)
                return False

            if fragment:
                self.simple_response(
                    '400 Bad Request',
                    'Illegal #fragment in Request-URI.',
                )
                return False

            if path is None:
                # FIXME: It looks like this case cannot happen
                self.simple_response(
                    '400 Bad Request',
                    'Invalid path in Request-URI.',
                )
                return False

            # Unquote the path+params (e.g. "/this%20path" -> "/this path").
            # https://www.w3.org/Protocols/rfc2616/rfc2616-sec5.html#sec5.1.2
            #
            # But note that "...a URI must be separated into its components
            # before the escaped characters within those components can be
            # safely decoded." https://www.ietf.org/rfc/rfc2396.txt, sec 2.4.2
            # Therefore, "/this%2Fpath" becomes "/this%2Fpath", not
            # "/this/path".
            try:
                # TODO: Figure out whether exception can really happen here.
                # It looks like it's caught on urlsplit() call above.
                atoms = [
                    urllib.parse.unquote_to_bytes(x)
                    for x in QUOTED_SLASH_REGEX.split(path)
                ]
            except ValueError as ex:
                self.simple_response('400 Bad Request', ex.args[0])
                return False
            path = QUOTED_SLASH.join(atoms)

        if not path.startswith(FORWARD_SLASH):
            path = FORWARD_SLASH + path

        if scheme is not EMPTY:
            self.scheme = scheme
        self.authority = authority
        self.path = path

        # Note that, like wsgiref and most other HTTP servers,
        # we "% HEX HEX"-unquote the path but not the query string.
        self.qs = qs

        # Compare request and server HTTP protocol versions, in case our
        # server does not support the requested protocol. Limit our output
        # to min(req, server). We want the following output:
        #     request    server     actual written   supported response
        #     protocol   protocol  response protocol    feature set
        # a     1.0        1.0           1.0                1.0
        # b     1.0        1.1           1.1                1.0
        # c     1.1        1.0           1.0                1.0
        # d     1.1        1.1           1.1                1.1
        # Notice that, in (b), the response will be "HTTP/1.1" even though
        # the client only understands 1.0. RFC 2616 10.5.6 says we should
        # only return 505 if the _major_ version is different.
        sp = int(self.server.protocol[5]), int(self.server.protocol[7])

        if sp[0] != rp[0]:
            self.simple_response('505 HTTP Version Not Supported')
            return False

        self.request_protocol = req_protocol

        # NVA PATCH: Set the correct protocol name to self.response_protocol
        if self.is_nva:
            self.response_protocol = 'NVA/%s.%s' % min(rp, sp)
        else:
            self.response_protocol = 'HTTP/%s.%s' % min(rp, sp)

        return True

    def send_headers(self):  # noqa: C901  # FIXME
        """Assert, process, and send the HTTP response message-headers.

        You must set ``self.status``, and :py:attr:`self.outheaders
        <HTTPRequest.outheaders>` before calling this.
        """
        hkeys = [key.lower() for key, value in self.outheaders]
        status = int(self.status[:3])

        if status == 413:
            # Request Entity Too Large. Close conn to avoid garbage.
            self.close_connection = True
        elif b'content-length' not in hkeys:
            # "All 1xx (informational), 204 (no content),
            # and 304 (not modified) responses MUST NOT
            # include a message-body." So no point chunking.
            if status < 200 or status in (204, 205, 304):
                pass
            else:
                needs_chunked = (
                    self.response_protocol == 'HTTP/1.1'
                    and self.method != b'HEAD'
                )
                if needs_chunked:
                    # Use the chunked transfer-coding
                    self.chunked_write = True
                    self.outheaders.append((b'Transfer-Encoding', b'chunked'))
                else:
                    # Closing the conn is the only way to determine len.
                    self.close_connection = True

        # Override the decision to not close the connection if the connection
        # manager doesn't have space for it.
        if not self.close_connection:
            can_keep = self.server.can_add_keepalive_connection
            self.close_connection = not can_keep

        if b'connection' not in hkeys:
            if self.response_protocol == 'HTTP/1.1':
                # Both server and client are HTTP/1.1 or better
                if self.close_connection:
                    self.outheaders.append((b'Connection', b'close'))
            else:
                # Server and/or client are HTTP/1.0
                if not self.close_connection:
                    self.outheaders.append((b'Connection', b'Keep-Alive'))

        if (b'Connection', b'Keep-Alive') in self.outheaders:
            self.outheaders.append((
                b'Keep-Alive',
                u'timeout={connection_timeout}'.
                format(connection_timeout=self.server.timeout).
                encode('ISO-8859-1'),
            ))

        if (not self.close_connection) and (not self.chunked_read):
            # Read any remaining request body data on the socket.
            # "If an origin server receives a request that does not include an
            # Expect request-header field with the "100-continue" expectation,
            # the request includes a request body, and the server responds
            # with a final status code before reading the entire request body
            # from the transport connection, then the server SHOULD NOT close
            # the transport connection until it has read the entire request,
            # or until the client closes the connection. Otherwise, the client
            # might not reliably receive the response message. However, this
            # requirement is not be construed as preventing a server from
            # defending itself against denial-of-service attacks, or from
            # badly broken client implementations."
            remaining = getattr(self.rfile, 'remaining', 0)
            if remaining > 0:
                self.rfile.read(remaining)

        if b'date' not in hkeys:
            self.outheaders.append((
                b'Date',
                email.utils.formatdate(usegmt=True).encode('ISO-8859-1'),
            ))

        if b'server' not in hkeys:
            self.outheaders.append((
                b'Server',
                self.server.server_name.encode('ISO-8859-1'),
            ))

        # NVA PATCH: Returns the NVA protocol name
        if self.is_nva:
            proto = self.response_protocol.encode('ascii')
        else:
            proto = self.server.protocol.encode('ascii')
        buf = [proto + SPACE + self.status + CRLF]
        for k, v in self.outheaders:
            buf.append(k + COLON + SPACE + v + CRLF)
        buf.append(CRLF)
        self.conn.wfile.write(EMPTY.join(buf))


class NVAHTTPConnection(cheroot.server.HTTPConnection):
    RequestHandlerClass = NVAHTTPRequest


class NVAHTTPServer(_cpnative_server.CPHTTPServer):
    ConnectionClass = NVAHTTPConnection

# 负责下载的函数


class NetworkManager:
    proxies = None

    @staticmethod
    def GET(url, sign=False):
        headers = {
            "User-Agent": "Macast",
            "Referer": "https://www.bilibili.com/client",
            "Origin": "https://www.bilibili.com"
        }
        if sign:
            url_path = url.split("?")[0]
            data = url.split("?")[1].split("&")
            params = {}
            for i in data:
                k, v = i.split("=")
                params[k] = v
            params.update({'appkey': APP_KEY, 'ts': int(time.time())})
            params = dict(sorted(params.items()))
            query = '&'.join([k + "=" + urllib.parse.quote(str(params[k]), safe='') for k in params])
            sign = hashlib.md5((query+APP_SEC).encode()).hexdigest()
            params.update({'sign':sign})
            query = '&'.join([k + "=" + urllib.parse.quote(str(params[k]), safe='') for k in params])
            url = f'{url_path}?{query}'

        try:
            data = requests.get(url, headers=headers, proxies=NetworkManager.proxies)
            return data
        except OSError as e:
            # fix proxy error with clash
            logger.error(f'nva requests.get OSError:{e}')
            if 'proxy' in str(e):
                try:
                    NetworkManager.proxies = {'http': None, "https": None}
                    data = requests.get(url, proxies=NetworkManager.proxies)
                    return data
                except Exception as e:
                    logger.error(f'nva requests.get Exception:{e}')

        cherrypy.engine.publish('app_notify', 'ERROR', 'Network error')
        raise Exception('Cannot get any data from network.')

# DanmakuManager 负责处理弹幕下载和渲染
# 通过cid下载xml实时弹幕，转换为ass，保存为本地文件
# todo 实现protobuf实时弹幕下载与转换
# todo 实现弹幕文字大小随视频比例变化


class DanmakuManager:
    # NVA PATCH: 弹幕文本里的 ASS 控制符必须转义，否则一条脏弹幕会毁掉整份字幕
    @staticmethod
    def clean_danmaku_text(text) -> str:
        text = str(text).replace('\r', ' ').replace('\n', ' ')
        text = text.replace('\\', '／').replace('{', '（').replace('}', '）')
        return text.strip()

    @staticmethod
    def get_danmaku(cid: str, file_path: str):
        """

        :param cid:
        :param file_path:
        :param is_portrait:
        :return:
        """
        # http://www.perlfu.co.uk/projects/asa/ass-specs.doc
        api = f'https://comment.bilibili.com/{cid}.xml'
        exist_time = 10
        res_x = 638
        res_y = 447

        lines = res_y // 25  # todo fix
        layers = [[-1 for _ in range(lines)] for _ in range(4)]

        def int2color(color_int):
            """
            :return: string, \c&Hbbggrr&
            """
            if color_int == 16777215:  # default color #FFFFFF
                return 'dark', ''
            color_int = hex(color_int)[2:]
            if len(color_int) < 6:
                color_int = '0' * (6 - len(color_int)) + color_int
            r = int(color_int[0:2], 16)
            g = int(color_int[2:4], 16)
            b = int(color_int[4:6], 16)
            gray = (r * 299 + g * 587 + b * 114) / 1000
            border_style = 'dark'
            if gray < 60:
                border_style = 'light'

            color_str = color_int[4:6] + color_int[2:4] + color_int[0:2]
            return border_style, rf'\c&H{color_str}&'

        def sec2str(t: float) -> str:
            sec = int(t)
            return f'{sec // 3600}:{(sec % 3600) // 60:02d}:{sec % 60:02d}.{int(t * 100) % 100:02d}'

        def create_postion(danmaku_position_type, layer_index, danmaku_text,
                           font_size, danmaku_start_time) -> str:
            if layer_index > 1:  # 是否是字幕层
                layer_index = 1

            y = -100
            if danmaku_position_type == 5:  # 顶部弹幕
                layer_index = 2
                for index, l in enumerate(layers[layer_index]):
                    if danmaku_start_time < l:
                        continue
                    layers[layer_index][index] = danmaku_start_time + exist_time
                    y = index * 25
                    break
                position_str = rf'\an8\pos({int(res_x / 2)},{y})'
            elif danmaku_position_type == 4:  # 底部弹幕
                layer_index = 3
                for index, l in enumerate(layers[layer_index]):
                    if danmaku_start_time < l:
                        continue
                    layers[layer_index][index] = danmaku_start_time + exist_time
                    y = res_y - index * 25
                    break
                position_str = rf'\an2\pos({int(res_x / 2)},{y})'
            else:  # 普通弹幕
                length = len(danmaku_text) * font_size
                for index, l in enumerate(layers[layer_index]):
                    danmaku_text_length = len(danmaku_text) * font_size
                    danmaku_text_time = (res_x * exist_time) / (res_x + danmaku_text_length)

                    if (danmaku_start_time + danmaku_text_time) < l:
                        continue
                    # 找到空位
                    layers[layer_index][index] = danmaku_start_time + exist_time
                    y = index * 25  # fix font size
                    break

                position_str = rf'\move({res_x},{y},{-length},{y})'

            # todo 根据视频大小 动态改变字体大小
            font_size = int(font_size)
            font = ''
            if font_size == 18:
                font = r'\fs18'
            elif font_size == 36:
                font = r'\fs36'

            return position_str + font

        try:
            danmaku = etree.fromstring(NetworkManager.GET(api).content)
            danmaku = danmaku.xpath("/i/d")
            ass = """[Script Info]
Title: 弹幕
Original Script: """ + api + """
Script Updated By: https://github.com/xfangfang/Macast-Plugin
Update Details: xml to ass
ScriptType: V4.00+
Collisions: Normal

PlayResX: 638
PlayResY: 447
PlayDepth: 8
Timer: 100.0
WrapStyle: 2


[v4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: dark, sans-serif, 25, &H36FFFFFF, &H36FFFFFF, &H36000000, &H36000000, 1, 0, 0, 0, 100, 100, 0.00, 0.00, 1, 1, 0, 7, 0, 0, 0, 0
Style: light, sans-serif, 25, &H36FFFFFF, &H36FFFFFF, &H36FFFFFF, &H36000000, 1, 0, 0, 0, 100, 100, 0.00, 0.00, 1, 1, 0, 7, 0, 0, 0, 0

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

            dms = []
            for i in danmaku:
                raw = i.attrib.get('p', '')
                text = i.text
                if not text:
                    continue  # NVA PATCH: 空文本弹幕直接丢弃
                fields = raw.split(',')
                if len(fields) < 8:
                    continue  # NVA PATCH: 字段不完整的脏数据
                try:
                    start = float(fields[0])
                except (TypeError, ValueError):
                    continue  # NVA PATCH: 时间戳异常的弹幕会让排序整体失败
                dms.append((start, fields + [text]))

            dms.sort(key=lambda item: item[0])

            skipped = 0
            for start_time, data in dms:
                try:
                    text = DanmakuManager.clean_danmaku_text(data[-1])
                    danmaku_type = int(data[1])
                    danmaku_layer = int(data[5])
                    if not text or danmaku_type >= 7:
                        continue
                    end_time = start_time + exist_time
                    position = create_postion(danmaku_type, danmaku_layer, text,
                                              int(float(data[2])), start_time)
                    style, color = int2color(int(data[3]))
                    # NVA PATCH: Name 字段原来放的是未清洗的弹幕文本，
                    # 文本里带逗号会破坏 Dialogue 的字段分隔，这里改用弹幕 id
                    comment = f'Dialogue: {danmaku_layer},{sec2str(start_time)},{sec2str(end_time)},' + \
                              f'{style},{data[7]},0000,0000,0000,,{{{position}{color}}}{text}\n'
                    ass += comment
                except Exception as e:
                    # NVA PATCH: 单条弹幕异常不能影响整个文件
                    skipped += 1
                    logger.debug(f'skip danmaku {data}: {e}')
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(ass)
            if skipped:
                logger.info(f'跳过 {skipped} 条异常弹幕 cid={cid}')
        except Exception as e:
            logger.error(f'Error create sub file: {e}')
            cherrypy.engine.publish('app_notify', 'ERROR', f'Error create sub file: {e}')
            return None

        return file_path


# NVAConectionHandler 负责保持每个客户端的长连接
# 解析和处理NVA协议数据，定时发送心跳包


class NVAConectionBaseHandler:

    def __init__(self, conn, req):
        self.sock = conn
        self.sock_lock = threading.Lock()

        self.counter = 0
        self.counter_lock = threading.Lock()

        self.cache = b''
        self.session = req.headers.get('Session', '')

        self.terminated = False
        self.ping_thread_running = False
        self.ping_thread = None

    def start(self):
        self.ping_thread_running = True
        self.ping_thread = threading.Thread(target=self.send_ping_thread,
                                            name='NVA_PING_THREAD',
                                            daemon=False)
        self.ping_thread.start()

    def cmd_from_client(self, method, counter, params=None):
        pass

    def res_from_client(self, counter, params=None):
        pass

    def terminate(self):
        self.ping_thread_running = False
        self.terminated = True
        if self.sock:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
                self.sock.close()
            except:
                pass
            finally:
                self.sock = None
        # NVA PATCH: 连接可能在 ping 线程创建前就被关闭
        if self.ping_thread is not None:
            self.ping_thread.join()

    def send_ping_thread(self, freq=1):
        logger.info("NVA_PING_THREAD START")
        # NVA PATCH: socket 已关闭时不要再操作它
        if self.sock is None:
            logger.info("NVA_PING_THREAD DONE (socket already closed)")
            return
        self.sock.setblocking(True)
        while self.ping_thread_running:
            time.sleep(freq)
            self.send_ping()

        logger.info("NVA_PING_THREAD DONE")

    def send_res(self, counter, data=None):
        logger.info(f"SEND_RES{counter} data:{data}")
        if data is None:
            binary = struct.pack(f">cBI", RET_CMD, 0, counter)
        else:
            data = json.dumps(data, separators=(',', ':')).encode()
            length = len(data)
            binary = struct.pack(f">cB2I{length}s", RET_CMD, 1, counter, length, data)
        logger.debug(f'SEND_RES {binary}')
        self.send(binary)

    def send_ping(self):
        logger.info(f'NVA_PING_THREAD send ping {self.counter}')
        with self.counter_lock:
            self.counter += 1
        binary = struct.pack(f">cBI", PING, 0, self.counter)
        self.send(binary)

    def send_cmd(self, cmd, data=None):
        logger.info(f"SEND_CMD{self.counter} cmd:{cmd} data:{data}")
        with self.counter_lock:
            self.counter += 1
        cmd = cmd.encode()
        cmd_length = len(cmd)

        if data is None:
            binary = struct.pack(f">cBI2B7sB{cmd_length}s", SEND_CMD, 2, self.counter, 1, 7, COMMAND, cmd_length, cmd)
        else:
            data = json.dumps(data, separators=(',', ':')).encode()
            length = len(data)
            binary = struct.pack(f">cBI2B7sB{cmd_length}sI{length}s",
                                 SEND_CMD, 3, self.counter, 1, 7, COMMAND, cmd_length,
                                 cmd, length, data)
        logger.debug(f"SEND_CMD {binary}")
        self.send(binary)

    def send(self, data):
        # NVA PATCH: 连接已经关闭时静默丢弃，避免 ping 线程刷出 AttributeError
        if self.terminated or self.sock is None:
            return
        with self.sock_lock:
            if self.sock is None:
                return
            try:
                self.sock.sendall(data)
            except OSError as e:
                # 对端断开属于正常竞态，接收侧会负责清理连接
                logger.debug(f'send 失败（连接已断开）: {e}')

    def parse_request(self, data):
        index = 0
        self.cache += data
        data = self.cache
        length = len(data)
        while index < length:
            if length - index < 6:  # the smallest package length
                break
            if data[index] not in [SEND_CMD[0], RET_CMD[0]]:
                # wrong header
                index += 1
                continue
            try:
                header, all_l, counter = struct.unpack('>cBI', data[index:index + 6])
                if data[index] == SEND_CMD[0]:
                    assert all_l in [2, 3]
                    if length - index - 6 < 10:
                        break
                    n, cmd_l, cmd_str, method_l = struct.unpack('>BB7sB', data[index + 6:index + 16])
                    assert n == 1 and cmd_l == 7 and cmd_str == COMMAND
                    if all_l == 2:
                        # eg: Command GetVolume
                        if length - index - 16 < method_l:
                            break
                        method = struct.unpack(f'>{method_l}s', data[index + 16:index + 16 + method_l])[0]
                        self.cmd_from_client(method.decode(), counter)
                        index += 16 + method_l
                    else:
                        # eg: Command OnProgress {"duration": 422, "position": 64}
                        if length - index - 16 < method_l + 4:
                            break
                        method, param_l = struct.unpack(f'>{method_l}sI', data[index + 16:index + method_l + 20])
                        if length - index - method_l - 20 < param_l:
                            break
                        params = \
                            struct.unpack(f'>{param_l}s', data[index + method_l + 20:index + method_l + 20 + param_l])[
                                0]
                        try:
                            params = json.loads(params)
                        except Exception as e:
                            # error decode params
                            logger.debug(f'客户端命令参数解析失败: {e}')
                        else:
                            self.cmd_from_client(method.decode(), counter, params)
                        finally:
                            index += method_l + 20 + param_l
                else:
                    assert all_l in [0, 1]
                    if all_l == 0:
                        # return nothing
                        self.res_from_client(counter)
                        index += 6
                    else:
                        # {"volume": 0}
                        if length - index - 6 < 4:
                            break
                        param_l = struct.unpack(f'>I', data[index + 6:index + 10])[0]
                        if length - index - 10 < param_l:
                            break
                        params = struct.unpack(f'>{param_l}s', data[index + 10:index + 10 + param_l])[0]
                        try:
                            params = json.loads(params)
                        except Exception as e:
                            # error decode params
                            logger.debug(f'客户端返回值解析失败: {e}')
                        else:
                            self.res_from_client(counter, params)
                        finally:
                            index += 10 + param_l
            except Exception as e:
                # NVA PATCH: 这里的异常以前被静默（debug 级别），命令失效时完全看不到原因
                logger.exception(f'解析请求失败: {e}')
                index += 1
                # try to get next batch of data
        self.cache = data[index:]


class NVAConectionHandler(NVAConectionBaseHandler):

    def __init__(self, conn, req):
        super(NVAConectionHandler, self).__init__(conn, req)
        self.session = req.headers.get('Session', '')
        self.uuid = req.headers.get('UUID', '')
        self.playlist = []
        self.sub = os.path.join(SETTING_DIR, 'macast.ass')
        # NVA PATCH: 记录当前弹幕状态与已生成弹幕的 cid
        self.danmaku_open = True
        self.danmaku_cid = ''
        # NVA PATCH: DASH 流的独立音轨地址
        self.audio_url = ''
        logger.info(f'创建 NVAConectionHandler session:{self.session[-4:]} uuid:{self.uuid[-4:]}')

        self.aid = ''
        self.oid = ''
        self.cid = ''
        self.epid = ''
        self.season_id = ''
        self.roomId = ''
        self.access_key = ''
        self.current_qn = 0
        self.desire_qn = 0
        self.desire_speed = 1
        self.qn = {}
        self.playurl_type = 1
        self.content_type = 1
        self.title = ''
        self.title_p = ''
        self.is_portrait = False
        self.danmaku_switch_save = True

    def __del__(self):
        logger.info(f'销毁 NVAConectionHandler session:{self.session[-4:]} uuid:{self.uuid[-4:]}')

    @property
    def renderer(self) -> Renderer:
        renderers = cherrypy.engine.publish('get_renderer')
        if len(renderers) == 0:
            logger.error("Unable to find an available renderer.")
            return Renderer()
        return renderers.pop()

    @property
    def protocol(self) -> Protocol:
        protocols = cherrypy.engine.publish('get_protocol')
        if len(protocols) == 0:
            logger.error("Unable to find an available protocol.")
            return NVAProtocol()
        return protocols.pop()

    def get_video_info(self):
        url = 'https://api.bilibili.com/x/tv/card/view_v2?'
        params = {
            # 'access_key': self.access_key,
            'auto_play': 0,
            'build': 106400,
            'card_type': 2 if self.epid != 0 else 1,
            'fourk': 0,
            'is_ad': 'false',
            'mobi_app': 'android_tv_yst',
            'object_id': self.season_id if self.epid != 0 else self.oid,
            'view_type': 2  # todo 验证参数含义
        }
        url += '&'.join([f'{i}={params[i]}' for i in params])
        play_list = []
        play_index = 0
        try:
            json_text = NetworkManager.GET(url).text
            json_obj = json.loads(json_text)
            if json_obj['code'] != 0:
                logger.error(f"Error getting video info 1: {json_obj['message']}")
                cherrypy.engine.publish('app_notify', 'ERROR', json_obj['message'])
                raise Exception('error')
            self.title = json_obj['data']['title']
            video_list = json_obj['data']['auto_play']['cid_list']
            for index, video in enumerate(video_list):
                title_p = video.get('title', '')
                if video.get('long_title', '') != '':
                    title_p = video.get('long_title', '')
                play_list.append({
                    'oid': video['playurl_args']['object_id'],
                    'epid': video['playurl_args']['object_id'],
                    'cid': video['playurl_args']['cid'],
                    'aid': video['aid'],
                    'title': title_p,
                    'is_portrait': video['is_portrait']
                })
                if int(self.cid) == int(video['playurl_args']['cid']):
                    play_index = index
                    logger.info(f"当前正在播放 分集{index + 1} {title_p}")
                    self.is_portrait = video['is_portrait']
                    self.renderer.set_media_title(f'{self.title} {title_p}')
        except Exception as e:
            logger.error(f"Error getting video info 2: {e}")
            cherrypy.engine.publish('app_notify', 'ERROR', f"Error getting video info: {e}")
        finally:
            self.protocol.play_list = play_list
            self.protocol.play_index = play_index

    def get_video_url(self) -> (str, dict):
        """NVA PATCH: 优先 DASH（B 站的高画质只通过 DASH 提供），
        失败时回退到 FLV 合并流（最高 720P）。"""
        for fnval in (16, None):
            url, qn = self.request_play_url(fnval)
            if url:
                return url, qn
        return None, {}

    def request_play_url(self, fnval=None) -> (str, dict):
        # NVA PATCH: 每次取流都重置音轨，避免上一个视频的音轨残留
        self.audio_url = ''

        base_url = 'https://api.bilibili.com/x/tv/playurl?'
        params = {
            'access_key': self.access_key,
            'actionKey': 'appkey',
            'appkey': APP_KEY,
            'build': 36700100,
            'cid': self.cid,
            'fourk': 1,
            'is_proj': 1,
            'mobile_access_key': self.access_key,
            'object_id': self.oid, # epid or aid
            'ogv_aid': self.aid, # ep aid or empty
            'platform': 'ios',
            'playurl_type': self.playurl_type,
            'protocol': 0,
            'qn': self.desire_qn,
        }
        if fnval:
            # NVA PATCH: 16 = DASH，只有 DASH 才会返回 1080P 及以上的轨道
            params['fnval'] = fnval
        url = base_url + '&'.join(f'{i}={params[i]}' for i in params)
        try:
            res = NetworkManager.GET(url, sign=True).text
            res = json.loads(res)
            if res['code'] != 0:
                error_msg = res.get('message', '')
                if error_msg != '':
                    cherrypy.engine.publish('app_notify', 'ERROR', error_msg)
                    logger.error(f'获取播放地址失败: {error_msg} 参数: {params}')
                return None, {}

            qn_support = {}
            qn_extras = res['data'].get('qn_extras', [])
            for i in qn_extras:
                q = i['qn']
                if q not in qn_support:
                    qn_support[q] = {}
                qn_support[q]['quality'] = q
                qn_support[q]['needVip'] = i.get('need_vip', False)
                qn_support[q]['needLogin'] = i.get('need_login', False)
            support_formats = res['data'].get('support_formats', [])
            for i in support_formats:
                q = i['quality']
                if q not in qn_support:
                    qn_support[q] = {}
                qn_support[q]['description'] = i.get('new_description', '')
                qn_support[q]['displayDesc'] = i.get('display_desc', '')
                qn_support[q]['superscript'] = "Macast " + i.get('superscript', '')  # todo: 专有尾巴
            # NVA PATCH: 部分视频不返回 support_formats（直播/课程等），用 accept_quality 兜底，
            # 否则客户端拿不到画质列表，表现为"没有切换画质的选项"
            accept_quality = res['data'].get('accept_quality') or []
            accept_description = res['data'].get('accept_description') or []
            for index, quality in enumerate(accept_quality):
                if quality not in qn_support:
                    qn_support_entry = {}
                    qn_support[quality] = qn_support_entry
                else:
                    qn_support_entry = qn_support[quality]
                if index < len(accept_description):
                    qn_support_entry.setdefault('description', accept_description[index])
                    qn_support_entry.setdefault('displayDesc', accept_description[index])
                    qn_support_entry.setdefault('superscript', '')
                qn_support_entry.setdefault('quality', quality)
                qn_support_entry.setdefault('needVip', False)
                qn_support_entry.setdefault('needLogin', False)
            for quality in qn_support:
                qn_support[quality].setdefault('description', '')
                qn_support[quality].setdefault('displayDesc', '')
                qn_support[quality].setdefault('superscript', '')
                qn_support[quality].setdefault('needVip', False)
                qn_support[quality].setdefault('needLogin', False)
            qn_support = [qn_support[i] for i in qn_support]
            # NVA PATCH: 先决定取流方式与实际画质，再决定是否提示降级
            reported_qn = res['data'].get('quality', 0)
            dash = res['data'].get('dash') or {}
            videos = dash.get('video') or []
            audios = dash.get('audio') or []
            audio_supported = getattr(self.renderer, 'support_audio_file', False)
            video_track = None
            audio_url = ''
            # DASH 的音视频是分开的：只有渲染器能挂外部音轨、且两条轨都在时才用 DASH，
            # 否则回退到合并流（720P 上限，但有声音）
            if videos and audios and audio_supported:
                # NVA PATCH: 客户端的画质参数是字符串（'80'），必须转 int 才能匹配轨道 id
                desire_qn = self.parse_qn(self.desire_qn)
                target_qn = desire_qn if any(v.get('id') == desire_qn
                                             for v in videos) else reported_qn
                video_track = next((v for v in videos if v.get('id') == target_qn), None) \
                    or max(videos, key=lambda v: v.get('id', 0))
                audio_url = max(audios, key=lambda a: a.get('id', 0))['base_url']
            actual_qn = video_track['id'] if video_track else reported_qn
            self.current_qn = actual_qn
            self.qn = {"curQn": self.current_qn,
                       "supportQnList": qn_support,
                       "userDesireQn": self.parse_qn(self.desire_qn)
                       }
            # NVA PATCH: 请求的画质被 B 站降级时说明原因，而不是静默回退
            desire_qn = self.parse_qn(self.desire_qn)
            if desire_qn and self.current_qn and int(self.current_qn) < desire_qn:
                try:
                    self.notify_qn_downgrade(qn_support)
                except Exception:
                    logger.exception('画质降级提示失败')

            if video_track:
                logger.info(f'使用 DASH 流 qn={actual_qn} 音轨={"有" if audio_url else "无"}')
                self.audio_url = audio_url
                return video_track['base_url'], self.qn

            # todo 清晰度切换
            # NVA PATCH: 这些字段不保证存在，用 get 避免 KeyError 直接打断播放
            durl = res['data'].get('durl')
            if durl:
                return durl[0]['url'], self.qn  # todo: fix error when durl have more than one videos

            if videos:
                # 兜底：只有视频轨可用时仍然给出地址（可能没有声音）
                logger.warning('DASH 流缺少可挂载的音轨，将静音播放视频轨')
                selected = max(videos, key=lambda v: v.get('id', 0))
                return selected['base_url'], self.qn

            # todo 多个直播流切换
            live = res['data'].get('live_mobile')
            if live and live.get('stream'):
                return live['stream'], self.qn

            live = res['data'].get('live_stream')
            if live and live.get('flv'):
                for i in live['flv']:
                    return i, self.qn


        except Exception as e:
            logger.error(f'error getting video urls {e}')
            cherrypy.engine.publish('app_notify', 'ERROR', f'error getting video urls {e}')
        return None, {}

    @staticmethod
    def parse_qn(value, default=0) -> int:
        """NVA PATCH: 客户端发来的画质是字符串（'80'），必须转成 int，
        否则与 DASH 轨 id（int）比较永远不相等，点 1080P 会静默失败"""
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def parse_speed(value, default=1.0) -> float:
        """NVA PATCH: 倍速参数同样是字符串，且空值/非法值不能中断命令"""
        try:
            speed = float(value)
        except (TypeError, ValueError):
            return default
        return speed if speed > 0 else default

    def danmaku_file(self, cid) -> str:
        """NVA PATCH: 每个视频使用独立弹幕文件，避免切集/切画质互相覆盖"""
        cid = str(cid or '').strip()
        name = ''.join(ch for ch in cid if ch.isalnum() or ch in ('_', '-'))
        if not name:
            return self.sub
        return os.path.join(SETTING_DIR, f'macast-danmaku-{name}.ass')

    def notify_qn_downgrade(self, qn_support):
        """NVA PATCH: 请求的画质被降级时，明确告诉用户原因（登录/大会员）"""
        want = int(self.desire_qn)
        entry = next((i for i in qn_support if i.get('quality') == want), None)
        reason = ''
        if entry:
            if entry.get('needVip'):
                reason = '需要大会员'
            elif entry.get('needLogin'):
                reason = '需要登录 B 站账号'
        current = next((i.get('displayDesc') or i.get('description', '')
                        for i in qn_support if i.get('quality') == self.current_qn), '')
        message = f'已切换到 {current or self.current_qn}'
        if reason:
            message += f'，更高画质{reason}'
        logger.info(f'画质降级: 请求 {want} -> 实际 {self.current_qn} ({reason or "无限制信息"})')
        self.renderer.set_media_text(message, 4000)
        cherrypy.engine.publish('app_notify', 'Macast', message)

    def send_play_cmd(self, url: str, start='0'):
        # NVA PATCH: 没有拿到播放地址时不要 re-load 空地址，否则播放器会停止
        if not url:
            logger.error('没有拿到播放地址，保持当前播放状态')
            cherrypy.engine.publish('app_notify', 'Macast', '获取播放地址失败，请检查网络或 B 站登录状态')
            return
        self.protocol.set_state_url(url)
        self.renderer.set_media_url(url, start)
        # NVA PATCH: DASH 流的音轨要单独挂载，必须在 loadfile 之后
        if self.audio_url:
            try:
                self.renderer.set_media_audio_file(self.audio_url)
            except Exception:
                # 挂载音轨失败不能影响播放、弹幕和后续控制命令
                logger.exception('挂载 DASH 音轨失败')
        self.renderer.set_media_speed(self.desire_speed)
        self.renderer.set_media_title(f'{self.title} {self.title_p}')
        cherrypy.engine.publish('renderer_av_uri', url)
        # 通知客户端，正在加载
        cherrypy.engine.publish('nva-broadcast', 'OnPlayState', {"playState": 3})
        try:
            self.update_play_state()
        except Exception:
            # NVA PATCH: 状态广播失败不能阻断后续的弹幕加载
            logger.exception('更新播放状态失败')
        threading.Thread(target=self.get_extra_info_thread,
                         name='NVA_EXTRA_INFO').start()

    def get_extra_info_thread(self):
        """NVA PATCH: 弹幕与分集信息在后台线程获取，异常必须写进日志"""
        try:
            # 直播暂不获取额外的信息
            if self.playurl_type == 4:
                self.renderer.set_media_title(f'直播间: {self.roomId}')
                return
            logger.info("start get_extra_info")
            self.load_danmaku()
            # 不获取课程的视频信息
            if self.content_type and int(self.content_type) != 2:
                self.get_video_info()
            logger.info("end get_extra_info")
        except Exception:
            logger.exception('获取弹幕/分集信息失败')

    def load_danmaku(self):
        """NVA PATCH: 下载并挂载弹幕，失败或没有弹幕时给出明确提示"""
        if not self.cid or self.playurl_type == 4:
            return
        sub_file = self.danmaku_file(self.cid)
        # 同一个视频（例如切换画质）不需要重新生成弹幕
        need_download = (self.danmaku_cid != str(self.cid)
                         or not os.path.exists(sub_file)
                         or os.path.getsize(sub_file) < 512)
        if need_download:
            result = DanmakuManager.get_danmaku(str(self.cid), sub_file)
            if result is None:
                logger.error(f'弹幕生成失败 cid={self.cid}')
                self.renderer.set_media_text('弹幕加载失败', 3000)
                return
            self.danmaku_cid = str(self.cid)
        try:
            size = os.path.getsize(sub_file)
        except OSError:
            size = 0
        if size < 512:
            logger.info(f'cid={self.cid} 没有弹幕数据')
            self.renderer.set_media_text('该视频暂无弹幕', 3000)
            return
        logger.info(f'挂载弹幕 {sub_file} ({size} bytes)')
        self.renderer.set_media_sub_file({
            'url': sub_file,
            'title': '弹幕'
        })
        self.renderer.set_media_sub_show(self.danmaku_open)

    def update_play_state(self):
        if self.danmaku_switch_save:
            self.danmaku_open = bool(self.protocol.get_state_display_subtitle())
        self.set_danmaku_visibility(self.danmaku_open)
        cherrypy.engine.publish('nva-broadcast', 'OnEpisodeSwitch',
                                {"playItem": {"aid": self.aid,
                                              "cid": self.cid,
                                              "contentType": self.content_type,
                                              "epId": self.epid,
                                              "seasonId": self.season_id},
                                 "qnDesc": self.qn,
                                 "title": f'{self.title} {self.title_p}'})
        cherrypy.engine.publish('nva-broadcast', 'OnQnSwitch', self.qn)
        # NVA PATCH: 播放速度状态还没就绪时 float('') 会抛异常，
        # 原来会让 send_play_cmd 中断（弹幕线程都不会启动）
        try:
            current_speed = round(float(self.protocol.get_state_speed()), 2)
        except (TypeError, ValueError):
            current_speed = 1.0
        support_speed = [0.5, 0.75, 1, 1.25, 1.5, 2]
        cherrypy.engine.publish('nva-broadcast', 'SpeedChanged',
                                {"currSpeed": current_speed, "supportSpeedList": support_speed})

    def set_danmaku_visibility(self, visible: bool):
        """NVA PATCH: 弹幕开关同时同步到渲染层与协议层。

        原实现只调用 renderer，协议层状态不会更新，导致下一次投屏
        update_play_state() 又按旧状态把弹幕关掉（issue #22）。
        """
        self.danmaku_open = bool(visible)
        self.renderer.set_media_sub_show(self.danmaku_open)
        self.protocol.set_state_display_subtitle(self.danmaku_open)
        cherrypy.engine.publish('nva-broadcast', 'OnDanmakuSwitch', {'open': self.danmaku_open})

    def cmd_from_client(self, method, counter, params=None):
        logger.info(f'CMD{counter} method:{method} params{params}')
        if method == 'GetVolume':
            volume = self.protocol.get_state_volume()
            self.send_res(counter, {'volume': volume})
        elif method == 'SetVolume':
            volume = params.get('volume', -1)
            if 0 <= volume <= 100:
                self.renderer.set_media_volume(volume)
        elif method == 'Pause':
            self.send_res(counter)
            self.renderer.set_media_pause()
        elif method == 'Resume':
            self.send_res(counter)
            self.renderer.set_media_resume()
        elif method == 'SendDanmaku':
            # todo 1.发送弹幕，2.通过附字幕实现实时显示
            # 1：滚动
            # 5：上
            # 4：下
            # {'size': 25, 'mRemoteDmId': 1184473088, 'content': '感动', 'action': '', 'type': 1, 'color': 16777215}
            # {'size': 18, 'mRemoteDmId': -1382023168, 'content': '？！', 'action': '', 'type': 4, 'color': 16777215}
            self.send_res(counter)
            self.renderer.set_media_text(f'暂未支持弹幕：{params["content"]}', 4000)
        elif method == 'SwitchDanmaku':
            self.send_res(counter)
            # NVA PATCH: 开关状态同步到协议层，避免下次投屏被旧状态覆盖
            is_open = params.get('open', True)
            if isinstance(is_open, str):
                is_open = is_open.lower() != 'false'
            self.set_danmaku_visibility(bool(is_open))
        elif method == 'SwitchSpeed':
            speed = self.parse_speed(params.get('speed', 1))
            self.desire_speed = speed
            self.renderer.set_media_speed(speed)
            self.renderer.set_media_text(f'修改倍速：{speed}X', 2000)
            # NVA PATCH: 必须把新倍速回传给客户端，否则 App 里的倍速 UI 不会更新
            # （表现为"切换倍速无效"）；同时写入协议状态，供后续投屏读取
            self.protocol.set_state_speed(str(speed))
            cherrypy.engine.publish('nva-broadcast', 'SpeedChanged',
                                    {"currSpeed": speed,
                                     "supportSpeedList": [0.5, 0.75, 1, 1.25, 1.5, 2]})
        elif method == 'SwitchQn':
            self.send_res(counter)
            # NVA PATCH: 不同客户端版本用的字段名不一样，且缺参数时不能抛异常中断整条命令
            qn = params.get('qn', params.get('quality', params.get('curQn')))
            try:
                qn = int(qn)
            except (TypeError, ValueError):
                logger.error(f'SwitchQn 参数无效: {params}')
                return
            if qn == self.current_qn:
                logger.info(f'SwitchQn 画质未变化 qn={qn}，忽略')
                return
            previous_qn = self.current_qn
            self.desire_qn = qn
            url, _ = self.get_video_url()
            if not url:
                # NVA PATCH: 切换失败时回退到原画质并把状态同步给客户端，避免 UI 与实际不一致
                logger.error(f'SwitchQn 失败 qn={qn}，回退到 {previous_qn}')
                self.desire_qn = previous_qn
                self.current_qn = previous_qn
                cherrypy.engine.publish('nva-broadcast', 'OnQnSwitch', self.qn)
                self.renderer.set_media_text('该画质不可用（可能需要登录 B 站或大会员）', 4000)
                return
            position = self.protocol.get_state_position()
            self.send_play_cmd(url, position)
        elif method == 'Stop':
            self.send_res(counter)
            self.renderer.set_media_stop()
        elif method == 'Play':
            self.send_res(counter)
            self.aid = params['aid']
            self.oid = params.get('oid', self.aid)
            self.cid = params['cid']
            self.roomId = params.get('roomId', 0)
            self.epid = int(params.get('epId', 0))
            self.access_key = params.get('accessKey', '')
            # NVA PATCH: 统一转成 int/float，客户端传的是字符串
            self.current_qn = self.parse_qn(params.get('userDesireQn'))
            self.desire_qn = self.parse_qn(params.get('userDesireQn'))
            self.content_type = params.get('contentType', 1)
            self.season_id = int(params.get('seasonId', 0))
            self.playurl_type = 1
            self.danmaku_switch_save = params.get('danmakuSwitchSave', True)
            self.desire_speed = self.parse_speed(params.get('userDesireSpeed', 1))
            self.title = ''
            if int(self.epid) != 0:
                # 番剧
                self.oid = self.epid
                self.playurl_type = 2
            if int(self.roomId) != 0:
                self.playurl_type = 4
                self.oid = self.roomId

            url, qn = self.get_video_url()
            logger.info(f'播放地址: {url} qn: {qn}')
            self.send_play_cmd(url, params.get('seekTs', 0))
        elif method == 'PlayUrl':
            # todo 开始时seek
            self.send_res(counter)
            url = params.get('url', '')
            title = params.get('title', '')
            self.title = title
            # NVA PATCH: 客户端直接给地址，没有分离音轨
            self.audio_url = ''

            video_info = json.loads(parse.parse_qs(url)['nva_ext'][0])
            ver = video_info.get('ver', -1)
            if ver != 2:
                logger.error("Maybe error in url parse")
            params = video_info.get('content', {})
            self.qn = {"curQn": 0,
                       "supportQnList": [{"description": "",
                                          "displayDesc": "",
                                          "needLogin": False,
                                          "needVip": False,
                                          "quality": 0,
                                          "superscript": ""}],
                       "userDesireQn": 0}
            logger.info(f'PlayUrl 参数: {params}')
            # todo
            self.aid = params['aid']
            self.oid = params.get('oid', self.aid)
            self.cid = params['cid']
            self.epid = int(params.get('epId', 0))
            self.access_key = params.get('accessKey', '')
            self.current_qn = self.parse_qn(params.get('userDesireQn'))
            self.desire_qn = self.parse_qn(params.get('userDesireQn'))
            self.content_type = params.get('contentType', 1)
            self.playurl_type = 1
            self.season_id = int(params.get('seasonId', 0))
            self.desire_speed = self.parse_speed(params.get('userDesireSpeed', 1))
            # todo danmuku switch save
            self.danmaku_switch_save = params.get('danmakuSwitchSave', True)
            if self.epid != 0:
                # 番剧
                self.oid = self.epid
                self.playurl_type = 2

            self.send_play_cmd(url, start=params.get('seekTs', 0))
        elif method == 'Seek':
            self.send_res(counter)
            position = params.get('seekTs', 0)  # second?
            duration = NVAProtocol.position_to_second(self.protocol.get_state_duration())
            cherrypy.engine.publish('nva-broadcast',
                                    'OnProgress', {"duration": duration,
                                                   "position": position
                                                   })
            position = f'{position // 3600}:{(position % 3600) // 60:02d}:{position % 60:02d}'
            self.renderer.set_media_position(position)
        else:
            self.send_res(counter)

    def res_from_client(self, counter, params=None):
        logger.info(f'RET{counter} params:{params}')

    def terminate(self):
        super(NVAConectionHandler, self).terminate()


# NVATool 负责将tcp长连接从 NVAHTTPServer 中分离，生成 NVAConectionHandler
# NVAHandler 修改自 DLNAHandler，负责HTTP服务的处理
# 增加了NVA协议的相关适配，启动时需调用 reload() 设置后端服务为 NVAHTTPServer


class NVATool(Tool):
    """NVA protocol tools for cherrypy
    """

    def __init__(self):
        Tool.__init__(self, 'before_request_body', self.set_nva_handler)

    def _setup(self):
        conf = self._merged_args()
        hooks = cherrypy.serving.request.hooks
        p = conf.pop("priority", getattr(self.callable, "priority",
                                         self._priority))
        hooks.attach(self._point, self.callable, priority=p, **conf)
        hooks.attach('before_finalize', self.nva_response_header, priority=70)
        hooks.attach('on_end_request', self.nva_start, priority=70)

    def set_nva_handler(self, handler_cls=NVAConectionHandler):
        logger.debug("NVATool set_nva_handler")
        request = cherrypy.serving.request
        conn = request.rfile.rfile.raw._sock
        request.nva_handler = handler_cls(conn, request)

    def nva_start(self):
        request = cherrypy.request
        if not hasattr(request, 'nva_handler'):
            return

        nva_handler = request.nva_handler
        request.nva_handler = None
        delattr(request, 'nva_handler')

        # By doing this we detach the socket from the CherryPy stack avoiding memory leaks
        request.rfile.rfile.detach()

        logger.debug(f'NVATool nva_start {request.remote.ip}:{request.remote.port}')

        if request.method == 'SETUP':
            cherrypy.engine.publish('nva-add', nva_handler)
        else:
            cherrypy.engine.publish('nva-restore', nva_handler)

    def nva_response_header(self):
        cherrypy.response.headers['Session'] = cherrypy.request.headers.get('Session', '')
        cherrypy.response.headers['UUID'] = Setting.get_usn()
        cherrypy.response.headers['NvaVersion'] = '1'


cherrypy.tools.nva = NVATool()


@cherrypy.expose
class NVAHandler(DLNAHandler):
    def reload(self):
        cherrypy.server.httpserver = NVAHTTPServer(cherrypy.server)
        self.build_description()

    def build_description(self):
        self.description = load_xml(XMLPath.DESCRIPTION.value).format(
            friendly_name='我的小电视',
            manufacturer="Bilibili Inc.",
            manufacturer_url="https://bilibili.com/",
            model_description="云视听小电视",
            model_name="Macast",
            model_url="https://app.bilibili.com/",
            model_number=Setting.get_version(),
            uuid=Setting.get_usn(),
            serial_num=1024,
            header_extra="""<X_brandName>Macast</X_brandName>
        <hostVersion>25</hostVersion>
        <ottVersion>106400</ottVersion>
        <channelName>master</channelName>
        <capability>254</capability>""",
            service_extra="""<service>
                <serviceType>urn:app-bilibili-com:service:NirvanaControl:3</serviceType>
                <serviceId>urn:app-bilibili-com:serviceId:NirvanaControl</serviceId>
                <controlURL>NirvanaControl/action</controlURL>
                <eventSubURL>NirvanaControl/event</eventSubURL>
                <SCPDURL>dlna/NirvanaControl.xml</SCPDURL>
            </service>"""
        ).encode()

    def GET(self, param=None, xml=None, **kwargs):
        if param == 'dlna' and xml == 'NirvanaControl.xml':
            return NVA_SERVICE
        return super(NVAHandler, self).GET(param, xml, **kwargs)

    @cherrypy.tools.nva()
    def SETUP(self, p):
        logger.info(f'SETUP ----{p}')
        logger.info(f'NVA 请求头: {dict(cherrypy.request.headers)}')

    @cherrypy.tools.nva()
    def RESTORE(self, p):
        logger.info(f'RESTORE ----{p}')
        logger.info(f'NVA 请求头: {dict(cherrypy.request.headers)}')

    @cherrypy.tools.nva()
    def STARTRESTORE(self, p):
        logger.info(f'STARTRESTORE ----{p}')
        logger.info(f'NVA 请求头: {dict(cherrypy.request.headers)}')


# NVA 协议主要代码


class SelectPoller(object):
    """ copy from ws4py.manager.SelectPoller

    """

    def __init__(self, timeout=0.1):
        """
        A socket poller that uses the `select`
        implementation to determines which
        file descriptors have data available to read.

        It is available on all platforms.
        """
        self._fds = []
        self.timeout = timeout

    def release(self):
        """
        Cleanup resources.
        """
        self._fds = []

    def register(self, fd):
        """
        Register a new file descriptor to be
        part of the select polling next time around.
        """
        if fd not in self._fds:
            self._fds.append(fd)

    def unregister(self, fd):
        """
        Unregister the given file descriptor.
        """
        if fd in self._fds:
            self._fds.remove(fd)

    def poll(self):
        """
        Polls once and returns a list of
        ready-to-be-read file descriptors.
        """
        if not self._fds:
            time.sleep(self.timeout)
            return []
        try:
            r, w, x = select.select(self._fds, [], [], self.timeout)
        except IOError as e:
            return []
        return r


class NVAProtocol(DLNAProtocol):
    """
    Some code is from ws4py.manager.WebSocketManager
    """

    def __init__(self):
        super(NVAProtocol, self).__init__()
        self.nva_manager = None
        self.lock = threading.Lock()
        self.clients = {}
        self.poller = SelectPoller(timeout=0.5)

        self.media_playing = False
        self.play_list = []  # [{oid:'', cid:'', title:'', is_portrait: false}...]
        self.play_index = 0

    def start(self):
        super(NVAProtocol, self).start()
        self.nva_manager = threading.Thread(target=self.run_manager,
                                            name="NVA_MANAGER_THREAD",
                                            daemon=True)
        self.nva_manager.start()
        cherrypy.engine.subscribe('nva-add', self.add)
        cherrypy.engine.subscribe('nva-broadcast', self.broadcast)
        cherrypy.engine.subscribe('nva-restore', self.restore)

    def stop(self):
        super(NVAProtocol, self).stop()
        cherrypy.engine.unsubscribe('nva-add', self.add)
        cherrypy.engine.unsubscribe('nva-broadcast', self.broadcast)
        cherrypy.engine.unsubscribe('nva-restore', self.restore)
        with self.lock:
            for fd in self.clients:
                self.clients[fd].terminate()
            self.clients.clear()
            self.poller.release()

    def restore(self, nva: NVAConectionHandler):
        self.add(nva)
        with self.lock:
            clients = self.clients.copy()
            nva_iter = iter(clients.values())

        for nva in nva_iter:
            if not nva.terminated:
                nva.update_play_state()

    def remove(self, nva: NVAConectionHandler):
        if nva not in self.clients:
            return
        logger.info(f"NVA Client {nva} leave.")
        with self.lock:
            fd = nva.sock.fileno()
            self.clients.pop(fd, None)
            self.poller.unregister(fd)
            nva.terminate()

    def add(self, nva: NVAConectionHandler):
        if nva in self.clients:
            return
        logger.info(f"NVA Client {nva} added.")
        with self.lock:
            new_fd = nva.sock.fileno()
            self.poller.register(new_fd)
            uuid = nva.uuid
            session = nva.session
            clients_remove_list = []
            for fd in self.clients:
                if self.clients[fd].uuid == uuid:
                    # 曾经连接过的设备重新连接
                    if self.clients[fd].session == session:
                        logger.info('设备断线重连：恢复之前的session')
                        # 恢复之前的session：手机断连，恢复session
                        # 移除旧连接
                        clients_remove_list.append(fd)
                        self.clients[fd].terminate()
                        # 将新的socket转移到旧连接上
                        self.clients[new_fd] = self.clients[fd]
                        self.clients[new_fd].sock = nva.sock
                        self.clients[new_fd].counter = 0
                        self.clients[new_fd].terminated = False
                    else:
                        # 新的session：手机应用重启，重新投屏
                        # 移除旧连接
                        logger.info('设备断线重连：移除旧连接')
                        clients_remove_list.append(fd)
                        self.clients[fd].terminate()
                        # 添加新的连接
                        self.clients[new_fd] = nva
                    break
            else:
                # 新设备连接
                logger.info('新设备连接')
                self.clients[new_fd] = nva

            for fd in clients_remove_list:
                self.poller.unregister(fd)
                self.clients.pop(fd, None)

            # 启动ping线程
            logger.info("启动ping线程")
            self.clients[new_fd].start()

    def broadcast(self, cmd, params=None):
        with self.lock:
            clients = self.clients.copy()
            nva_iter = iter(clients.values())

        for nva in nva_iter:
            if not nva.terminated:
                try:
                    nva.send_cmd(cmd, params)
                except:
                    pass

    def set_playlist(self, play_list, play_index):
        self.play_index = play_index
        self.play_list = play_list

    @staticmethod
    def position_to_second(position: str) -> int:
        pos = position.split(':')
        if len(pos) < 3:
            return 0
        return int(pos[0]) * 3600 + int(pos[1]) * 60 + int(pos[2])

    def set_state_position(self, data: str):
        """
        :param data: string, eg: 00:00:00
        :return:
        """

        if data != self.get_state_position():
            position = self.position_to_second(data)
            duration = self.position_to_second(self.get_state_duration())
            if duration > 0:
                self.broadcast('OnProgress',
                               {"duration": duration,
                                "position": position
                                })
        super(NVAProtocol, self).set_state_position(data)

    # todo 直播时 总时长会不断增加，其实直播时无须返回时长信息
    # 目前nva协议并没有涉及直播投放
    def set_state_duration(self, data: str):
        """
        :param data: string, eg: 00:00:00
        :return:
        """
        if data != self.get_state_duration():
            duration = self.position_to_second(data)
            if duration > 0:
                # 有时候播放器初始化时会设置duration为0，这时候不需要发送给客户端
                position = self.position_to_second(self.get_state_position())
                self.broadcast('OnProgress',
                               {"duration": duration,
                                "position": position
                                })
        super(NVAProtocol, self).set_state_duration(data)

    def set_state_transport(self, data: str):
        super(NVAProtocol, self).set_state_transport(data)
        # 以下对playState的猜测，暂未得到确切验证
        # 3 加载中
        # 4 播放中
        # 5 暂停
        # 6 媒体播放结束 end of file
        # 7 停止
        if data == 'PLAYING':
            self.broadcast('OnPlayState', {"playState": 4})
            if not self.media_playing:
                # 播放成功
                self.broadcast('PLAY_SUCCESS')
                self.media_playing = True
            return
        elif data == 'PAUSED_PLAYBACK':
            self.broadcast('OnPlayState', {"playState": 5})
            return
        elif data == 'STOPPED':
            self.broadcast('OnPlayState', {"playState": 7})
        elif data == 'NO_MEDIA_PRESENT':
            self.broadcast('OnPlayState', {"playState": 6})
            self.play_index += 1
            if self.play_index < len(self.play_list):
                logger.info(f"准备播放 分集{self.play_index + 1} {self.play_list[self.play_index]}")
                # 切换下一集
                with self.lock:
                    clients = self.clients.copy()
                    nva_iter = iter(clients.values())
                next_video = self.play_list[self.play_index]
                for nva in nva_iter:
                    if nva:
                        nva.cid = next_video['cid']
                        nva.oid = nva.aid = next_video['aid']
                        if next_video['epid'] != 0:
                            nva.oid = nva.epid = next_video['epid']
                        nva.title_p = next_video['title']
                        url, qn = nva.get_video_url()
                        logger.info(f'播放地址: {url} qn: {qn}')
                        nva.send_play_cmd(url)
                        break
                else:
                    logger.error("客户端断开连接，播放结束")

            else:
                logger.info(f'分集{self.play_index} {self.play_list}')
                logger.info("没有下一集，播放结束")
        self.media_playing = False

        # 不同播放状态应返回的 playState 序列

        # 播放一条视频
        # 加载中(3)、播放(4)、播放成功(PLAY_SUCCESS)

        # 分集1播放完毕，自动播放分集2
        # 媒体播放结束(6)、加载下一条视频(3)、播放(4)、播放成功(PLAY_SUCCESS)
        # MPVRenderer实现的顺序  媒体播放结束(6)、播放停止(7)、加载下一条视频(3)、播放(4)、播放成功(PLAY_SUCCESS)

        # 当所有分集播放完毕时
        # 播放停止(7)、媒体播放结束(6)、加载推荐视频(3)、播放(4)、播放成功(PLAY_SUCCESS)
        # MPVRenderer实现的顺序：媒体播放结束(6)、播放停止(7)

        # 在正在播放时，切投其他视频
        # 暂停(5)、播放(4)、加载中(3)、播放(4)、播放成功(PLAY_SUCCESS)
        # MPVRenderer实现的顺序实现的顺序：停止(7)、加载中(3)、播放(4)、播放成功(PLAY_SUCCESS)

    def set_state_transport_error(self):
        """
        :return:
        """
        super(NVAProtocol, self).set_state_transport_error()
        self.broadcast('OnPlayState', {"playState": 3})

    # todo 反向控制手机静音/貌似没有这个功能
    def set_state_mute(self, data: bool):
        """
        :param data: bool
        :return:
        """
        super(NVAProtocol, self).set_state_mute(data)

    # todo 反向控制手机音量/貌似没有这个功能
    def set_state_volume(self, data: int):
        """
        :param data: int, range from 0 to 100
        :return:
        """
        super(NVAProtocol, self).set_state_volume(data)

    def set_state_speed(self, data: str):
        super(NVAProtocol, self).set_state_speed(data)
        current_speed = round(float(data), 2)
        support_speed = [0.5, 0.75, 1, 1.25, 1.5, 2]
        self.broadcast('SpeedChanged',
                       {"currSpeed": current_speed, "supportSpeedList": support_speed})

    def set_state_display_subtitle(self, data: bool):
        super(NVAProtocol, self).set_state_display_subtitle(data)
        self.broadcast('OnDanmakuSwitch',
                       {'open': data})

    def run_manager(self):
        while self.running:
            with self.lock:
                polled = self.poller.poll()
            logger.debug(f'polled {polled}')
            if not self.running:
                break
            for fd in polled:
                if not self.running:
                    break
                nva = self.clients.get(fd, None)
                if nva and not nva.terminated:
                    try:
                        data = nva.sock.recv(2048)
                        if data == b'':
                            raise Exception('socket received null data')
                        nva.parse_request(data)
                    except (socket.error, OSError, Exception) as e:
                        if hasattr(e, "errno") and e.errno == errno.EINTR:
                            logger.error("socket: errno.EINTR")
                            pass
                        else:
                            logger.error(f"ERROR received data: {e}")
                            nva.terminate()
                            with self.lock:
                                self.poller.unregister(fd)
                            # todo 移除长时间未连接的客户端
                            # 下面的注释代码是立刻移除断开连接的客户端
                            # 但是立刻移除会导致意外断开连接的客户端无法完成重连
                            # 当断开连接的客户端数量过多时可能会导致内存占用小幅增加
                            # 不过日常使用的情况影响不大，所以暂时先不处理这个问题
                            # with self.lock:
                            #     self.clients.pop(fd, None)
                            #     self.poller.unregister(fd)
                else:
                    logger.debug(f'retained clients {self.clients}')
                del nva

    @property
    def handler(self):
        if self._handler is None:
            self._handler = NVAHandler()
        return self._handler

    def init_services(self, description=XMLPath.DESCRIPTION.value):
        super(NVAProtocol, self).init_services()
        self.build_action('urn:app-bilibili-com:service:NirvanaControl:3',
                          'NirvanaControl',
                          etree.fromstring(NVA_SERVICE))


if __name__ == '__main__':
    from macast import cli
    from macast_renderer.mpv import MPVRenderer

    cli(renderer=MPVRenderer(path='mpv'), protocol=NVAProtocol())
