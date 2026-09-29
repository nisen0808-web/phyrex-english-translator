"""Allowlisted native-messaging bridge for Chrome and Edge on macOS."""
import json
import os
import struct
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import build_opener, ProxyHandler
from runtime import ROOT, USER_DIR, instance_id, python_path

EXTENSION_ID = 'kiceknjkkhbfedilkgiegndlehnffmcc'
URL = 'http://127.0.0.1:8878'
opener = build_opener(ProxyHandler({}))


def read_exact(stream, count):
    data = bytearray()
    while len(data) < count:
        part = stream.read(count - len(data))
        if not part:
            if not data:
                return None
            raise ValueError('连接消息不完整。')
        data.extend(part)
    return bytes(data)


def read_message(stream):
    header = read_exact(stream, 4)
    if header is None:
        return None
    size = struct.unpack('<I', header)[0]
    if not 1 <= size <= 16384:
        raise ValueError('连接消息长度无效。')
    payload = read_exact(stream, size)
    if payload is None:
        raise ValueError('连接消息不完整。')
    return json.loads(payload.decode('utf-8'))


def write_message(stream, message):
    body = json.dumps(message, ensure_ascii=False).encode('utf-8')
    stream.write(struct.pack('<I', len(body)) + body)
    stream.flush()


def health():
    try:
        with opener.open(URL + '/api/config', timeout=1) as response:
            cfg = json.loads(response.read(2 * 1024 * 1024))
        if cfg.get('distribution') != 'public' or cfg.get('instance') != instance_id():
            raise ValueError('另一份组件占用了端口，请先关闭那一份，再重新连接。')
        return True
    except (URLError, TimeoutError, ConnectionError):
        return False


def ensure_service():
    if health():
        return
    os.umask(0o077)
    USER_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (USER_DIR / 'service.log').open('ab') as log, (USER_DIR / 'service-error.log').open('ab') as error_log:
        process = subprocess.Popen([python_path(), '-B', '-E', '-s', '-X', 'utf8', str(ROOT / 'app.py'), '--port', '8878'],
            cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=error_log,
            start_new_session=True, close_fds=True)
    for _ in range(120):
        if health():
            return
        if process.poll() is not None:
            raise ValueError('连接组件启动失败，请查看 user-data/service-error.log。')
        time.sleep(.25)
    raise ValueError('连接组件启动较慢，请稍后重新连接。')


def dispatch(message):
    if not isinstance(message, dict) or message.get('command') != 'start':
        return {'ok': False, 'error': '不支持的连接请求。'}
    ensure_service()
    return {'ok': True, 'url': URL + '/?view=sidebar'}


def main():
    if len(sys.argv) < 2 or sys.argv[1].rstrip('/') != 'chrome-extension://' + EXTENSION_ID:
        return 1
    while True:
        try:
            message = read_message(sys.stdin.buffer)
            if message is None:
                return 0
            result = dispatch(message)
        except (ValueError, UnicodeError) as exc:
            result = {'ok': False, 'error': str(exc) if any('\u3400' <= c <= '\u9fff' for c in str(exc)) else '连接请求格式无效。'}
        except Exception:
            result = {'ok': False, 'error': '本机连接失败，请重新安装连接组件后再试。'}
        write_message(sys.stdout.buffer, result)


if __name__ == '__main__':
    raise SystemExit(main())
