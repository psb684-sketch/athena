"""SQLite schema, connections, and transaction boundaries. No external packages."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA_VERSION = "3"
TRASH_SCHEMA = """
CREATE TABLE IF NOT EXISTS trash (
 id INTEGER PRIMARY KEY, entity TEXT NOT NULL, entity_id INTEGER NOT NULL,
 label TEXT NOT NULL, impact TEXT NOT NULL, deleted_at TEXT NOT NULL,
 restored_at TEXT, purged_at TEXT
);
CREATE TABLE IF NOT EXISTS trash_rows (
 trash_id INTEGER NOT NULL REFERENCES trash(id), table_name TEXT NOT NULL,
 row_id INTEGER NOT NULL, PRIMARY KEY(trash_id,table_name,row_id)
);
CREATE INDEX IF NOT EXISTS idx_trash_rows_lookup ON trash_rows(table_name,row_id);
"""
HISTORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS edit_history (
 id INTEGER PRIMARY KEY, entity TEXT NOT NULL, entity_id INTEGER NOT NULL,
 label TEXT NOT NULL, before_json TEXT NOT NULL, after_json TEXT NOT NULL,
 edited_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_edit_history_entity ON edit_history(entity,entity_id,id);
"""
SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS products (
 id INTEGER PRIMARY KEY, sku TEXT NOT NULL UNIQUE COLLATE NOCASE,
 name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 120),
 spec TEXT NOT NULL DEFAULT '', unit TEXT NOT NULL DEFAULT '개',
 price INTEGER NOT NULL CHECK(typeof(price)='integer' AND price BETWEEN 0 AND 1000000000),
 minimum INTEGER NOT NULL CHECK(typeof(minimum)='integer' AND minimum BETWEEN 0 AND 1000000),
 archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1)), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS partners (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 120),
 contact TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '', address TEXT NOT NULL DEFAULT '',
 note TEXT NOT NULL DEFAULT '', archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1)),
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sales (
 id INTEGER PRIMARY KEY, number TEXT NOT NULL UNIQUE, partner_id INTEGER NOT NULL REFERENCES partners(id),
 partner_name TEXT NOT NULL, day TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('sale','opening')),
 total INTEGER NOT NULL CHECK(typeof(total)='integer' AND total BETWEEN 1 AND 1000000000000),
 note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sale_lines (
 id INTEGER PRIMARY KEY, sale_id INTEGER NOT NULL REFERENCES sales(id),
 product_id INTEGER NOT NULL REFERENCES products(id), product_name TEXT NOT NULL,
 spec TEXT NOT NULL, unit TEXT NOT NULL,
 qty INTEGER NOT NULL CHECK(typeof(qty)='integer' AND qty BETWEEN 1 AND 1000000),
 price INTEGER NOT NULL CHECK(typeof(price)='integer' AND price BETWEEN 0 AND 1000000000),
 UNIQUE(sale_id,product_id)
);
CREATE TABLE IF NOT EXISTS returns (
 id INTEGER PRIMARY KEY, sale_id INTEGER NOT NULL REFERENCES sales(id), day TEXT NOT NULL,
 total INTEGER NOT NULL CHECK(typeof(total)='integer' AND total BETWEEN 0 AND 1000000000000),
 note TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS return_lines (
 id INTEGER PRIMARY KEY, return_id INTEGER NOT NULL REFERENCES returns(id),
 sale_line_id INTEGER NOT NULL REFERENCES sale_lines(id),
 qty INTEGER NOT NULL CHECK(typeof(qty)='integer' AND qty BETWEEN 1 AND 1000000),
 UNIQUE(return_id,sale_line_id)
);
CREATE TABLE IF NOT EXISTS payments (
 id INTEGER PRIMARY KEY, sale_id INTEGER NOT NULL REFERENCES sales(id), day TEXT NOT NULL,
 amount INTEGER NOT NULL CHECK(typeof(amount)='integer' AND amount!=0 AND abs(amount)<=1000000000000),
 method TEXT NOT NULL CHECK(method IN ('transfer','cash','card','other')),
 note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS movements (
 id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id), day TEXT NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('opening','receive','adjust','sale','return')),
 qty INTEGER NOT NULL CHECK(typeof(qty)='integer' AND qty!=0 AND abs(qty)<=1000000),
 sale_id INTEGER REFERENCES sales(id), return_id INTEGER REFERENCES returns(id),
 note TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (
 id INTEGER PRIMARY KEY, action TEXT NOT NULL, note TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS requests (key TEXT PRIMARY KEY, result TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_movements_product ON movements(product_id);
CREATE INDEX IF NOT EXISTS idx_sales_partner ON sales(partner_id,day);
CREATE INDEX IF NOT EXISTS idx_sales_day ON sales(day);
CREATE INDEX IF NOT EXISTS idx_payments_sale ON payments(sale_id);
CREATE INDEX IF NOT EXISTS idx_returns_sale ON returns(sale_id);
CREATE INDEX IF NOT EXISTS idx_lines_sale ON sale_lines(sale_id);
CREATE INDEX IF NOT EXISTS idx_return_lines_sale ON return_lines(sale_line_id);
""" + TRASH_SCHEMA + HISTORY_SCHEMA + """
"""
TABLES = ('meta','products','partners','sales','sale_lines','returns','return_lines','payments','movements','audit','requests','trash','trash_rows','edit_history')

def connect(path):
    conn = sqlite3.connect(str(path), timeout=15, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA synchronous=FULL')
    conn.execute('PRAGMA trusted_schema=OFF')
    return conn

def initialize(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as conn:
        # Never silently migrate a database belonging to another application/version.
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if tables:
            if 'meta' not in tables:
                raise ValueError('아테나 데이터 파일이 아닙니다.')
            meta = dict(conn.execute('SELECT key,value FROM meta'))
            if meta.get('app') != 'ATHENA_PC' or meta.get('schema') not in ('1','2',SCHEMA_VERSION):
                raise ValueError('지원하지 않는 데이터 버전입니다. 기존 파일을 보존했습니다.')
            if meta.get('schema') == '1':
                conn.executescript(TRASH_SCHEMA)
                conn.execute("UPDATE meta SET value='2' WHERE key='schema'")
                meta['schema']='2'
            if meta.get('schema') == '2':
                conn.executescript(HISTORY_SCHEMA)
                conn.execute("UPDATE meta SET value=? WHERE key='schema'",(SCHEMA_VERSION,))
        conn.executescript(SCHEMA)
        for key, value in [('app','ATHENA_PC'),('schema',SCHEMA_VERSION),('revision','0'),('business','우리 사업장'),('owner',''),('phone',''),('address','')]:
            conn.execute('INSERT OR IGNORE INTO meta VALUES (?,?)', (key,value))
    conn.close()

@contextmanager
def transaction(path):
    conn = connect(path)
    try:
        conn.execute('BEGIN IMMEDIATE')
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()

def rows(conn, query, args=()):
    return [dict(row) for row in conn.execute(query, args)]

def one(conn, query, args=()):
    row = conn.execute(query,args).fetchone()
    return dict(row) if row else None

def active(table, alias):
    """SQL fragment for rows that are not in an unrestored trash operation."""
    return f"NOT EXISTS (SELECT 1 FROM trash_rows dx JOIN trash tx ON tx.id=dx.trash_id WHERE dx.table_name='{table}' AND dx.row_id={alias}.id AND tx.restored_at IS NULL)"

SALES_QUERY = """
SELECT s.*, COALESCE(r.returned,0) AS returned, COALESCE(p.paid,0) AS paid,
 s.total-COALESCE(r.returned,0) AS net,
 s.total-COALESCE(r.returned,0)-COALESCE(p.paid,0) AS balance,
 c.name AS partner_current_name
FROM (SELECT * FROM sales sx WHERE NOT EXISTS (SELECT 1 FROM trash_rows dx JOIN trash tx ON tx.id=dx.trash_id WHERE dx.table_name='sales' AND dx.row_id=sx.id AND tx.restored_at IS NULL)) s
JOIN partners c ON c.id=s.partner_id
LEFT JOIN (SELECT sale_id,SUM(total) returned FROM returns rx WHERE NOT EXISTS (SELECT 1 FROM trash_rows dx JOIN trash tx ON tx.id=dx.trash_id WHERE dx.table_name='returns' AND dx.row_id=rx.id AND tx.restored_at IS NULL) GROUP BY sale_id) r ON r.sale_id=s.id
LEFT JOIN (SELECT sale_id,SUM(amount) paid FROM payments px WHERE NOT EXISTS (SELECT 1 FROM trash_rows dx JOIN trash tx ON tx.id=dx.trash_id WHERE dx.table_name='payments' AND dx.row_id=px.id AND tx.restored_at IS NULL) GROUP BY sale_id) p ON p.sale_id=s.id
"""
