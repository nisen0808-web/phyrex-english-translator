# 低延迟优化测试版 · 0.3.1-beta

减少英语直播翻译中的程序等待，保留 ChatGPT、Grok、Gemini 选择、556 条美联储与宏观财经术语、中文朗读、逐段复制和 TXT / Word / SRT 导出。每个人继续登录自己的 AI 账号。

- 本机识别与 AI 翻译流水线并行，自动选择 4–8 秒分段，并保留切点附近尚未识别完的声音。
- ChatGPT 提前准备官方连接和临时会话，逐字显示中文；复用连接确认登录，减少每段重复启动进程。
- 译文即时推送，只更新变化的段落。断线后恢复完整状态，推送不可用时保留原轮询方式。
- 生成中的中文只用于预览；完成并校验后才可复制、朗读和导出。待核实说明仍保留，复制与朗读只取正文。
- Windows x64 的兼容 NVIDIA 显卡可选启用本机识别加速；不支持时使用 CPU。Mac 本次使用 CPU。

识别模型、专业词库和翻译上下文保留，不靠猜测未来讲话或强行缩短分段来提速。网络和 AI 服务响应仍有波动，不承诺零延迟或固定延迟。

## 下载与更新

**首次安装：** Windows 下载 Windows-x64-Compact.7z；Mac 按芯片下载 macOS-arm64.zip 或 macOS-x86_64.zip。Source code 不包含运行组件和语音模型。

**已有 0.3.0 完整版：** 下载 `PhyrexNi-0.3.1-Windows-Mac-App-Update.zip`，三个平台共用，小体积、不含大型运行组件。停止组件并备份后，按包内说明合并文件，保留 `user-data` 与 `.runtime`，重启并刷新页面。更新后在扩展管理页重新加载原扩展。

**已有 0.2.x 完整版：** 下载对应系统和芯片的 `PhyrexNi-AI-0.3.1-…-Update.zip`，包含三 AI 组件，复用原语音模型。按说明合并隐藏的 `.runtime/ai`；不要用小体积 App 更新包跨越 0.2.x。

**可选 NVIDIA 加速：** Windows 用户先停止组件，再运行 `Enable-GPU.cmd`。兼容性检查通过后首次下载约 1.1 GB 的固定版本 NVIDIA 库，并校验 SHA-256。程序不改系统驱动；没有兼容显卡不下载。需至少 4 GB 可用空间。重新启动后页面应显示“显卡加速”。

## 数据与验证范围

音频在本机识别；英文、短上下文与相关术语发给用户选定的官方 AI 服务。应用记录仅保存中文。Grok/Gemini 官方组件可能写临时缓存，本工具在翻译后及下次启动时清理；异常退出可能暂留缓存。

发布必须通过 Windows、Apple 芯片 Mac、Intel Mac 的原生组件与重新解压检查，另有各平台 27 项管线、流式、显卡回退、安装和 HTTP 推送检查，12 项 AI 路由与账号隔离检查，15 项朗读检查。前端检查包含 500 段局部刷新、断线重连、历史切换和旧响应隔离。检查报告与 SHA-256 均在附件中。

Windows 使用真实 ChatGPT 账号按原速回放 24 秒美联储音频，6 段对应 6 次翻译，预热没有额外翻译请求。单次测得片段提交至本机推送收到中文首字的中位数约 2.40 秒，另需音频采集时间，不含 YouTube 采集和浏览器渲染。该样本不能代表其他网络、显卡或长期直播表现。

**真实 Grok/Google 授权、额度和模型译文，以及 Mac 的真实 AI 延迟和浏览器朗读，尚未完成本轮实测。** 原生构建检查不是这些环节的证明。Mac 尚未经过 Apple 公证；此版没有新增杀毒认证。仍为 GitHub 公开测试版，尚未上架扩展商店。

[安装说明](https://github.com/nisen0808-web/phyrex-english-translator#首次使用) · [AI 账号说明](https://github.com/nisen0808-web/phyrex-english-translator/blob/main/AI_PROVIDERS.md) · [验证范围](https://github.com/nisen0808-web/phyrex-english-translator/blob/main/VERIFICATION.md) · [反馈问题](https://github.com/nisen0808-web/phyrex-english-translator/issues)
