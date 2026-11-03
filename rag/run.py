"""本地知识库启动器。

用法：
  python rag/run.py add "书.pdf" --title "书名" --author "作者"
  python rag/run.py list
  python rag/run.py search "五度相生律"
  python rag/run.py serve
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rag.cli import main  # noqa: E402

if __name__ == '__main__':
    sys.exit(main())
