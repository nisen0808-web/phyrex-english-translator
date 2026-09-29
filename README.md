# @PhyrexNi · 美联储英语直播译文

把英语直播、回放和访谈翻译成中文。优先支持美联储与宏观财经内容，也可选择通用英语场景。

**0.3.0-beta · Windows 10/11 x64 / macOS 14+ · Chrome / Edge · 仅英语 → 中文**

新增 **ChatGPT、Grok、Google Gemini** 三种翻译 AI，分别登录自己的账号。保留中文朗读：中文播放时屏蔽英文外放，英文音轨继续识别。

## 下载

- [Windows 完整包 · 7z](https://github.com/nisen0808-web/phyrex-english-translator/releases/download/v0.3.0-beta/Fed-English-Translator-0.3.0-beta-Windows-x64-Compact.7z)
- [Mac 完整包 · Apple 芯片（M 系列）](https://github.com/nisen0808-web/phyrex-english-translator/releases/download/v0.3.0-beta/Fed-English-Translator-0.3.0-beta-macOS-arm64.zip)
- [Mac 完整包 · Intel](https://github.com/nisen0808-web/phyrex-english-translator/releases/download/v0.3.0-beta/Fed-English-Translator-0.3.0-beta-macOS-x86_64.zip)

已有 0.2.x 完整版可使用对应系统和芯片的更新包，复用原语音模型：

- [Windows x64 三 AI 更新包](https://github.com/nisen0808-web/phyrex-english-translator/releases/download/v0.3.0-beta/PhyrexNi-AI-0.3.0-Windows-x64-Update.zip)
- [Mac · Apple 芯片 三 AI 更新包](https://github.com/nisen0808-web/phyrex-english-translator/releases/download/v0.3.0-beta/PhyrexNi-AI-0.3.0-macOS-arm64-Update.zip)
- [Mac · Intel 三 AI 更新包](https://github.com/nisen0808-web/phyrex-english-translator/releases/download/v0.3.0-beta/PhyrexNi-AI-0.3.0-macOS-x86_64-Update.zip)

更新包不能单独运行。先结束采集、运行 Stop 脚本并备份，再按包内说明合并文件，包括隐藏的 `.runtime/ai`。保留 `user-data` 和原语音组件；不熟悉文件合并时请选择完整包。

[版本说明、完整附件与 SHA-256](https://github.com/nisen0808-web/phyrex-english-translator/releases/tag/v0.3.0-beta) · [安装与下载页面](https://nisen0808-web.github.io/phyrex-english-translator/) · [隐私说明](docs/privacy.html)

首次使用请选择完整包。GitHub 自动提供的 **Source code** 不包含语音模型与本机运行组件。

## 首次使用

### Windows

1. 使用支持 7z 的解压工具（例如 [7-Zip](https://www.7-zip.org/)），把整个完整包解压到固定文件夹。
2. 双击 `Install-Connector.cmd`，为当前 Windows 用户安装本机连接。
3. 在 Chrome 打开 `chrome://extensions`，或在 Edge 打开 `edge://extensions`。
4. 打开“开发者模式”，点击“加载已解压的扩展程序”，选择包内的 **extension** 文件夹。
5. 固定扩展，点击打开侧栏，选择 ChatGPT、Grok 或 Google Gemini，登录自己的对应账号。
6. 播放英语视频，点击“选择直播标签页，开始翻译”，选择播放页面并勾选共享标签页音频。

侧栏无法共享声音时，点击“完整页面”，或运行 `Start.cmd`。翻译期间保持采集页面打开。结束时点“结束采集并保存”，等待文字处理完成后导出。用完可运行 `Stop.cmd`。

### Mac

在苹果菜单“关于本机”查看芯片，下载对应的完整 ZIP，双击解压到固定文件夹。

1. 双击 `Install-Connector.command`，为当前用户注册本机连接。
2. Chrome / Edge 扩展管理页开启开发者模式，加载包内的 **extension** 文件夹。
3. 打开扩展并选择 AI 并登录自己的账号，然后选择播放英语视频的标签页并勾选共享音频。
4. 侧栏无法采集时，点击“完整页面”或运行 `Start.command`；用完运行 `Stop.command`。

Mac 包尚未经过 Apple 公证，首次打开可能出现开发者验证提示；请参阅 [Apple 官方说明](https://support.apple.com/102445)，不要关闭系统安全防护。系统要求录屏/音频权限时，请为正在使用的浏览器授权。[详细 Mac 安装说明](mac/app/先读我-Mac.md)

## 开启中文朗读

1. 在开始采集前勾选“中文朗读 · 朗读时屏蔽英文”。
2. 选择本机中文声音和语速，点击“试听”。
3. 保持 YouTube 音量开启，正常共享播放标签页的音频。

只朗读本次采集的新中文正文，不读时间戳和“待核实”说明，也不重读历史记录。暂停朗读会恢复英文；继续后只读新译文。积压过多会跳过较早的朗读，文字不会删除。

朗读使用本机中文语音，不增加配音 API 或 Codex 请求。未安装中文声音时，文字翻译仍可使用。中文存在分段、识别和翻译延迟，并非零延迟同传。[完整朗读说明](READ_ALOUD.md)

## 能做什么

- 英语直播、回放、访谈和课程转中文；支持美联储 / 财经及通用英语两种场景。
- 内置 **556 条**美联储、通胀、劳动力市场、增长、金融、流动性、银行信用及数据口径术语，可编辑至 1000 条。
- 每段有独立复制图标；带“待核实”的段落也能复制，只复制正文。
- 中文记录自动保存在本机，支持 TXT、Word 和 SRT 导出。
- 可选中文朗读、声音与语速选择、暂停及跳过；朗读时屏蔽英文外放。
- 声音在本机识别，识别后的英文、短上下文与相关术语经官方组件发给所选 AI，使用用户自己的账号额度。

## 测试范围

这是 GitHub 公开测试版，尚未上架 Chrome / Edge 商店。需要浏览器扩展配合本机组件。ChatGPT 需要 Codex 权限，Grok 需要 Grok Build 权限；Gemini 使用 Google 登录。各家额度及可用模型以账号为准，不自动切换 AI。[AI 选择与账号说明](AI_PROVIDERS.md)

三个系统完整包在发布流程中通过组件运行、独立账号、页面服务和重新解压检查，新增 12 项 AI 检查，朗读逻辑有 13 项检查。真实 Grok/Google 账号授权、账号额度及实际模型译文尚未实测。Windows 浏览器本机试听与 Web Audio 音轨分离也已检查。真实 YouTube 长时间直播、用户电脑的中文声音、Mac 浏览器朗读与物理扬声器效果仍需试用。

数字、否定语气和专有名词出现“待核实”时，请结合原音判断。[完整验证范围](VERIFICATION.md)

## 反馈问题

[提交测试反馈](https://github.com/nisen0808-web/phyrex-english-translator/issues/new?template=bug_report.yml)。请说明操作系统、Mac 芯片类型、浏览器版本、所选 AI、中文声音、操作步骤和错误文字。可选填公开视频链接与时间位置。

不要公开登录凭据、Cookie、API 密钥、整个 `user-data` 文件夹或未经处理的私人内容。

## 升级、记录与卸载

完整包升级：先结束翻译并停止旧组件，把新版解压到新目录。需要迁移时，自行复制旧目录的 `user-data` 到新目录，再注册新版本机组件并重新加载新版扩展。也可按上面的轻量更新说明保留原目录。

中文记录和自定义术语位于 `user-data`，ChatGPT 登录位于 `user-data/account`，Grok/Gemini 分别位于 `user-data/providers`。应用记录仅保存中文。官方组件可能写临时会话缓存，本工具在翻译结束和下次启动时清理；异常退出可能暂留英文缓存。

Windows 先运行 `Stop.cmd`，再运行 `Uninstall-Connector.cmd`；Mac 对应为 `Stop.command` 和 `Uninstall-Connector.command`。卸载连接注册后，账号和记录仍保留，由用户自行管理。转发时请使用 Releases 中的原始干净压缩包。

第三方组件及许可随完整包保留，见 [第三方说明](THIRD_PARTY_NOTICES.md)。本工具由 @PhyrexNi 发布，与 YouTube、Google、Microsoft、OpenAI、xAI 及美联储无官方隶属或认可关系。
