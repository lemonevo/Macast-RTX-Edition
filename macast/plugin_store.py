# Copyright (c) 2021 by xfangfang. All Rights Reserved.
#
# Plugin store: list and install the renderer/protocol plugins published in the
# upstream Macast plugins repository.
#
# Plugin files are Python modules that Macast imports at startup, therefore the
# store accepts downloads only from this repository's plugins directory or the
# upstream xfangfang/Macast-plugins repository, and validates every file before
# it reaches the plugin directory.

import json
import logging
import os
import re
import time
from urllib.parse import urlsplit

import requests

from .utils import PROTOCOL_DIR, RENDERER_DIR, SETTING_DIR

logger = logging.getLogger("PluginStore")
logger.setLevel(logging.INFO)

PLUGIN_REPO_PAGE = 'https://github.com/lemonevo/Macast-RTX-Edition/tree/main/plugins'
# 插件清单：优先本仓库的 plugins/info.json，取不到时回退上游清单
PLUGIN_REPO_INFO_URLS = (
    'https://raw.githubusercontent.com/lemonevo/Macast-RTX-Edition/main/plugins/info.json',
    'https://raw.githubusercontent.com/xfangfang/Macast-plugins/main/info.json',
)
PLUGIN_REPO_INFO_URL = PLUGIN_REPO_INFO_URLS[0]
ALLOWED_PLUGIN_HOST = 'raw.githubusercontent.com'
# 本仓库自己维护的插件源；同时保留上游仓库，方便回退安装上游插件
ALLOWED_PLUGIN_PATH_PREFIXES = (
    '/lemonevo/Macast-RTX-Edition/',
    '/xfangfang/Macast-plugins/',
)
PLUGIN_TYPES = (RENDERER_DIR, PROTOCOL_DIR)
MAX_PLUGIN_BYTES = 2 * 1024 * 1024
MAX_REPO_BYTES = 512 * 1024
REPO_CACHE_SECONDS = 600
REPO_TIMEOUT = 10
PLUGIN_TIMEOUT = 20
USER_AGENT = 'Macast-RTX-Edition'

_FILENAME_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]*\.py$')
_METADATA_PATTERN = re.compile(r'<macast\.([A-Za-z0-9_]+)>(.*?)</macast', re.DOTALL)

_repo_cache = {'time': 0.0, 'data': None}


class PluginStoreError(Exception):
    """Raised when a plugin cannot be listed, downloaded or installed."""


def _fetch_text(url, limit, timeout):
    """Download a text resource with a hard size limit."""
    try:
        response = requests.get(url, timeout=timeout, stream=True,
                                headers={'User-Agent': USER_AGENT})
    except requests.RequestException as error:
        raise PluginStoreError('无法连接插件仓库（{}）'.format(error)) from None
    with response:
        if response.status_code != 200:
            raise PluginStoreError('插件仓库返回 HTTP {}'.format(response.status_code))
        declared = response.headers.get('Content-Length', '')
        if declared.isdigit() and int(declared) > limit:
            raise PluginStoreError('下载内容超过大小限制')
        chunks = []
        size = 0
        for chunk in response.iter_content(8192):
            if not chunk:
                continue
            size += len(chunk)
            if size > limit:
                raise PluginStoreError('下载内容超过大小限制')
            chunks.append(chunk)
    try:
        return b''.join(chunks).decode('utf-8')
    except UnicodeDecodeError:
        raise PluginStoreError('下载内容不是有效的 UTF-8 文本') from None


def plugin_filename(url):
    """Return the plugin file name of a URL, or None when it is not a .py file."""
    if not isinstance(url, str):
        return None
    name = os.path.basename(urlsplit(url).path)
    if not _FILENAME_PATTERN.match(name):
        return None
    return name


def is_allowed_plugin_url(url):
    """Only the curated upstream plugin repository may provide plugins."""
    if not isinstance(url, str):
        return False
    parts = urlsplit(url)
    if parts.scheme != 'https' or parts.netloc != ALLOWED_PLUGIN_HOST:
        return False
    if not any(parts.path.startswith(prefix) for prefix in ALLOWED_PLUGIN_PATH_PREFIXES):
        return False
    # Reject paths that escape the curated repository prefix.
    if '..' in parts.path.split('/'):
        return False
    if parts.query or parts.fragment:
        return False
    return plugin_filename(url) is not None


def plugin_supports_platform(platform, current_platform):
    """Check the comma separated <macast.platform> list of a plugin."""
    if not platform:
        return True
    supported = [item.strip() for item in platform.split(',') if item.strip()]
    return not supported or current_platform in supported


def parse_plugin_metadata(source):
    """Read the <macast.*> metadata block of a plugin file."""
    return {key.strip(): value.strip()
            for key, value in _METADATA_PATTERN.findall(source)}


def load_repo_plugins(force=False):
    """List installable plugins of the curated repository.

    The list is cached for REPO_CACHE_SECONDS so that opening the settings page
    repeatedly does not hit the network every time.
    """
    now = time.monotonic()
    cached = _repo_cache['data']
    if not force and cached is not None and now - _repo_cache['time'] < REPO_CACHE_SECONDS:
        return cached

    info = None
    last_error = None
    for info_url in PLUGIN_REPO_INFO_URLS:
        try:
            info = json.loads(_fetch_text(info_url, MAX_REPO_BYTES, REPO_TIMEOUT))
        except PluginStoreError as error:
            last_error = error
            logger.warning('无法读取插件清单 %s: %s', info_url, error)
            continue
        except ValueError:
            last_error = PluginStoreError('插件仓库清单格式无法识别')
            logger.warning('插件清单格式无法识别: %s', info_url)
            continue
        break
    if info is None:
        raise last_error or PluginStoreError('无法读取插件清单')
    entries = info.get('plugin_v1') if isinstance(info, dict) else None
    if not isinstance(entries, list):
        raise PluginStoreError('插件仓库清单格式无法识别')

    plugins = []
    for entry in entries:
        if not isinstance(entry, dict) or not is_allowed_plugin_url(entry.get('url', '')):
            logger.warning('Ignoring plugin entry outside the curated repository: %s', entry)
            continue
        plugin_type = entry.get('type', RENDERER_DIR)
        if plugin_type not in PLUGIN_TYPES:
            logger.warning('Ignoring plugin with unsupported type: %s', entry.get('type'))
            continue
        plugins.append({
            'author': entry.get('author', ''),
            'desc': entry.get('desc', ''),
            'host_version': entry.get('host_version', ''),
            'platform': entry.get('platform', ''),
            'title': entry.get('title', '') or plugin_filename(entry['url'])[:-3],
            'type': plugin_type,
            'url': entry['url'],
            'version': entry.get('version', ''),
        })

    data = {
        'repo_url': info.get('repo_url', PLUGIN_REPO_PAGE),
        'plugins': plugins,
    }
    _repo_cache['time'] = now
    _repo_cache['data'] = data
    return data


def install_plugin(plugin, platform=None, setting_dir=None):
    """Download one curated plugin into the local plugin directory.

    Returns the metadata of the installed plugin. Raises PluginStoreError when
    the plugin is not part of the curated repository, does not match its type
    slot, or cannot be written.
    """
    if not isinstance(plugin, dict):
        raise PluginStoreError('插件描述格式错误')
    plugin_type = plugin.get('type', RENDERER_DIR)
    if plugin_type not in PLUGIN_TYPES:
        raise PluginStoreError('不支持的插件类型：{}'.format(plugin_type))
    url = plugin.get('url', '')
    if not is_allowed_plugin_url(url):
        raise PluginStoreError('插件地址不在受信任的插件仓库内')
    filename = plugin_filename(url)

    source = _fetch_text(url, MAX_PLUGIN_BYTES, PLUGIN_TIMEOUT)
    metadata = parse_plugin_metadata(source)
    expected = 'renderer' if plugin_type == RENDERER_DIR else 'protocol'
    if expected not in metadata:
        raise PluginStoreError('插件文件缺少 <macast.{}> 元数据'.format(expected))
    supported = metadata.get('platform', plugin.get('platform', ''))
    if platform is not None and not plugin_supports_platform(supported, platform):
        raise PluginStoreError('该插件不支持当前平台（{}）'.format(supported or '未知'))

    target_dir = os.path.join(
        SETTING_DIR if setting_dir is None else setting_dir, plugin_type)
    target_path = os.path.join(target_dir, filename)
    replaced = os.path.exists(target_path)
    temporary_path = target_path + '.part'
    try:
        os.makedirs(target_dir, exist_ok=True)
        with open(temporary_path, 'w', encoding='utf-8', newline='') as plugin_file:
            plugin_file.write(source)
        os.replace(temporary_path, target_path)
    except OSError as error:
        raise PluginStoreError('无法写入插件目录（{}）'.format(error)) from None
    finally:
        if os.path.exists(temporary_path):
            try:
                os.remove(temporary_path)
            except OSError:
                pass

    logger.info('Installed plugin %s to %s', metadata.get('title', filename), target_path)
    return {
        'author': metadata.get('author', ''),
        'desc': metadata.get('desc', ''),
        'path': target_path,
        'platform': supported,
        'replaced': replaced,
        'title': metadata.get('title', '') or filename[:-3],
        'type': plugin_type,
        'version': metadata.get('version', ''),
    }


def uninstall_plugin(plugin, setting_dir=None):
    """Remove a plugin file that this store installed.

    Symmetric with install_plugin: the file name is derived from the curated
    repository URL, so only plugin files can be deleted and the target can never
    leave the renderer/protocol directory.
    """
    if not isinstance(plugin, dict):
        raise PluginStoreError('插件描述格式错误')
    plugin_type = plugin.get('type', RENDERER_DIR)
    if plugin_type not in PLUGIN_TYPES:
        raise PluginStoreError('不支持的插件类型：{}'.format(plugin_type))
    url = plugin.get('url', '')
    if not is_allowed_plugin_url(url):
        raise PluginStoreError('插件地址不在受信任的插件仓库内')
    filename = plugin_filename(url)

    directory = os.path.join(
        SETTING_DIR if setting_dir is None else setting_dir, plugin_type)
    target_path = os.path.join(directory, filename)
    if os.path.dirname(os.path.realpath(target_path)) != os.path.realpath(directory):
        raise PluginStoreError('插件路径无效')
    if not os.path.isfile(target_path):
        raise PluginStoreError('未找到已安装的插件文件：{}'.format(filename))
    try:
        os.remove(target_path)
    except OSError as error:
        raise PluginStoreError('无法删除插件（{}）'.format(error)) from None
    remove_plugin_cache(directory, filename)

    logger.info('Removed plugin %s', target_path)
    return {
        'file': filename,
        'path': target_path,
        'removed': True,
        'title': plugin.get('title', '') or filename[:-3],
        'type': plugin_type,
        'version': plugin.get('version', ''),
    }


def remove_plugin_cache(directory, filename):
    """Drop the byte code that an uninstalled plugin left behind."""
    cache_dir = os.path.join(directory, '__pycache__')
    if not os.path.isdir(cache_dir):
        return
    prefix = filename[:-len('.py')] + '.'
    for entry in os.listdir(cache_dir):
        if entry.startswith(prefix):
            try:
                os.remove(os.path.join(cache_dir, entry))
            except OSError:
                logger.warning('Cannot remove cached byte code %s', entry)
