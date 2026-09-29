# 第三方组件

为方便首次使用，本测试包包含以下运行组件。各组件的许可证随包保留；应用代码与第三方组件的许可应分别查阅。

| 组件 | 来源与许可文件 |
| --- | --- |
| Python 3.12 | https://www.python.org/ · `licenses/Python-LICENSE.txt` 及 `.runtime/python` 内保留的许可文件 |
| OpenAI Codex CLI 0.158.0 | https://github.com/openai/codex/releases/tag/rust-v0.158.0 · `licenses/Codex-LICENSE.txt`、`licenses/Codex-NOTICE.txt` |
| faster-whisper | https://github.com/SYSTRAN/faster-whisper · `.runtime/packages/faster_whisper-*.dist-info` |
| Whisper small 模型 | https://huggingface.co/Systran/faster-whisper-small · 转换自 https://github.com/openai/whisper · `licenses/Whisper-LICENSE.txt` |
| CTranslate2、NumPy、ONNX Runtime、PyAV 及其他依赖 | 包内 `.runtime/packages` 中相应的 `.dist-info`、`licenses`、`LICENSE` 和 `NOTICE` 文件 |

依赖的确切版本和文件摘要记录在 `manifest.sha256.json`。

Codex 官方 Mac 组件包的来源和 SHA-256 记录在 `sources.lock.json` 的对应芯片条目中。

这是独立工具的测试分发包，不代表 YouTube、Google、Microsoft、OpenAI 或美联储的官方产品或认可。
# Mac 包补充说明

Mac 版使用 Astral python-build-standalone 提供的 CPython 3.12.14 可移植运行环境；保留其包内许可文件。官方项目：https://github.com/astral-sh/python-build-standalone 。

各芯片版本的 Python、Codex、Whisper 模型和 Python wheel 下载来源、版本与 SHA-256 固定在 `sources.lock.json`；以该清单及包内各组件许可为准。Intel 版使用仍提供对应 Mac wheel 的 ONNX Runtime 1.23.2，Apple 芯片版使用 1.30.0。


0.3.0 新增官方组件：Grok Build 1.0.44（Apache-2.0，.runtime/ai/grok/THIRD_PARTY_NOTICES.md）、Gemini CLI 0.61.0（Apache-2.0，.runtime/ai/gemini/LICENSE）、Node.js 24.21.0（.runtime/ai/node/LICENSE）。固定来源和校验值见 .runtime/ai/sources.lock.json。
