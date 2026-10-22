"""PDF metin katmanından koordinatlı 'run' (kesintisiz metin parçası) çıkarımı."""
from dataclasses import dataclass


@dataclass
class Run:
    x0: float
    x1: float
    top: float
    size: float
    font: str
    text: str

    @property
    def bold(self) -> bool:
        return "Bold" in self.font

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    def __repr__(self):
        return f"Run({self.x0:.1f},{self.top:.1f},{self.size},{self.text!r})"


def page_runs(page, gap: float = 1.2) -> list[Run]:
    """Karakterleri PDF çizim sırasıyla birleştirir. Taşan (kırpılmış) metinler kendi
    satırına ait kalır; boşluklu sayı sütunları ayrı run olur."""
    runs: list[Run] = []
    cur = None
    for c in page.chars:
        if (cur is not None and abs(c["top"] - cur.top) < 0.5 and c["size"] == cur.size
                and c["x0"] >= cur.x1 - 0.5 and c["x0"] - cur.x1 < gap):
            cur.text += c["text"]
            cur.x1 = c["x1"]
        else:
            cur = Run(c["x0"], c["x1"], c["top"], round(c["size"], 1), c["fontname"], c["text"])
            runs.append(cur)
    out = []
    for r in runs:
        t = r.text.strip()
        if t:
            r.text = t
            out.append(r)
    return out


def courier_lines(page, split_gap: float = 30.0) -> list[tuple[float, float, list[dict]]]:
    """Sabit genişlikli (Courier) cevap dizisi satırları: (top, x0, chars)."""
    lines: dict[float, list] = {}
    for c in page.chars:
        if "Courier" in c["fontname"]:
            lines.setdefault(round(c["top"], 1), []).append(c)
    out = []
    for top in sorted(lines):
        cs = sorted(lines[top], key=lambda c: c["x0"])
        # aynı yükseklikte iki sütunun dizileri olabilir -> büyük boşlukta böl
        seg = [cs[0]]
        for c in cs[1:]:
            if c["x0"] - seg[-1]["x1"] > split_gap:
                out.append((top, seg[0]["x0"], seg))
                seg = []
            seg.append(c)
        out.append((top, seg[0]["x0"], seg))
    return sorted(out, key=lambda t: (t[0], t[1]))


def num(s: str) -> float:
    return float(s.replace("%", "").replace(".", "").replace(",", ".").strip())


def page_tokens(page, gap: float = 1.0, overlap: float = -0.2, line_tol: float = 1.0) -> list[Run]:
    """Karakterleri satır + x sırasına göre token'lara böler (çizim sırasından bağımsız).
    Boşluk karakteri, büyük aralık veya üst üste binme token'ı ayırır. Tablolar için uygundur."""
    chars = sorted(page.chars, key=lambda c: (c["top"], c["x0"]))
    lines: list[list[dict]] = []
    for c in chars:
        if lines and abs(c["top"] - lines[-1][0]["top"]) <= line_tol and c["size"] == lines[-1][0]["size"]:
            lines[-1].append(c)
        else:
            # aynı satırda farklı punto olabilir; mevcut satırlardan uygun olanı ara
            for ln in reversed(lines[-4:]):
                if abs(c["top"] - ln[0]["top"]) <= line_tol and c["size"] == ln[0]["size"]:
                    ln.append(c)
                    break
            else:
                lines.append([c])
    out = []
    for ln in lines:
        ln.sort(key=lambda c: c["x0"])
        cur = None
        for c in ln:
            if c["text"].isspace():
                cur = None
                continue
            d = c["x0"] - cur.x1 if cur else None
            if cur is not None and overlap <= d <= gap:
                cur.text += c["text"]; cur.x1 = c["x1"]
            else:
                cur = Run(c["x0"], c["x1"], c["top"], round(c["size"], 1), c["fontname"], c["text"])
                out.append(cur)
    return out
