"""SQLite 持久层：书 / 页 / 块。"""
import hashlib
import json
import os
import sqlite3
import time

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS books (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL,
  author TEXT DEFAULT '',
  year TEXT DEFAULT '',
  lang TEXT DEFAULT '',
  tags TEXT DEFAULT '',
  source_path TEXT DEFAULT '',
  stored_path TEXT DEFAULT '',
  sha256 TEXT DEFAULT '',
  page_count INTEGER DEFAULT 0,
  chunk_count INTEGER DEFAULT 0,
  added_at TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS pages (
  book_id INTEGER NOT NULL,
  page_no INTEGER NOT NULL,
  text TEXT DEFAULT '',
  PRIMARY KEY (book_id, page_no)
);
CREATE TABLE IF NOT EXISTS chunks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  book_id INTEGER NOT NULL,
  ord INTEGER NOT NULL,
  page_start INTEGER NOT NULL,
  page_end INTEGER NOT NULL,
  text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_book ON chunks(book_id);
"""


def connect():
    config.ensure_dirs()
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def file_sha256(path, limit_bytes=None):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            block = f.read(1024 * 1024)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def slugify(text):
    import re
    text = text.lower().strip()
    keep = []
    for ch in text:
        if ch.isalnum() and ord(ch) < 128:
            keep.append(ch)
        elif '\u4e00' <= ch <= '\u9fff':
            keep.append(ch)
        elif ch in ' -_':
            keep.append('-')
    s = re.sub(r'-{2,}', '-', ''.join(keep)).strip('-')
    return s or 'book'


def get_book(conn, ident):
    """ident 可以是 id、slug 或标题片段。"""
    row = None
    if isinstance(ident, int) or (isinstance(ident, str) and ident.isdigit()):
        row = conn.execute('SELECT * FROM books WHERE id=?', (int(ident),)).fetchone()
    if row is None:
        row = conn.execute('SELECT * FROM books WHERE slug=?', (ident,)).fetchone()
    if row is None:
        row = conn.execute('SELECT * FROM books WHERE title LIKE ? ORDER BY id LIMIT 1',
                           (f'%{ident}%',)).fetchone()
    return row


def add_book(conn, *, slug, title, author='', year='', lang='', tags='',
             source_path='', stored_path='', sha=None):
    existing = conn.execute('SELECT * FROM books WHERE slug=?', (slug,)).fetchone()
    if existing:
        return existing, False
    cur = conn.execute(
        'INSERT INTO books (slug,title,author,year,lang,tags,source_path,stored_path,sha256,added_at)'
        ' VALUES (?,?,?,?,?,?,?,?,?,?)',
        (slug, title, author, year, lang, tags, source_path, stored_path, sha or '',
         time.strftime('%Y-%m-%dT%H:%M:%S')),
    )
    return conn.execute('SELECT * FROM books WHERE id=?', (cur.lastrowid,)).fetchone(), True


def save_pages(conn, book_id, pages):
    conn.executemany(
        'INSERT OR REPLACE INTO pages (book_id,page_no,text) VALUES (?,?,?)',
        [(book_id, pno, text) for pno, text in pages],
    )


def save_chunks(conn, book_id, chunks):
    conn.execute('DELETE FROM chunks WHERE book_id=?', (book_id,))
    conn.executemany(
        'INSERT INTO chunks (book_id,ord,page_start,page_end,text) VALUES (?,?,?,?,?)',
        [(book_id, o, ps, pe, body) for o, ps, pe, body in chunks],
    )


def finalize_book(conn, book_id, page_count, chunk_count):
    conn.execute('UPDATE books SET page_count=?, chunk_count=? WHERE id=?',
                 (page_count, chunk_count, book_id))


def all_chunks(conn):
    rows = conn.execute(
        'SELECT c.id, c.book_id, c.ord, c.page_start, c.page_end, c.text,'
        ' b.title AS book_title, b.slug AS book_slug'
        ' FROM chunks c JOIN books b ON b.id=c.book_id'
    ).fetchall()
    return rows


def page_text(conn, book_id, page_no):
    row = conn.execute('SELECT text FROM pages WHERE book_id=? AND page_no=?',
                       (book_id, page_no)).fetchone()
    return row['text'] if row else ''


def list_books(conn):
    return conn.execute('SELECT * FROM books ORDER BY id').fetchall()


def export_json(conn, path):
    books = []
    for b in list_books(conn):
        books.append({
            'id': b['id'], 'slug': b['slug'], 'title': b['title'],
            'author': b['author'], 'year': b['year'], 'lang': b['lang'],
            'tags': b['tags'], 'pageCount': b['page_count'],
            'chunkCount': b['chunk_count'], 'addedAt': b['added_at'],
        })
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'books': books}, f, ensure_ascii=False, indent=2)
    return books
