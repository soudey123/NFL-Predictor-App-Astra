"""Transparent point-margin model; no fitted or calibrated parameters."""
import math

VERSION = '1.0'

def predict(home, away, adjustments=None, neutral=False):
    a = adjustments or {}
    for key, value in a.items():
        if key not in ('home_qb', 'away_qb', 'home_rest', 'away_rest') or type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError('Invalid adjustment')
        limit = 7 if 'qb' in key else 4
        if not 0 <= value <= limit:
            raise ValueError('Adjustment outside allowed range')
    parts = {
        'Point differential': .65 * (home['differential'] - away['differential']),
        'Season record': 6 * (home['win_rate'] - away['win_rate']),
        'Home field': 0 if neutral else 1.5,
        'Extra rest': .25 * (a.get('home_rest', 0) - a.get('away_rest', 0)),
        'QB impact': a.get('away_qb', 0) - a.get('home_qb', 0),
    }
    margin = sum(parts.values())
    total = max(28, min(65, (home['points_for'] + away['points_against'] + away['points_for'] + home['points_against']) / 2))
    hs = max(0, round((total + margin) / 2))
    aws = max(0, round((total - margin) / 2))
    if hs == aws:
        if margin >= 0: hs += 1
        else: aws += 1
    probability = max(.05, min(.95, 1 / (1 + math.exp(-margin / 7))))
    return {'home_probability': round(probability * 100, 1), 'home_score': hs, 'away_score': aws,
            'winner': 'home' if margin >= 0 else 'away', 'margin': round(margin, 2),
            'factors': {k: round(v, 2) for k, v in parts.items()}, 'version': VERSION}
