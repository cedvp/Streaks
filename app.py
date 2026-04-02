
from flask import Flask, render_template, request, jsonify, session, redirect
import sqlite3
import json
from datetime import date, timedelta

app = Flask(__name__)
app.secret_key = 'streaks-secret-key-change-in-prod'
DB_PATH = 'streaks.db'

USERS = {
    'cedric': 'calypso',
    'caroline': 'easa',
    'admin': 'blabla',
}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS alcohol (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL DEFAULT '',
        date TEXT NOT NULL,
        units REAL NOT NULL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS fitness (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL DEFAULT '',
        date TEXT NOT NULL,
        minutes INTEGER NOT NULL,
        comment TEXT DEFAULT ""
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS bike_ride (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL DEFAULT '',
        date TEXT NOT NULL,
        hours REAL NOT NULL,
        dplus INTEGER DEFAULT 0,
        km REAL NOT NULL,
        comment TEXT DEFAULT ""
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS coke (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL DEFAULT '',
        date TEXT NOT NULL,
        units REAL NOT NULL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS hike (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL DEFAULT '',
        date TEXT NOT NULL,
        km REAL NOT NULL,
        dplus INTEGER DEFAULT 0,
        hours REAL NOT NULL,
        comment TEXT DEFAULT ""
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS swimming (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL DEFAULT '',
        date TEXT NOT NULL,
        metres INTEGER NOT NULL,
        minutes INTEGER NOT NULL,
        comment TEXT DEFAULT ""
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS custom_activities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        name TEXT NOT NULL,
        icon TEXT NOT NULL DEFAULT '📊',
        tracking_type TEXT NOT NULL DEFAULT 'zero',
        fields TEXT NOT NULL DEFAULT '["units"]',
        position INTEGER DEFAULT 0
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS custom_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        activity_id INTEGER NOT NULL,
        user_id TEXT NOT NULL,
        date TEXT NOT NULL,
        data TEXT NOT NULL DEFAULT '{}',
        comment TEXT DEFAULT ''
    )''')
    # Migrate existing tables that may lack user_id
    for table in ['alcohol', 'fitness', 'bike_ride', 'coke', 'hike', 'swimming']:
        cols = [row[1] for row in c.execute(f'PRAGMA table_info({table})').fetchall()]
        if 'user_id' not in cols:
            c.execute(f"ALTER TABLE {table} ADD COLUMN user_id TEXT NOT NULL DEFAULT ''")
    conn.commit()
    conn.close()


init_db()


def current_user():
    return session.get('user')


@app.route('/')
def index():
    if not current_user():
        return redirect('/login')
    return render_template('index.html', current_user=current_user())


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.json
        username = (data.get('username') or '').lower().strip()
        password = data.get('password') or ''
        if username in USERS and USERS[username] == password:
            session['user'] = username
            return jsonify({'success': True})
        return jsonify({'error': 'Invalid username or password'}), 401
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/login')


# ── Custom activities ──────────────────────────────────────────────────────────

@app.route('/custom_activities')
def list_custom_activities():
    user = current_user()
    if not user:
        return jsonify([])
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM custom_activities WHERE user_id=? ORDER BY position, id', (user,)
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d['fields'] = json.loads(d['fields'])
        result.append(d)
    return jsonify(result)


@app.route('/custom_activities', methods=['POST'])
def create_custom_activity():
    user = current_user()
    if not user:
        return jsonify({'error': 'Not authenticated'}), 401
    data = request.json
    conn = get_db()
    try:
        conn.execute(
            'INSERT INTO custom_activities (user_id, name, icon, tracking_type, fields) VALUES (?, ?, ?, ?, ?)',
            (user, data['name'], data.get('icon', '📊'), data['tracking_type'], json.dumps(data['fields']))
        )
        conn.commit()
        row = conn.execute('SELECT last_insert_rowid() as id').fetchone()
        return jsonify({'success': True, 'id': row['id']})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@app.route('/custom_activities/<int:act_id>', methods=['DELETE'])
def delete_custom_activity(act_id):
    user = current_user()
    if not user:
        return jsonify({'error': 'Not authenticated'}), 401
    conn = get_db()
    try:
        conn.execute('DELETE FROM custom_entries WHERE activity_id=? AND user_id=?', (act_id, user))
        conn.execute('DELETE FROM custom_activities WHERE id=? AND user_id=?', (act_id, user))
        conn.commit()
        return jsonify({'success': True})
    finally:
        conn.close()


@app.route('/data/custom/<int:act_id>')
def get_custom_data(act_id):
    user = current_user()
    if not user:
        return jsonify({'error': 'Not authenticated'}), 401
    conn = get_db()
    c = conn.cursor()
    start_date = (date.today() - timedelta(days=371)).isoformat()
    try:
        act = c.execute(
            'SELECT * FROM custom_activities WHERE id=? AND user_id=?', (act_id, user)
        ).fetchone()
        if not act:
            return jsonify({})
        fields = json.loads(act['fields'])
        rows = c.execute(
            'SELECT date, data FROM custom_entries WHERE activity_id=? AND user_id=? AND date >= ?',
            (act_id, user, start_date)
        ).fetchall()
        result = {}
        for row in rows:
            d = row['date']
            entry_data = json.loads(row['data'])
            if d not in result:
                result[d] = {f: 0 for f in fields}
            for f in fields:
                result[d][f] = round((result[d].get(f) or 0) + (entry_data.get(f) or 0), 4)
        return jsonify(result)
    finally:
        conn.close()


@app.route('/entries/custom/<int:act_id>')
def get_custom_entries(act_id):
    user = current_user()
    if not user:
        return jsonify({'error': 'Not authenticated'}), 401
    conn = get_db()
    start_date = (date.today() - timedelta(days=371)).isoformat()
    try:
        rows = conn.execute(
            'SELECT * FROM custom_entries WHERE activity_id=? AND user_id=? AND date >= ? ORDER BY date DESC',
            (act_id, user, start_date)
        ).fetchall()
        result = []
        for r in rows:
            entry = dict(r)
            entry['data'] = json.loads(entry['data'])
            result.append(entry)
        return jsonify(result)
    finally:
        conn.close()


@app.route('/add/custom/<int:act_id>', methods=['POST'])
def add_custom_entry(act_id):
    user = current_user()
    if not user:
        return jsonify({'error': 'Not authenticated'}), 401
    payload = request.json
    conn = get_db()
    try:
        act = conn.execute(
            'SELECT * FROM custom_activities WHERE id=? AND user_id=?', (act_id, user)
        ).fetchone()
        if not act:
            return jsonify({'error': 'Activity not found'}), 404
        fields = json.loads(act['fields'])
        entry_date = payload.get('date', '')
        comment = payload.get('comment', '')
        data = {}
        for f in fields:
            v = payload.get(f)
            if v is not None and v != '':
                data[f] = float(v)
        conn.execute(
            'INSERT INTO custom_entries (activity_id, user_id, date, data, comment) VALUES (?, ?, ?, ?, ?)',
            (act_id, user, entry_date, json.dumps(data), comment)
        )
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@app.route('/update/custom/<int:act_id>/<int:entry_id>', methods=['PUT'])
def update_custom_entry(act_id, entry_id):
    user = current_user()
    if not user:
        return jsonify({'error': 'Not authenticated'}), 401
    payload = request.json
    conn = get_db()
    try:
        act = conn.execute(
            'SELECT * FROM custom_activities WHERE id=? AND user_id=?', (act_id, user)
        ).fetchone()
        if not act:
            return jsonify({'error': 'Activity not found'}), 404
        fields = json.loads(act['fields'])
        entry_date = payload.get('date', '')
        comment = payload.get('comment', '')
        data = {}
        for f in fields:
            v = payload.get(f)
            if v is not None and v != '':
                data[f] = float(v)
        conn.execute(
            'UPDATE custom_entries SET date=?, data=?, comment=? WHERE id=? AND activity_id=? AND user_id=?',
            (entry_date, json.dumps(data), comment, entry_id, act_id, user)
        )
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@app.route('/delete/custom/<int:act_id>/<int:entry_id>', methods=['DELETE'])
def delete_custom_entry(act_id, entry_id):
    user = current_user()
    if not user:
        return jsonify({'error': 'Not authenticated'}), 401
    conn = get_db()
    try:
        conn.execute(
            'DELETE FROM custom_entries WHERE id=? AND activity_id=? AND user_id=?',
            (entry_id, act_id, user)
        )
        conn.commit()
        return jsonify({'success': True})
    finally:
        conn.close()


@app.route('/delete_all/custom/<int:act_id>', methods=['DELETE'])
def delete_all_custom_entries(act_id):
    user = current_user()
    if not user:
        return jsonify({'error': 'Not authenticated'}), 401
    conn = get_db()
    try:
        conn.execute('DELETE FROM custom_entries WHERE activity_id=? AND user_id=?', (act_id, user))
        conn.commit()
        return jsonify({'success': True})
    finally:
        conn.close()


# ── Standard activity helpers ──────────────────────────────────────────────────

def _expand_dates(data):
    if data.get('date_from') and data.get('date_to'):
        start = date.fromisoformat(data['date_from'])
        end = date.fromisoformat(data['date_to'])
        if end < start:
            start, end = end, start
        days = []
        cur = start
        while cur <= end:
            days.append(cur.isoformat())
            cur += timedelta(days=1)
        return days
    return [data['date']]


@app.route('/add/<activity>', methods=['POST'])
def add_entry(activity):
    user = current_user()
    if not user:
        return jsonify({'error': 'Not authenticated'}), 401
    data = request.json
    conn = get_db()
    c = conn.cursor()
    try:
        if activity == 'alcohol':
            dates = _expand_dates(data)
            for d in dates:
                c.execute('INSERT INTO alcohol (user_id, date, units) VALUES (?, ?, ?)',
                          (user, d, float(data['units'])))
        elif activity == 'fitness':
            c.execute('INSERT INTO fitness (user_id, date, minutes, comment) VALUES (?, ?, ?, ?)',
                      (user, data['date'], int(data['minutes']), data.get('comment', '')))
        elif activity == 'bike':
            c.execute('INSERT INTO bike_ride (user_id, date, hours, dplus, km, comment) VALUES (?, ?, ?, ?, ?, ?)',
                      (user, data['date'], float(data['hours']), int(data.get('dplus', 0) or 0),
                       float(data['km']), data.get('comment', '')))
        elif activity == 'coke':
            dates = _expand_dates(data)
            for d in dates:
                c.execute('INSERT INTO coke (user_id, date, units) VALUES (?, ?, ?)',
                          (user, d, float(data['units'])))
        elif activity == 'hike':
            c.execute('INSERT INTO hike (user_id, date, km, dplus, hours, comment) VALUES (?, ?, ?, ?, ?, ?)',
                      (user, data['date'], float(data['km']), int(data.get('dplus', 0) or 0),
                       float(data['hours']), data.get('comment', '')))
        elif activity == 'swimming':
            c.execute('INSERT INTO swimming (user_id, date, metres, minutes, comment) VALUES (?, ?, ?, ?, ?)',
                      (user, data['date'], int(data['metres']), int(data['minutes']), data.get('comment', '')))
        else:
            return jsonify({'error': 'Unknown activity'}), 400
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@app.route('/update/<activity>/<int:entry_id>', methods=['PUT'])
def update_entry(activity, entry_id):
    user = current_user()
    if not user:
        return jsonify({'error': 'Not authenticated'}), 401
    data = request.json
    conn = get_db()
    c = conn.cursor()
    try:
        if activity == 'alcohol':
            c.execute('UPDATE alcohol SET date=?, units=? WHERE id=? AND user_id=?',
                      (data['date'], float(data['units']), entry_id, user))
        elif activity == 'fitness':
            c.execute('UPDATE fitness SET date=?, minutes=?, comment=? WHERE id=? AND user_id=?',
                      (data['date'], int(data['minutes']), data.get('comment', ''), entry_id, user))
        elif activity == 'bike':
            c.execute('UPDATE bike_ride SET date=?, hours=?, dplus=?, km=?, comment=? WHERE id=? AND user_id=?',
                      (data['date'], float(data['hours']), int(data.get('dplus', 0) or 0),
                       float(data['km']), data.get('comment', ''), entry_id, user))
        elif activity == 'coke':
            c.execute('UPDATE coke SET date=?, units=? WHERE id=? AND user_id=?',
                      (data['date'], float(data['units']), entry_id, user))
        elif activity == 'hike':
            c.execute('UPDATE hike SET date=?, km=?, dplus=?, hours=?, comment=? WHERE id=? AND user_id=?',
                      (data['date'], float(data['km']), int(data.get('dplus', 0) or 0),
                       float(data['hours']), data.get('comment', ''), entry_id, user))
        elif activity == 'swimming':
            c.execute('UPDATE swimming SET date=?, metres=?, minutes=?, comment=? WHERE id=? AND user_id=?',
                      (data['date'], int(data['metres']), int(data['minutes']),
                       data.get('comment', ''), entry_id, user))
        else:
            return jsonify({'error': 'Unknown activity'}), 400
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@app.route('/data/<activity>')
def get_data(activity):
    user = current_user()
    if not user:
        return jsonify({'error': 'Not authenticated'}), 401
    conn = get_db()
    c = conn.cursor()
    start_date = (date.today() - timedelta(days=371)).isoformat()
    try:
        if activity == 'alcohol':
            rows = c.execute(
                'SELECT date, SUM(units) as units FROM alcohol WHERE date >= ? AND user_id=? GROUP BY date',
                (start_date, user)).fetchall()
            data = {r['date']: {'units': r['units']} for r in rows}
        elif activity == 'fitness':
            rows = c.execute(
                'SELECT date, SUM(minutes) as minutes, GROUP_CONCAT(comment, " | ") as comment '
                'FROM fitness WHERE date >= ? AND user_id=? GROUP BY date', (start_date, user)).fetchall()
            data = {r['date']: {'minutes': r['minutes'], 'comment': r['comment']} for r in rows}
        elif activity == 'bike':
            rows = c.execute(
                'SELECT date, SUM(hours) as hours, SUM(dplus) as dplus, SUM(km) as km, '
                'GROUP_CONCAT(comment, " | ") as comment '
                'FROM bike_ride WHERE date >= ? AND user_id=? GROUP BY date', (start_date, user)).fetchall()
            data = {r['date']: {'hours': r['hours'], 'dplus': r['dplus'],
                                'km': r['km'], 'comment': r['comment']} for r in rows}
        elif activity == 'coke':
            rows = c.execute(
                'SELECT date, SUM(units) as units FROM coke WHERE date >= ? AND user_id=? GROUP BY date',
                (start_date, user)).fetchall()
            data = {r['date']: {'units': r['units']} for r in rows}
        elif activity == 'hike':
            rows = c.execute(
                'SELECT date, SUM(km) as km, SUM(dplus) as dplus, SUM(hours) as hours, '
                'GROUP_CONCAT(comment, " | ") as comment '
                'FROM hike WHERE date >= ? AND user_id=? GROUP BY date', (start_date, user)).fetchall()
            data = {r['date']: {'km': r['km'], 'dplus': r['dplus'],
                                'hours': r['hours'], 'comment': r['comment']} for r in rows}
        elif activity == 'swimming':
            rows = c.execute(
                'SELECT date, SUM(metres) as metres, SUM(minutes) as minutes, '
                'GROUP_CONCAT(comment, " | ") as comment '
                'FROM swimming WHERE date >= ? AND user_id=? GROUP BY date', (start_date, user)).fetchall()
            data = {r['date']: {'metres': r['metres'], 'minutes': r['minutes'],
                                'comment': r['comment']} for r in rows}
        elif activity == 'sport':
            fit = {r['date']: (r['val'] or 0) for r in c.execute(
                'SELECT date, SUM(minutes) as val FROM fitness WHERE date >= ? AND user_id=? GROUP BY date',
                (start_date, user)).fetchall()}
            bike = {r['date']: (r['val'] or 0) for r in c.execute(
                'SELECT date, ROUND(SUM(hours)*60) as val FROM bike_ride WHERE date >= ? AND user_id=? GROUP BY date',
                (start_date, user)).fetchall()}
            hike = {r['date']: (r['val'] or 0) for r in c.execute(
                'SELECT date, ROUND(SUM(hours)*60) as val FROM hike WHERE date >= ? AND user_id=? GROUP BY date',
                (start_date, user)).fetchall()}
            swim = {r['date']: (r['val'] or 0) for r in c.execute(
                'SELECT date, SUM(minutes) as val FROM swimming WHERE date >= ? AND user_id=? GROUP BY date',
                (start_date, user)).fetchall()}
            all_dates = set(fit) | set(bike) | set(hike) | set(swim)
            data = {d: {'minutes': fit.get(d, 0) + bike.get(d, 0) + hike.get(d, 0) + swim.get(d, 0)}
                    for d in all_dates}
        elif activity == 'food':
            alc = {r['date']: r['units'] for r in c.execute(
                'SELECT date, SUM(units) as units FROM alcohol WHERE date >= ? AND user_id=? GROUP BY date',
                (start_date, user)).fetchall()}
            coke_d = {r['date']: r['units'] for r in c.execute(
                'SELECT date, SUM(units) as units FROM coke WHERE date >= ? AND user_id=? GROUP BY date',
                (start_date, user)).fetchall()}
            all_dates = set(alc) | set(coke_d)
            data = {d: {'alcohol': alc.get(d, None), 'coke': coke_d.get(d, None)} for d in all_dates}
        else:
            return jsonify({'error': 'Unknown activity'}), 400
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@app.route('/entries/<activity>')
def get_entries(activity):
    user = current_user()
    if not user:
        return jsonify({'error': 'Not authenticated'}), 401
    conn = get_db()
    c = conn.cursor()
    start_date = (date.today() - timedelta(days=371)).isoformat()
    try:
        table_map = {
            'alcohol': 'alcohol',
            'fitness': 'fitness',
            'bike': 'bike_ride',
            'coke': 'coke',
            'hike': 'hike',
            'swimming': 'swimming',
        }
        if activity not in table_map:
            return jsonify([])
        table = table_map[activity]
        rows = c.execute(
            f'SELECT * FROM {table} WHERE user_id=? AND date >= ? ORDER BY date DESC',
            (user, start_date)).fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()


@app.route('/delete/<activity>/<int:entry_id>', methods=['DELETE'])
def delete_entry(activity, entry_id):
    user = current_user()
    if not user:
        return jsonify({'error': 'Not authenticated'}), 401
    table_map = {
        'alcohol': 'alcohol', 'fitness': 'fitness', 'bike': 'bike_ride',
        'coke': 'coke', 'hike': 'hike', 'swimming': 'swimming',
    }
    if activity not in table_map:
        return jsonify({'error': 'Unknown activity'}), 400
    conn = get_db()
    try:
        conn.execute(f'DELETE FROM {table_map[activity]} WHERE id=? AND user_id=?', (entry_id, user))
        conn.commit()
        return jsonify({'success': True})
    finally:
        conn.close()


@app.route('/delete_all/<activity>', methods=['DELETE'])
def delete_all_entries(activity):
    user = current_user()
    if not user:
        return jsonify({'error': 'Not authenticated'}), 401
    table_map = {
        'alcohol': 'alcohol', 'fitness': 'fitness', 'bike': 'bike_ride',
        'coke': 'coke', 'hike': 'hike', 'swimming': 'swimming',
    }
    if activity not in table_map:
        return jsonify({'error': 'Unknown activity'}), 400
    conn = get_db()
    try:
        conn.execute(f'DELETE FROM {table_map[activity]} WHERE user_id=?', (user,))
        conn.commit()
        return jsonify({'success': True})
    finally:
        conn.close()


@app.route('/export')
def export_data():
    user = current_user()
    if not user:
        return jsonify({'error': 'Not authenticated'}), 401
    conn = get_db()
    c = conn.cursor()
    table_map = {
        'alcohol': 'alcohol', 'fitness': 'fitness', 'bike': 'bike_ride',
        'coke': 'coke', 'hike': 'hike', 'swimming': 'swimming',
    }
    result = {}
    for activity, table in table_map.items():
        rows = c.execute(f'SELECT * FROM {table} WHERE user_id=? ORDER BY date', (user,)).fetchall()
        result[activity] = [dict(r) for r in rows]
    # Custom activities
    acts = c.execute('SELECT * FROM custom_activities WHERE user_id=? ORDER BY id', (user,)).fetchall()
    result['_custom_activities'] = []
    result['_custom_entries'] = {}
    for act in acts:
        ad = dict(act)
        ad['fields'] = json.loads(ad['fields'])
        result['_custom_activities'].append(ad)
        entries = c.execute(
            'SELECT * FROM custom_entries WHERE activity_id=? AND user_id=? ORDER BY date',
            (act['id'], user)
        ).fetchall()
        parsed = []
        for e in entries:
            ed = dict(e)
            ed['data'] = json.loads(ed['data'])
            parsed.append(ed)
        result['_custom_entries'][str(act['id'])] = parsed
    conn.close()
    return jsonify(result)


@app.route('/import', methods=['POST'])
def import_data():
    user = current_user()
    if not user:
        return jsonify({'error': 'Not authenticated'}), 401
    data = request.json
    conn = get_db()
    c = conn.cursor()
    try:
        table_fields = {
            'alcohol': ('alcohol', ['date', 'units']),
            'fitness': ('fitness', ['date', 'minutes', 'comment']),
            'bike': ('bike_ride', ['date', 'hours', 'dplus', 'km', 'comment']),
            'coke': ('coke', ['date', 'units']),
            'hike': ('hike', ['date', 'km', 'dplus', 'hours', 'comment']),
            'swimming': ('swimming', ['date', 'metres', 'minutes', 'comment']),
        }
        inserted = 0
        for activity, (table, fields) in table_fields.items():
            for row in data.get(activity, []):
                cols = ['user_id'] + fields
                vals = [user] + [row.get(f, '') for f in fields]
                placeholders = ','.join(['?'] * len(cols))
                c.execute(f'INSERT INTO {table} ({",".join(cols)}) VALUES ({placeholders})', vals)
                inserted += 1
        # Import custom activities (remapping IDs)
        id_map = {}
        for act in data.get('_custom_activities', []):
            c.execute(
                'INSERT INTO custom_activities (user_id, name, icon, tracking_type, fields) VALUES (?, ?, ?, ?, ?)',
                (user, act['name'], act.get('icon', '📊'), act['tracking_type'], json.dumps(act['fields']))
            )
            new_id = c.execute('SELECT last_insert_rowid() as id').fetchone()['id']
            id_map[str(act['id'])] = new_id
        for old_id, entries in data.get('_custom_entries', {}).items():
            new_act_id = id_map.get(old_id)
            if not new_act_id:
                continue
            for e in entries:
                c.execute(
                    'INSERT INTO custom_entries (activity_id, user_id, date, data, comment) VALUES (?, ?, ?, ?, ?)',
                    (new_act_id, user, e['date'], json.dumps(e['data']), e.get('comment', ''))
                )
                inserted += 1
        conn.commit()
        return jsonify({'success': True, 'inserted': inserted})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


if __name__ == '__main__':
    app.run(debug=True, port=5000)
