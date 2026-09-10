"""Local-only HTTP application and durable forecast/pick ledger."""
import json
import sqlite3
import os
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path
from threading import RLock
import data
from model import predict

ROOT = Path(__file__).parent
DB = Path(os.environ.get('GRIDIRON_DB', ROOT / 'gridiron.sqlite3'))
LOCK = RLock()

def connect():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    db.execute('CREATE TABLE IF NOT EXISTS games (id TEXT PRIMARY KEY, payload TEXT NOT NULL, forecast TEXT, pick TEXT, picked_at TEXT)')
    return db

def locked(g):
    return g['completed'] or g['status'] != 'Scheduled' or datetime.fromisoformat(g['date'].replace('Z', '+00:00')) <= datetime.now(timezone.utc)

def forecast(g, adjustments=None):
    return predict(g['home'], g['away'], adjustments, neutral=g['neutral'])

def load_week(week, refresh=False):
    with LOCK:
        games, warning, updated = data.schedule(week, refresh)
        with connect() as db:
            for g in games:
                row = db.execute('SELECT * FROM games WHERE id=?',(g['id'],)).fetchone()
                saved = json.loads(row['forecast']) if row and row['forecast'] else None
                if not saved and not locked(g): saved = forecast(g)
                db.execute('INSERT INTO games(id,payload,forecast) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,forecast=excluded.forecast', (g['id'],json.dumps(g),json.dumps(saved) if saved else None))
                g.update(prediction=saved or forecast(g), eligible=bool(saved), pick=row['pick'] if row else None, locked=locked(g))
        return dict(games=games, warning=warning, updated=updated, season=data.SEASON)

def leaderboard():
    stats = {name:dict(name=name,correct=0,total=0,pending=0) for name in ('Model','You')}
    with connect() as db:
        for r in db.execute('SELECT * FROM games'):
            g=json.loads(r['payload'])
            for name, pick in [('Model', json.loads(r['forecast'])['winner'] if r['forecast'] else None),('You',r['pick'])]:
                if not pick: continue
                if not g['completed']: stats[name]['pending']+=1; continue
                if g['actual_home']==g['actual_away']: continue
                stats[name]['total']+=1
                stats[name]['correct']+= int(pick==('home' if g['actual_home']>g['actual_away'] else 'away'))
    return list(stats.values())

class Handler(BaseHTTPRequestHandler):
    def reply(self, body, status=200, content_type='application/json'):
        payload=json.dumps(body).encode() if content_type=='application/json' else body
        self.send_response(status); self.send_header('Content-Type',content_type); self.send_header('Content-Length',str(len(payload))); self.send_header('X-Content-Type-Options','nosniff'); self.end_headers(); self.wfile.write(payload)
    def do_GET(self):
        try:
            u=urlparse(self.path); q=parse_qs(u.query)
            if u.path=='/api/week':
                week=int(q.get('week',['1'])[0])
                if not 1<=week<=18: raise ValueError('Week must be between 1 and 18')
                self.reply(load_week(week)); return
            if u.path=='/api/leaderboard': self.reply(leaderboard()); return
            if u.path=='/api/teams': self.reply(list(data.teams().values())); return
            assets={'/':('index.html','text/html'),'/app.js':('app.js','text/javascript'),'/style.css':('style.css','text/css')}
            if u.path not in assets: self.reply({'error':'Not found'},404); return
            name, mime=assets[u.path]; self.reply((ROOT/'static'/name).read_bytes(),content_type=mime)
        except (ValueError,KeyError) as exc: self.reply({'error':str(exc)},400)
        except Exception: self.reply({'error':'Unable to load data. Check server logs and retry.'},500); import traceback; traceback.print_exc()
    def do_POST(self):
        try:
            # JSON-only and same-origin browser requests prevent cross-site mutations.
            if self.headers.get('Content-Type')!='application/json': raise ValueError('JSON required')
            origin=self.headers.get('Origin')
            if origin and origin != 'http://'+self.headers.get('Host',''): raise ValueError('Invalid origin')
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=4096: raise ValueError('Invalid request size')
            b=json.loads(self.rfile.read(size))
            if self.path=='/api/refresh':
                week=int(b['week'])
                if not 1<=week<=18: raise ValueError('Invalid week')
                self.reply(load_week(week,True)); return
            with LOCK, connect() as db:
                row=db.execute('SELECT * FROM games WHERE id=?',(str(b['id']),)).fetchone()
                if not row: raise ValueError('Load the game first')
                g=json.loads(row['payload'])
                if self.path=='/api/scenario': self.reply(forecast(g,b.get('adjustments',{}))); return
                if self.path!='/api/pick': self.reply({'error':'Not found'},404); return
                if locked(g): raise ValueError('Picks are locked at kickoff')
                if b['pick'] not in ('home','away',None): raise ValueError('Invalid pick')
                db.execute('UPDATE games SET pick=?,picked_at=? WHERE id=?',(b['pick'],datetime.now(timezone.utc).isoformat(),g['id']))
            self.reply({'ok':True})
        except (ValueError,KeyError,TypeError) as exc: self.reply({'error':str(exc)},400)
        except Exception: self.reply({'error':'Unable to save. Please retry.'},500); import traceback; traceback.print_exc()

if __name__=='__main__':
    port=int(os.environ.get('PORT','8000'))
    print(f'Gridiron: http://127.0.0.1:{port}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()
