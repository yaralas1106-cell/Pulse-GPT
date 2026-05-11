"""
rag/parsers.py — PDF/文本解析 → List[dict]
每个 chunk dict: {text, source, doc_type, page, section, chunk_id}
"""
import re
import uuid
import pickle
import html as html_lib
from pathlib import Path
from typing import Iterator

import fitz  # pymupdf

from rag.config import DOCS, CHUNK_SIZE, CHUNK_OVERLAP


def _extract_page_text(page: fitz.Page) -> str:
    """
    提取页面文字，自动处理 CJK 字体乱码问题。
    优先用 HTML 模式（保留 Unicode 实体），回退到普通文本模式。
    """
    # 检测是否有 CJK 字体
    blocks = page.get_text("dict")["blocks"]
    has_cjk_font = any(
        "PingFang" in span.get("font", "") or
        "CJK" in span.get("font", "") or
        "Noto" in span.get("font", "") or
        "Hei" in span.get("font", "") or
        "Song" in span.get("font", "") or
        "Kai" in span.get("font", "")
        for b in blocks if b.get("type") == 0
        for line in b.get("lines", [])
        for span in line.get("spans", [])
    )

    if has_cjk_font:
        # HTML 模式：实体编码保留了正确的 Unicode
        html_text = page.get_text("html")
        # 移除 HTML 标签，解码实体
        text = re.sub(r"<[^>]+>", " ", html_text)
        text = html_lib.unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        return text
    else:
        return page.get_text("text").strip()


# ── 文本切分（不依赖 langchain）────────────────────────────────────────────────

def _split_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """按字符递归切分，优先在段落/句子边界切割"""
    separators = ["\n\n", "\n", "。", ".", "！", "？", "；", " "]
    if len(text) <= size:
        return [text.strip()] if text.strip() else []

    for sep in separators:
        parts = text.split(sep)
        if len(parts) == 1:
            continue
        chunks, current = [], ""
        for part in parts:
            candidate = current + sep + part if current else part
            if len(candidate) > size:
                if current.strip():
                    chunks.append(current.strip())
                current = text[max(0, len(current) - overlap):] + sep + part if overlap else part
            else:
                current = candidate
        if current.strip():
            chunks.append(current.strip())
        if chunks:
            return chunks

    # 硬切
    return [text[i:i + size].strip() for i in range(0, len(text), size - overlap) if text[i:i + size].strip()]


def _detect_section(text: str, page: int) -> str:
    """从文本头部提取章节标题（简单启发式）"""
    lines = text.strip().split("\n")
    for line in lines[:5]:
        line = line.strip()
        if 3 < len(line) < 80 and not line.endswith("。"):
            # 排除纯数字行
            if not re.match(r"^[\d\s\.]+$", line):
                return line
    return f"Page {page}"


# ── PDF → chunks ──────────────────────────────────────────────────────────────

def parse_pdf(
    pdf_path: Path,
    source_key: str,
    doc_type: str,
    page_start: int = 0,
    page_end: int | None = None,
    verbose: bool = True,
) -> Iterator[dict]:
    """逐页解析 PDF，切分成 chunks，yield dict"""
    doc = fitz.open(str(pdf_path))
    total = len(doc)
    end = min(page_end or total, total)

    for page_num in range(page_start, end):
        if verbose and page_num % 50 == 0:
            print(f"  [{source_key}] parsing page {page_num}/{end}...")
        page = doc[page_num]
        text = _extract_page_text(page)
        if not text or len(text) < 20:
            continue
        section = _detect_section(text, page_num + 1)
        for chunk in _split_text(text):
            if len(chunk) < 30:
                continue
            yield {
                "chunk_id": str(uuid.uuid4()),
                "text": chunk,
                "source": source_key,
                "doc_type": doc_type,
                "page": page_num + 1,
                "section": section,
            }
    doc.close()


def parse_tutorial_dir(dir_path: Path, source_key: str = "music_tutorial") -> Iterator[dict]:
    """扫描目录下所有 PDF，逐个解析"""
    pdfs = sorted(dir_path.glob("*.pdf"))
    print(f"[{source_key}] 发现 {len(pdfs)} 个 PDF")
    for pdf_path in pdfs:
        lesson_name = pdf_path.stem
        for chunk in parse_pdf(pdf_path, source_key, "tutorial", verbose=False):
            chunk["lesson"] = lesson_name
            yield chunk


# ── 缓存层：避免重复解析 ──────────────────────────────────────────────────────

def load_or_parse_chunks(cache_path: Path, source_key: str) -> list[dict]:
    """如有缓存直接加载，否则重新解析并缓存"""
    if cache_path.exists():
        print(f"[cache] 加载 {source_key} ({cache_path.name})")
        with open(cache_path, "rb") as f:
            return pickle.load(f)

    print(f"[parse] 解析 {source_key} ...")
    cfg = DOCS[source_key]

    if source_key == "music_tutorial":
        chunks = list(parse_tutorial_dir(cfg["path"], source_key))
    else:
        chunks = list(parse_pdf(cfg["path"], source_key, cfg["type"]))

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "wb") as f:
        pickle.dump(chunks, f)
    print(f"[parse] {source_key}: {len(chunks)} chunks → 已缓存")
    return chunks
