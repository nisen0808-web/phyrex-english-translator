"""Build a small cross-platform source patch for public 0.3.0–0.3.3."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = ('app.py', 'latency.py', 'streaming.py', 'live_updates.py', 'recognizer.py',
         'bridge.py', 'fed_phrasing.py', 'providers.py', 'provider_auth.py', 'claude_api.py', 'deepseek_api.py', 'deepseek_transport.py',
         'web/app.js', 'web/index.html', 'web/style.css', 'gpu_runtime.py', 'setup_gpu.py',
         'Enable-GPU.cmd', 'extension/manifest.json', '加速更新说明.md',
         'AI选择说明.md', '中文朗读说明.md', 'VERIFICATION.md', 'PRIVACY.md')
NAME = 'PhyrexNi-0.3.4-Windows-Mac-App-Update'
NOTE = '''@PhyrexNi · DeepSeek API 可选接入 · 0.3.4-beta · 2026-10-27

适用于已经安装 0.3.0-beta、0.3.1-beta、0.3.2-beta 或 0.3.3-beta 的外部分发版。
Windows x64 / Mac Apple 芯片 / Mac Intel 共用此轻量更新包；不能独立运行，不能用于个人本地版或 0.2.x 旧版。

1. 结束采集并等待处理，导出需要的文字；关闭页面，运行 Stop.cmd 或 Stop.command。
2. 备份现有组件目录。保留 user-data、.runtime 和 extension，不删除已有账号、记录或语音模型。
3. 将本包的全部应用文件合并到原组件目录并替换同名文件；新增 deepseek_api.py 和 deepseek_transport.py 必须复制。合并 web 和 extension 文件夹，不要删除旧文件夹。
4. 组件目录是包含 Start.cmd / Start.command 的文件夹。旧版系统专用“先读我”仍为旧版说明，本包 AI选择说明.md 和 PRIVACY.md 适用于本次更新。
5. 运行 Start.cmd / Start.command，刷新页面，在扩展管理页重新加载原扩展；页面底部应显示 0.3.4 BETA。

Claude API 和 DeepSeek API 是可选、单独计费的服务，使用者自行在本机页面输入对应的 API 密钥。密钥仅保留在运行组件的内存，切换 AI 或关闭后要重新输入。DeepSeek 默认启用思考，可能增加等待和费用；达到输出上限时会暂停。输入密钥不会触发付费测试；翻译请求可能产生费用。不要把密钥发给发布者。

保留原 ChatGPT、Grok、Gemini 和 Claude 选项，原有识别、朗读、逐段复制和导出。没有新增固定速度或准确率承诺。原 manifest.sha256.json 不再代表被替换的文件，请用 latency-update-checksums.json 核对。需要回退时停止组件并恢复之前备份。

发布前须通过 Windows、两种 Mac 原生构建和离线回归；API 测试只用模拟响应，真实密钥、账单及译文未做本轮实测。Mac 尚未经过 Apple 公证，本版没有新增杀毒认证。
'''


def build(output):
    output.mkdir(parents=True, exist_ok=True)
    files = {}
    for relative in FILES:
        data = (ROOT / 'windows/app' / relative).read_bytes()
        assert data == (ROOT / 'mac/app' / relative).read_bytes(), relative
        files[relative] = data
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    metadata = {'base_version': '0.3.0-beta', 'version': '0.3.4-beta',
                'compatible_base_versions': ['0.3.0-beta', '0.3.1-beta', '0.3.2-beta', '0.3.3-beta'],
                'update': 'deepseek-api-20261027',
                'platforms': ['Windows x64', 'macOS arm64', 'macOS x86_64'], 'files': hashes}
    archive = output / (NAME + '.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as package:
        for name, data in files.items():
            package.writestr(name, data)
        package.writestr('安装更新.txt', NOTE.encode('utf-8'))
        package.writestr('latency-update-checksums.json', json.dumps(metadata, indent=2).encode('utf-8'))
    with zipfile.ZipFile(archive) as package:
        assert package.testzip() is None
        assert set(package.namelist()) == set(FILES) | {'安装更新.txt', 'latency-update-checksums.json'}
        for name, digest in hashes.items():
            assert hashlib.sha256(package.read(name)).hexdigest() == digest
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(digest + '  ' + archive.name + '\n', encoding='ascii')
    report = {'archive': str(archive), 'bytes': archive.stat().st_size, 'sha256': digest,
              'checks': [f'{len(FILES)} allowlisted app and documentation files only',
                         'Windows and Mac app files byte-identical',
                         'All compressed entries readable and checksum-verified',
                         'No runtime, account, recordings, user API key or model files included']}
    (output / (NAME + '-checks.json')).write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    build(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'dist')
