## Mac 公开测试版

**macOS 14 或更新版本 · Chrome / Edge · 仅英语 → 中文**

两种完整 ZIP 均包含 Python、Codex、本地语音模型和浏览器扩展，无需另装 Python 或 Homebrew。

- **Apple 芯片（M 系列）**：下载名称以 `macOS-arm64.zip` 结尾的文件。
- **Intel 芯片**：下载名称以 `macOS-x86_64.zip` 结尾的文件。

在苹果菜单“关于本机”查看芯片。不要下载 GitHub 自动生成的 Source code，它没有运行组件。

### 安装

1. 双击 ZIP 完整解压，将整个文件夹放到固定位置。
2. 双击 `Install-Connector.command`，安装当前用户的浏览器连接。
3. Chrome / Edge 的扩展管理页开启开发者模式，加载包内的 `extension` 文件夹。
4. 打开扩展，登录自己的、支持 Codex 的 ChatGPT 账号。
5. 播放英语视频，选择播放标签页并勾选共享音频。

侧栏无法采集时，可点“完整页面”，或双击 `Start.command`。使用完毕运行 `Stop.command`；卸载连接运行 `Uninstall-Connector.command`。账号和中文记录保留在本机 `user-data`。

### 功能

- 556 条美联储、宏观、金融和劳动力市场术语，并支持通用英语。
- 每段独立复制中文，不复制“待核实”说明。
- 中文自动保存，支持 TXT、Word 和 SRT 导出。
- 使用自己的 ChatGPT / Codex 额度。

### 验证范围

附件只在两种原生 Mac 构建任务都通过后发布。检查包括运行组件、本机接口边界、账号隔离、连接配置、合成英语语音识别，以及 ZIP 解压到含空格的新路径后的重复运行；具体结果见附件 `checks.json`。这些检查没有代替真实账号登录、浏览器授权、YouTube 采集和长时间直播测试。

这个版本尚未经过 Apple 公证，也没有 Mac 第三方杀毒认证。首次打开可能出现系统开发者验证提示，请核对来源并参阅 [Apple 官方说明](https://support.apple.com/102445)；不要关闭系统安全防护。Windows 版本此前的 Defender 扫描结果不代表 Mac 包已通过同样扫描。

文件校验值见对应 `.sha256` 附件。下载项为公开测试包，请勿转发使用后包含账号凭据的目录。

[下载与说明](https://nisen0808-web.github.io/phyrex-english-translator/) · [测试反馈](https://github.com/nisen0808-web/phyrex-english-translator/issues)
