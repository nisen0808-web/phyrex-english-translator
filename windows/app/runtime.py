"""Self-contained receiver runtime. Never discover the publisher's machine or login."""
import os
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
USER_DIR = Path(os.environ.get('FED_TRANSLATOR_USER_DIR', str(ROOT / 'user-data'))).resolve()


def instance_id():
    return hashlib.sha256(str(ROOT).casefold().encode('utf-8')).hexdigest()[:16]


def acquire_instance_lock():
    if os.name != 'nt':
        return None
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateMutexW(None, False, 'Local\\FedEnglishTranslator-' + instance_id())
    if not handle:
        raise RuntimeError('无法创建连接组件的运行锁。')
    if ctypes.get_last_error() == 183:
        kernel.CloseHandle(handle)
        raise SystemExit('This copy of the translator is already running.')
    return handle


def settings():
    return {}


def prepare():
    packages = ROOT / '.runtime/packages'
    sys.path.insert(0, str(packages))
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    return {}


def codex_path():
    binary = ROOT / '.runtime/codex/codex-x86_64-pc-windows-msvc.exe'
    if not binary.is_file():
        raise RuntimeError('连接组件不完整，请重新解压完整分发包。')
    return str(binary)


def model_path():
    model = ROOT / '.runtime/model'
    if not (model / 'model.bin').is_file():
        raise RuntimeError('语音模型缺失，请重新解压完整分发包。')
    return model
