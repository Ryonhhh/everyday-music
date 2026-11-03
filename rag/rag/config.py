"""路径与常量配置。"""
import os

RAG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(RAG_DIR)
PYLIBS = os.path.join(RAG_DIR, '.pylibs')
BOOKS_DIR = os.path.join(RAG_DIR, 'books')
DB_DIR = os.path.join(RAG_DIR, 'db')
DB_PATH = os.path.join(DB_DIR, 'rag.db')
INDEX_CACHE = os.path.join(DB_DIR, 'bm25.cache.json')
DATA_DIR = os.path.join(ROOT, 'data')

CHUNK_CHARS = 1100
CHUNK_OVERLAP = 160
MIN_CHUNK_CHARS = 120


def ensure_dirs():
    for d in (BOOKS_DIR, DB_DIR, DATA_DIR):
        os.makedirs(d, exist_ok=True)
