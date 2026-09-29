# 三 AI 公开测试版 · 0.3.0-beta

外部版新增 ChatGPT、Grok、Google Gemini 选择。Windows、Apple 芯片 Mac、Intel Mac 均包含官方组件；使用各自的个人账号。

- ChatGPT 继续通过 Codex 登录；Grok 使用官方 Grok Build，账号需要有 Build 权限；Gemini 使用官方 Gemini CLI 的 Google 登录。
- 选择 AI 后登录自己的账号。不同服务分别计算额度，不自动切换，不内置发布者账号，不要求 API 密钥。
- 一场采集固定使用开始时选定的 AI。美联储 556 条术语、通用英语、逐段复制、中文朗读及 TXT/Word/SRT 导出共用。
- 保留中文朗读时屏蔽英文外放，识别音轨持续采集。朗读默认关闭，需系统本机中文声音。

## 下载

首次使用选完整包：Windows 选 Windows-x64-Compact.7z；Mac 按芯片选 macOS-arm64.zip 或 macOS-x86_64.zip。Source code 不含运行组件和语音模型。

已有 0.2.x 完整版可用对应系统及芯片的 PhyrexNi-AI-0.3.0-…-Update.zip，复用原语音模型与 Python。升级前结束采集、运行 Stop 脚本并备份；按包内说明合并文件，包含隐藏的 .runtime/ai，保留 user-data 及原语音组件。不熟悉文件合并时请用完整包，在停止旧组件后迁移 user-data 并重新注册扩展。

## 数据与测试范围

声音在本机识别；英文文字、短上下文与术语发给所选 AI 官方服务。应用记录仅保存中文。Grok/Gemini 官方组件可能写临时会话缓存，本工具在翻译后和下次启动时清理；异常退出可能暂留缓存，不承诺英文从不落盘。

发布要求三个系统通过组件运行、账号隔离、页面和重新解压检查，另有 12 项 provider 检查及 13 项朗读检查。包括真实官方组件无账号启动与 Gemini 登录协议初始化；模拟译文用于检查路由和错误处理。

**真实 Grok/Google 账号授权、账号权限与额度、实际模型译文尚未完成实测。** 真实直播、不同系统中文声音和物理扬声器效果仍需公开测试。检查报告及 SHA-256 随附件提供。

Mac 尚未经过 Apple 公证；此版尚无新的杀毒认证。仍为 GitHub 公开测试版，尚未上架 Chrome/Edge 商店。

[AI 账号说明](https://github.com/nisen0808-web/phyrex-english-translator/blob/main/AI_PROVIDERS.md) · [安装说明](https://github.com/nisen0808-web/phyrex-english-translator#首次使用) · [反馈问题](https://github.com/nisen0808-web/phyrex-english-translator/issues)
