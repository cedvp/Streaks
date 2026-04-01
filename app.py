
from flask import Flask, render_template, request, jsonify
import sqlite3
from datetime import date, timedelta

app = Flask(__name__)
DB_PATH = 'streaks.db'


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS alcohol (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        units REAL NOT NULL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS fitness (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        minutes INTEGER NOT NULL,
        comment TEXT DEFAULT ""
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS bike_ride (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        hours REAL NOT NULL,
        dplus INTEGER DEFAULT 0,
        km REAL NOT NULL,
        comment TEXT DEFAULT ""
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS coke (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        units REAL NOT NULL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS hike (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        km REAL NOT NULL,
        dplus INTEGER DEFAULT 0,
        hours REAL NOT NULL,
        comment TEXT DEFAULT ""
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS swimming (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        metres INTEGER NOT NULL,
        minutes INTEGER NOT NULL,
        comment TEXT DEFAULT ""
    )''')
    conn.commit()
    conn.close()


init_db()


@app.route('/')
def index():
    return render_template('index.html')


def _expand_dates(data):
    """Return a list of ISO date strings. Handles single date or from/to range."""
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
    data = request.json
    conn = get_db()
    c = conn.cursor()
    try:
        if activity == 'alcohol':
            dates = _expand_dates(data)
            for d in dates:
                c.execute('INSERT INTO alcohol (date, units) VALUES (?, ?)',
                          (d, float(data['units'])))
        elif activity == 'fitness':
            c.execute('INSERT INTO fitness (date, minutes, comment) VALUES (?, ?, ?)',
                      (data['date'], int(data['minutes']), data.get('comment', '')))
        elif activity == 'bike':
            c.execute('INSERT INTO bike_ride (date, hours, dplus, km, comment) VALUES (?, ?, ?, ?, ?)',
                      (data['date'], float(data['hours']), int(data.get('dplus', 0)),
                       float(data['km']), data.get('comment', '')))
        elif activity == 'coke':
            dates = _expand_dates(data)
            for d in dates:
                c.execute('INSERT INTO coke (date, units) VALUES (?, ?)',
                          (d, float(data['units'])))
        elif activity == 'hike':
            c.execute('INSERT INTO hike (date, km, dplus, hours, comment) VALUES (?, ?, ?, ?, ?)',
                      (data['date'], float(data['km']), int(data.get('dplus', 0)),
                       float(data['hours']), data.get('comment', '')))
        elif activity == 'swimming':
            c.execute('INSERT INTO swimming (date, metres, minutes, comment) VALUES (?, ?, ?, ?)',
                      (data['date'], int(data['metres']), int(data['minutes']), data.get('comment', '')))
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
    conn = get_db()
    c = conn.cursor()
    start_date = (date.today() - timedelta(days=371)).isoformat()
    try:
        if activity == 'alcohol':
            rows = c.execute(
                'SELECT date, SUM(units) as units FROM alcohol WHERE date >= ? GROUP BY date',
                (start_date,)).fetchall()
            data = {r['date']: {'units': r['units']} for r in rows}

        elif activity == 'fitness':
            rows = c.execute(
                'SELECT date, SUM(minutes) as minutes, GROUP_CONCAT(comment, " | ") as comment '
                'FROM fitness WHERE date >= ? GROUP BY date', (start_date,)).fetchall()
            data = {r['date']: {'minutes': r['minutes'], 'comment': r['comment']} for r in rows}

        elif activity == 'bike':
            rows = c.execute(
                'SELECT date, SUM(hours) as hours, SUM(dplus) as dplus, SUM(km) as km, '
                'GROUP_CONCAT(comment, " | ") as comment '
                'FROM bike_ride WHERE date >= ? GROUP BY date', (start_date,)).fetchall()
            data = {r['date']: {'hours': r['hours'], 'dplus': r['dplus'],
                                'km': r['km'], 'comment': r['comment']} for r in rows}

        elif activity == 'coke':
            rows = c.execute(
                'SELECT date, SUM(units) as units FROM coke WHERE date >= ? GROUP BY date',
                (start_date,)).fetchall()
            data = {r['date']: {'units': r['units']} for r in rows}

        elif activity == 'hike':
            rows = c.execute(
                'SELECT date, SUM(km) as km, SUM(dplus) as dplus, SUM(hours) as hours, '
                'GROUP_CONCAT(comment, " | ") as comment '
                'FROM hike WHERE date >= ? GROUP BY date', (start_date,)).fetchall()
            data = {r['date']: {'km': r['km'], 'dplus': r['dplus'],
                                'hours': r['hours'], 'comment': r['comment']} for r in rows}

        elif activity == 'swimming':
            rows = c.execute(
                'SELECT date, SUM(metres) as metres, SUM(minutes) as minutes, '
                'GROUP_CONCAT(comment, " | ") as comment '
                'FROM swimming WHERE date >= ? GROUP BY date', (start_date,)).fetchall()
            data = {r['date']: {'metres': r['metres'], 'minutes': r['minutes'],
                                'comment': r['comment']} for r in rows}

        elif activity == 'sport':
            fit = {r['date']: (r['val'] or 0) for r in c.execute(
                'SELECT date, SUM(minutes) as val FROM fitness WHERE date >= ? GROUP BY date',
                (start_date,)).fetchall()}
            bike = {r['date']: (r['val'] or 0) for r in c.execute(
                'SELECT date, ROUND(SUM(hours)*60) as val FROM bike_ride WHERE date >= ? GROUP BY date',
                (start_date,)).fetchall()}
            hike = {r['date']: (r['val'] or 0) for r in c.execute(
                'SELECT date, ROUND(SUM(hours)*60) as val FROM hike WHERE date >= ? GROUP BY date',
                (start_date,)).fetchall()}
            swim = {r['date']: (r['val'] or 0) for r in c.execute(
                'SELECT date, SUM(minutes) as val FROM swimming WHERE date >= ? GROUP BY date',
                (start_date,)).fetchall()}
            all_dates = set(fit) | set(bike) | set(hike) | set(swim)
            data = {d: {'minutes': fit.get(d, 0) + bike.get(d, 0) + hike.get(d, 0) + swim.get(d, 0)}
                    for d in all_dates}
        else:
            return jsonify({'error': 'Unknown activity'}), 400

        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@app.route('/entries/<activity>')
def get_entries(activity):
    conn = get_db()
    c = conn.cursor()
    try:
        table_map = {
            'alcohol': ('alcohol', 'date DESC'),
            'fitness': ('fitness', 'date DESC'),
            'bike': ('bike_ride', 'date DESC'),
            'coke': ('coke', 'date DESC'),
            'hike': ('hike', 'date DESC'),
            'swimming': ('swimming', 'date DESC'),
        }
        if activity not in table_map:
            return jsonify([])
        table, order = table_map[activity]
        rows = c.execute(f'SELECT * FROM {table} ORDER BY {order} LIMIT 20').fetchall()
        return jsonify([dict(r) for r in rows])
    finally:
        conn.close()


@app.route('/delete/<activity>/<int:entry_id>', methods=['DELETE'])
def delete_entry(activity, entry_id):
    table_map = {
        'alcohol': 'alcohol',
        'fitness': 'fitness',
        'bike': 'bike_ride',
        'coke': 'coke',
        'hike': 'hike',
        'swimming': 'swimming',
    }
    if activity not in table_map:
        return jsonify({'error': 'Unknown activity'}), 400
    conn = get_db()
    try:
        conn.execute(f'DELETE FROM {table_map[activity]} WHERE id = ?', (entry_id,))
        conn.commit()
        return jsonify({'success': True})
    finally:
        conn.close()


if __name__ == '__main__':
    app.run(debug=True, port=5000)
