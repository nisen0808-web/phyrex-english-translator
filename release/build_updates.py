"""Build small, checksummed UI updates for existing public companion installations."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'dist-updates'
OUT.mkdir(exist_ok=True)
for platform, folder, base in [('Windows', 'windows', '0.2.2-beta'), ('Mac', 'mac', '0.2.3-mac-beta')]:
    files = {}
    for name in ('app.js', 'index.html', 'style.css'):
        files['web/' + name] = (ROOT / folder / 'app/web' / name).read_bytes()
    files['中文朗读说明.md'] = (ROOT / 'READ_ALOUD.md').read_bytes()
    files['PRIVACY.md'] = (ROOT / folder / 'app/PRIVACY.md').read_bytes()
    files['安装更新.txt'] = (f'@PhyrexNi 中文朗读更新 · 0.2.5-beta · {platform}\n\n'
        f'仅适用于已安装的 {base} 公开测试版，不能单独运行；后台版本号仍显示原版本。\n'
        '1. 结束采集，等待文字保存，关闭翻译页面。\n'
        '2. 备份原组件目录的 web 文件夹及 PRIVACY.md。\n'
        '3. 把本包的 web 文件夹、PRIVACY.md 和中文朗读说明.md 复制到原组件目录，替换同名文件。\n'
        '4. 重新打开翻译页面；在开始采集前选择中文声音、试听并勾选中文朗读。\n\n'
        '不要删除 user-data，不需重新登录、重下载模型或重新注册扩展。\n'
        '回退时恢复备份的 web 和 PRIVACY.md 即可。\n'
        '这是公开测试功能：不同系统声音、浏览器标签页音频与真实直播表现仍需试用。\n').encode('utf-8')
    hashes = {name: hashlib.sha256(body).hexdigest() for name, body in files.items()}
    files['checksums.json'] = json.dumps(hashes, ensure_ascii=False, indent=2).encode('utf-8')
    archive = OUT / f'PhyrexNi-Read-Aloud-0.2.5-{platform}-Update.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, content in files.items():
            z.writestr(name, content)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None and set(z.namelist()) == set(files)
        for name, checksum in hashes.items():
            assert hashlib.sha256(z.read(name)).hexdigest() == checksum
    archive.with_suffix('.zip.sha256').write_text(hashlib.sha256(archive.read_bytes()).hexdigest() + '  ' + archive.name + '\n', encoding='ascii')
    print(archive.name, archive.stat().st_size)
