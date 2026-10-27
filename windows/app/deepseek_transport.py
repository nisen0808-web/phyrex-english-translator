"""Isolated single-request DeepSeek transport; credentials arrive over stdin only.

This process never writes request text, credentials or remote response bodies to
disk or stderr.  Its parent enforces the whole-request deadline and reaps it.
"""
import base64
import json
from pathlib import Path
import ssl
import sys
from urllib import error, request

API_URL = 'https://api.deepseek.com/chat/completions'
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_INPUT_BYTES = 512 * 1024

# -I keeps the working directory and caller's PYTHONPATH out of imports.  The
# bundled CA package is part of this app, not an inherited user environment.
sys.path.insert(0, str(Path(__file__).resolve().parent / '.runtime' / 'packages'))


class _DenyRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _open(req, timeout):
    import certifi
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_verify_locations(cafile=certifi.where())
    opener = request.build_opener(request.ProxyHandler({}), _DenyRedirect(),
                                  request.HTTPSHandler(context=context))
    return opener.open(req, timeout=timeout)


def _exchange(key, body, timeout):
    req = response = raw = None
    try:
        req = request.Request(API_URL, data=body, method='POST', headers={
            'authorization': 'Bearer ' + key,
            'content-type': 'application/json', 'accept': 'application/json'})
        try:
            with _open(req, timeout) as response:
                status = response.status
                if type(status) is not int or not 100 <= status <= 599:
                    return {'kind': 'uncertain'}
                if status != 200:
                    return {'kind': 'status', 'status': status}
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    return {'kind': 'format'}
                return {'kind': 'response', 'status': status,
                        'body': base64.b64encode(raw).decode('ascii')}
        except error.HTTPError as exc:
            status = exc.code
            try:
                exc.close()
            except Exception:
                pass
            return {'kind': 'status', 'status': status} if type(status) is int and 100 <= status <= 599 else {'kind': 'uncertain'}
        except (ImportError, ModuleNotFoundError, ssl.SSLError):
            # SSL negotiation failures might occur after a request is accepted;
            # the conservative billing-uncertain result is handled by parent.
            return {'kind': 'uncertain'}
        except Exception:
            return {'kind': 'uncertain'}
    finally:
        key = body = req = response = raw = None


def main():
    key = body = payload = result = None
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            result = {'kind': 'configuration'}
        else:
            payload = json.loads(raw.decode('utf-8'))
            key = payload.get('key')
            body = base64.b64decode(payload.get('body', ''), validate=True)
            timeout = payload.get('socket_timeout')
            if (not isinstance(key, str) or not key.startswith('sk-') or
                    not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or
                    not 0 < timeout <= 90 or len(body) > MAX_INPUT_BYTES // 2):
                result = {'kind': 'configuration'}
            else:
                try:
                    import certifi
                    if not Path(certifi.where()).is_file():
                        raise ImportError()
                except Exception:
                    result = {'kind': 'configuration'}
                else:
                    result = _exchange(key, body, timeout)
        sys.stdout.write(json.dumps(result, separators=(',', ':')))
        sys.stdout.flush()
    except Exception:
        # Never render tracebacks, raw HTTP output, request text or credentials.
        sys.stdout.write('{"kind":"uncertain"}')
        sys.stdout.flush()
    finally:
        key = body = payload = result = raw = None


if __name__ == '__main__':
    main()
