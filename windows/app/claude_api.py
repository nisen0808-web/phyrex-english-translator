"""Optional Claude Messages API translation, with an explicitly supplied memory-only key.

No subscription credentials, environment API keys, background checks or automatic
retries are used. One call sends one Messages request to Anthropic's fixed HTTPS
endpoint. The caller is responsible for collecting informed consent before use.
"""
import json
import re
import ssl
import threading
import time
from urllib import error, request

import bridge

API_URL = 'https://api.anthropic.com/v1/messages'
API_VERSION = '2023-06-01'
MODELS = ('claude-sonnet-5-5', 'claude-haiku-5-5')
DEFAULT_MODEL = MODELS[0]
TIMEOUT_SECONDS = 90
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_OUTPUT_TOKENS = 4096

_key = None
_workspace_id = None
_key_lock = threading.RLock()


def set_api_key(value, workspace_id=''):
    """Keep an explicitly entered API key only in this process; never return it.

    Keys are not confirmed until the user starts a translation. A cleared or
    replaced key already captured by an in-flight request may complete; the UI
    should disallow credential changes while translations are pending.
    """
    global _key, _workspace_id
    failure = None
    with _key_lock:
        # A failed replacement must never silently leave the previous billing
        # account selected after the user attempted to change credentials.
        _key = None
        _workspace_id = None
        if not isinstance(value, str):
            failure = '请输入 Anthropic Console API 密钥。'
        else:
            value = value.strip()
            if not re.fullmatch(r'sk-ant-api[A-Za-z0-9_-]{4,500}', value):
                failure = 'API 密钥格式无效，请检查输入。'
            elif not isinstance(workspace_id, str):
                failure = '工作区 ID 格式无效，请检查输入。'
            else:
                workspace_id = workspace_id.strip()
                if workspace_id and not re.fullmatch(r'wrkspc_[A-Za-z0-9]{8,100}', workspace_id):
                    failure = '工作区 ID 格式无效，请检查输入。'
                else:
                    _key = value
                    _workspace_id = workspace_id or None
    value = workspace_id = None
    if failure:
        raise ValueError(failure) from None


def clear_api_key():
    """Forget the key for future requests; do not attempt network calls."""
    global _key, _workspace_id
    with _key_lock:
        _key = None
        _workspace_id = None


def has_api_key():
    """A key is present, not proof of valid credentials, access, or balance."""
    with _key_lock:
        return _key is not None


class _DenyRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _open(req, timeout):
    # A dedicated opener avoids implicit proxy settings from the environment,
    # default opener customization, and cross-domain credential redirects.
    context = None
    configuration_failed = False
    try:
        import certifi
        # create_default_context() reads SSLKEYLOGFILE. Construct a client
        # context explicitly so inherited debugging settings cannot create a
        # TLS key log, while retaining certificate and hostname verification.
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cafile=certifi.where())
    except Exception:
        configuration_failed = True
    if configuration_failed:
        req = timeout = context = None
        raise bridge.TranslationError('Claude 安全证书组件不可用，请重新解压完整安装包。', 'configuration') from None
    opener = request.build_opener(request.ProxyHandler({}), _DenyRedirect(),
                                  request.HTTPSHandler(context=context))
    return opener.open(req, timeout=timeout)


def _format_error():
    return bridge.TranslationError('Claude 返回内容不完整或格式异常，本次请求可能已产生费用。请检查后手动决定是否重试。', 'format')


def _status_error(code):
    if code in (401, 403):
        return bridge.TranslationError('Claude API 密钥或账号权限未通过，请检查后重新输入。', 'auth')
    if code in (402, 429):
        return bridge.TranslationError('Claude API 账单、额度或请求频率受限，请检查后继续。', 'quota')
    if code == 404:
        return bridge.TranslationError('Claude 模型不可用，请检查账号和所选模型。', 'model')
    if code in (408, 409) or code >= 500:
        return bridge.TranslationError('Claude 请求未能确认结果，可能已产生费用。请检查后手动决定是否重试。', 'billing_uncertain')
    return bridge.TranslationError('Claude API 请求未完成，请检查模型、工作区 ID 和额度后手动重试。', 'api')


def _parse_message(raw):
    try:
        outer = json.loads(raw.decode('utf-8'))
        if (not isinstance(outer, dict) or outer.get('type') != 'message'
                or outer.get('role') != 'assistant' or outer.get('stop_reason') != 'end_turn'):
            raise ValueError()
        details = outer.get('stop_details')
        if isinstance(details, dict) and details.get('type') == 'refusal':
            raise ValueError()
        blocks = outer.get('content')
        if not isinstance(blocks, list) or not blocks:
            raise ValueError()
        pieces = []
        for block in blocks:
            if not isinstance(block, dict):
                raise ValueError()
            kind = block.get('type')
            if kind == 'text' and isinstance(block.get('text'), str):
                pieces.append(block['text'])
            elif kind not in ('thinking', 'redacted_thinking'):
                # No tools are requested. Unexpected output is not a translation.
                raise ValueError()
        if not pieces:
            raise ValueError()
        # Model thinking is discarded in memory and never saved or returned.
        text = ''.join(pieces).strip()
        if text.startswith('```'):
            text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text, flags=re.I)
        result = json.loads(text)
        if not isinstance(result, dict) or set(result) != {'chinese', 'review', 'note'}:
            raise ValueError()
        return bridge.validate_result(result)
    except (ValueError, TypeError, AttributeError, UnicodeError):
        raise _format_error() from None


def translate(source, context, glossary, model=DEFAULT_MODEL, profile='fed'):
    """Return (validated Chinese result, elapsed seconds); never retry or log.

    Provider routing must treat ``billing_uncertain`` as non-retryable. API errors
    and response bodies are deliberately omitted from exceptions and state.
    """
    with _key_lock:
        key = _key
        workspace_id = _workspace_id
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
            prompt = bridge.translation_prompt(source, context, glossary, profile)
            if key in prompt or (workspace_id and workspace_id in prompt):
                outcome = ('preflight', None)
            else:
                body = json.dumps({'model': model, 'max_tokens': MAX_OUTPUT_TOKENS,
                                   'messages': [{'role': 'user', 'content': prompt}]},
                                  ensure_ascii=False).encode('utf-8')
                headers = {'x-api-key': key, 'anthropic-version': API_VERSION,
                           'content-type': 'application/json', 'accept': 'application/json'}
                if workspace_id:
                    headers['anthropic-workspace-id'] = workspace_id
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
                        if any(secret and (secret in result['chinese'] or secret in result['note'])
                               for secret in (key, workspace_id)):
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
        # Never propagate an inner exception/traceback that can retain a request.
        outcome = ('configuration' if exc.kind == 'configuration' else 'format', None)
    except Exception:
        outcome = ('uncertain' if attempted else 'request', None)
    finally:
        # Diagnostic traceback capture may include frame locals. Clear every
        # reference to credentials, request objects and raw response content
        # before an error escapes this frame. This cannot protect process memory
        # from a different program with sufficient local access.
        key = workspace_id = prompt = body = headers = req = raw = response = None
        source = context = glossary = model = profile = None
    if outcome is not None:
        kind, status = outcome
        if kind == 'status':
            raise _status_error(status) from None
        if kind == 'model':
            raise bridge.TranslationError('请选择 Claude 支持的翻译模式。', 'model') from None
        if kind == 'auth':
            raise bridge.TranslationError('请先输入自己的 Anthropic Console API 密钥。', 'auth') from None
        if kind == 'preflight':
            raise bridge.TranslationError('翻译资料中包含 API 密钥或工作区 ID，已停止发送。', 'format') from None
        if kind == 'configuration':
            raise bridge.TranslationError('Claude 安全证书组件不可用，请重新解压完整安装包。', 'configuration') from None
        if kind == 'format':
            raise _format_error() from None
        if kind == 'uncertain':
            raise bridge.TranslationError('Claude 请求未能确认结果，可能已产生费用。请检查后手动决定是否重试。', 'billing_uncertain') from None
        raise bridge.TranslationError('Claude 翻译资料或设置无效，未发送请求。', 'api') from None
    return result, elapsed
