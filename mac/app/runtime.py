"""Portable macOS runtime with a private account and a per-copy process lock."""
import hashlib
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
USER_DIR = Path(os.environ.get('FED_TRANSLATOR_USER_DIR', str(ROOT / 'user-data'))).resolve()


def instance_id():
    return hashlib.sha256(str(ROOT).encode('utf-8')).hexdigest()[:16]


def acquire_instance_lock():
    import fcntl
    USER_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = (USER_DIR / 'service.lock').open('a+')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        raise SystemExit('This copy of the translator is already running.') from None
    return lock


def settings():
    return {}


def prepare():
    os.umask(0o077)
    sys.path.insert(0, str(ROOT / '.runtime/packages'))
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    return {}


def python_path():
    binary = ROOT / '.runtime/python/bin/python3'
    if not binary.is_file():
        raise RuntimeError('Mac 运行组件不完整，请完整解压测试包。')
    return str(binary)


def codex_path():
    binary = ROOT / '.runtime/codex/codex'
    if not binary.is_file():
        raise RuntimeError('Codex 组件不完整，请完整解压测试包。')
    return str(binary)


def model_path():
    model = ROOT / '.runtime/model'
    if not (model / 'model.bin').is_file():
        raise RuntimeError('语音模型缺失，请完整解压测试包。')
    return model
