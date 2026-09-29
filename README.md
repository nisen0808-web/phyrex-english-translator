# @PhyrexNi · 美联储英语直播译文

把英语直播、回放和访谈翻译成中文。优先支持美联储与宏观财经内容，也可选择通用英语场景。

**公开测试版 0.2.2-beta · Windows 10/11 x64 · Chrome / Edge · 仅英语 → 中文**

## 下载

[**下载 Windows 完整测试包 · 581 MB（7z）**](https://github.com/nisen0808-web/phyrex-english-translator/releases/download/v0.2.2-beta/Fed-English-Translator-0.2.2-beta-Windows-x64-Compact.7z)

[版本与全部附件](https://github.com/nisen0808-web/phyrex-english-translator/releases/tag/v0.2.2-beta) · [安装与下载页面](https://nisen0808-web.github.io/phyrex-english-translator/) · [隐私说明](docs/privacy.html)

请下载上面的完整测试包。GitHub 自动提供的 **Source code** 压缩包仅包含本仓库的说明和网页，不包含语音模型与本机组件。

## 首次使用

1. 使用支持 7z 的解压工具（例如 [7-Zip](https://www.7-zip.org/)），把**整个压缩包**解压到一个固定文件夹。
2. 双击解压目录中的 `Install-Connector.cmd`，为当前 Windows 用户安装本机连接。
3. 在 Chrome 打开 `chrome://extensions`，或在 Edge 打开 `edge://extensions`。
4. 打开“开发者模式”，点击“加载已解压的扩展程序”，选择解压目录里的 **extension** 文件夹。
5. 固定“PhyrexNi · 美联储英语直播译文”，点击扩展打开侧栏。首次使用需登录**自己的、支持 Codex 的 ChatGPT 账号**。
6. 在另一个标签页播放英语视频，点击“选择直播标签页，开始翻译”，选中播放页面并勾选“共享标签页音频”。

如果侧栏无法共享声音，请点击“完整页面”，或者双击解压目录中的 `Start.cmd`，在完整页面里选择视频标签页。

翻译期间保持采集页面打开。结束时点“结束采集并保存”，等处理完成后导出。暂时不用时，可运行 `Stop.cmd`。

## 能做什么

- 英语直播、回放、访谈和课程转中文；支持美联储 / 财经及通用英语两种场景。
- 内置 **556 条**美联储、通胀、劳动力市场、增长、金融、流动性、银行信用及数据口径术语，可编辑至 1000 条。
- 每一段有独立复制图标；带“待核实”的段落也能复制，复制内容不含时间戳和核实说明。
- 中文记录自动保存在本机，支持 TXT、Word 和 SRT 导出。
- 声音在本机识别，识别后的英文、短上下文与相关术语由官方 Codex 发送给 OpenAI 翻译，使用用户自己的账号额度。

## 这轮测试的范围

这是 **GitHub 公开测试版，尚未上架 Chrome / Edge 商店**。需要浏览器扩展配合本机组件，不能只装扩展。

已经检查包内运行环境、本地语音模型、术语匹配、导出和新用户账号隔离。高压缩包解压后的 **3159 个文件与原始 ZIP 逐项一致**，并通过一段真实美联储音频的本地识别测试。

不同电脑上的完整扩展安装、首次 ChatGPT 登录，以及长时间真实直播采集仍需要本轮用户测试。翻译有分段和处理延迟，准确率并非保证；数字、否定语气和专有名词出现“待核实”时，请结合原音判断。[完整验证范围](VERIFICATION.md)

## 反馈问题

[提交测试反馈](https://github.com/nisen0808-web/phyrex-english-translator/issues/new?template=bug_report.yml)。请说明 Windows 与浏览器版本、操作步骤、错误文字和大致发生时间。可选填公开视频链接与时间位置。

不要在公开反馈里附带登录凭据、Cookie、API 密钥、整个 `user-data` 文件夹或未经处理的私人内容。

## 记录与卸载

中文记录和自定义术语位于解压目录的 `user-data`，官方 Codex 登录凭据位于 `user-data/account`。本工具不持久保存原始音频或英语逐字稿。

先运行 `Stop.cmd`，再运行 `Uninstall-Connector.cmd` 可移除本机连接注册；账号和记录会保留，需要删除时由用户自行管理 `user-data`。转发时请使用 Releases 中的原始干净压缩包。

## 文件校验

文件：`Fed-English-Translator-0.2.2-beta-Windows-x64-Compact.7z`  
字节数：`581253142`  
SHA-256：`24b3c081b4fb9e01a7006493429c02193f4aeb9ade939901592e2be13b775725`

第三方组件及许可随完整包保留，见 [第三方说明](THIRD_PARTY_NOTICES.md)。本工具由 @PhyrexNi 发布，与 YouTube、Google、Microsoft、OpenAI 及美联储无官方隶属或认可关系。
