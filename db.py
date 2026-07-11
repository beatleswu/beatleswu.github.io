from psycopg2.extras import DictCursor
from psycopg2.pool import ThreadedConnectionPool
import os
import re
import threading

DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://go:go@postgres:5432/go_odyssey')

# ── 連線池：避免每個請求都重新 TCP 連線 + 認證（單行程多執行緒）──
_pool = None
_pool_lock = threading.Lock()

def _get_pool():
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = ThreadedConnectionPool(
                    minconn=2, maxconn=15, dsn=DATABASE_URL)
    return _pool

def translate_placeholders(sql):
    if not sql:
        return sql
    
    # Translate INSERT OR IGNORE INTO to INSERT INTO ... ON CONFLICT DO NOTHING
    if 'insert or ignore' in sql.lower():
        sql = re.sub(r'(?i)\bINSERT\s+OR\s+IGNORE\s+INTO\b', 'INSERT INTO', sql)
        if 'on conflict' not in sql.lower():
            sql = sql.strip()
            has_semicolon = sql.endswith(';')
            if has_semicolon:
                sql = sql[:-1].strip()
            sql += ' ON CONFLICT DO NOTHING'
            if has_semicolon:
                sql += ';'

    # If the SQL has no ? placeholders, it's already using native %s syntax — skip translation
    if '?' not in sql:
        return sql
    chars = []
    in_quote = False
    quote_char = None
    i = 0
    while i < len(sql):
        c = sql[i]
        if c == "'" or c == '"':
            if not in_quote:
                in_quote = True
                quote_char = c
            elif quote_char == c:
                if i + 1 < len(sql) and sql[i+1] == c:
                    chars.append(c)
                    chars.append(c)
                    i += 2
                    continue
                else:
                    in_quote = False
                    quote_char = None
        elif c == '%' and not in_quote:
            chars.append('%%')
            i += 1
            continue
        elif c == '?' and not in_quote:
            chars.append('%s')
            i += 1
            continue
        chars.append(c)
        i += 1
    return "".join(chars)

class PostgresCursorWrapper:
    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, sql, parameters=None):
        processed_sql = translate_placeholders(sql)
        if parameters is not None:
            self._cursor.execute(processed_sql, parameters)
        else:
            self._cursor.execute(processed_sql)
        return self

    def executemany(self, sql, seq_of_parameters):
        processed_sql = translate_placeholders(sql)
        self._cursor.executemany(processed_sql, seq_of_parameters)
        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def description(self):
        return self._cursor.description

    def close(self):
        self._cursor.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._cursor.close()

    def __getattr__(self, name):
        return getattr(self._cursor, name)

class PostgresConnectionWrapper:
    def __init__(self, conn, pooled=False):
        self._conn = conn
        self._row_factory = None
        self._pooled = pooled
        self._released = False

    def cursor(self, *args, **kwargs):
        cursor = self._conn.cursor(*args, **kwargs)
        return PostgresCursorWrapper(cursor)

    def execute(self, sql, parameters=None):
        cursor = self.cursor()
        cursor.execute(sql, parameters)
        return cursor

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        """歸還連線池（或關閉非池連線）。冪等：重複呼叫安全。"""
        if self._released:
            return
        self._released = True
        if self._pooled:
            try:
                # 連線已壞（如 PG 重啟）→ 丟棄不回池
                _get_pool().putconn(self._conn, close=bool(self._conn.closed))
            except Exception:
                try: self._conn.close()
                except Exception: pass
        else:
            self._conn.close()

    @property
    def row_factory(self):
        return self._row_factory

    @row_factory.setter
    def row_factory(self, value):
        self._row_factory = value

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type:
                self._conn.rollback()
            else:
                self._conn.commit()
        finally:
            self.close()

    def __getattr__(self, name):
        return getattr(self._conn, name)

def get_db():
    pool = _get_pool()
    conn = pool.getconn()
    # 撿到壞連線（PG 重啟後殘留）→ 丟棄重拿一次
    if conn.closed:
        pool.putconn(conn, close=True)
        conn = pool.getconn()
    conn.cursor_factory = DictCursor
    return PostgresConnectionWrapper(conn, pooled=True)
