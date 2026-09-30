@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo @PhyrexNi · 开启显卡加速（Windows x64 / NVIDIA）
echo 首次下载约 1.1 GB，需要至少 4 GB 可用空间。
echo 仅加速本机语音识别，翻译继续使用自己的 AI 账号。
echo 请先运行 Stop.cmd 关闭翻译组件，再继续。
if not exist "%~dp0.runtime\python\python.exe" (
  echo 请先解压完整分发包；此更新包不能单独运行。
  pause
  exit /b 1
)
pause
"%~dp0.runtime\python\python.exe" -B -X utf8 "%~dp0setup_gpu.py"
if errorlevel 1 (
  echo 安装未完成，可继续使用 CPU 模式。
  pause
  exit /b 1
)
echo 安装完成。重新启动后，请确认页面显示“显卡加速”。
pause
