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
