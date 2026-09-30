"""Provider routing and actual offline CLI startup. Never invokes a model or signs in."""
import argparse
import io
import json
import os
import queue
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

parser = argparse.ArgumentParser()
parser.add_argument('root', type=Path)
parser.add_argument('report', type=Path)
parser.add_argument('--ai-root', type=Path)
parser.add_argument('--packages', type=Path)
args = parser.parse_args()
scratch = tempfile.TemporaryDirectory(prefix='phyrex-provider-check-')
os.environ['FED_TRANSLATOR_USER_DIR'] = str(Path(scratch.name).resolve() / 'user-data')
sys.path.insert(0, str(args.root.resolve()))
if args.packages:
    sys.path.insert(0, str(args.packages.resolve()))
import runtime
runtime.prepare()
import providers as p
import provider_auth as auth
import app
if args.ai_root:
    p.ROOT = args.ai_root.resolve()
checks = []


class Providers(unittest.TestCase):
    def tearDown(self):
        checks.append(self._testMethodName)

    def test_allowlist_and_modes(self):
        self.assertEqual(set(p.PROVIDERS), {'chatgpt', 'grok', 'gemini'})
        for provider in p.PROVIDERS:
            for model in p.PROVIDERS[provider]['models']:
                p.validate_model(provider, model)
        for provider, model in [('unknown', 'auto'), ('grok', 'gpt-6-sol'), ('gemini', '--help')]:
            with self.assertRaises(ValueError):
                p.validate_model(provider, model)

    def test_isolated_accounts_and_no_inherited_credentials(self):
        injected = {key: 'not-a-real-key' for key in ['OPENAI_API_KEY','GEMINI_API_KEY','GOOGLE_API_KEY','XAI_API_KEY','GROK_API_KEY','NODE_OPTIONS','GEMINI_CLI_HOME','GROK_HOME','GOOGLE_APPLICATION_CREDENTIALS','GOOGLE_GENAI_USE_VERTEXAI']}
        with patch.dict(os.environ, injected):
            a, b = p.environment('grok'), p.environment('gemini')
        for env in (a, b):
            for key in set(injected) - {'GEMINI_CLI_HOME', 'GROK_HOME'}:
                self.assertNotIn(key, env)
        self.assertNotEqual(a['HOME'], b['HOME'])
        self.assertEqual(Path(b['GEMINI_CLI_HOME']).resolve(), p.home('gemini').resolve())
        self.assertIn('decision = "deny"', (p.home('gemini') / '.gemini/deny-tools.toml').read_text())

    def test_foreign_account_never_defaults_to_ready(self):
        for provider in ('grok','gemini'):
            p.mark_login(provider, False)
            self.assertFalse(p.login_status(provider)['ready'])
            with patch.object(p.subprocess, 'run') as run, self.assertRaises(p.TranslationError):
                p.translate('Do not lower rates.', '', {}, 'auto', provider=provider)
            run.assert_not_called()

    def test_chatgpt_route_is_preserved(self):
        with patch.object(p.bridge, 'translate', return_value=({'chinese':'利率不变。'}, 1)) as translate:
            p.translate('rates', '', {}, 'gpt-6-luna')
            translate.assert_called_once_with('rates', '', {}, 'gpt-6-luna', 'fed', on_partial=None, session_id=None)

    def test_foreign_routes_share_financial_prompt_and_have_no_fallback(self):
        translated = {'chinese':'政策利率保持不变。', 'review':True, 'note':'请核对数字。'}
        for provider in ('grok','gemini'):
            p.mark_login(provider, True)
            response = translated if provider == 'grok' else {'response':json.dumps(translated)}
            with patch.object(p.subprocess, 'run', return_value=Mock(returncode=0,stdout=json.dumps(response),stderr='')) as run:
                result, _ = p.translate('policy rate unchanged', '', {'policy rate':'政策利率'}, 'auto', provider=provider)
            self.assertEqual(result, translated)
            command = run.call_args.args[0]
            prompt = command[command.index('-p')+1] if provider == 'grok' else run.call_args.kwargs['input']
            self.assertIn('政策利率', prompt)
            self.assertIn('禁止调用任何工具', prompt)
            self.assertIn('--deny' if provider == 'grok' else '--policy', command)
            self.assertEqual(run.call_count, 1)

    def test_result_validation_prevents_english_or_malformed_records(self):
        for response in ['hello', '{}', '{"chinese":"English only", "review":false,"note":""}', json.dumps({'chinese':'中文 The Federal Reserve will not change the interest rate today.', 'review':False, 'note':''})]:
            with self.assertRaises(p.TranslationError):
                p.unwrap_result(response)
        self.assertEqual(p.unwrap_result('```json\n{"chinese":"中文", "review":false, "note":""}\n```')['chinese'], '中文')

    def test_errors_do_not_expose_raw_output_or_switch_provider(self):
        for provider in ('grok','gemini'):
            p.mark_login(provider, True)
            failure = p.error('OAuth quota 429 secret-token', provider)
            self.assertEqual(failure.kind, 'quota')
            self.assertNotIn('secret-token', str(failure))
            self.assertTrue(p.login_status(provider)['ready'])
            self.assertEqual(p.error('invalid_grant secret-token', provider).kind,'auth')
            self.assertFalse(p.login_status(provider)['ready'])

    def test_transient_cache_cleanup_preserves_credentials(self):
        for provider, folder in [('gemini','.gemini'),('grok','.grok')]:
            state = p.home(provider) / folder
            state.mkdir(parents=True,exist_ok=True)
            credential = state / 'oauth_creds.json'
            credential.write_text('test-placeholder')
            cache = state / ('tmp' if provider == 'gemini' else 'sessions')
            cache.mkdir(exist_ok=True)
            (cache / 'conversation.json').write_text('temporary English')
            p.clear_transient_history(provider)
            self.assertFalse(cache.exists())
            self.assertTrue(credential.exists())
            credential.unlink()

    def test_auth_urls_reject_phishing_and_login_does_not_reset(self):
        self.assertTrue(auth.official_login_url('gemini','https://accounts.google.com/o/oauth2/auth'))
        self.assertTrue(auth.official_login_url('grok','https://auth.x.ai/oauth'))
        for url in ['https://accounts.google.com.evil.example','https://user@accounts.google.com','http://accounts.google.com','https://accounts.google.com:1234']:
            self.assertFalse(auth.official_login_url('gemini',url))
        manager = auth.LoginManager(); manager.select('gemini')
        manager.result['running'] = True
        manager.select('gemini')
        self.assertTrue(manager.state()['running'])
        with self.assertRaises(ValueError): manager.select('grok')

    def test_acp_login_handshake_does_not_request_translation(self):
        manager = auth.LoginManager(); manager.select('gemini')
        messages = [{'id':1,'result':{'authMethods':[{'id':'oauth-personal'}]}}, {'id':2,'result':{}}]
        stdin = io.StringIO()
        stdin.close = lambda: None
        process = Mock(stdin=stdin, stdout=io.StringIO('\n'.join(json.dumps(x) for x in messages)), poll=Mock(return_value=None))
        manager.process = process
        manager._read(process,'gemini')
        self.assertTrue(p.login_status('gemini')['ready'])
        self.assertEqual([json.loads(line)['method'] for line in stdin.getvalue().splitlines()], ['initialize','authenticate'])

    def test_session_provider_is_fixed_and_stale_start_rejected(self):
        with patch.object(app.threading.Thread,'start'), patch.object(app,'login_status',return_value={'ready':True,'message':'test'}):
            engine = app.Engine(data=Path(scratch.name)/'records', warm=False)
            engine.select_provider('grok')
            engine.asr={'ready':True}
            with self.assertRaises(ValueError): engine.start('test','gpt-6-luna',provider='chatgpt')
            sid = engine.start('测试','auto',provider='grok')
            self.assertEqual(engine.sessions[sid]['provider'], 'grok')
            with self.assertRaises(ValueError): engine.select_provider('gemini')
            engine.finish(sid)
            engine.select_provider('gemini')
            with self.assertRaises(ValueError): engine.retry(sid)

    def test_actual_official_grok_help_and_gemini_acp_initialization(self):
        env = p.environment('grok')
        result = subprocess.run(p.cli('grok') + ['--help'], env=env, capture_output=True, text=True, encoding='utf-8', timeout=45)
        self.assertEqual(result.returncode,0, result.stderr[:300])
        for flag in ('--no-plan','--no-subagents','--permission-mode','--max-turns','--deny','--tools','--verbatim'):
            self.assertIn(flag,result.stdout)
        env=p.environment('gemini',login=True)
        command=p.cli('gemini')+['--acp','--extensions','none']
        request=json.dumps({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':1,'clientCapabilities':{}}})+'\n'
        process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,cwd=p.home('gemini')/'work',text=True,encoding='utf-8')
        replies=queue.Queue(); errors=[]
        def read():
            for line in process.stdout:
                if line.startswith('{'): replies.put(json.loads(line))
        threading.Thread(target=read,daemon=True).start()
        threading.Thread(target=lambda:errors.extend(process.stderr.readlines()),daemon=True).start()
        try:
            process.stdin.write(request); process.stdin.flush()
            reply=replies.get(timeout=45)
            self.assertIn('oauth-personal',[x['id'] for x in reply.get('result',{}).get('authMethods',[])],''.join(errors)[-1500:])
        finally:
            process.terminate(); process.wait(timeout=10)
            process.stdin.close(); process.stdout.close(); process.stderr.close()
        p.clear_transient_history('gemini')


suite = unittest.defaultTestLoader.loadTestsFromTestCase(Providers)
result = unittest.TextTestRunner(verbosity=2).run(suite)
args.report.parent.mkdir(parents=True,exist_ok=True)
args.report.write_text(json.dumps({'passed':result.testsRun-len(result.failures)-len(result.errors),'checks':checks,'not_tested':['real Grok/Google account authorization, entitlement, quota or model response','live YouTube audio with these providers']},indent=2),encoding='utf-8')
scratch.cleanup()
sys.exit(not result.wasSuccessful())
