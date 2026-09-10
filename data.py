"""ESPN adapter. Cached schedules are real snapshots, never synthetic results."""
import json
import urllib.request
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).parent
SEASON = 2026
URL = 'https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates=2026&seasontype=2&week='

def teams():
    result = {}
    raw = json.loads((ROOT / 'standings.json').read_text())
    for conference in raw['children']:
        for entry in conference['standings']['entries']:
            s = {x['name']: x.get('value') for x in entry['stats']}
            n = s['wins'] + s['losses'] + s['ties']
            if n <= 0: raise ValueError('Missing season statistics')
            t = entry['team']
            result[t['id']] = dict(id=t['id'], name=t['displayName'], abbr=t['abbreviation'],
                differential=(s['pointsFor']-s['pointsAgainst'])/n,
                points_for=s['pointsFor']/n, points_against=s['pointsAgainst']/n,
                win_rate=(s['wins']+.5*s['ties'])/n, record=f"{int(s['wins'])}–{int(s['losses'])}" + (f"–{int(s['ties'])}" if s['ties'] else ""))
    return result

def parse(raw, week):
    if raw.get('season', {}).get('year') != SEASON or raw.get('week', {}).get('number') != week:
        raise ValueError('Feed returned a different season or week')
    roster = teams()
    games = []
    for e in raw['events']:
        c = e['competitions'][0]
        sides = {x['homeAway']: x for x in c['competitors']}
        h, a = sides['home'], sides['away']
        date = e['date']
        datetime.fromisoformat(date.replace('Z', '+00:00'))
        status = c['status']['type']
        games.append(dict(id=e['id'], week=week, date=date, home=roster[h['team']['id']], away=roster[a['team']['id']],
            completed=bool(status['completed']), status=status['description'],
            actual_home=int(h.get('score', 0)), actual_away=int(a.get('score', 0)),
            venue=c.get('venue', {}).get('fullName', 'Venue unavailable'), neutral=c.get('neutralSite', False)))
    return games

def schedule(week, refresh=False):
    path = ROOT / 'cache' / f'{week}.json'
    warning = None
    if refresh or not path.exists():
        try:
            req = urllib.request.Request(URL + str(week), headers={'User-Agent':'GridironLocal/1.0'})
            with urllib.request.urlopen(req, timeout=12) as response:
                raw = json.load(response)
            parse(raw, week)
            temp = path.with_suffix('.tmp')
            temp.write_text(json.dumps(raw))
            temp.replace(path)
        except Exception as exc:
            if not path.exists(): raise ValueError('ESPN is unavailable and this week has no cache. Try again later.') from exc
            warning = 'Live refresh unavailable. Showing the last saved ESPN snapshot.'
    try:
        games = parse(json.loads(path.read_text()), week)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('Schedule data is malformed. Try refreshing ESPN.') from exc
    return games, warning, datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
