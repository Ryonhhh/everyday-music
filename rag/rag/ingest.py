"""入库流程：把一本 PDF 解析并写入知识库。

命令行与本地网页上传共用这里的实现。
"""
import os
import shutil
import time

from . import chunker, config, pdftext, store


def ingest_path(path, *, title=None, author='', year='', lang='', tags='',
                slug=None, force=False, copy_into_library=True, log=print):
    """解析并入库一本 PDF，返回 (book_row, created)。"""
    if not os.path.isfile(path):
        raise FileNotFoundError(path)

    config.ensure_dirs()
    title = title or pdftext.book_title_guess(path)
    slug = slug or store.slugify(title)
    sha = store.file_sha256(path)

    conn = store.connect()
    try:
        book, created = store.add_book(
            conn, slug=slug, title=title, author=author, year=year, lang=lang,
            tags=tags, source_path=os.path.abspath(path), stored_path='', sha=sha,
        )
        if not created and not force:
            log(f'已存在，跳过：{book["title"]}（slug={slug}）；如需重建请用 --force')
            return book, False
        if not created and force:
            log(f'已存在，按 --force 重建：{book["title"]}')

        log(f'解析 PDF：{os.path.basename(path)}')
        t0 = time.time()
        pages = pdftext.extract_pages(path)
        total = sum(len(t) for _, t in pages)
        log(f'  {len(pages)} 页，{total:,} 字符，{time.time() - t0:.1f}s')

        store.save_pages(conn, book['id'], pages)
        chunks = chunker.chunk_pages(pages)
        log(f'  切分 {len(chunks)} 个检索块')
        store.save_chunks(conn, book['id'], chunks)
        store.finalize_book(conn, book['id'], len(pages), len(chunks))
        conn.commit()  # 先落库，后面拷贝失败也不丢数据

        if copy_into_library:
            stored = os.path.join(config.BOOKS_DIR, f'{slug}.pdf')
            if os.path.abspath(path) != os.path.abspath(stored):
                try:
                    if os.path.exists(stored):
                        os.remove(stored)
                    shutil.copy2(path, stored)
                except OSError as exc:
                    log(f'  [warn] 未能复制书籍副本（{exc.__class__.__name__}），源文件仍在原处')
                    stored = os.path.abspath(path)
            conn.execute('UPDATE books SET stored_path=? WHERE id=?', (stored, book['id']))
            conn.commit()

        log(f'完成：{title}  →  id={book["id"]}  slug={slug}')
        return book, True
    finally:
        conn.close()
