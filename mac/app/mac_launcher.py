"""User-level install/start/stop; no sudo, login item or security setting changes."""
import argparse
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
from runtime import ROOT, USER_DIR, prepare

HOST = 'org.fedtranslator.bridge'
EXTENSION = 'chrome-extension://kiceknjkkhbfedilkgiegndlehnffmcc/'


def manifest_paths(home):
    support = Path(home) / 'Library/Application Support'
    return [support / browser / 'NativeMessagingHosts' / (HOST + '.json')
            for browser in ('Google/Chrome', 'Microsoft Edge')]


def install(home=None):
    expected = str(ROOT / 'NativeHost.sh')
    data = {'name': HOST, 'description': 'PhyrexNi English translation connector',
            'path': expected, 'type': 'stdio', 'allowed_origins': [EXTENSION]}
    for path in manifest_paths(home or Path.home()):
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            current = json.loads(path.read_text(encoding='utf-8'))
            if current.get('path') != expected:
                backup = path.with_suffix('.json.previous')
                if backup.exists():
                    raise RuntimeError('检测到旧组件和已有备份，请先卸载旧组件再安装。')
                path.rename(backup)
        temporary = path.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        os.chmod(temporary, 0o600)
        temporary.replace(path)
    print('本机连接已安装。请在 Chrome / Edge 中加载本目录的 extension 文件夹。')


def uninstall(home=None):
    for path in manifest_paths(home or Path.home()):
        if path.exists() and json.loads(path.read_text(encoding='utf-8')).get('path') == str(ROOT / 'NativeHost.sh'):
            path.unlink()
            backup = path.with_suffix('.json.previous')
            if backup.exists():
                backup.replace(path)
    print('本目录的连接已移除；你的账号和中文记录保留。')


def stop():
    pid_file = USER_DIR / 'server.pid'
    if not pid_file.exists():
        print('这份组件尚未运行。')
        return
    pid = int(pid_file.read_text(encoding='ascii'))
    if pid <= 1:
        raise RuntimeError('进程记录无效。')
    command = subprocess.run(['/bin/ps', '-p', str(pid), '-o', 'command='],
                             capture_output=True, text=True, check=False).stdout.strip()
    # Require the exact per-copy app path followed by this server's port arguments.
    if command and str(ROOT / 'app.py') + ' --port 8878' not in command:
        raise RuntimeError('进程已变化，为保护其他程序，没有停止它。')
    if command:
        os.kill(pid, signal.SIGTERM)
    pid_file.unlink(missing_ok=True)
    print('本机翻译组件已停止。')


def check_platform():
    if platform.system() != 'Darwin':
        raise RuntimeError('这个包只能在 Mac 上运行。')
    info = json.loads((ROOT / 'build-info.json').read_text(encoding='utf-8'))
    if platform.machine() != info['architecture']:
        raise RuntimeError('芯片版本不匹配，请在“关于本机”确认 Apple 芯片或 Intel，然后下载对应的包。')
    if tuple(map(int, platform.mac_ver()[0].split('.')[:2])) < (14, 0):
        raise RuntimeError('本测试包需要 macOS 14 或更新版本。')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['install', 'uninstall', 'start', 'stop'])
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    prepare()
    check_platform()
    if args.action == 'install':
        install()
    elif args.action == 'uninstall':
        uninstall()
    elif args.action == 'stop':
        stop()
    else:
        from native_host import ensure_service
        ensure_service()
        if not args.no_browser:
            for browser in ('Google Chrome', 'Microsoft Edge'):
                result = subprocess.run(['/usr/bin/open', '-a', browser, 'http://127.0.0.1:8878/'],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if result.returncode == 0:
                    break
            else:
                print('请在 Chrome / Edge 打开 http://127.0.0.1:8878/')
        print('翻译组件已启动。')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(str(exc))
        raise SystemExit(1) from None
