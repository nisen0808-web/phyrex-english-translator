"""Optional, app-local NVIDIA runtime. Pinned official wheels, verified before use."""
import hashlib
import os
from pathlib import Path
import platform
import shutil
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent
PACKAGES = (
    ('cublas', 'https://files.pythonhosted.org/packages/e2/2a/4f27ca96232e8b5269074a72e03b4e0d43aa68c9b965058b1684d07c6ff8/nvidia_cublas_cu12-12.4.5.8-py3-none-win_amd64.whl',
     '5a796786da89203a0657eda402bcdcec6180254a8ac22d72213abc42069522dc'),
    ('cudnn', 'https://files.pythonhosted.org/packages/3d/90/0bd6e586701b3a890fd38aa71c387dab4883d619d6e5ad912ccbd05bfd67/nvidia_cudnn_cu12-9.10.2.21-py3-none-win_amd64.whl',
     'c6288de7d63e6cf62988f0923f96dc339cea362decb1bf5b3141883392a7d65e'),
)


def check_hardware():
    if os.name != 'nt' or platform.machine().lower() not in ('amd64', 'x86_64'):
        raise RuntimeError('此可选加速组件仅适用于 Windows x64 和 NVIDIA 显卡。')
    from runtime import prepare
    prepare()
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() < 1:
            raise RuntimeError('未检测到可用的 NVIDIA 显卡，请继续使用 CPU 模式；无需下载加速组件。')
        if 'int8_float32' not in ctranslate2.get_supported_compute_types('cuda'):
            raise RuntimeError('当前显卡不支持此加速方式，请继续使用 CPU 模式。')
    except (ImportError, OSError) as exc:
        raise RuntimeError('无法加载显卡检测组件。请先安装完整版本，并确认 NVIDIA 驱动正常。') from exc


def install():
    # Check before opening any network connection or removing a ready marker.
    check_hardware()
    print('已检测到兼容 NVIDIA 显卡。仅安装本机语音识别加速库，翻译仍使用自己的 AI 账号。', flush=True)
    if shutil.disk_usage(ROOT).free < 4_000_000_000:
        raise RuntimeError('请保留至少 4 GB 可用空间。')
    target = ROOT / '.runtime/gpu'
    target.mkdir(parents=True, exist_ok=True)
    marker = target / 'ready.txt'
    marker.unlink(missing_ok=True)
    for name, url, expected in PACKAGES:
        archive = target / (name + '.download')
        print('正在下载并校验 NVIDIA ' + name + '…', flush=True)
        digest = hashlib.sha256()
        try:
            with urllib.request.urlopen(url, timeout=60) as response, archive.open('wb') as stream:
                total = int(response.headers.get('Content-Length', 0))
                received, last_percent = 0, -1
                while block := response.read(4 * 1024 * 1024):
                    digest.update(block)
                    stream.write(block)
                    received += len(block)
                    percent = min(100, received * 100 // total) if total else 0
                    if total and percent // 10 > last_percent // 10:
                        print(name + '：' + str(percent) + '%', flush=True)
                        last_percent = percent
            if digest.hexdigest() != expected:
                raise RuntimeError('下载文件校验失败，请重试。')
            with zipfile.ZipFile(archive) as package:
                for entry in package.infolist():
                    # No Python or wheel install scripts are executed.
                    if entry.is_dir() or not (entry.filename.endswith('.dll') or 'LICENSE' in entry.filename):
                        continue
                    destination = (target / entry.filename).resolve()
                    if not destination.is_relative_to(target.resolve()):
                        raise RuntimeError('下载包路径无效。')
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with package.open(entry) as source, destination.open('wb') as stream:
                        shutil.copyfileobj(source, stream)
        finally:
            archive.unlink(missing_ok=True)
    marker.write_text('\n'.join(digest for _, _, digest in PACKAGES), encoding='ascii')
    print('本机加速库安装完成。请结束当前翻译，重启组件后确认显示“显卡加速”。', flush=True)


if __name__ == '__main__':
    try:
        install()
    except Exception as exc:
        print('显卡加速安装未完成：' + str(exc), file=sys.stderr, flush=True)
        print('可以继续用 Start.cmd 启动 CPU 版。', file=sys.stderr, flush=True)
        raise SystemExit(1)
