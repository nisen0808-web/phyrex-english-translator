# 美联储用语优化测试版 · 0.3.2-beta

美联储模式新增七组用法提示，让增长、通胀、政策立场和劳动力市场的中文表达更贴近原意。ChatGPT、Grok、Google Gemini 都会使用这些提示；每个人继续登录自己的 AI 账号。

## 本次变化

- 区分“增长放缓”和“温和增长”、“通胀放缓”和“通缩”、“招聘放缓”和“裁员”。
- 区分百分比、百分点、基点以及 by / to / from，保留原文的数字、单位、否定与不确定性。
- 区分 PCE 支出与 PCE 价格指数，区分同比、环比、年化、实际与名义口径。
- 仅按当前片段加入有限提示，保持连接预热可复用；通用英语模式不变。

保留 556 条可编辑术语、现有识别模型、连接预热与流式预览、中文朗读、每段复制和 TXT / Word / SRT 导出。不增加翻译请求次数，不改变外部版默认模型或分段设置。提示增加少量输入文本，具体额度由所选 AI 决定。本版没有新的速度提升承诺，也不包含个人版高消耗竞速或声纹实验。

## 下载与更新

**已有 0.3.0 或 0.3.1 完整版：** 下载 `PhyrexNi-0.3.2-Windows-Mac-App-Update.zip`，Windows 和两种 Mac 共用。停止组件并备份后，把全部应用文件合并到原组件目录；新增的 `fed_phrasing.py` 必须复制。保留 `user-data`、`.runtime`，重启、刷新页面并重新加载扩展。底部应显示 **0.3.2 BETA**。这个包不能独立运行，也不能用于个人本地版。

**已有 0.2.x 完整版：** 下载对应系统和芯片的 `PhyrexNi-AI-0.3.2-…-Update.zip`，按包内说明合并隐藏的 `.runtime/ai`；不要使用共用轻量包跨越 0.2.x。

**首次使用：** 下载 Windows x64、Mac Apple 芯片或 Mac Intel 完整包。Windows 使用 7z，Mac 使用 ZIP。Source code 不包含运行组件或语音模型。Mac 要求 macOS 14+，芯片必须匹配。

## 验证范围

发布门禁包含三平台原生组件、独立账号目录、本机服务、重新解压检查，以及每个平台的 27 项管线检查、12 项 AI 检查、15 项朗读检查、新增 9 项美联储用法集成检查。三种 AI 的新提示路由采用模拟输出验证，不调用真实模型。检查报告和 SHA-256 随附件发布。

同份用法模块在个人版做过 17 组订阅账号文本对照，其中 16 组清晰输入未发现语义偏差；一组含糊听写仍有歧义，应保留待核实。该样本不是所有音频准确率保证，也不能证明延迟改善。外部版新增测试核对提示、预热与三 AI 接入，不能替代真实 YouTube 长时间端到端测试。

本轮未实测真实 Grok/Google 登录、额度与模型译文，也未实测 Mac 浏览器朗读和真实 AI 延迟。Mac 尚未经过 Apple 公证，此版没有新增杀毒认证。仍为 GitHub 公开测试版，尚未上架扩展商店。

音频在本机识别，英文及相关上下文发送给所选 AI 官方服务；应用记录仅保存中文。Grok/Gemini 临时缓存清理的原有说明见 [隐私说明](https://nisen0808-web.github.io/phyrex-english-translator/privacy.html)。

[安装说明](https://github.com/nisen0808-web/phyrex-english-translator#首次使用) · [验证范围](https://github.com/nisen0808-web/phyrex-english-translator/blob/main/VERIFICATION.md) · [反馈问题](https://github.com/nisen0808-web/phyrex-english-translator/issues)
