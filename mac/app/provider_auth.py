"""User-triggered provider sign-in; only official authorization URLs reach the UI."""
import json
import re
import subprocess
import threading
from urllib.parse import urlparse

from auth import LoginManager as ChatGPTLogin
from providers import (PROVIDERS, LOCKS, NO_WINDOW, cli, environment, home,
                       login_status, mark_login, validate_provider)


def official_login_url(provider, url):
    allowed = {'grok': {'auth.x.ai', 'accounts.x.ai', 'grok.com'}, 'gemini': {'accounts.google.com'}}
    parsed = urlparse(url)
    return parsed.scheme == 'https' and parsed.hostname in allowed.get(provider, set()) and not parsed.username and not parsed.password and parsed.port in (None, 443)


class LoginManager:
    def __init__(self):
        self.chatgpt = ChatGPTLogin()
        self.lock = threading.RLock()
        self.provider = 'chatgpt'
        self.process = None
        self.result = {'running': False, 'message': '', 'url': ''}

    def state(self):
        with self.lock:
            value = self.chatgpt.state() if self.provider == 'chatgpt' else dict(self.result)
            return dict(value, provider=self.provider)

    def select(self, provider):
        validate_provider(provider)
        with self.lock:
            if provider == self.provider:
                return
            if provider != self.provider and self.state()['running']:
                raise ValueError('请先完成当前 AI 的登录，再切换。')
            self.provider = provider
            self.result = {'running': False, 'message': '', 'url': ''}

    def start(self, provider='chatgpt'):
        validate_provider(provider)
        with self.lock:
            if self.state()['running']:
                if self.provider != provider:
                    raise ValueError('另一个 AI 正在登录，请先完成登录。')
                return self.state()
            self.provider = provider
            if provider == 'chatgpt':
                return self.chatgpt.start()
            command = cli(provider)
            env = environment(provider, login=True)
            if provider == 'grok':
                command += ['login', '--oauth']
            else:
                command += ['--acp']
            try:
                process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace',
                    env=env, cwd=home(provider) / 'work', creationflags=NO_WINDOW)
            except OSError:
                raise ValueError('无法启动官方登录组件，请重新解压完整包。') from None
            self.process = process
            self.result = {'running': True, 'message': '请在官方页面登录自己的 ' + PROVIDERS[provider]['label'] + ' 账号。', 'url': ''}
            mark_login(provider, False)
            threading.Thread(target=self._urls, args=(process, provider), daemon=True).start()
            threading.Thread(target=self._read, args=(process, provider), daemon=True).start()
            threading.Thread(target=self._timeout, args=(process,), daemon=True).start()
            return self.state()

    def _find_url(self, process, provider, line):
        for url in re.findall(r'https://[^\s\x1b<>"\x27]+', line):
            try:
                allowed = official_login_url(provider, url)
            except ValueError:
                allowed = False
            if allowed:
                with self.lock:
                    if self.process is process:
                        self.result['url'] = url

    def _urls(self, process, provider):
        try:
            for line in process.stderr:
                self._find_url(process, provider, line)
        finally:
            process.stderr.close()

    @staticmethod
    def _send(process, identity, method, params):
        process.stdin.write(json.dumps({'jsonrpc': '2.0', 'id': identity, 'method': method, 'params': params}) + '\n')
        process.stdin.flush()

    def _read(self, process, provider):
        authenticated = False
        try:
            if provider == 'gemini':
                self._send(process, 1, 'initialize', {'protocolVersion': 1, 'clientCapabilities': {}, 'clientInfo': {'name': 'phyrex-translator', 'version': '0.3.0'}})
            for line in process.stdout:
                self._find_url(process, provider, line)
                if provider != 'gemini':
                    continue
                try:
                    message = json.loads(line)
                except ValueError:
                    continue
                if message.get('id') == 1:
                    methods = message.get('result', {}).get('authMethods', [])
                    if not any(item.get('id') == 'oauth-personal' for item in methods):
                        break
                    self._send(process, 2, 'authenticate', {'methodId': 'oauth-personal'})
                elif message.get('id') == 2:
                    authenticated = 'result' in message and 'error' not in message
                    break
                elif 'method' in message and 'id' in message:
                    # Login never grants model tools, local files or terminal access.
                    process.stdin.write(json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'error': {'code': -32601, 'message': 'Unsupported method'}}) + '\n')
                    process.stdin.flush()
            if provider == 'grok':
                authenticated = process.wait() == 0
        except (OSError, ValueError, TypeError):
            authenticated = False
        finally:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait()
            process.stdout.close()
            process.stdin.close()
            with self.lock:
                if self.process is process:
                    mark_login(provider, authenticated)
                    self.result = {'running': False, 'url': '', 'message': '登录已完成，可开始翻译。' if authenticated else '登录未完成或账号权限不足，请重新登录。'}

    def _timeout(self, process):
        try:
            process.wait(timeout=300)
        except subprocess.TimeoutExpired:
            with self.lock:
                if self.process is process and process.poll() is None:
                    process.terminate()

    def cancel(self):
        self.chatgpt.cancel()
        with self.lock:
            if self.process and self.process.poll() is None:
                self.process.terminate()
