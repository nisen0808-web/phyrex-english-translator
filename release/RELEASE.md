# 中文朗读公开测试版 · 0.2.5-beta

新增可选中文朗读，Windows、Apple 芯片 Mac 和 Intel Mac 完整包均已包含。

- 开始采集前勾选“中文朗读 · 朗读时屏蔽英文”，选择本机中文声音并试听。
- 中文朗读时屏蔽英文外放，读完或暂停朗读后恢复；识别用的英文音轨继续采集。
- 只读本次直播的新中文正文，不读时间戳和“待核实”说明，不重读历史记录。
- 支持语速、声音选择、暂停和跳过。积压过多会跳过较早的朗读，中文文字记录仍保留。
- 使用本机中文语音，不增加配音 API 或 Codex 请求。没有系统中文声音时，文字翻译照常可用。

请保持 YouTube 播放器音量开启，并共享**标签页音频**。若浏览器不能确认英文外放已受控，工具会提示重新选择或关闭朗读，避免双重声音。中文有识别、翻译和朗读延迟，并非零延迟同传。

## 下载选择

首次安装请选择完整包：Windows 为 `Windows-x64-Compact.7z`，Mac 根据芯片选择 `macOS-arm64.zip` 或 `macOS-x86_64.zip`。GitHub 的 Source code 不包含运行组件和语音模型。

已安装 Windows 0.2.2-beta / Mac 0.2.3-mac-beta 的用户可以下载对应的 `Read-Aloud-0.2.5-…-Update.zip`。更新包仅约 20 KB，不能单独运行。结束采集并关闭页面，备份原 `web` 文件夹和 `PRIVACY.md`，再按包内说明替换。账号、记录和语音模型不变；后台版本号仍显示原版本。

使用新版完整包升级时，请先停止旧组件。需要迁移的用户可自行复制旧目录的 `user-data` 到新版目录，再注册新版本机组件并重新加载新版扩展。请勿把含个人数据的目录转发给别人。

## 验证范围

发布流程仅在三个系统包完成组件、账号隔离、页面服务与重新解压运行检查后发布；朗读队列、重复过滤、异常恢复和英文外放控制另有 13 项自动检查，结果和 SHA-256 随附件提供。

Windows 浏览器中已完成本机中文试听及真实 Web Audio / AudioWorklet 的外放与识别通道分离检查。自动检查不等于所有用户电脑都能正常朗读：Mac 实机浏览器中文声音、真实 YouTube 音频共享、长时间直播和物理扬声器效果仍需公开测试。

Mac 包尚未经过 Apple 公证。历史版本的 Windows 病毒扫描记录不构成本次新版或 Mac 包的杀毒认证。

此版翻译仍使用用户自己的 ChatGPT / Codex；Grok 接入尚未发布。扩展仍处于 GitHub 公开测试阶段，尚未上架 Chrome 商店。

[安装说明](https://github.com/nisen0808-web/phyrex-english-translator#首次使用) · [朗读说明](https://github.com/nisen0808-web/phyrex-english-translator/blob/main/READ_ALOUD.md) · [反馈问题](https://github.com/nisen0808-web/phyrex-english-translator/issues)
