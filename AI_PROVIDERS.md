# 选择翻译 AI · 0.3.3-beta

外部版可选 ChatGPT、Grok、Google Gemini 和 Claude API。前三项使用用户自己的服务账号；Claude 选项使用用户主动提供的 Anthropic Console API 密钥。不会向发布者提供密码、Cookie 或密钥。

| 选择 | 使用方式 | 账号要求和费用 |
| --- | --- | --- |
| ChatGPT | 官方 Codex 0.158.0 | 登录自己的 ChatGPT，账号需要 Codex 权限。 |
| Grok | 官方 Grok Build 1.0.44 | 登录自己的 Grok，账号需要 Grok Build 权限；网页能用不代表有 Build 权限。 |
| Google Gemini | 官方 Gemini CLI 0.61.0 | 登录自己的 Google 账号；部分公司或学校账号可能需要额外配置。 |
| Claude API | Anthropic 官方 Messages API | 用户自行提供 Anthropic Console API 密钥，按 API 额度或账单独立计费，不使用 Claude 聊天订阅限额。 |

选择 Claude API 后，在本机页面输入自己的 API 密钥；如账号配置需要，也可填写工作区 ID。密钥只保留在本机运行中的组件内存，可在页面清除，关闭组件后需要重新输入。输入密钥不会触发付费测试；翻译请求可能产生 API 用量，具体额度、价格和账单由 Anthropic Console 决定。不要把密钥发给发布者或其他人。Claude API 使用直接连接，不读取系统环境中的代理设置；网络需要允许连接 Anthropic API。

各家权限和额度分别计算；工具不自动切换 AI，不使用发布者账号，也不自动读取已有 API 密钥。Claude API 和 Claude 网页订阅是独立的服务及计费渠道，请在使用前了解自己的 API 账单设置。

同一场采集固定使用开始时选择的 AI。切换前结束采集并等待已提交片段处理完成。语音在本机识别，识别出的英文、短上下文及相关术语发给所选服务；中文记录保存在本机。Grok/Gemini 官方组件可能写入临时缓存，异常退出时可能暂留。详见 PRIVACY.md。

自动检查使用模拟网络响应；真实 Claude API 密钥、额度、模型翻译，以及 Grok/Google 实际账号授权仍需用户自行试用，不保证所有账号均可用。Mac 浏览器朗读和真实 YouTube 长时间直播尚未完成本轮实测。

官方说明：[Anthropic API 入门](https://platform.claude.com/docs/en/get-started)、[Grok Build](https://docs.x.ai/build/overview)、[Gemini 账号登录](https://geminicli.com/docs/get-started/authentication/)。
