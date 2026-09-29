# @PhyrexNi · 英语直播译文 Mac 测试版

macOS 14 或更新版本，Chrome / Edge。下载 Apple 芯片版（M 系列，arm64）或 Intel 版（x86_64）；可在苹果菜单“关于本机”查看芯片。

## 首次安装

1. 双击 ZIP 完整解压，把整个文件夹放到你个人的“应用程序”文件夹等固定位置。不要单独移动内部文件。
2. 双击 `Install-Connector.command`。它仅为当前用户注册 Chrome / Edge 的本机连接，不需要管理员密码。
3. Chrome 地址栏输入 `chrome://extensions`，或 Edge 输入 `edge://extensions`；开启开发者模式，加载本目录的 `extension` 文件夹。
4. 打开扩展侧栏，登录自己的、支持 Codex 的 ChatGPT 账号。
5. 播放英语视频，选择播放标签页并勾选共享标签页音频。仅支持英语转中文。

如果侧栏无法采集声音，点“完整页面”，或者双击 `Start.command`，在 Chrome / Edge 的完整页面里操作。Safari 不在本测试版支持范围内。若 macOS 要求屏幕或音频录制权限，请由你在系统设置中允许正在使用的浏览器，然后按系统提示重启浏览器。

这是尚未经过 Apple 公证的公开测试版。首次打开可能出现开发者验证提示；只在核对来源和文件校验值后，按 [Apple 的官方说明](https://support.apple.com/102445)决定是否允许该项目。不要关闭 Gatekeeper 或系统防护。运行检查不等于已经验证所有 Mac 上的系统授权流程。

## 日常使用

内置 556 条美联储、宏观、金融和劳动力市场术语；支持通用英语场景。每段有独立复制图标，“待核实”段落也可以复制译文，但不会复制核实说明。中文自动保存，可导出 TXT、Word、SRT。

结束时先点击页面里的“结束采集并保存”，等待队列完成；暂时不用可双击 `Stop.command`。关闭采集页面会停止继续采集。

记录与自定义术语在 `user-data`，登录凭据在 `user-data/account`。工具不持久保存原始音频和英文逐字稿，但识别后的英文及上下文会发送给 OpenAI 翻译，适用你的账号设置和额度。不要转发使用后的文件夹；请分享 GitHub 原始 ZIP。

## 卸载和升级

先停止翻译并运行 `Stop.command`，再运行 `Uninstall-Connector.command`，最后在浏览器中移除扩展。卸载脚本保留你的账号和中文记录。

升级时使用新的干净文件夹，停止旧版后复制自己的 `user-data` 到新版，再运行新版安装脚本并重新加载扩展。移动文件夹后也需要重新安装连接。

这是完整运行包，不需要另装 Python、Homebrew 或购买 API。没有自动更新、开机自启或系统防护绕过操作。

测试反馈：https://github.com/nisen0808-web/phyrex-english-translator/issues
