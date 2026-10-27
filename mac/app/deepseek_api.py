"""DeepSeek text translation using an explicitly supplied, memory-only API key.

One call makes at most one request. No credentials or provider settings are
read from the environment; the engine must not auto-retry uncertain charges.
"""
import base64
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import unicodedata
from urllib import error, request

import bridge

API_URL = 'https://api.deepseek.com/chat/completions'
MODELS = ('deepseek-flash', 'deepseek-v4-pro')
DEFAULT_MODEL = MODELS[0]
TIMEOUT_SECONDS = 90
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_OUTPUT_TOKENS = 4096
JSON_EXAMPLE_INSTRUCTION = (
    '以下 JSON 仅为输出格式示例，不是待翻译内容；不要复制示例译文。'
    '请根据后续提供的实际英文内容翻译，并只返回同样结构的 JSON：\n'
    '{"chinese":"示例译文","review":false,"note":""}\n'
)

_key = None
_key_lock = threading.RLock()
_transport_slot = threading.Lock()
_CHILD_SCRIPT = Path(__file__).resolve().with_name('deepseek_transport.py')
_MAX_CHILD_INPUT = 512 * 1024
_MAX_CHILD_OUTPUT = 2 * 1024 * 1024


def set_api_key(value):
    """Replace the current key; a failed replacement also clears the old key."""
    global _key
    failure = None
    with _key_lock:
        _key = None
        if not isinstance(value, str):
            failure = '请输入自己的 DeepSeek API 密钥。'
        else:
            value = value.strip()
            if not re.fullmatch(r'sk-[A-Za-z0-9_-]{4,500}', value):
                failure = 'DeepSeek API 密钥格式无效，请检查输入。'
            else:
                _key = value
    value = None
    if failure:
        raise ValueError(failure) from None


def clear_api_key():
    """Forget the key for future requests; in-flight requests may complete."""
    global _key
    with _key_lock:
        _key = None


def has_api_key():
    """Presence is not proof of validity, permissions, or available balance."""
    with _key_lock:
        return _key is not None


class _Response(io.BytesIO):
    def __init__(self, body, status):
        super().__init__(body)
        self.status = status


def _child_environment(key):
    """Keep ordinary OS settings only; never inherit provider secrets/proxies."""
    keep = {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATH', 'TEMP', 'TMP', 'TMPDIR',
            'LANG', 'LANGUAGE', 'LC_ALL', 'LC_CTYPE', 'TZ', 'LD_LIBRARY_PATH',
            'DYLD_LIBRARY_PATH'}
    return {name: value for name, value in os.environ.items()
            if name.upper() in keep and key not in value}


def _release_after_reap(proc):
    try:
        proc.wait()
    except Exception:
        # Keep the slot closed if the operating system cannot confirm exit.
        return
    if proc.poll() is not None:
        _transport_slot.release()


def _open(req, timeout):
    """Run one official request in a reaped child with an overall deadline.

    Killing a client process does not guarantee server-side cancellation or
    prevent a charge. A second local request is refused until the first child
    is known to have exited; callers must still confirm a manual retry.
    """
    acquired = _transport_slot.acquire(blocking=False)
    if not acquired:
        req = timeout = None
        raise bridge.TranslationError('上一次 DeepSeek 请求仍在结束，请等待或重启组件；可能已产生费用。', 'billing_uncertain') from None
    proc = timer = payload = key = authorization = child_env = output = response = result = raw = status = kind = None
    outcome = None
    release_here = True
    timed_out = threading.Event()
    try:
        started = time.monotonic()
        if (req.full_url != API_URL or req.get_method() != 'POST' or
                not isinstance(req.data, bytes) or len(req.data) > _MAX_CHILD_INPUT // 2 or
                not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not 0 < timeout <= 90):
            outcome = 'configuration'
        else:
            authorization = dict((name.lower(), value) for name, value in req.header_items()).get('authorization', '')
            key = authorization.removeprefix('Bearer ') if authorization.startswith('Bearer ') else ''
            if not re.fullmatch(r'sk-[A-Za-z0-9_-]{4,500}', key):
                outcome = 'configuration'
            else:
                payload = json.dumps({'key': key, 'body': base64.b64encode(req.data).decode('ascii'),
                                      'socket_timeout': timeout}, separators=(',', ':')).encode('utf-8')
                if len(payload) > _MAX_CHILD_INPUT:
                    outcome = 'configuration'
                else:
                    child_env = _child_environment(key)
                    proc = subprocess.Popen([sys.executable, '-I', '-B', str(_CHILD_SCRIPT)],
                                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                            env=child_env, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                    remaining = max(0.001, timeout - (time.monotonic() - started))

                    def expire(child=proc):
                        timed_out.set()
                        try:
                            child.terminate()
                        except (OSError, ProcessLookupError):
                            pass

                    timer = threading.Timer(remaining, expire)
                    timer.daemon = True
                    timer.start()
                    try:
                        output, _ = proc.communicate(payload, timeout=remaining + 1.0)
                    except subprocess.TimeoutExpired:
                        timed_out.set()
                    if timed_out.is_set() or time.monotonic() - started >= timeout:
                        outcome = 'uncertain'
                    elif proc.returncode != 0 or len(output or b'') > _MAX_CHILD_OUTPUT:
                        outcome = 'uncertain'
                    else:
                        result = json.loads(output.decode('utf-8'))
                        kind, status = result.get('kind'), result.get('status')
                        if kind == 'configuration':
                            outcome = 'configuration'
                        elif kind == 'format':
                            outcome = 'format'
                        elif kind == 'status' and type(status) is int and 100 <= status <= 599:
                            response = _Response(b'', status)
                        elif kind == 'response' and status == 200:
                            raw = base64.b64decode(result.get('body', ''), validate=True)
                            if len(raw) > MAX_RESPONSE_BYTES:
                                outcome = 'format'
                            else:
                                response = _Response(raw, 200)
                        else:
                            outcome = 'uncertain'
    except (OSError, ValueError, TypeError, UnicodeError):
        outcome = 'uncertain' if proc is not None else 'configuration'
    except Exception:
        outcome = 'uncertain'
    finally:
        if timer is not None:
            timer.cancel()
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                    proc.wait(timeout=1.0)
                except (OSError, subprocess.TimeoutExpired):
                    pass
            except OSError:
                pass
            if proc.poll() is None:
                release_here = False
                threading.Thread(target=_release_after_reap, args=(proc,), daemon=True).start()
        # communicate may retain its input internally on some Python versions.
        if proc is not None and hasattr(proc, '_input'):
            proc._input = None
        req = timeout = payload = key = authorization = child_env = output = proc = timer = result = raw = status = kind = None
        if release_here:
            _transport_slot.release()
    if outcome == 'configuration':
        raise bridge.TranslationError('DeepSeek 连接组件或安全证书不可用，请检查安装包。', 'configuration') from None
    if outcome == 'format':
        raise _format_error() from None
    if outcome is not None:
        raise bridge.TranslationError('DeepSeek 请求超过等待时限或未能确认结果，可能已产生费用。请检查后手动决定是否重试。', 'billing_uncertain') from None
    return response


def _format_error():
    return bridge.TranslationError('DeepSeek 返回内容不完整或格式异常，本次请求可能已产生费用。请检查后手动决定是否重试。', 'format')


def _status_error(code):
    if code in (401, 403):
        return bridge.TranslationError('DeepSeek API 密钥或账号权限未通过，请检查后重新输入。', 'auth')
    if code in (402, 429):
        return bridge.TranslationError('DeepSeek API 余额或请求频率受限，请检查后继续。', 'quota')
    if code == 404:
        return bridge.TranslationError('DeepSeek 模型不可用，请检查账号和所选模型。', 'model')
    if code in (408, 409) or code >= 500:
        return bridge.TranslationError('DeepSeek 请求未能确认结果，可能已产生费用。请检查后手动决定是否重试。', 'billing_uncertain')
    return bridge.TranslationError('DeepSeek API 请求未完成，请检查模型与账户后手动重试。', 'api')


def _parse_message(raw):
    try:
        outer = json.loads(raw.decode('utf-8'))
        if not isinstance(outer, dict) or outer.get('object') != 'chat.completion':
            raise ValueError()
        choices = outer.get('choices')
        if not isinstance(choices, list) or len(choices) != 1:
            raise ValueError()
        choice = choices[0]
        if not isinstance(choice, dict) or choice.get('finish_reason') != 'stop':
            raise ValueError()
        message = choice.get('message')
        if not isinstance(message, dict) or message.get('role') != 'assistant' or message.get('tool_calls') or message.get('refusal'):
            raise ValueError()
        text = message.get('content')
        if not isinstance(text, str):
            raise ValueError()
        text = text.strip()
        if text.startswith('```'):
            text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text, flags=re.I)
        result = json.loads(text)
        if not isinstance(result, dict) or set(result) != {'chinese', 'review', 'note'}:
            raise ValueError()
        # Reject only the standalone example, regardless of presentation or metadata.
        chinese = result['chinese']
        normalized = ''.join(char for char in unicodedata.normalize('NFKC', chinese)
                             if not char.isspace() and not unicodedata.category(char).startswith('P')
                             and unicodedata.category(char) != 'Cf') if isinstance(chinese, str) else ''
        if normalized == '示例译文':
            raise ValueError()
        # reasoning_content is not read, logged, persisted, or exposed.
        return bridge.validate_result(result)
    except (ValueError, TypeError, AttributeError, UnicodeError):
        raise _format_error() from None


def translate(source, context, glossary, model=DEFAULT_MODEL, profile='fed'):
    """Return validated Chinese text and latency without implicit retries."""
    with _key_lock:
        key = _key
    outcome = None
    result = None
    elapsed = 0.0
    prompt = body = headers = req = raw = response = None
    attempted = False
    try:
        if model not in MODELS:
            outcome = ('model', None)
        elif key is None:
            outcome = ('auth', None)
        else:
            prompt = JSON_EXAMPLE_INSTRUCTION + bridge.translation_prompt(source, context, glossary, profile)
            if key in prompt:
                outcome = ('preflight', None)
            else:
                body = json.dumps({'model': model, 'max_tokens': MAX_OUTPUT_TOKENS,
                                   'messages': [{'role': 'user', 'content': prompt}],
                                   'response_format': {'type': 'json_object'}, 'stream': False},
                                  ensure_ascii=False).encode('utf-8')
                headers = {'authorization': 'Bearer ' + key,
                           'content-type': 'application/json', 'accept': 'application/json'}
                req = request.Request(API_URL, data=body, method='POST', headers=headers)
                started = time.monotonic()
                attempted = True
                with _open(req, TIMEOUT_SECONDS) as response:
                    if type(response.status) is not int or not 100 <= response.status <= 599:
                        outcome = ('uncertain', None)
                    elif response.status != 200:
                        outcome = ('status', response.status)
                    else:
                        raw = response.read(MAX_RESPONSE_BYTES + 1)
                if outcome is None:
                    if len(raw) > MAX_RESPONSE_BYTES:
                        outcome = ('format', None)
                    else:
                        result = _parse_message(raw)
                        if key in result['chinese'] or key in result['note']:
                            outcome = ('format', None)
                            result = None
                        else:
                            elapsed = round(time.monotonic() - started, 2)
    except error.HTTPError as exc:
        code = exc.code
        try:
            exc.close()
        except Exception:
            pass
        outcome = ('status', code) if type(code) is int and 100 <= code <= 599 else ('uncertain', None)
        code = None
    except bridge.TranslationError as exc:
        outcome = (exc.kind if exc.kind in ('configuration', 'billing_uncertain') else 'format', None)
    except Exception:
        outcome = ('uncertain' if attempted else 'request', None)
    finally:
        key = prompt = body = headers = req = raw = response = None
        source = context = glossary = model = profile = None
    if outcome is not None:
        kind, status = outcome
        if kind == 'status':
            raise _status_error(status) from None
        if kind == 'model':
            raise bridge.TranslationError('请选择 DeepSeek 支持的翻译模式。', 'model') from None
        if kind == 'auth':
            raise bridge.TranslationError('请先输入自己的 DeepSeek API 密钥。', 'auth') from None
        if kind == 'preflight':
            raise bridge.TranslationError('翻译资料中包含 API 密钥，已停止发送。', 'format') from None
        if kind == 'configuration':
            raise bridge.TranslationError('DeepSeek 安全证书组件不可用，请重新解压完整安装包。', 'configuration') from None
        if kind == 'format':
            raise _format_error() from None
        if kind in ('uncertain', 'billing_uncertain'):
            raise bridge.TranslationError('DeepSeek 请求未能确认结果，可能已产生费用。请检查后手动决定是否重试。', 'billing_uncertain') from None
        raise bridge.TranslationError('DeepSeek 翻译资料或设置无效，未发送请求。', 'api') from None
    return result, elapsed
