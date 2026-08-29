import re

_BLOCK_SPLIT = re.compile(r"(?=^#{1,6}\s)|\n\s*\n", re.MULTILINE)


def chunk_markdown(text: str, *, max_chars: int = 1200, overlap: int = 100) -> list[str]:
    text = text.replace("\r\n", "\n").strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    blocks = [b.strip() for b in _BLOCK_SPLIT.split(text) if b and b.strip()]
    if not blocks:
        return _window_split(text, max_chars, overlap)

    chunks: list[str] = []
    current = ""
    for block in blocks:
        if len(block) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_window_split(block, max_chars, overlap))
            continue
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) <= max_chars:
            current = candidate
            continue
        chunks.append(current)
        if overlap > 0 and current:
            prefix = current[-overlap:].lstrip()
            current = f"{prefix}\n\n{block}" if prefix else block
            if len(current) > max_chars:
                current = block
        else:
            current = block
    if current:
        chunks.append(current)
    return chunks


def _window_split(text: str, max_chars: int, overlap: int) -> list[str]:
    step = max(max_chars - overlap, 1)
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        out.append(text[i : i + max_chars])
        i += step
    return out
