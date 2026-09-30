"""Build a small cross-platform source patch for an installed 0.3.0-beta."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = ('app.py', 'latency.py', 'streaming.py', 'live_updates.py', 'recognizer.py', 'bridge.py', 'providers.py', 'web/app.js', 'web/index.html', 'web/style.css', 'gpu_runtime.py', 'setup_gpu.py', 'Enable-GPU.cmd', 'extension/manifest.json', '加速更新说明.md')
NAME = 'PhyrexNi-0.3.1-Windows-Mac-App-Update'

NOTE = '''@PhyrexNi · 连接预热、即时推送与显卡加速更新 · 0.3.1-beta · 2026-10-01

适用于已经安装 0.3.0-beta 的外部分发版。
Windows x64 / Mac Apple 芯片 / Mac Intel 共用此更新包。
此包不能独立运行，也不能用于个人本地版或 0.2.x 旧版。

安装方法
1. 结束采集，等待处理完成并导出需要的文字。
2. 关闭翻译页面，运行组件目录的 Stop.cmd（Windows）或 Stop.command（Mac）。
3. 备份现有组件目录。不要删除 user-data、.runtime 或 extension。
4. 将本包中的九个 .py 文件、Enable-GPU.cmd 、加速更新说明.md、extension/manifest.json 和 web 内的三个文件复制到现有组件的对应位置，替换同名文件；新增 live_updates.py 也必须复制。
   组件目录是包含 Start.cmd / Start.command 的文件夹，不是 extension 文件夹。
   web 文件夹应合并内容，不要删除整个旧 web 文件夹。
5. 运行 Start.cmd / Start.command，然后刷新原翻译页面；扩展管理页重新加载原扩展，侧栏也需要刷新。
6. 页面底部显示 0.3.1 BETA 即表示新版页面已载入。

可选显卡加速（仅 Windows x64 + NVIDIA）
本包不含大型显卡库。有兼容 NVIDIA 显卡时，先停止组件，再双击 Enable-GPU.cmd。
先检测显卡兼容性，不兼容则不下载。安装器显示下载进度。
首次下载约 1.1 GB，至少需 4 GB 可用空间。程序只从 NVIDIA 官方 Python 包下载固定版本，校验 SHA-256 后解压到本工具目录，不改系统驱动。
重新启动后，页面应显示“本地语音识别已就绪 · 显卡加速”。依赖缺失或显卡不可用时继续用 CPU。
Mac 本次继续使用 CPU，不具备这项 NVIDIA 加速。

本次改进
- 开始采集时提前准备 ChatGPT 连接和临时会话；不额外发送翻译请求。
- 复用官方连接检查 ChatGPT 登录，每段不再另启登录检查进程；权限检查和 API 密钥拒绝规则保留。
- 译文变化立即推送到页面；掉线后重新接收完整状态，推送不可用时保留轮询。
- 每次只更新变化的段落，保留已有段落、复制图标状态和手动滚动位置。
- 等待 AI 翻译时，同步识别下一段英语，减少音频积压。
- ChatGPT 通过官方 Codex 保持临时会话，逐字显示生成中的中文。兼容性不足时回到原翻译方式。
- 按实际处理耗时自动选择 4–8 秒分段，不再把正常并行处理误判为积压；处理空闲时可在自然停顿处更早提交音频。
- 切点附近尚未识别出的音频保留到下一段，减少漏词。
- 检测异常重复字符，先重新识别再翻译；保留待核实提示。
- 术语解释只用于理解，不提前补写说话人尚未说出的后续内容。
- 生成中的中文明确标注；完成并通过格式检查后才进入复制、朗读和导出。
- 页面显示识别、AI 翻译和排队情况，保留原模型、精度设置及专业词库。
- 每段复制、中文朗读、记录及导出继续保留。

注意
分段秒数不是总延迟；短分段会更频繁地请求 AI，额度用量可能增加。
此次逐字显示功能仅接入 ChatGPT；Grok/Gemini 保留原方式，使用相同自动分段及跨段识别改进。
AI 服务响应慢或网络不稳定时仍可能等待。此次未改变登录方式及 AI 模型。
已有全文记录和登录仍由旧组件保留，本包不含账号、音频、私人记录或大型运行组件。
原 manifest.sha256.json 不再代表被替换的文件，请用本包 latency-update-checksums.json 核对。
需要回退时，停止组件后恢复之前备份的对应文件；原版没有 latency.py / streaming.py / live_updates.py 时可删除这些新增文件。

验证范围
个人版 52 项后端检查通过；Windows/Mac 分发源码分别通过 27 项管线、流式、推送、显卡回退及安装检查。
中文朗读 15 项检查通过；前端分段、500 段局部刷新、推送合并、旧响应隔离、历史切换及重连逻辑检查通过。
本次对照确认三份应用的识别代码、术语库、场景设置、翻译指令、输出校验及音频切分规则均未改变。
Windows 个人版按原速回放 24 秒公开美联储音频，RTX 4070、相同模型、4 秒分段，并通过真实本机推送接口接收中文。
6 段对应 6 次翻译请求，没有因预热增加请求；连接准备约 0.73 秒在采集期间完成。
从片段提交到推送收到中文首字中位约 2.40 秒，另需音频采集时间；不含 YouTube 采集和浏览器渲染。
网络和模型响应有波动，这次结果不能证明总延迟每次都会更短，也不承诺固定延迟或几乎同步。
Mac 本次通过源码逻辑检查，尚未在 Mac 机器上实测延迟。
Grok/Gemini 本次没有账号实测，不能保证其延迟改善幅度。
'''


def build(output):
    output.mkdir(parents=True, exist_ok=True)
    files = {}
    for relative in FILES:
        data = (ROOT / 'windows/app' / relative).read_bytes()
        assert data == (ROOT / 'mac/app' / relative).read_bytes(), relative
        files[relative] = data
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    metadata = {'base_version': '0.3.0-beta', 'version': '0.3.1-beta', 'update': 'overhead-20261001',
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
              'checks': ['Fifteen allowlisted app files only', 'Windows and Mac app files byte-identical',
                         'All compressed entries readable and checksum-verified',
                         'No runtime, account, recordings or model files included']}
    (output / (NAME + '-checks.json')).write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    build(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'dist')
