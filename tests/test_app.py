import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch
import model, data, server

TEAM=dict(differential=0, win_rate=.5, points_for=22, points_against=22)
class ModelTests(unittest.TestCase):
    def test_home_advantage(self):
        p=model.predict(TEAM,TEAM)
        self.assertGreater(p['home_probability'],50)
        self.assertEqual(p['margin'],1.5)
    def test_neutral(self):
        self.assertEqual(model.predict(TEAM,TEAM,neutral=True)['home_probability'],50)
    def test_qb_penalty(self):
        self.assertLess(model.predict(TEAM,TEAM,{'home_qb':5})['home_probability'],model.predict(TEAM,TEAM)['home_probability'])
    def test_rest(self):
        self.assertEqual(model.predict(TEAM,TEAM,{'home_rest':4})['margin'],2.5)
    def test_probability_caps_and_nonnegative_score(self):
        p=model.predict(dict(TEAM,differential=90),TEAM)
        self.assertEqual(p['home_probability'],95)
        self.assertGreaterEqual(p['away_score'],0)
    def test_score_winner_consistent(self):
        for delta in range(-15,16):
            p=model.predict(dict(TEAM,differential=delta),TEAM)
            self.assertEqual(p['winner'],'home' if p['home_score']>p['away_score'] else 'away')
    def test_invalid_inputs(self):
        for a in ({'home_qb':8},{'home_rest':-1},{'other':1},{'home_qb':float('nan')},{'home_qb':True}):
            with self.assertRaises(ValueError):model.predict(TEAM,TEAM,a)
    def test_factors_sum(self):
        p=model.predict(TEAM,TEAM,{'away_qb':3,'home_rest':2})
        self.assertAlmostEqual(sum(p['factors'].values()),p['margin'])
class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=server.DB;server.DB=Path(self.tmp.name)/'test.db'
    def tearDown(self):server.DB=self.old;self.tmp.cleanup()
    def test_all_schedule_snapshots(self):
        total=0
        for week in range(1,19):
            games,_,_=data.schedule(week);total+=len(games)
        self.assertEqual(total,272)
    def test_malformed_feed(self):
        with self.assertRaises(ValueError):data.parse({},1)
    def test_persistent_forecast_and_grading(self):
        with patch('server.locked',return_value=False):
            game=server.load_week(1)['games'][0]
        with server.connect() as db:
            original=db.execute('SELECT forecast FROM games WHERE id=?',(game['id'],)).fetchone()[0]
            g=json.loads(db.execute('SELECT payload FROM games WHERE id=?',(game['id'],)).fetchone()[0])
            side=json.loads(original)['winner'];g.update(completed=True,actual_home=24 if side=='home' else 10,actual_away=24 if side=='away' else 10)
            db.execute('UPDATE games SET pick=?,payload=? WHERE id=?',(side,json.dumps(g),game['id']))
        rows=server.leaderboard()
        self.assertEqual([r['correct'] for r in rows],[1,1])
        self.assertEqual([r['total'] for r in rows],[1,1])
        with patch('server.locked',return_value=True):server.load_week(1)
        with server.connect() as db:self.assertEqual(db.execute('SELECT forecast FROM games WHERE id=?',(game['id'],)).fetchone()[0],original)
    def test_late_loaded_games_excluded(self):
        with patch('server.locked',return_value=True):
            games=server.load_week(1)['games']
        self.assertTrue(all(not g['eligible'] for g in games))
    def test_kickoff_lock(self):
        self.assertTrue(server.locked(dict(completed=False,status='Scheduled',date='2020-01-01T00:00Z')))
    def test_tie_not_graded(self):
        with server.connect() as db:
            db.execute('INSERT INTO games VALUES(?,?,?,?,?)',('tie',json.dumps(dict(completed=True,actual_home=20,actual_away=20)),json.dumps({'winner':'home'}),'home',None))
        self.assertTrue(all(r['total']==0 for r in server.leaderboard()))

class EndpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.old=server.DB; server.DB=Path(self.tmp.name)/'api.db'
        with patch('server.locked',return_value=False): self.game=server.load_week(1)['games'][0]
    def tearDown(self): server.DB=self.old; self.tmp.cleanup()
    def post(self,path,body):
        import io
        h=object.__new__(server.Handler)
        raw=json.dumps(body).encode();h.path=path;h.rfile=io.BytesIO(raw)
        h.headers={'Content-Type':'application/json','Content-Length':str(len(raw)),'Host':'127.0.0.1:8000','Origin':'http://127.0.0.1:8000'}
        responses=[];h.reply=lambda body,status=200,**kw:responses.append((status,body));h.do_POST()
        return responses[0]
    def test_pick_save_clear_and_lock(self):
        with patch('server.locked',return_value=False):
            self.assertEqual(self.post('/api/pick',{'id':self.game['id'],'pick':'home'})[0],200)
        with server.connect() as db:self.assertEqual(db.execute('SELECT pick FROM games WHERE id=?',(self.game['id'],)).fetchone()[0],'home')
        with patch('server.locked',return_value=True):
            self.assertEqual(self.post('/api/pick',{'id':self.game['id'],'pick':'away'})[0],400)
        with patch('server.locked',return_value=False):self.assertEqual(self.post('/api/pick',{'id':self.game['id'],'pick':None})[0],200)
    def test_scenario_does_not_change_ledger(self):
        with server.connect() as db:before=tuple(db.execute('SELECT * FROM games WHERE id=?',(self.game['id'],)).fetchone())
        code,result=self.post('/api/scenario',{'id':self.game['id'],'adjustments':{'home_qb':5}})
        self.assertEqual(code,200);self.assertLess(result['home_probability'],self.game['prediction']['home_probability'])
        with server.connect() as db:self.assertEqual(tuple(db.execute('SELECT * FROM games WHERE id=?',(self.game['id'],)).fetchone()),before)
    def test_bad_pick(self):
        with patch('server.locked',return_value=False):self.assertEqual(self.post('/api/pick',{'id':self.game['id'],'pick':'invalid'})[0],400)
    def test_refresh_falls_back(self):
        with patch('urllib.request.urlopen',side_effect=OSError('offline')):
            games,warning,_=data.schedule(1,True)
        self.assertEqual(len(games),16);self.assertIn('unavailable',warning)

if __name__=='__main__':unittest.main()
