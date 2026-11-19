"""ORBIT game server. Run with flask --app app:create_app run."""
import csv
import hashlib
import hmac
import io
import os
from pathlib import Path
import secrets
import sqlite3
import tempfile
import time

from flask import Flask, Response, abort, g, jsonify, request, session
from werkzeug.exceptions import HTTPException

ROOT = Path(__file__).resolve().parent


class Problem(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


def require(condition, status, message):
    if not condition:
        raise Problem(status, message)


def text(data, key, maximum):
    value = data.get(key)
    require(isinstance(value, str) and 0 < len(value.strip()) <= maximum and
            all(c.isprintable() or c == '\u200c' for c in value.strip()), 400, 'متن نامعتبر است.')
    return value.strip()


def integer(data, key, low, high):
    n = data.get(key)
    require(type(n) is int and low <= n <= high, 400, 'عدد خارج از محدوده است.')
    return n


def private_value(path):
    # link publishes a completely written mode-0600 file even with competing workers.
    if not path.exists():
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
            f.write((secrets.token_urlsafe(32) + '\n').encode())
        try:
            os.link(f.name, path)
        except FileExistsError:
            pass
        finally:
            os.unlink(f.name)
    return path.read_text().strip()


MAX_TEAM_SIZE = 8

SCHEMA = f'''
CREATE TABLE IF NOT EXISTS round(id INTEGER PRIMARY KEY CHECK(id=1), phase TEXT DEFAULT 'idle', prior TEXT, deadline INTEGER, frozen INTEGER DEFAULT 0, capacity INTEGER DEFAULT {MAX_TEAM_SIZE}, formingMinutes INTEGER DEFAULT 10, playMinutes INTEGER DEFAULT 45, announcement TEXT DEFAULT '');
INSERT OR IGNORE INTO round(id) VALUES(1);
CREATE TABLE IF NOT EXISTS teams(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE COLLATE NOCASE, code TEXT NOT NULL UNIQUE, stage INTEGER NOT NULL DEFAULT 0, score INTEGER NOT NULL DEFAULT 0, hintUsed INTEGER NOT NULL DEFAULT 0, advanced INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS members(id INTEGER PRIMARY KEY AUTOINCREMENT, team INTEGER NOT NULL REFERENCES teams ON DELETE CASCADE, name TEXT NOT NULL, token TEXT NOT NULL UNIQUE);
CREATE INDEX IF NOT EXISTS roster ON members(team,id);
CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, team INTEGER NOT NULL REFERENCES teams ON DELETE CASCADE, name TEXT NOT NULL, text TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS chat ON messages(team,id);
CREATE TABLE IF NOT EXISTS admins(token TEXT PRIMARY KEY, expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS failures(ip TEXT PRIMARY KEY, since INTEGER, attempts INTEGER);
CREATE TABLE IF NOT EXISTS log(id INTEGER PRIMARY KEY, message TEXT NOT NULL);
'''


def run(sql, args=()):
    return g.db.execute(sql, args)


def one(sql, args=()):
    return run(sql, args).fetchone()


def note(message):
    run('INSERT INTO log(message) VALUES(?)', (message,))


def round_state():
    r = dict(one('SELECT * FROM round'))
    if r['phase'] == 'forming' and r['deadline'] <= g.now:
        run("UPDATE round SET phase='playing', deadline=deadline+60*playMinutes")
        note('بازی به صورت خودکار آغاز شد.')
        return round_state()
    if r['phase'] == 'playing' and r['deadline'] <= g.now:
        run("UPDATE round SET phase='ended', deadline=NULL")
        note('زمان بازی پایان یافت.')
        return round_state()
    return r


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def admin_required():
    require(one('SELECT 1 FROM admins WHERE token=? AND expires>?',
                (digest(session.get('admin', '')), g.now)), 401, 'ورود مدیر لازم است.')


def member(required=False):
    m = one('SELECT id,name,team FROM members WHERE token=?',(digest(session.get('player','')),))
    require(m or not required,401,'ابتدا عضو یک گروه شوید.')
    return m


def team_info(t):
    data = {k:t[k] for k in ('id','name','code','stage','score')}
    data['members'] = [dict(m) for m in run('SELECT id,name FROM members WHERE team=? ORDER BY id',(t['id'],))]
    return data


def remove_member(mid):
    m = one('SELECT team FROM members WHERE id=?',(mid,))
    require(m,404,'عضو پیدا نشد.')
    run('DELETE FROM members WHERE id=?',(mid,))
    run('DELETE FROM teams WHERE id=? AND NOT EXISTS(SELECT 1 FROM members WHERE team=?)',(m[0],m[0]))


def ranked():
    return run('SELECT * FROM teams ORDER BY score DESC, stage DESC, advanced, id')


def snapshot(admin=False):
    r = round_state()
    result = {k: r[k] for k in ('phase','announcement','capacity','formingMinutes','playMinutes')}
    result.update(remaining=r['frozen'] if r['phase']=='paused' else max(0,(r['deadline'] or 0)-g.now),
                  me=None, team=None, puzzle=None, leaders=[])
    teams = list(ranked())
    result['leaders'] = [{k:t[k] for k in ('name','score','stage')} for t in teams]
    m = member()
    if m:
        result['me'] = {k:m[k] for k in ('id','name')}
        t = one('SELECT * FROM teams WHERE id=?',(m['team'],))
        info = team_info(t)
        info['messages'] = [dict(row) for row in run('SELECT name,text FROM messages WHERE team=? ORDER BY id DESC LIMIT 100',(t['id'],))][::-1]
        info['hintUsed'] = bool(t['hintUsed'])
        result['team'] = info
        if r['phase']=='playing':
            from puzzles import STAGES, puzzle
            if t['stage'] < STAGES:
                p = puzzle(t['code'],t['stage']+1)
                members = info['members']
                slot = next(i for i,v in enumerate(members) if v['id']==m['id'])
                clues = p['clues']
                result['puzzle'] = {k:p[k] for k in ('title','prompt','format')}
                result['puzzle'].update(clues=clues[slot::len(members)],
                                        hint=p['hint'] if t['hintUsed'] else None)
    if admin:
        result.update(teams=[team_info(t) for t in teams], log=[x['message'] for x in run('SELECT message FROM log ORDER BY id DESC LIMIT 100')])
    return result


def create_app(config=None):
    app = Flask(__name__, static_folder=str(ROOT / 'static'), static_url_path='/static')
    app.config.update(DATABASE=os.environ.get('ORBIT_DB', str(ROOT/'data'/'orbit.sqlite3')),
                      ADMIN_PASSWORD=os.environ.get('ORBIT_ADMIN_PASSWORD'), SECRET_KEY=os.environ.get('ORBIT_SECRET'),
                      CLOCK=time.time, MAX_CONTENT_LENGTH=16384, SESSION_COOKIE_SAMESITE='Strict',
                      SESSION_COOKIE_NAME='orbit_hard_session',
                      SESSION_COOKIE_SECURE=os.environ.get('ORBIT_COOKIE_SECURE') == '1')
    app.config.update(config or {})
    directory = Path(app.config['DATABASE']).resolve().parent
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    for key, filename in [('SECRET_KEY','session.secret'), ('ADMIN_PASSWORD','admin.password')]:
        if not app.config[key]:
            app.config[key] = private_value(directory/filename)
        if not app.config[key].strip():
            raise ValueError(f'{key} cannot be blank')
    db = sqlite3.connect(app.config['DATABASE'], timeout=10)
    try:
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript(SCHEMA)
    finally:
        db.close()

    @app.before_request
    def begin():
        # Docker ships one static tree; the admin document has a dedicated URL.
        if request.endpoint == 'static' and os.path.normpath(request.view_args['filename']) == 'admin.html':
            abort(404)
        if not request.path.startswith('/api/'):
            return
        if request.method == 'POST':
            origin = request.headers.get('Origin')
            require(not origin or origin == request.host_url.rstrip('/'), 403, 'مبدأ درخواست مجاز نیست.')
            g.data = request.get_json(silent=True)
            require(isinstance(g.data, dict), 400, 'بدنهٔ درخواست باید یک شیء JSON باشد.')
        g.db = sqlite3.connect(app.config['DATABASE'], isolation_level=None, timeout=10)
        g.db.row_factory = sqlite3.Row
        run('PRAGMA foreign_keys=ON')
        run('BEGIN IMMEDIATE')
        g.now = int(app.config['CLOCK']())
        round_state()

    @app.after_request
    def finish(response):
        if request.path.startswith('/api/'):
            if 'db' in g:
                if response.status_code < 400 or g.get('record_failure'):
                    g.db.commit()
                else:
                    g.db.rollback()
            response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @app.teardown_request
    def close(_error):
        if 'db' in g:
            g.db.close()

    @app.errorhandler(Problem)
    def problem(exc):
        return jsonify(error=exc.message), exc.status

    @app.errorhandler(HTTPException)
    def http_error(exc):
        if request.path.startswith('/api/'):
            return jsonify(error='درخواست قابل پردازش نیست.'), exc.code
        return exc

    @app.get('/')
    def index():
        return app.send_static_file('index.html')

    @app.get('/admin')
    def admin_page():
        response = app.send_static_file('admin.html')
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/api/state')
    def state():
        return snapshot()

    @app.post('/api/create')
    @app.post('/api/join')
    def enroll():
        require(round_state()['phase']=='forming',409,'زمان تشکیل گروه نیست.')
        require(not member(),409,'شما عضو یک گروه هستید.')
        name = text(g.data,'name',40)
        if request.path=='/api/create':
            label = text(g.data,'team',60)
            require(not one('SELECT id FROM teams WHERE name=?',(label,)),409,'نام گروه تکراری است.')
            while True:
                code = secrets.token_hex(4).upper()
                if not one('SELECT id FROM teams WHERE code=?',(code,)):
                    break
            tid = run('INSERT INTO teams(name,code) VALUES(?,?)',(label,code)).lastrowid
        else:
            t = one('SELECT id FROM teams WHERE code=?',(text(g.data,'code',16).upper(),))
            require(t,404,'کد گروه پیدا نشد.')
            tid = t['id']
            require(one('SELECT COUNT(*) FROM members WHERE team=?',(tid,))[0] < min(round_state()['capacity'], MAX_TEAM_SIZE),409,'ظرفیت گروه تکمیل است.')
        token = secrets.token_urlsafe(32)
        run('INSERT INTO members(name,team,token) VALUES(?,?,?)',(name,tid,digest(token)))
        session['player'] = token
        return jsonify(ok=True)

    @app.post('/api/leave')
    def leave():
        m = member(True)
        require(round_state()['phase']=='forming',409,'خروج فقط هنگام تشکیل گروه ممکن است.')
        remove_member(m['id'])
        session.pop('player',None)
        return jsonify(ok=True)

    @app.post('/api/chat')
    def chat():
        m = member(True)
        require(round_state()['phase'] in ('forming','playing'),409,'گفت‌وگو اکنون فعال نیست.')
        run('INSERT INTO messages(team,name,text) VALUES(?,?,?)',(m['team'],m['name'],text(g.data,'text',500)))
        run('DELETE FROM messages WHERE team=? AND id NOT IN (SELECT id FROM messages WHERE team=? ORDER BY id DESC LIMIT 100)',(m['team'],m['team']))
        return jsonify(ok=True)

    @app.post('/api/hint')
    @app.post('/api/answer')
    def progress():
        from puzzles import puzzle, normalize, STAGES
        m = member(True)
        require(round_state()['phase']=='playing',409,'بازی در حال اجرا نیست.')
        t = one('SELECT * FROM teams WHERE id=?',(m['team'],))
        stage = integer(g.data,'stage',0,STAGES)
        require(t['stage']==stage and stage<STAGES,409,'این مرحله دیگر فعال نیست.')
        if request.path=='/api/hint':
            run('UPDATE teams SET hintUsed=1 WHERE id=?',(t['id'],))
        else:
            answer = text(g.data,'answer',200)
            require(normalize(answer)==normalize(puzzle(t['code'],stage+1)['answer']),400,'پاسخ درست نیست.')
            run('UPDATE teams SET stage=stage+1,score=score+100-20*hintUsed,hintUsed=0,advanced=? WHERE id=?',(g.now,t['id']))
        return jsonify(ok=True)

    @app.post('/api/admin/login')
    def login():
        supplied = text(g.data,'password',512)
        ip = request.remote_addr or ''
        run('DELETE FROM failures WHERE since<=?', (g.now-900,))
        row = one('SELECT attempts FROM failures WHERE ip=?', (ip,))
        require(not row or row[0]<6, 429, 'تلاش بیش از حد؛ بعداً امتحان کنید.')
        if not hmac.compare_digest(app.config['ADMIN_PASSWORD'].encode(), supplied.encode()):
            run('INSERT INTO failures VALUES(?,?,1) ON CONFLICT(ip) DO UPDATE SET attempts=attempts+1', (ip,g.now))
            g.record_failure = True
            raise Problem(401, 'رمز نادرست است.')
        run('DELETE FROM failures WHERE ip=?', (ip,))
        run('DELETE FROM admins WHERE expires<=? OR token=?', (g.now,digest(session.get('admin',''))))
        token = secrets.token_urlsafe(32)
        run('INSERT INTO admins VALUES(?,?)',(digest(token), g.now+28800))
        session['admin'] = token
        return jsonify(ok=True)

    @app.post('/api/admin/logout')
    def logout():
        admin_required()
        run('DELETE FROM admins WHERE token=?',(digest(session.pop('admin')),))
        return jsonify(ok=True)

    @app.get('/api/admin/state')
    def admin_state():
        admin_required()
        return snapshot(True)

    @app.get('/api/admin/teams/<int:team_id>/answer-key')
    def answer_key(team_id):
        admin_required()
        from puzzles import STAGES, puzzle
        team = one('SELECT code FROM teams WHERE id=?', (str(team_id),))
        require(team, 404, 'تیم پیدا نشد.')
        stages = []
        for stage in range(1, STAGES + 1):
            packet = puzzle(team['code'], stage)
            stages.append(dict(stage=stage, title=packet['title'], answer=packet['answer']))
        return jsonify(stages=stages)

    @app.get('/api/admin/export')
    def export():
        admin_required()
        output = io.StringIO(newline='')
        writer = csv.writer(output)
        writer.writerow(('name','score','stage'))
        for t in ranked():
            name = t['name']
            writer.writerow(("'"+name if name.startswith(('=','+','-','@')) else name,t['score'],t['stage']))
        return Response(output.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename="orbit-ranking.csv"'})

    @app.post('/api/admin/action')
    def action():
        admin_required()
        r, d = round_state(), g.data
        a, p = text(d,'action',20), r['phase']
        def allowed(*phases):
            require(p in phases, 409, 'این عملیات در مرحلهٔ فعلی مجاز نیست.')
        if a == 'settings':
            allowed('idle')
            for key, maximum in [('capacity',MAX_TEAM_SIZE),('formingMinutes',180),('playMinutes',360)]:
                if key in d:
                    run(f'UPDATE round SET {key}=?',(integer(d,key,1,maximum),))
        elif a in ('form','start'):
            allowed(*(('idle',) if a=='form' else ('idle','forming')))
            phase, minutes = ('forming',r['formingMinutes']) if a=='form' else ('playing',r['playMinutes'])
            run('UPDATE round SET phase=?,deadline=?',(phase,g.now+60*minutes))
        elif a=='pause':
            allowed('forming','playing')
            run("UPDATE round SET prior=phase,phase='paused',frozen=deadline-?,deadline=NULL",(g.now,))
        elif a=='resume':
            allowed('paused')
            run('UPDATE round SET phase=prior,prior=NULL,deadline=?+frozen,frozen=0',(g.now,))
        elif a=='end':
            allowed('forming','playing','paused')
            run("UPDATE round SET phase='ended',prior=NULL,deadline=NULL,frozen=0")
        elif a=='reset':
            run("UPDATE round SET phase='idle',prior=NULL,deadline=NULL,frozen=0,announcement='' ")
            run('DELETE FROM teams')
            run('DELETE FROM log')
        elif a=='kick':
            remove_member(integer(d,'memberId',1,2**63-1))
        elif a=='score':
            cursor = run('UPDATE teams SET score=score+? WHERE id=?',(integer(d,'delta',-10000,10000),integer(d,'teamId',1,2**63-1)))
            require(cursor.rowcount,404,'گروه پیدا نشد.')
        elif a=='announce':
            run('UPDATE round SET announcement=?',(text(d,'text',500),))
        else:
            raise Problem(400,'عملیات ناشناخته است.')
        note('عملیات مدیر: '+a)
        return jsonify(ok=True)

    return app


if __name__ == '__main__':
    create_app().run()
