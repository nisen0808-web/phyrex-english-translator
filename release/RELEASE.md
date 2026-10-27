# DeepSeek API 可选接入 · 0.3.4-beta

外部测试版新增 DeepSeek API 选项，同时保留 ChatGPT、Grok、Google Gemini 和 Claude API。DeepSeek 使用用户自己提供的 API 密钥，按 DeepSeek API 账户余额及用量计费。输入密钥不会发起付费测试；开始翻译后，识别出的英文、必要上下文及匹配的术语会发送给 DeepSeek，可能产生 API 用量和费用，默认启用思考，思考输出也可能计费并增加等待；每次请求的 max_tokens 参数设为 4096；接口返回长度限制时该片段会暂停，手动重试可能再次计费。请求等待约 90 秒后会停止，但服务端仍可能完成并计费。

密钥暂存在本机运行进程内存，DeepSeek 请求时经本机匿名管道传递；可手动清除，切换 AI 或关闭组件后需要重新输入。不要向发布者提供密钥。原有本机英语识别、美联储词库、中文朗读、逐段复制和 TXT / Word / SRT 导出保留。没有新增固定延迟或准确率承诺。

## 安装和更新

- 已安装外部版 0.3.0、0.3.1、0.3.2 或 0.3.3：下载 `PhyrexNi-0.3.4-Windows-Mac-App-Update.zip`。三个平台共用，不能单独运行。停止组件并备份后，按包内说明合并文件，保留 `user-data` 与 `.runtime`；重新启动并加载扩展。
- 使用更早版本的用户建议下载对应系统的完整包；0.2.x 升级本轮未实测。
- 首次使用：下载 Windows x64、Mac Apple 芯片或 Mac Intel 完整包。Source code 不含本机运行组件和语音模型；Mac 需 macOS 14+。

## 验证与限制

发布前须通过三个平台的原生构建、组件运行、重新解压及离线回归检查；检查报告和 SHA-256 随版本附件提供。API 调用和错误处理采用模拟响应验证，不使用真实账号、密钥或模型。本轮尚未实测真实 DeepSeek API 账单、模型译文与实时延迟，亦未实测长时间 YouTube 直播及 Mac 浏览器物理朗读。测试不能证明总体翻译准确率或固定延迟。Mac 未经过 Apple 公证；没有新增杀毒认证。

[安装说明](https://github.com/nisen0808-web/phyrex-english-translator#首次使用) · [隐私说明](https://nisen0808-web.github.io/phyrex-english-translator/privacy.html) · [反馈问题](https://github.com/nisen0808-web/phyrex-english-translator/issues)
