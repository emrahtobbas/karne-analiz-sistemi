"""Supara (Alfa Seri vb.) karne formatı — metin katmanlı PDF.

Yapı: 1-3 sayfa okul net listesi (BES/ÇAP ile aynı şablon) + öğrenci başına 2 sayfa:
  1. sayfa: özet kutuları, puan/sıralama, ders tablosu (sınıf/kurum/genel ortalamalı), cevap ızgaraları
  2. sayfa: kazanım tabloları (S D Y B%)
Bu formatta "Kurum Soru Analizi" yok: soru-kazanım ve A↔B kitapçık eşlemesi inference.py ile çıkarılır.
"""
from __future__ import annotations

import re
from collections import defaultdict

import pdfplumber

from ..pdfutil import Run, num, page_tokens
from ..taxonomy import section_code, subject_code
from .bes_cap import cluster_lines, net_list_tokens, parse_net_list

PARSER_NAME = "supara"
PARSER_VERSION = "0.1.0"
PUBLISHER = "Supara"

NUM = re.compile(r"-?\d[\d,]*")


def _lines(tokens, tol=1.5):
    return [sorted(l, key=lambda r: r.x0) for l in cluster_lines(tokens, tol)]


def page_kind(tokens) -> str:
    texts = {t.text for t in tokens}
    head = " ".join(t.text for t in tokens if t.top < 30)
    if "NET" in head and "LİSTESİ" in head:
        return "net_list"
    if "Öğrenci" in texts and "Anahtarı" in texts and "Katılımlar" in texts:
        return "card_main"
    if "Öğrenci" in texts and "B%" in texts and "Anahtarı" not in texts:
        return "card_kazanim"
    return "unknown"


def detect(pdf) -> float:
    kinds = [page_kind(page_tokens(p)) for p in pdf.pages[: min(8, len(pdf.pages))]]
    if "card_main" in kinds and "card_kazanim" in kinds:
        return 0.95
    return 0.0


def _after(line, label, until=None):
    xs = [t for t in line if t.text == label]
    if not xs:
        return None
    x0 = xs[0].x1
    x1 = next((t.x0 for t in line if t.text == until), 1e9) if until else 1e9
    return " ".join(t.text for t in line if x0 < t.x0 < x1 - 0.5).strip()


def parse_card_main(p, page_no) -> dict:
    toks = page_tokens(p)
    lines = _lines(toks)
    d: dict = {"page": page_no, "percentile": None}
    d["school"] = " ".join(t.text for t in lines[0])
    loc = " ".join(t.text for t in lines[1])
    city, _, district = loc.partition("/")
    d["city"], d["district"] = city.strip(), district.strip()
    d["exam_name"] = " ".join(t.text for t in lines[2])
    who = next(l for l in lines if any(t.text == "Öğrenci" for t in l))
    d["name"] = _after(who, "Öğrenci", "Sınıf")
    d["class_name"] = _after(who, "Sınıf", "Öğr.No")
    d["school_no"] = _after(who, "Öğr.No")

    big = sorted([t for t in toks if t.size >= 18], key=lambda t: t.x0)
    q, c, w, b = (int(num(t.text)) for t in big[:4])
    d["totals"] = {"questions": q, "correct": c, "wrong": w, "blank": b, "net": num(big[4].text)}

    keys5 = ["sube", "kurum", "ilce", "il", "genel"]
    puan_line = next(l for l in lines if l[0].text == "TYT" and len(l) >= 8 and re.fullmatch(r"\d+,\d{3}", l[1].text))
    d["score_type"] = puan_line[0].text
    d["points"] = num(puan_line[1].text)
    d["avg_points_genel"] = num(puan_line[2].text)
    d["ranks"] = dict(zip(keys5, (int(t.text) for t in puan_line[3:8])))
    kat = next(l for l in lines if l[0].text == "Katılımlar")
    d["participation"] = dict(zip(keys5, (int(t.text) for t in kat[1:6])))

    # ---- ders tablosu
    hdr_top = next(t.top for t in toks if t.text == "Test" and t.size == 8)
    grid_top = min(t.top for t in toks if t.text == "Anahtarı")
    rows = []
    for l in lines:
        if not (hdr_top + 5 < l[0].top < grid_top - 20):
            continue
        k = next((i for i, t in enumerate(l) if NUM.fullmatch(t.text)), None)
        if not k or len(l) - k < 8:
            continue
        name = " ".join(t.text for t in l[:k])
        v = [t.text for t in l[k:]]
        soru, dd, yy = int(v[0]), int(v[1]), int(v[2])
        rows.append({"name": name, "top": l[0].top, "questions": soru, "correct": dd, "wrong": yy,
                     "blank": soru - dd - yy, "net": num(v[3]), "success_pct": num(v[4]),
                     "avg": {"sinif": num(v[5]), "kurum": num(v[6]), "genel": num(v[7])},
                     "section": section_code(name)})
    sections, pending = [], []
    for r in rows:
        try:
            single = subject_code(r["name"]) == "TURKCE"
        except KeyError:
            single = False
        if single:  # Türkçe tek dersli bölüm, "TYT" ön eki olmadan basılıyor
            sections.append({"code": "TYT_TURKCE", "name": "TYT Türkçe", "row": r, "subjects": [r]})
        elif r["section"]:
            sections.append({"code": r["section"], "name": r["name"], "row": r,
                             "subjects": pending or [dict(r, name=r["name"].replace("TYT ", ""))]})
            pending = []
        else:
            pending.append(r)

    # ---- cevap ızgaraları: numara satırı -> öğrenci satırı -> cevap anahtarı satırı
    num_lines = [l for l in lines if len(l) >= 5 and all(t.text.isdigit() for t in l) and l[0].text == "1"
                 and l[0].size <= 6.5]
    key_lines = [l for l in lines if any(t.text == "Anahtarı" for t in l)]
    for nl in num_lines:
        centers = [(int(t.text), t.cx) for t in nl]
        kl = min((l for l in key_lines if l[0].top > nl[0].top), key=lambda l: l[0].top)
        al = [l for l in lines if nl[0].top < l[0].top < kl[0].top]
        label = " ".join(t.text for t in (al[0] if al else []) if not re.fullmatch(r"[A-Ea-e*]", t.text))
        sec = section_code(label)

        def place(line, skip_x):
            out = {}
            for t in line:
                if re.fullmatch(r"[A-Ea-e*]", t.text) and t.x0 > skip_x:  # "*" = çift/geçersiz işaretleme
                    no, cx = min(centers, key=lambda c: abs(c[1] - t.cx))
                    if abs(cx - t.cx) < 6:
                        out[no] = t.text
            return out

        first_x = nl[0].x0 - 4
        keymap = place(kl, first_x)
        given = place(al[0], first_x) if al else {}
        bk = next((t.text for t in kl if re.fullmatch(r"[A-F]", t.text) and t.x1 <= first_x + 1), None)
        n = len(centers)
        s = next((x for x in sections if x["code"] == sec), None)
        if s is None:
            raise ValueError(f"s.{page_no}: ızgara bölümü bulunamadı: {label!r}")
        s["key"] = "".join(keymap.get(i, "?") for i in range(1, n + 1))
        s["given"] = [given.get(i) for i in range(1, n + 1)]
        s["booklet"] = bk
    return d | {"sections": sections}


def parse_card_kazanim(p) -> tuple[str, list[dict]]:
    toks = page_tokens(p)
    who = next(l for l in _lines(toks) if any(t.text == "Öğrenci" for t in l))
    name = _after(who, "Öğrenci", "Sınıf")
    small = [t for t in toks if t.size <= 4.5]
    mid = p.width / 2
    out = []
    for right in (False, True):
        half = [t for t in small if (t.x0 >= mid) == right]
        subject = None
        cols = None
        for l in _lines(half, 1.0):
            texts = [t.text for t in l]
            if "B%" in texts:
                cols = {t.text: t.cx for t in l if t.text in ("S", "D", "Y", "B%")}
                xs = min(t.x0 for t in l if t.text == "S") - 2
                subject = " ".join(t.text for t in l if t.x0 < xs)
                continue
            if cols is None or (l[0].bold and not any(NUM.fullmatch(x) for x in texts)):
                continue  # bölüm başlığı (TYT Sosyal vb.)
            name_t = [t for t in l if t.x0 < xs]
            nums = [t for t in l if t.x0 >= xs and t.text.isdigit()]
            vals = {}
            for t in nums:
                lab = min(cols, key=lambda k: abs(cols[k] - t.cx))
                vals[lab] = int(t.text)
            if len(vals) < 4:
                continue
            out.append({"subject": subject, "kazanim": " ".join(t.text for t in name_t),
                        "questions": vals["S"], "correct": vals["D"], "wrong": vals["Y"],
                        "success_pct": float(vals["B%"])})
    return name, out


def parse(path: str) -> dict:
    raw = {"cards": [], "net_list_pages": [], "unknown_pages": [], "kinds": {}, "questions": []}
    with pdfplumber.open(path) as pdf:
        raw["page_count"] = len(pdf.pages)
        for i, p in enumerate(pdf.pages, start=1):
            toks = page_tokens(p)
            kind = page_kind(toks)
            raw["kinds"][i] = kind
            if kind == "card_main":
                raw["cards"].append(parse_card_main(p, i) | {"kazanim_rows": []})
            elif kind == "card_kazanim":
                name, rows = parse_card_kazanim(p)
                card = raw["cards"][-1] if raw["cards"] else None
                if card is None or card["name"] != name:
                    raise ValueError(f"s.{i}: kazanım sayfası önceki karneyle eşleşmiyor ({name})")
                card["kazanim_rows"].extend(rows)
            elif kind == "net_list":
                raw["net_list_pages"].append((i, net_list_tokens(p)))
            else:
                raw["unknown_pages"].append(i)
    raw["net_list"] = parse_net_list(raw.pop("net_list_pages"))
    return raw
