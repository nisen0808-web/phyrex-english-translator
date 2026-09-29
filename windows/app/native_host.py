"""A tiny allowlisted native-messaging launcher; never accepts commands or credentials."""
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import build_opener, ProxyHandler
from runtime import ROOT, USER_DIR, instance_id

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
    stream.write(struct.pack('<I', len(body)))
    stream.write(body)
    stream.flush()


def health():
    try:
        with opener.open(URL + '/api/config', timeout=1) as response:
            # A fully edited 1000-entry glossary can exceed the old 256 KiB cap.
            cfg = json.loads(response.read(2 * 1024 * 1024))
        if cfg.get('distribution') != 'public' or cfg.get('instance') != instance_id():
            raise ValueError('另一份翻译组件占用了端口，请先关闭那一份，再重新连接。')
        return True
    except (URLError, TimeoutError, ConnectionError):
        return False


def ensure_service():
    if health():
        return
    USER_DIR.mkdir(parents=True, exist_ok=True)
    log = (USER_DIR / 'service.log').open('ab')
    error_log = (USER_DIR / 'service-error.log').open('ab')
    try:
        process = subprocess.Popen([str(ROOT / '.runtime/python/python.exe'), '-B', '-X', 'utf8',
                                    str(ROOT / 'app.py'), '--port', '8878'], cwd=ROOT,
                                   stdin=subprocess.DEVNULL, stdout=log, stderr=error_log,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    finally:
        log.close()
        error_log.close()
    for _ in range(80):
        if health():
            return
        if process.poll() is not None:
            raise ValueError('连接组件启动失败，请重新解压完整测试包。')
        time.sleep(.25)
    raise ValueError('连接组件启动较慢，请稍后点击重新连接。')


def dispatch(message):
    if not isinstance(message, dict) or message.get('command') != 'start':
        return {'ok': False, 'error': '不支持的连接请求。'}
    ensure_service()
    return {'ok': True, 'url': URL + '/?view=sidebar'}


def main():
    if len(sys.argv) < 2 or sys.argv[1].rstrip('/') != 'chrome-extension://' + EXTENSION_ID:
        return 1
    if os.name == 'nt':
        import msvcrt
        msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
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
