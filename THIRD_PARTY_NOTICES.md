# 第三方组件

为方便首次使用，本测试包包含以下运行组件。各组件的许可证随包保留；应用代码与第三方组件的许可应分别查阅。

| 组件 | 来源与许可文件 |
| --- | --- |
| Python 3.12 | https://www.python.org/ · `licenses/Python-LICENSE.txt` 和 `.runtime/python/LICENSE.txt` |
| OpenAI Codex CLI 0.158.0 | https://github.com/openai/codex/releases/tag/rust-v0.158.0 · `licenses/Codex-LICENSE.txt`、`licenses/Codex-NOTICE.txt` |
| faster-whisper | https://github.com/SYSTRAN/faster-whisper · `.runtime/packages/faster_whisper-*.dist-info` |
| Whisper small 模型 | https://huggingface.co/Systran/faster-whisper-small · 转换自 https://github.com/openai/whisper · `licenses/Whisper-LICENSE.txt` |
| CTranslate2、NumPy、ONNX Runtime、PyAV 及其他依赖 | 包内 `.runtime/packages` 中相应的 `.dist-info`、`licenses`、`LICENSE` 和 `NOTICE` 文件 |

依赖的确切版本和文件摘要记录在 `manifest.sha256.json`。

Codex 官方 Windows x64 组件 ZIP 的 SHA-256：
`a18dfc0184543cd647198b6c4a2fb01598b91503e54209e04221a65a942de03c`

这是独立工具的测试分发包，不代表 YouTube、Google、Microsoft、OpenAI 或美联储的官方产品或认可。


Mac 0.2.3-mac-beta 的可移植 Python、各架构依赖和固定文件校验值见 [Mac 第三方说明](mac/app/THIRD_PARTY_NOTICES.md) 与 [下载来源清单](mac/sources.lock.json)。


0.3.0 新增 Grok Build 1.0.44、Gemini CLI 0.61.0（均 Apache-2.0）及 Node.js 24.21.0。固定来源和完整校验值见 [AI 组件清单](release/ai-sources.lock.json)，许可和第三方声明保留在完整包 .runtime/ai 中。
