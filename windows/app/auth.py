"""Local, user-triggered official Codex login. Never expose or log credentials."""
import re
import subprocess
import threading
from urllib.parse import urlparse
from bridge import NO_WINDOW, environment, login_status
from runtime import codex_path

class LoginManager:
    def __init__(self):
        self.lock = threading.RLock()
        self.process = None
        self.result = {'running': False, 'message': '', 'url': ''}

    def state(self):
        with self.lock:
            return dict(self.result)

    def start(self):
        with self.lock:
            if self.result['running']:
                return dict(self.result)
            try:
                self.process = subprocess.Popen([codex_path(), 'login'], stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                    encoding='utf-8', errors='replace', env=environment(), creationflags=NO_WINDOW)
            except (OSError, RuntimeError):
                raise ValueError('无法启动官方登录，请重新解压完整安装包或检查 Codex 安装。') from None
            self.result = {'running': True, 'message': '请在浏览器的 OpenAI 官方页面登录自己的 ChatGPT。', 'url': ''}
            threading.Thread(target=self._read, args=(self.process,), daemon=True).start()
            threading.Thread(target=self._timeout, args=(self.process,), daemon=True).start()
            return dict(self.result)

    def _read(self, process):
        try:
            for line in process.stdout:
                # Only an official authorization link may reach the local UI.
                for url in re.findall(r'https://[^\s\x1b]+', line):
                    parsed = urlparse(url)
                    if parsed.hostname in {'auth.openai.com', 'auth.chatgpt.com', 'chatgpt.com'} and not parsed.username:
                        with self.lock:
                            if self.process is process:
                                self.result['url'] = url
            process.wait()
            status = login_status()
            with self.lock:
                if self.process is process:
                    self.result = {'running': False, 'message': status['message'] if status['ready'] else '登录未完成，请重新点击登录。', 'url': ''}
        finally:
            if process.stdout:
                process.stdout.close()
            with self.lock:
                if self.process is process:
                    self.result['running'] = False

    def _timeout(self, process):
        try:
            process.wait(timeout=300)
        except subprocess.TimeoutExpired:
            with self.lock:
                if self.process is process and process.poll() is None:
                    process.terminate()

    def cancel(self):
        with self.lock:
            if self.process and self.process.poll() is None:
                self.process.terminate()
