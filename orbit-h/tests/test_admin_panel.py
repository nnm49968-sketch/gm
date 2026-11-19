"""Browser regression using a private Chrome profile and disposable game."""
import json
import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from werkzeug.serving import make_server

from app import create_app
from puzzles import puzzle


@unittest.skipUnless(shutil.which('google-chrome'), 'requires headless Chrome')
class AdminPanel(unittest.TestCase):
    def test_open_poll_close(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(dict(DATABASE=str(Path(tmp)/'game.db'), ADMIN_PASSWORD='test', SECRET_KEY='test'))
            requests = []
            from flask import request

            @app.before_request
            def count_keys():
                if request.path.endswith('/answer-key'):
                    requests.append(request.path)

            @app.get('/check')
            def check():
                return '''<body><output>pending</output><script>
                (async()=>{
                  const post=(url,body)=>fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
                  await post('/api/admin/login',{password:'test'});
                  const f=document.createElement('iframe'); f.src='/admin';
                  await new Promise(done=>{f.onload=done; document.body.append(f)});
                  const win=f.contentWindow, doc=f.contentDocument;
                  await win.sync();
                  const button=doc.querySelector('.crew [aria-expanded="false"]');
                  if(!button)throw Error('missing team key toggle');
                  await button.onclick();
                  const panel=doc.getElementById(button.getAttribute('aria-controls'));
                  if(!panel || !panel.textContent.includes(ANSWER))throw Error('missing exact answer');
                  if (!(await post('/api/join',{code:TEAM_CODE,name:'two'})).ok)throw Error('join failed');
                  await win.sync();
                  if(!panel.isConnected || panel.hidden || !panel.textContent.includes(ANSWER))throw Error('poll lost panel');
                  button.click();
                  if(!panel.hidden || panel.textContent)throw Error('key retained after close');
                  return 'passed';
                })().then(s=>document.querySelector('output').textContent=s,e=>document.querySelector('output').textContent=e.message);
                </script>'''.replace('TEAM_CODE', json.dumps(code)).replace('ANSWER', json.dumps(puzzle(code, 3)['answer']))

            client = app.test_client()
            client.post('/api/admin/login', json={'password':'test'})
            client.post('/api/admin/action', json={'action':'form'})
            creator = app.test_client()
            self.assertEqual(creator.post('/api/create', json={'team':'crew','name':'one'}).status_code, 200)
            code = creator.get('/api/state').json['team']['code']
            server = make_server('127.0.0.1', 0, app, threaded=True)
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                result = subprocess.run(['google-chrome','--headless','--disable-gpu','--disable-dev-shm-usage',
                    '--no-sandbox',f'--user-data-dir={tmp}/chrome','--dump-dom','--virtual-time-budget=8000',
                    f'http://127.0.0.1:{server.server_port}/check'], capture_output=True, text=True, timeout=30, check=True)
                self.assertIn('<output>passed</output>',result.stdout.split('<script>')[0])
                self.assertEqual(len(requests), 1)
            finally:
                server.shutdown()
                thread.join()
                server.server_close()
