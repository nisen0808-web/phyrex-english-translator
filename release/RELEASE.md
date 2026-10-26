# Claude API 可选接入 · 0.3.3-beta

外部测试版新增 Claude API 选项，同时保留 ChatGPT、Grok、Google Gemini。Claude 使用用户自己提供的 Anthropic Console API 密钥，并按 API 额度或账单独立计费，不使用 Claude 网页订阅限额。

输入密钥不会触发付费测试；选择 Claude 并开始翻译后，音频识别后的英文及必要上下文会发送给 Anthropic，可能产生 API 用量和费用。密钥仅保留在本机组件的运行内存，可手动清除；关闭组件后需重新输入。不要向发布者提供密钥。

原有本机英语识别、美联储用语、中文朗读、每段复制、TXT / Word / SRT 导出保留。没有新增固定延迟或翻译准确率承诺。ChatGPT、Grok、Gemini 的账号方式不变。

## 安装和更新

- 已安装外部版 0.3.0、0.3.1 或 0.3.2：下载 `PhyrexNi-0.3.3-Windows-Mac-App-Update.zip`。三个平台共用，不能单独运行。先停止组件并备份，再按包内说明合并文件，保留 `user-data` 与 `.runtime`；重启后刷新页面并重新加载扩展。确认页面底部显示 0.3.3 BETA。
- 已安装外部版 0.2.x：对应系统和芯片的 `PhyrexNi-AI-0.3.3-…-Update.zip` 面向旧版设计，但本轮未实际测试 0.2.x 升级，建议使用完整包；不要用轻量包跨越 0.2.x。
- 首次使用：下载 Windows x64、Mac Apple 芯片或 Mac Intel 完整包。Source code 不含运行组件和语音模型；Mac 需 macOS 14+。

## 验证与限制

发布前必须通过三个平台的原生组件、账号目录隔离、本机服务、重新解压及离线回归检查；实际检查报告和 SHA-256 随版本附件提供。Claude API 的调用和错误处理采用模拟响应验证，不使用真实账号或模型。

Claude 对最终修订版的独立复核因额度或请求频率受限未完成。本轮尚未实测真实 Claude API 密钥、账单与译文，Grok/Google 真实账号，Mac 浏览器物理朗读及长时间 YouTube 直播。测试不能证明总体翻译准确率或某个固定延迟。Mac 未经过 Apple 公证；没有新增杀毒认证。仍为 GitHub 公开测试版，尚未上架扩展商店。

英文及相关上下文会发送给用户选择的服务。Grok/Gemini 官方组件可能写入临时缓存，工具会清理自己的缓存；异常退出可能暂留。详见 [隐私说明](https://nisen0808-web.github.io/phyrex-english-translator/privacy.html)。

[安装说明](https://github.com/nisen0808-web/phyrex-english-translator#首次使用) · [验证范围](https://github.com/nisen0808-web/phyrex-english-translator/blob/main/VERIFICATION.md) · [反馈问题](https://github.com/nisen0808-web/phyrex-english-translator/issues)
