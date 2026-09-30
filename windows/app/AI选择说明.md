# 选择翻译 AI · 0.3.1-beta

外部版可选 ChatGPT、Grok 和 Google Gemini。先选择 AI，再点击对应的登录按钮，使用自己的账号。不会要求你向发布者提供密码、Cookie 或 API 密钥。

| 选择 | 官方本机组件 | 账号要求 |
| --- | --- | --- |
| ChatGPT | OpenAI Codex 0.158.0 | 账号需要有 Codex 权限；保留快速和精细两种翻译模式。 |
| Grok | Grok Build 1.0.44 | 账号需要有 Grok Build 权限；普通 Grok 网页可用不代表一定能使用 Build。模型由账号默认设置决定。 |
| Google Gemini | Gemini CLI 0.61.0 | 登录自己的 Google 账号，模型由账号可用范围决定。个人账号较适合首次测试，部分公司或学校账号需要额外项目配置。 |

三者的订阅、使用权限和额度分别计算，以官方账号界面为准。本工具不自动切换 AI、不内置发布者账号，也不读取已有 API 密钥。

同一场采集固定使用开始时选择的 AI。先结束采集、处理完已提交片段，再切换；译文、词库、复制、导出和中文朗读共用。额度不足时保留已完成的中文，提示等待或重新登录后继续。Grok 和 Gemini 的登录标记只表示此前完成过授权，实际权限和额度在翻译时检查。

语音在本机识别。识别出的英文、短上下文及相关术语发给所选 AI 的服务。应用记录只保存中文；Grok/Gemini 官方组件可能生成临时会话缓存，本工具在每次翻译结束和下次启动时清理自己的临时目录。异常退出时缓存可能暂时留在本机，不能保证英文从不落盘。详见 PRIVACY.md。

组件校验、无账号启动、Gemini 登录协议初始化、模拟译文路由和错误处理经过自动检查。真实 Grok/Google 授权、账号额度及实际模型翻译仍需用户实测；这不是对所有账号均可用的保证。

官方说明：[Grok Build](https://docs.x.ai/build/overview)、[Grok 无界面调用](https://docs.x.ai/build/cli/headless-scripting)、[Gemini 账号登录](https://geminicli.com/docs/get-started/authentication/)、[Gemini 无界面调用](https://geminicli.com/docs/cli/headless/)。
