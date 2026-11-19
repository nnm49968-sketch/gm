import concurrent.futures
import csv
import io
import tempfile
import threading
import unittest
from pathlib import Path


class OrbitAPI(unittest.TestCase):
    def setUp(self):
        from app import create_app
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.now = 10000
        self.cfg = dict(TESTING=True, DATABASE=str(Path(self.tmp.name) / 'test.db'),
                        ADMIN_PASSWORD='secret-test', SECRET_KEY='test-key', CLOCK=lambda: self.now)
        self.app = create_app(self.cfg)
        self.cookie_name = self.app.config['SESSION_COOKIE_NAME']
        self.admin = self.app.test_client()
        self.player = self.app.test_client()

    def login(self):
        self.assertEqual(self.admin.post('/api/admin/login', json={'password':'secret-test'}).status_code, 200)

    def act(self, action, **data):
        return self.admin.post('/api/admin/action', json=dict(action=action, **data))

    def state(self, client=None):
        return (client or self.player).get('/api/state').get_json()

    def test_admin_scope_and_revocable_login(self):
        self.assertEqual(self.act('start').status_code, 401)
        self.assertEqual(self.admin.get('/api/admin/export').status_code, 401)
        self.assertEqual(self.admin.post('/api/admin/login', json={'password':'bad'}).status_code, 401)
        self.login()
        self.assertNotEqual(self.cookie_name, 'session')  # classic Flask cookie
        saved = self.admin.get_cookie(self.cookie_name).value
        self.assertEqual(self.admin.get('/api/admin/state').status_code, 200)
        self.assertEqual(self.admin.post('/api/admin/logout', json={}).status_code, 200)
        self.admin.set_cookie(self.cookie_name, saved)
        self.assertEqual(self.admin.get('/api/admin/state').status_code, 401)

    def test_timers_pause_catchup_and_restart(self):
        from app import create_app
        self.login()
        self.assertEqual(self.state()['phase'], 'idle')
        self.assertEqual(self.state()['formingMinutes'], 10)
        self.assertEqual(self.act('settings', capacity=4, formingMinutes=1, playMinutes=2).status_code, 200)
        self.assertEqual(self.act('form').status_code, 200)
        self.now += 10
        self.assertEqual(self.act('pause').status_code, 200)
        self.now += 700
        self.assertEqual(self.state()['remaining'], 50)
        self.assertEqual(self.act('resume').status_code, 200)
        self.now += 70
        restarted = create_app(self.cfg).test_client()
        self.assertEqual(self.state(restarted)['phase'], 'playing')
        self.assertEqual(self.state()['remaining'], 100)
        self.now += 100
        self.assertEqual(self.state()['phase'], 'ended')
        self.assertEqual(self.act('resume').status_code, 409)
        self.assertEqual(self.act('reset').status_code, 200)
        self.assertEqual(self.state()['phase'], 'idle')

    def test_login_throttle_and_bad_payloads(self):
        for _ in range(8):
            r = self.admin.post('/api/admin/login', json={'password':'bad'})
        self.assertEqual(r.status_code, 429)
        self.now += 901
        self.login()
        self.assertEqual(self.act('settings', capacity=True).status_code, 400)
        self.assertEqual(self.admin.post('/api/admin/action', json=[]).status_code, 400)
        self.assertEqual(self.admin.post('/api/admin/action', json={'action':'reset'}, headers={'Origin':'https://other.test'}).status_code, 403)
        self.assertNotIn('teams', self.state())
        self.assertNotIn('log', self.state())
        self.assertEqual(self.admin.get('/api/state').headers['Cache-Control'], 'no-store')
        self.assertEqual(self.admin.get('/app.py').status_code, 404)
        self.assertEqual(self.admin.get('/puzzles.py').status_code, 404)

    def lobby(self):
        self.login()
        self.assertEqual(self.player.post('/api/create',json={'name':'A','team':'Orbit'}).status_code,409)
        self.act('form')
        self.assertEqual(self.player.post('/api/create',json={'name':'A','team':'Orbit'}).status_code,200)
        return self.state()['team']['code']

    def test_private_team_answer_key(self):
        from unittest.mock import patch
        from puzzles import puzzle
        code = self.lobby()
        tid = self.state()['team']['id']
        path = f'/api/admin/teams/{tid}/answer-key'
        for client in (self.player, self.app.test_client()):
            denied = client.get(path)
            self.assertEqual(denied.status_code, 401)
            self.assertEqual(denied.headers['Cache-Control'], 'no-store')
        self.assertEqual(self.admin.get('/api/admin/teams/999/answer-key').status_code, 404)
        response = self.admin.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        rows = response.get_json()['stages']
        self.assertEqual(rows, [dict(stage=i, title=puzzle(code,i)['title'], answer=puzzle(code,i)['answer']) for i in range(1,5)])
        with patch('puzzles.puzzle', return_value={'title': 'test', 'answer': '0012'}):
            self.assertEqual(self.admin.get(path).json['stages'][0]['answer'], '0012')
        self.act('start')
        for client, url in ((self.player, '/api/state'), (self.admin, '/api/admin/state')):
            self.assertNotIn('"answer":', client.get(url).text)
        self.admin.post('/api/admin/logout', json={})
        self.assertEqual(self.admin.get(path).status_code, 401)

    def test_admin_html_route_and_fonts(self):
        for path in ('/static/admin.html', '/static/./admin.html'):
            with self.player.get(path) as response:
                self.assertEqual(response.status_code, 404)
        with self.player.get('/admin') as response:
            self.assertEqual(response.status_code, 200)
            self.assertIn('href="/static/fonts.css"', response.text)
            self.assertEqual(response.headers['Cache-Control'], 'no-store')

    def test_team_membership_and_private_chat(self):
        code = self.lobby()
        guest = self.app.test_client()
        self.assertEqual(guest.post('/api/join',json={'name':'B','code':code.lower()}).status_code,200)
        self.assertEqual(guest.post('/api/chat',json={'text':'private'}).status_code,200)
        team = self.state()['team']
        self.assertEqual(len(team['members']),2)
        self.assertEqual(team['messages'],[{'name':'B','text':'private'}])
        stranger = self.app.test_client()
        self.assertNotIn(code, stranger.get('/api/state').text)
        self.assertNotIn('private', stranger.get('/api/state').text)
        self.assertEqual(stranger.post('/api/chat',json={'text':'x'}).status_code,401)
        self.assertEqual(guest.post('/api/leave',json={}).status_code,200)
        self.assertIsNone(self.state(guest)['team'])
        self.assertEqual(len(self.state()['team']['members']),1)

    def test_hard_capacity_range(self):
        self.login()
        self.assertEqual(self.state()['capacity'], 8)
        for size in range(1, 9):
            self.assertEqual(self.act('settings', capacity=size).status_code, 200)
            self.assertEqual(self.state()['capacity'], size)
        for invalid in (0, 9, 32):
            self.assertEqual(self.act('settings', capacity=invalid).status_code, 400)
            self.assertEqual(self.state()['capacity'], 8)

    def test_capacity_is_atomic(self):
        self.login()
        self.act('settings',capacity=2)
        self.act('form')
        self.player.post('/api/create',json={'name':'A','team':'T'})
        code = self.state()['team']['code']
        barrier = threading.Barrier(4)
        def join(i):
            client = self.app.test_client()
            barrier.wait(timeout=5)
            return client.post('/api/join',json={'name':str(i),'code':code}).status_code
        with concurrent.futures.ThreadPoolExecutor(4) as pool:
            self.assertEqual(sorted(pool.map(join,range(4))), [200,409,409,409])

    def full_team(self):
        code = self.lobby()
        clients = [self.player]
        for slot in range(1, 8):
            guest = self.app.test_client()
            self.assertEqual(guest.post('/api/join', json={'code': code, 'name': str(slot)}).status_code, 200)
            clients.append(guest)
        overflow = self.app.test_client()
        self.assertEqual(overflow.post('/api/join', json={'code': code, 'name': 'extra'}).status_code, 409)
        self.assertEqual(self.act('start').status_code, 200)
        return code, clients

    def assert_deal(self, clients, packet):
        hands = []
        for slot, client in enumerate(clients):
            view = self.state(client)['puzzle']
            self.assertNotIn('answer', view)
            self.assertEqual(view['clues'], packet['clues'][slot::len(clients)])
            hands.extend(view['clues'])
        self.assertEqual(len(set(hands)), 8)
        self.assertEqual(len(hands), 8)
        self.assertCountEqual(hands, packet['clues'])

    def test_eight_sessions_four_stages(self):
        from puzzles import puzzle
        code, clients = self.full_team()
        path = f"/api/admin/teams/{self.state()['team']['id']}/answer-key"
        self.assertEqual(clients[-1].get(path).status_code, 401)
        rows = self.admin.get(path).json['stages']
        self.assertEqual([row['stage'] for row in rows], [1, 2, 3, 4])
        for stage, row in enumerate(rows):
            with self.subTest(stage=stage):
                packet = puzzle(code, stage + 1)
                self.assertEqual((row['title'], row['answer']), (packet['title'], packet['answer']))
                self.assert_deal(clients, packet)
                payload = {'stage': stage, 'answer': row['answer']}
                self.assertEqual(clients[stage+1].post('/api/answer', json=payload).status_code, 200)
                self.assertEqual(self.player.post('/api/answer', json=payload).status_code, 409)
        for client in clients:
            state = self.state(client)
            self.assertEqual((state['team']['stage'], state['team']['score']), (4, 400))
            self.assertIsNone(state['puzzle'])

    def test_kick_redeals_current_stage_to_live_roster(self):
        from puzzles import puzzle
        code, clients = self.full_team()
        packet = puzzle(code, 1)
        while len(clients) > 1:
            kicked = clients.pop(len(clients)//2)
            mid = self.state(kicked)['me']['id']
            self.assertEqual(self.act('kick', memberId=mid).status_code, 200)
            self.assertIsNone(self.state(kicked)['puzzle'])
            self.assertEqual(kicked.post('/api/answer', json={'stage': 0, 'answer': packet['answer']}).status_code, 401)
            self.assert_deal(clients, packet)

    def test_scoped_clues_hints_and_atomic_progress(self):
        code = self.lobby()
        from puzzles import puzzle, STAGES
        mate = self.app.test_client()
        mate.post('/api/join',json={'name':'mate','code':code})
        self.assertIsNone(self.state()['puzzle'])
        self.act('start')
        p = puzzle(code,1)
        mine = self.state()['puzzle']
        self.assertEqual(mine['clues'],p['clues'][::2])
        self.assertEqual(self.state(mate)['puzzle']['clues'],p['clues'][1::2])
        self.assertNotIn('answer', mine)
        self.assertIsNone(mine['hint'])
        self.act('pause')
        self.assertEqual(mate.post('/api/hint',json={'stage':0}).status_code,409)
        self.act('resume')
        self.assertEqual(mate.post('/api/hint',json={'stage':0}).status_code,200)
        self.assertEqual(self.state()['puzzle']['hint'],p['hint'])
        self.assertEqual(mate.post('/api/answer',json={'stage':0,'answer':'incorrect'}).status_code,400)
        saved = self.player.get_cookie(self.cookie_name).value
        barrier = threading.Barrier(4)
        def solve(_):
            c = self.app.test_client()
            c.set_cookie(self.cookie_name,saved)
            barrier.wait(timeout=5)
            return c.post('/api/answer',json={'stage':0,'answer':p['answer']}).status_code
        with concurrent.futures.ThreadPoolExecutor(4) as pool:
            self.assertEqual(sorted(pool.map(solve,range(4))),[200,409,409,409])
        self.assertEqual(self.state()['team']['score'],80)
        self.assertFalse(self.state()['team']['hintUsed'])
        for stage in range(1,STAGES):
            r = mate.post('/api/answer',json={'stage':stage,'answer':puzzle(code,stage+1)['answer']})
            self.assertEqual(r.status_code,200)
        self.assertIsNone(self.state()['puzzle'])
        self.assertEqual(self.state()['leaders'][0]['stage'],STAGES)
        self.assertEqual(self.state()['team']['score'],80+100*(STAGES-1))

    def test_progress_and_identity_survive_reopening(self):
        from app import create_app
        from puzzles import puzzle
        code = self.lobby()
        self.act('start')
        self.player.post('/api/answer',json={'stage':0,'answer':puzzle(code,1)['answer']})
        self.player.post('/api/hint',json={'stage':1})
        new_client = create_app(self.cfg).test_client()
        new_client.set_cookie(self.cookie_name,self.player.get_cookie(self.cookie_name).value)
        state = self.state(new_client)
        self.assertEqual((state['team']['code'],state['team']['stage'],state['team']['score']), (code,1,100))
        self.assertTrue(state['team']['hintUsed'])
        self.assertEqual(new_client.post('/api/hint',json={'stage':0}).status_code,409)

    def test_admin_cookie_expires_and_https_origin_matches(self):
        from app import create_app
        secure = create_app(dict(self.cfg, SESSION_COOKIE_SECURE=True)).test_client()
        url = 'https://orbit.example'
        response = secure.post('/api/admin/login',base_url=url,headers={'Origin':url},json={'password':'secret-test'})
        self.assertEqual(response.status_code,200)
        for field in ('Secure','HttpOnly','SameSite=Strict'):
            self.assertIn(field,response.headers['Set-Cookie'])
        self.now += 28800
        self.assertEqual(secure.get('/api/admin/state',base_url=url).status_code,401)

    def test_moderation_rank_export_and_reset(self):
        code = self.lobby()
        old = self.player.get_cookie(self.cookie_name).value
        second = self.app.test_client()
        second.post('/api/create',json={'name':'B','team':'=formula'})
        team = self.state(second)['team']
        self.assertEqual(self.act('score',teamId=team['id'],delta=25).status_code,200)
        self.assertEqual(self.act('announce',text='Hello').status_code,200)
        self.assertEqual(self.state()['announcement'],'Hello')
        self.assertEqual(self.state()['leaders'][0],{'name':'=formula','score':25,'stage':0})
        rows = list(csv.DictReader(io.StringIO(self.admin.get('/api/admin/export').text)))
        self.assertEqual(rows[0]['name'],"'=formula")
        self.assertEqual(len(self.admin.get('/api/admin/state').json['teams']),2)
        self.assertEqual(self.act('kick',memberId=team['members'][0]['id']).status_code,200)
        self.assertIsNone(self.state(second)['me'])
        self.act('reset')
        self.act('form')
        second.post('/api/create',json={'name':'New','team':'New team'})
        self.player.set_cookie(self.cookie_name,old)
        self.assertIsNone(self.state()['me'])
        self.assertNotIn(code,self.admin.get('/api/admin/state').text)
        self.assertEqual(self.state()['announcement'],'')


if __name__ == '__main__':
    unittest.main()
