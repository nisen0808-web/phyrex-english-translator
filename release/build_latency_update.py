"""Build a small cross-platform source patch for an installed 0.3.0-beta or 0.3.1-beta."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = ('app.py', 'latency.py', 'streaming.py', 'live_updates.py', 'recognizer.py', 'bridge.py', 'fed_phrasing.py', 'providers.py', 'web/app.js', 'web/index.html', 'web/style.css', 'gpu_runtime.py', 'setup_gpu.py', 'Enable-GPU.cmd', 'extension/manifest.json', '加速更新说明.md', 'VERIFICATION.md', 'PRIVACY.md')
NAME = 'PhyrexNi-0.3.2-Windows-Mac-App-Update'

NOTE = '''@PhyrexNi · 美联储用语优化 · 0.3.2-beta · 2026-10-27

适用于已经安装 0.3.0-beta 或 0.3.1-beta 的外部分发版。
Windows x64 / Mac Apple 芯片 / Mac Intel 共用此更新包。
此包不能独立运行，也不能用于个人本地版或 0.2.x 旧版。

安装方法
1. 结束采集，等待处理完成并导出需要的文字。
2. 关闭翻译页面，运行组件目录的 Stop.cmd（Windows）或 Stop.command（Mac）。
3. 备份现有组件目录，保留 user-data、.runtime 和 extension。
4. 将本包全部应用文件合并到原组件目录，替换同名文件，新增的 fed_phrasing.py 也必须复制。
   组件目录是包含 Start.cmd / Start.command 的文件夹，不是 extension 文件夹。
   web 与 extension 均应合并内容，不能删除整个旧文件夹；不要替换 user-data 或 .runtime。
5. 运行 Start.cmd / Start.command，刷新页面；在扩展管理页重新加载原扩展并刷新侧栏。
6. 页面底部应显示 0.3.2 BETA。

本次改进
- 美联储模式增加七组按当前片段匹配的用法提示：增长与放缓、政策立场、通胀与通缩、劳动力市场、百分比与基点、PCE、统计口径。
- 区分增长放缓与温和增长、通胀回落与物价下跌、招聘放缓与裁员；保留否定、程度和不确定性。
- 不改写识别出的英文，不根据术语猜补后文；听写含糊仍提示待核实。
- 三种 AI 共用；通用英语模式不变。不增加模型调用次数，不改变模型和音频分段设置。
- 保留现有连接预热、逐字预览、中文朗读、逐段复制、记录与导出。

注意
用法提示会增加少量输入文本，具体额度取决于所选 AI；此版不承诺固定延迟或几乎同步。
原有 Windows NVIDIA 可选加速继续保留，具体安装见加速更新说明.md；Mac 继续使用 CPU。
本包不含账号、音频、私人记录或大型运行组件。
原 manifest.sha256.json 不再代表被替换的文件，请用 latency-update-checksums.json 核对。
回退时停止组件，再恢复之前备份的对应文件。

验证范围
发布流程必须通过 Windows、两种 Mac 的组件检查、管线检查和九项美联储用法集成检查。
三种 AI 路由使用模拟输出核验；不代表本轮实测了三个真实账号或 YouTube 长时间直播。
检查报告与 SHA-256 随 GitHub 版本附件提供。Mac 尚未经过 Apple 公证，此版没有新增杀毒认证。
'''


def build(output):
    output.mkdir(parents=True, exist_ok=True)
    files = {}
    for relative in FILES:
        data = (ROOT / 'windows/app' / relative).read_bytes()
        assert data == (ROOT / 'mac/app' / relative).read_bytes(), relative
        files[relative] = data
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    metadata = {'base_version': '0.3.0-beta', 'version': '0.3.2-beta', 'compatible_base_versions': ['0.3.0-beta', '0.3.1-beta'], 'update': 'fed-usage-20261027',
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
              'checks': ['Eighteen allowlisted app files only', 'Windows and Mac app files byte-identical',
                         'All compressed entries readable and checksum-verified',
                         'No runtime, account, recordings or model files included']}
    (output / (NAME + '-checks.json')).write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    build(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'dist')
