"""Explicit, account-isolated provider routing through official local CLIs."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time

import bridge
from runtime import ROOT, USER_DIR

TranslationError = bridge.TranslationError
NO_WINDOW = bridge.NO_WINDOW
PROVIDERS = {
    'chatgpt': {'label': 'ChatGPT', 'models': {'gpt-6-luna': '快速 · 日常跟看', 'gpt-6-sol': '精细 · 更高额度消耗'}, 'login_label': '登录自己的 ChatGPT', 'notice': '通过官方 Codex 使用自己的 ChatGPT 账号；可用模型及额度以账号为准。'},
    'grok': {'label': 'Grok', 'models': {'auto': '自动 · 使用账号默认模型'}, 'login_label': '登录自己的 Grok', 'notice': '通过官方 Grok Build 使用自己的 Grok 账号；账号需要具有 Grok Build 使用权限。'},
    'gemini': {'label': 'Google Gemini', 'models': {'auto': '自动 · 使用账号可用模型'}, 'login_label': '登录自己的 Google 账号', 'notice': '通过官方 Gemini CLI 使用自己的 Google 账号；部分公司或学校账号需要额外配置，建议先用个人账号。'},
}
LOCKS = {name: threading.RLock() for name in PROVIDERS}


def validate_provider(provider):
    if provider not in PROVIDERS:
        raise ValueError('请选择 ChatGPT、Grok 或 Google Gemini。')
    return provider


def validate_model(provider, model):
    validate_provider(provider)
    if model not in PROVIDERS[provider]['models']:
        raise ValueError('请选择当前 AI 支持的翻译模式。')
    return model


def home(provider):
    validate_provider(provider)
    return USER_DIR / 'providers' / provider


def cli(provider):
    validate_provider(provider)
    if provider == 'chatgpt':
        return [bridge.codex_path()]
    ai = ROOT / '.runtime' / 'ai'
    if provider == 'grok':
        command = [ai / 'grok' / ('grok.exe' if os.name == 'nt' else 'grok')]
    else:
        command = [ai / 'node' / ('node.exe' if os.name == 'nt' else 'bin/node'), ai / 'gemini/bundle/gemini.js']
    if not all(p.is_file() for p in command):
        raise ValueError('此 AI 的本机组件不完整，请下载 0.3.0 或更新的完整包。')
    return [str(p) for p in command]


def mark_login(provider, ready):
    folder = home(provider)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / 'login-state.json'
    temporary = folder / 'login-state.tmp'
    temporary.write_text(json.dumps({'ready': bool(ready)}), encoding='utf-8')
    os.replace(temporary, target)


def login_status(provider='chatgpt'):
    validate_provider(provider)
    if provider == 'chatgpt':
        return bridge.login_status()
    try:
        cli(provider)
    except ValueError as exc:
        return {'ready': False, 'message': str(exc), 'installed': False}
    try:
        ready = json.loads((home(provider) / 'login-state.json').read_text(encoding='utf-8')).get('ready') is True
    except (OSError, ValueError, AttributeError):
        ready = False
    label = PROVIDERS[provider]['label']
    return {'ready': ready, 'installed': True, 'message': label + (' 登录已完成；翻译时检查账号权限及额度。' if ready else ' 尚未登录，请登录自己的账号。')}


def environment(provider, login=False):
    validate_provider(provider)
    if provider == 'chatgpt':
        return bridge.environment()
    folder = home(provider)
    folder.mkdir(parents=True, exist_ok=True)
    # No inherited provider credentials, routing, agent hooks or Node injection.
    keep = {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATH', 'PATHEXT', 'TEMP', 'TMP', 'LANG', 'LC_ALL',
            'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY', 'SSL_CERT_FILE', 'SSL_CERT_DIR',
            'DISPLAY', 'WAYLAND_DISPLAY', 'XDG_RUNTIME_DIR', 'DBUS_SESSION_BUS_ADDRESS'}
    env = {key: value for key, value in os.environ.items() if key.upper() in keep}
    env.update(HOME=str(folder), USERPROFILE=str(folder), PYTHONIOENCODING='utf-8', NO_COLOR='1',
               OTEL_SDK_DISABLED='true', DO_NOT_TRACK='1')
    work = folder / 'work'; work.mkdir(exist_ok=True)
    if provider == 'grok':
        state = folder / '.grok'; state.mkdir(exist_ok=True)
        env.update(GROK_HOME=str(state), GROK_DISABLE_AUTOUPDATER='1', GROK_WEB_FETCH='0', GROK_MEMORY='0',
                   GROK_SUBAGENTS='0', GROK_WRITE_FILE='0', GROK_TOOL_SEARCH='0', GROK_CRASH_HANDLER='0', GROK_AGENT_DASHBOARD='0')
        for family in ('CURSOR', 'CLAUDE'):
            for feature in ('SKILLS', 'RULES', 'AGENTS', 'MCPS', 'HOOKS'):
                env[f'GROK_{family}_{feature}_ENABLED'] = '0'
        (state / 'config.toml').write_text('[cli]\nauto_update = false\n[session]\nload_envrc = false\n[ui]\npermission_mode = "dontAsk"\n[permission]\nrules = [{ action = "deny", tool = "*" }]\n', encoding='utf-8')
    else:
        state = folder / '.gemini'; state.mkdir(exist_ok=True)
        env.update(GEMINI_CLI_HOME=str(folder), GEMINI_CLI_NO_RELAUNCH='1', GEMINI_CLI_SURFACE='phyrex-english-translator')
        if not login:
            env['NO_BROWSER'] = '1'
        settings = {'security': {'auth': {'selectedType': 'oauth-personal'}, 'disableYoloMode': True},
                    'tools': {'core': [], 'exclude': ['*']}, 'mcpServers': {}, 'mcp': {'allowed': []},
                    'telemetry': {'enabled': False, 'logPrompts': False}, 'usageStatisticsEnabled': False,
                    'advanced': {'ignoreLocalEnv': True, 'autoConfigureMemory': False},
                    'general': {'enableAutoUpdate': False}, 'model': {'maxSessionTurns': 1}, 'hooksConfig': {'enabled': False},
                    'experimental': {'enableAgents': False}, 'context': {'fileName': []}}
        if login:
            # ACP authenticate explicitly starts OAuth after initialize; do not
            # run headless authentication before the client can speak ACP.
            settings['security']['auth'] = {'useExternal': True}
        (state / 'settings.json').write_text(json.dumps(settings), encoding='utf-8')
        (state / 'deny-tools.toml').write_text('[[rule]]\ntoolName = "*"\ndecision = "deny"\npriority = 999\n', encoding='utf-8')
    return env


def clear_transient_history(provider):
    """Only remove generated caches inside this application's own provider home."""
    if provider == 'chatgpt':
        return
    base = home(provider).resolve()
    names = ('.gemini/tmp', '.gemini/history') if provider == 'gemini' else ('.grok/sessions', '.grok/logs', '.grok/history', '.grok/history.txt', '.grok/crash')
    for name in names:
        target = base / name
        if not target.exists() and not target.is_symlink():
            continue
        if not target.resolve().is_relative_to(base) or target.is_symlink():
            raise TranslationError('AI 临时目录异常，已停止处理，请重新解压完整包。', 'storage')
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()


def error(raw, provider):
    kind = bridge.failure_kind(raw)
    label = PROVIDERS[provider]['label']
    text = raw.lower()
    if kind != 'quota' and any(s in text for s in ('not authenticated', 'not logged in', 'sign in', 'oauth', 'credential', 'invalid_grant')):
        kind = 'auth'
    if kind == 'quota':
        message = label + ' 额度或请求频率受限，请稍后重试；不会自动切换其他 AI。'
    elif kind == 'auth':
        mark_login(provider, False)
        message = label + ' 登录或账号权限需要重新确认，请重新登录。'
    elif kind == 'model':
        message = label + ' 当前账号不能使用所选模型，请检查账号权限。'
    else:
        message = label + ' 翻译未完成，请检查网络后重试。'
    return TranslationError(message, kind)


def unwrap_result(raw):
    text = raw.strip()
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text, flags=re.I)
    try:
        value = json.loads(text)
        for _ in range(3):
            if isinstance(value, dict) and 'chinese' in value:
                return bridge.validate_result(value)
            if isinstance(value, dict):
                value = next((value[key] for key in ('structured_output', 'response', 'result') if key in value), None)
            elif isinstance(value, str):
                value = json.loads(re.sub(r'^```(?:json)?\s*|\s*```$', '', value.strip(), flags=re.I))
            else:
                break
    except (ValueError, TypeError, AttributeError):
        pass
    raise TranslationError('AI 返回的译文格式异常，已阻止保存，请重试该段。', 'format')


def translate(source, context, glossary, model=None, profile='fed', provider='chatgpt'):
    validate_provider(provider)
    model = model or next(iter(PROVIDERS[provider]['models']))
    validate_model(provider, model)
    if provider == 'chatgpt':
        return bridge.translate(source, context, glossary, model, profile)
    status = login_status(provider)
    if not status['ready']:
        raise TranslationError(status['message'], 'auth')
    with LOCKS[provider]:
        env = environment(provider)
        clear_transient_history(provider)
        prompt = bridge.translation_prompt(source, context, glossary, profile)
        command = cli(provider)
        if provider == 'grok':
            command += ['-p', prompt, '--output-format', 'plain', '--tools', '', '--deny', '*',
                        '--permission-mode', 'dontAsk', '--no-plan', '--no-subagents', '--disable-web-search',
                        '--max-turns', '1', '--verbatim']
            input_text = None
        else:
            command += ['-p', '按输入要求翻译，仅返回 JSON。', '--output-format', 'json',
                        '--policy', str(home(provider) / '.gemini/deny-tools.toml'), '--extensions', 'none']
            input_text = prompt
        started = time.monotonic()
        try:
            proc = subprocess.run(command, input=input_text, stdin=None if input_text is not None else subprocess.DEVNULL,
                                  capture_output=True, text=True, encoding='utf-8', errors='replace',
                                  env=env, cwd=home(provider) / 'work', timeout=90, creationflags=NO_WINDOW)
            if proc.returncode:
                raise error(proc.stderr + proc.stdout, provider)
            return unwrap_result(proc.stdout), round(time.monotonic() - started, 2)
        except subprocess.TimeoutExpired:
            raise TranslationError(PROVIDERS[provider]['label'] + ' 翻译等待超过 90 秒，请检查网络后继续处理。') from None
        finally:
            clear_transient_history(provider)
