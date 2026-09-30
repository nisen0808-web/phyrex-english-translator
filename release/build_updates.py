"""Build app and AI updates that reuse the recipient speech runtime."""
import hashlib
import json
from pathlib import Path
import zipfile


def build_update(root, source, output, platform):
    files = {}
    for file in source.rglob('*'):
        if not file.is_file():
            continue
        relative = file.relative_to(source)
        assert '__pycache__' not in relative.parts and file.suffix != '.pyc'
        files[relative.as_posix()] = root / relative
    for file in (root / '.runtime/ai').rglob('*'):
        if file.is_file():
            files[file.relative_to(root).as_posix()] = file
    hashes = {name:hashlib.sha256(file.read_bytes()).hexdigest() for name,file in files.items()}
    note = ('@PhyrexNi 三 AI 更新 · 0.3.1-beta · ' + platform + '\n\n'
        '适用于对应平台已有的 0.2.x 或 0.3.0 完整版；不能单独运行。Mac 芯片必须匹配。\n'
        '1. 结束采集、保存文字，关闭页面，运行旧组件的 Stop.cmd / Stop.command。\n'
        '2. 备份整个旧组件目录，尤其是 user-data。\n'
        '3. 将本包所有内容合并复制到旧组件目录并替换同名文件；包含隐藏的 .runtime/ai 文件夹。\n'
        '   Mac Finder 可用 Command+Shift+句号显示隐藏文件。只能合并 .runtime，不能删除或替换整个 .runtime 目录。\n'
        '4. 保留 .runtime/python、packages、model、codex 和 user-data。\n'
        '5. 重新启动组件，并在扩展管理页重新加载 extension。\n'
        '6. 选择 ChatGPT、Grok 或 Google Gemini，登录所选账号再开始翻译。\n\n'
        '旧 manifest.sha256.json 不再代表更新后的整包；本次覆盖文件见 update-checksums.json。\n'
        '若不熟悉文件夹合并，请下载新版完整包并迁移 user-data。回退时停止组件并恢复整个备份目录。\n')
    archive = output / ('PhyrexNi-AI-0.3.1-' + platform + '-Update.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,file in files.items():
            z.write(file,name)
        z.writestr('安装更新.txt', note.encode('utf-8'))
        z.writestr('update-checksums.json',json.dumps(hashes,indent=2).encode('utf-8'))
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for name,digest in hashes.items():
            assert hashlib.sha256(z.read(name)).hexdigest()==digest
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(digest+'  '+archive.name+'\n',encoding='ascii')
    (output/(archive.stem+'-checks.json')).write_text(json.dumps({'checks':['all update entries extracted and checksum verified','includes full app and official AI runtimes; excludes speech runtime and user data'],'files':len(files),'sha256':digest},indent=2),encoding='utf-8')
