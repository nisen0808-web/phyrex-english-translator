"""Local-only event delivery; no recognition or translation decisions live here."""
import json
import socket
import threading


class LiveUpdates:
    def initialize_updates(self):
        self.changed = threading.Condition(self.lock)
        self.revision = 0
        self.preparations = {}

    def notify_changed(self):
        with self.changed:
            self.revision += 1
            self.changed.notify_all()

    def wait_for_change(self, revision, timeout=1):
        with self.changed:
            self.changed.wait_for(lambda: self.revision != revision, timeout)

    def prepare_session(self, session):
        prepare = getattr(self.translator, 'prepare', None)
        if prepare is None:
            return
        cancelled = threading.Event()
        self.preparations[session['id']] = cancelled
        options = dict(model=session['model'], profile=session['profile'],
                       session_id=session['id'], cancelled=cancelled)
        if 'provider' in session:
            options['provider'] = session['provider']

        def run():
            try:
                prepare(**options)
            except Exception:
                # No inference is sent during preparation. The normal request
                # still performs its own auth and error handling if this fails.
                pass
        threading.Thread(target=run, daemon=True).start()

    def cancel_preparation(self, session_id):
        cancelled = self.preparations.pop(session_id, None)
        if cancelled:
            cancelled.set()


class StateDelta:
    """Send a full snapshot on connect, then only changed rows and fresh metadata."""
    def __init__(self):
        self.sid = None
        self.rows = {}
        self.initial = True

    def encode(self, state):
        session = state.get('session')
        sid = session['id'] if session else None
        rows = {r['seq']: r for r in session['rows']} if session else {}
        if self.initial or self.sid != sid:
            event, payload = 'snapshot', state
        else:
            metadata = dict(state)
            if session:
                metadata['session'] = {k: v for k, v in session.items() if k != 'rows'}
            event, payload = 'update', {'state': metadata,
                'rows': [r for seq, r in rows.items() if self.rows.get(seq) != r],
                'removed': [seq for seq in self.rows if seq not in rows]}
        self.sid, self.rows, self.initial = sid, rows, False
        return ('event: ' + event + '\ndata: ' + json.dumps(payload, ensure_ascii=False) + '\n\n').encode('utf-8')


def serve_events(handler, sid):
    # The caller applies the same Host/Origin checks as the state endpoint.
    handler.send_response(200)
    handler.send_header('Content-Type', 'text/event-stream; charset=utf-8')
    handler.send_header('Cache-Control', 'no-store')
    handler.send_header('X-Content-Type-Options', 'nosniff')
    handler.send_header('Connection', 'close')
    handler.end_headers()
    handler.close_connection = True
    handler.connection.settimeout(5)
    delta, revision = StateDelta(), -1
    try:
        handler.wfile.write(b'retry: 1000\n\n')
        handler.wfile.flush()
        while True:
            state = handler.engine.state(sid)
            current = state['revision']
            if revision != current or state.get('pending'):
                handler.wfile.write(delta.encode(state))
                revision = current
            else:
                handler.wfile.write(b': alive\n\n')
            handler.wfile.flush()
            handler.engine.wait_for_change(revision)
    except (BrokenPipeError, ConnectionResetError, TimeoutError, socket.timeout, OSError):
        return
