import sqlite3
import json
from datetime import datetime
from datetime import timedelta
from flask import Flask, g, render_template, request, jsonify, abort, send_from_directory
from flask_cors import CORS
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, 'data.db')

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def query_db(query, args=(), one=False):
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv

def init_db():
    db = get_db()
    db.executescript('''
    CREATE TABLE IF NOT EXISTS menu (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        price REAL NOT NULL,
        description TEXT,
    available INTEGER DEFAULT 1,
    max_qty INTEGER DEFAULT 3,
    category TEXT DEFAULT 'General'
    );

    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        table_number TEXT,
        items TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL
    );
    ''')
    db.commit()

    # seed menu if empty
    cur = db.execute('SELECT COUNT(1) as c FROM menu')
    c = cur.fetchone()[0]
    if c == 0:
        items = [
            ('Idli', 1.50, 'Steamed rice cake'),
            ('Dosa', 2.50, 'Crispy lentil crepe'),
            ('Chole Bhature', 4.00, 'Spicy chickpeas with fried bread'),
            ('Thali', 6.50, 'Mixed dishes served on a platter')
        ]
        db.executemany('INSERT INTO menu (name, price, description) VALUES (?, ?, ?)', items)
        db.commit()

    # ensure `available` column exists for older DBs (safe migration)
    cur = db.execute("PRAGMA table_info(menu)")
    cols = [r[1] for r in cur.fetchall()]
    if 'available' not in cols:
        try:
            db.execute('ALTER TABLE menu ADD COLUMN available INTEGER DEFAULT 1')
            db.commit()
        except Exception:
            pass
    if 'max_qty' not in cols:
        try:
            db.execute('ALTER TABLE menu ADD COLUMN max_qty INTEGER DEFAULT 10')
            db.commit()
        except Exception:
            pass

def ensure_menu_columns():
    # idempotent: make sure menu table has expected columns for older DBs
    db = get_db()
    try:
        cur = db.execute("PRAGMA table_info(menu)")
        cols = [r[1] for r in cur.fetchall()]
        if 'available' not in cols:
            try:
                db.execute('ALTER TABLE menu ADD COLUMN available INTEGER DEFAULT 1')
                db.commit()
            except Exception:
                pass
        if 'max_qty' not in cols:
            try:
                db.execute('ALTER TABLE menu ADD COLUMN max_qty INTEGER DEFAULT 10')
                db.commit()
            except Exception:
                pass
        if 'category' not in cols:
            try:
                db.execute("ALTER TABLE menu ADD COLUMN category TEXT DEFAULT 'General'")
                db.commit()
            except Exception:
                pass
    except Exception:
        # pragma may fail if menu table missing; leave init_db to handle creation
        pass

# Initialize the database inside the application context so it works
try:
    with app.app_context():
        init_db()
except Exception:
    # If initialization fails here (for example when running tests or import-time
    # checks), the app will attempt to initialize on first request.
    pass

# UI routes
@app.route('/')
def index():
    ensure_menu_columns()
    menu = query_db('SELECT * FROM menu ORDER BY id')
    menu_list = [dict(m) for m in menu]
    # ensure category exists and sort by category for the template
    for m in menu_list:
        m['category'] = m.get('category') or 'General'
    menu_list.sort(key=lambda x: (x.get('category') or 'General', x.get('id') or 0))
    return render_template('index.html', menu=menu_list)

@app.route('/kitchen')
def kitchen():
    return render_template('kitchen.html')


@app.route('/summary')
def summary_page():
    return render_template('summary.html')


@app.route('/reports')
def reports():
    return render_template('reports.html')

# API routes
@app.route('/api/menu')
def api_menu():
    try:
        ensure_menu_columns()
        menu = query_db('SELECT * FROM menu ORDER BY id')
        # convert availability to boolean and ensure fields exist
        out = []
        for m in menu:
            row = dict(m)
            row['available'] = bool(row.get('available', 1))
            row['max_qty'] = int(row.get('max_qty') or 10)
            row['category'] = row.get('category') or 'General'
            out.append(row)
        # sort by category then id for stable client rendering
        out.sort(key=lambda x: (x.get('category') or 'General', x.get('id') or 0))
        return jsonify(out)
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        # include traceback in response to aid local debugging (dev only)
        return jsonify({'error': str(e), 'traceback': tb}), 500


@app.route('/api/menu', methods=['POST'])
def create_menu_item():
    data = request.get_json() or {}
    ensure_menu_columns()
    name = (data.get('name') or '').strip()
    price_in = data.get('price')

    if not name:
        return jsonify({'error': 'name required'}), 400

    # Try to find existing item by name (case-insensitive)
    existing = query_db('SELECT * FROM menu WHERE LOWER(name) = LOWER(?)', (name,), one=True)
    db = get_db()

    # If exists, treat this POST as an update of provided fields
    if existing:
        to_update = {}
        # optional fields
        if price_in is not None:
            try:
                price = float(price_in)
                if price < 0:
                    return jsonify({'error': 'price must be non-negative'}), 400
                to_update['price'] = price
            except Exception:
                return jsonify({'error': 'invalid price'}), 400
        if 'description' in data:
            to_update['description'] = data.get('description') or ''
        if 'available' in data:
            to_update['available'] = 1 if bool(data.get('available')) else 0
        if 'max_qty' in data:
            try:
                mq = int(data.get('max_qty') or 10)
                if mq < 1:
                    mq = 1
                to_update['max_qty'] = mq
            except Exception:
                to_update['max_qty'] = 10
        if 'category' in data:
            to_update['category'] = data.get('category') or 'General'

        if not to_update:
            # nothing to change
            r = dict(existing)
            r['available'] = bool(r.get('available', 1))
            r['max_qty'] = int(r.get('max_qty') or 10)
            r['category'] = r.get('category') or 'General'
            return jsonify(r), 200

        # build update
        fields = []
        vals = []
        for k, v in to_update.items():
            fields.append(f"{k} = ?")
            vals.append(v)
        vals.append(existing['id'])
        try:
            cur = db.execute('UPDATE menu SET ' + ','.join(fields) + ' WHERE id = ?', vals)
            db.commit()
        except Exception as e:
            import traceback
            traceback.print_exc()
            return jsonify({'error': str(e)}), 500
        row = query_db('SELECT * FROM menu WHERE id = ?', (existing['id'],), one=True)
        r = dict(row)
        r['available'] = bool(r.get('available', 1))
        r['max_qty'] = int(r.get('max_qty') or 10)
        r['category'] = r.get('category') or 'General'
        r['updated'] = True
        return jsonify(r), 200

    # Not existing: create new item (price required)
    if price_in is None:
        return jsonify({'error': 'price required for new item'}), 400
    try:
        price = float(price_in)
        if price < 0:
            return jsonify({'error': 'price must be non-negative'}), 400
    except Exception:
        return jsonify({'error': 'invalid price'}), 400

    description = data.get('description') or ''
    category = data.get('category') or 'General'
    available = 1 if data.get('available', True) else 0
    try:
        max_qty = int(data.get('max_qty') or 10)
        if max_qty < 1:
            max_qty = 1
    except Exception:
        max_qty = 10

    try:
        cur = db.execute('INSERT INTO menu (name, price, description, available, max_qty, category) VALUES (?, ?, ?, ?, ?, ?)',
                         (name, price, description, available, max_qty, category))
        db.commit()
    except sqlite3.IntegrityError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    row = query_db('SELECT * FROM menu WHERE id = ?', (cur.lastrowid,), one=True)
    r = dict(row)
    r['available'] = bool(r.get('available', 1))
    r['max_qty'] = int(r.get('max_qty') or 10)
    r['category'] = r.get('category') or 'General'
    r['created'] = True
    return jsonify(r), 201


@app.route('/api/menu/<int:item_id>', methods=['PUT'])
def update_menu_item(item_id):
    ensure_menu_columns()
    data = request.get_json() or {}
    fields = []
    vals = []
    for key in ('name', 'price', 'description', 'available', 'max_qty', 'category'):
        if key in data:
            val = data[key]
            if key == 'available':
                val = 1 if bool(val) else 0
            elif key == 'price':
                # validate price
                try:
                    if val is None:
                        return jsonify({'error': 'price cannot be null'}), 400
                    val = float(val)
                    if val < 0:
                        return jsonify({'error': 'price must be non-negative'}), 400
                except Exception:
                    return jsonify({'error': 'invalid price'}), 400
            elif key == 'max_qty':
                try:
                    val = int(val)
                    if val < 1:
                        val = 1
                except Exception:
                    val = 10
            fields.append(f"{key} = ?")
            vals.append(val)
    if not fields:
        return jsonify({'error': 'no fields provided'}), 400
    vals.append(item_id)
    db = get_db()
    try:
        cur = db.execute('UPDATE menu SET ' + ','.join(fields) + ' WHERE id = ?', vals)
        db.commit()
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    if cur.rowcount == 0:
        return jsonify({'error': 'not found'}), 404
    row = query_db('SELECT * FROM menu WHERE id = ?', (item_id,), one=True)
    r = dict(row)
    r['available'] = bool(r.get('available', 1))
    r['max_qty'] = int(r.get('max_qty') or 10)
    r['category'] = r.get('category') or 'General'
    return jsonify(r)


@app.route('/api/menu/<int:item_id>/availability', methods=['PUT'])
def set_menu_availability(item_id):
    data = request.get_json() or {}
    avail = data.get('available')
    if avail is None:
        return jsonify({'error': 'available boolean required'}), 400
    val = 1 if bool(avail) else 0
    db = get_db()
    cur = db.execute('UPDATE menu SET available = ? WHERE id = ?', (val, item_id))
    db.commit()
    if cur.rowcount == 0:
        return jsonify({'error': 'not found'}), 404
    row = query_db('SELECT * FROM menu WHERE id = ?', (item_id,), one=True)
    r = dict(row)
    r['available'] = bool(r.get('available', 1))
    return jsonify(r)

@app.route('/api/orders', methods=['GET'])
def api_orders():
    rows = query_db('SELECT * FROM orders ORDER BY id DESC')
    orders = []
    for r in rows:
        o = dict(r)
        o['items'] = json.loads(o['items'])
        orders.append(o)
    return jsonify(orders)

@app.route('/api/orders', methods=['POST'])
def create_order():
    data = request.get_json() or {}
    table = data.get('table') or ''
    items = data.get('items')
    if not items or not isinstance(items, list):
        return jsonify({'error': 'items array required'}), 400
    # validate items against menu: existence, availability, max_qty
    menu_rows = query_db('SELECT id, name, price, available, max_qty FROM menu')
    menu = {r['id']: dict(r) for r in menu_rows}
    problems = []
    for it in items:
        iid = it.get('id')
        qty = int(it.get('qty') or 0)
        if iid not in menu:
            problems.append(f"item id {iid} not found")
            continue
        m = menu[iid]
        if not bool(m.get('available', 1)):
            problems.append(f"{m.get('name')} is currently unavailable")
        maxq = int(m.get('max_qty') or 10)
        if qty < 1:
            problems.append(f"invalid qty for {m.get('name')}")
        elif qty > maxq:
            problems.append(f"{m.get('name')} exceeds max qty ({maxq})")
    if problems:
        return jsonify({'error': 'validation failed', 'details': problems}), 400
    items_json = json.dumps(items)
    created_at = datetime.utcnow().isoformat() + 'Z'
    db = get_db()
    cur = db.execute('INSERT INTO orders (table_number, items, status, created_at) VALUES (?, ?, ?, ?)',
                     (table, items_json, 'pending', created_at))
    db.commit()
    order_id = cur.lastrowid
    row = query_db('SELECT * FROM orders WHERE id = ?', (order_id,), one=True)
    o = dict(row)
    o['items'] = json.loads(o['items'])
    return jsonify(o), 201


def parse_iso(dt_str):
    # created_at stored as ISO with trailing Z
    if not dt_str:
        return None
    if dt_str.endswith('Z'):
        dt_str = dt_str[:-1]
    try:
        return datetime.fromisoformat(dt_str)
    except Exception:
        return None


def get_menu_map():
    rows = query_db('SELECT id, name, price FROM menu')
    return {r['id']: {'name': r['name'], 'price': float(r['price'])} for r in rows}


@app.route('/api/reports')
def api_reports():
    # ?period=day|week|month  & range=N  (defaults: day=7, week=4, month=6)
    period = (request.args.get('period') or 'day').lower()
    try:
        r = int(request.args.get('range') or 0)
    except Exception:
        r = 0
    menu_map = get_menu_map()

    now = datetime.utcnow()
    entries = []

    if period == 'day':
        days = r if r>0 else 7
        for i in range(days-1, -1, -1):
            day = (now - timedelta(days=i)).date()
            start = datetime.combine(day, datetime.min.time())
            end = datetime.combine(day, datetime.max.time())
            rows = query_db('SELECT * FROM orders WHERE created_at BETWEEN ? AND ?', (start.isoformat()+'Z', end.isoformat()+'Z'))
            orders_count = len(rows)
            items_count = 0
            revenue = 0.0
            for rrow in rows:
                oitems = json.loads(rrow['items'])
                for it in oitems:
                    qty = int(it.get('qty') or 0)
                    items_count += qty
                    price = menu_map.get(it.get('id'), {}).get('price', 0.0)
                    revenue += price * qty
            entries.append({'period': day.isoformat(), 'orders': orders_count, 'items': items_count, 'revenue': round(revenue,2)})

    elif period == 'week':
        weeks = r if r>0 else 4
        # week labels are ISO year-week
        for i in range(weeks-1, -1, -1):
            week_start = (now - timedelta(weeks=i)).date()
            # normalize to Monday
            week_start = week_start - timedelta(days=week_start.weekday())
            week_end = week_start + timedelta(days=6)
            start = datetime.combine(week_start, datetime.min.time())
            end = datetime.combine(week_end, datetime.max.time())
            rows = query_db('SELECT * FROM orders WHERE created_at BETWEEN ? AND ?', (start.isoformat()+'Z', end.isoformat()+'Z'))
            orders_count = len(rows)
            items_count = 0
            revenue = 0.0
            for rrow in rows:
                oitems = json.loads(rrow['items'])
                for it in oitems:
                    qty = int(it.get('qty') or 0)
                    items_count += qty
                    price = menu_map.get(it.get('id'), {}).get('price', 0.0)
                    revenue += price * qty
            label = f"{week_start.isoformat()} to {week_end.isoformat()}"
            entries.append({'period': label, 'orders': orders_count, 'items': items_count, 'revenue': round(revenue,2)})

    elif period == 'month':
        months = r if r>0 else 6
        # compute month starts
        def month_start(dt):
            return dt.replace(day=1)
        base = now
        for i in range(months-1, -1, -1):
            m = (base.replace(day=1) - timedelta(days=30*i))
            start = datetime(m.year, m.month, 1)
            # rough end: add 32 days then set to first of next month minus 1 day
            nx = (start + timedelta(days=40)).replace(day=1)
            end = nx - timedelta(seconds=1)
            rows = query_db('SELECT * FROM orders WHERE created_at BETWEEN ? AND ?', (start.isoformat()+'Z', end.isoformat()+'Z'))
            orders_count = len(rows)
            items_count = 0
            revenue = 0.0
            for rrow in rows:
                oitems = json.loads(rrow['items'])
                for it in oitems:
                    qty = int(it.get('qty') or 0)
                    items_count += qty
                    price = menu_map.get(it.get('id'), {}).get('price', 0.0)
                    revenue += price * qty
            label = f"{start.year}-{start.month:02d}"
            entries.append({'period': label, 'orders': orders_count, 'items': items_count, 'revenue': round(revenue,2)})

    else:
        return jsonify({'error':'invalid period'}), 400

    return jsonify({'period': period, 'data': entries})

def update_order_status(order_id):
    data = request.get_json() or {}
    status = data.get('status')
    # allow rejected as an explicit kitchen rejection state
    if status not in ('pending', 'served', 'cancelled', 'rejected'):
        return jsonify({'error': 'invalid status'}), 400
    db = get_db()
    cur = db.execute('UPDATE orders SET status = ? WHERE id = ?', (status, order_id))
    db.commit()
    if cur.rowcount == 0:
        return jsonify({'error': 'not found'}), 404
    row = query_db('SELECT * FROM orders WHERE id = ?', (order_id,), one=True)
    o = dict(row)
    o['items'] = json.loads(o['items'])
    return jsonify(o)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
