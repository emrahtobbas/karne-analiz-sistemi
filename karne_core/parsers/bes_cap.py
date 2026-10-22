"""BES / ÇAP formatındaki deneme raporları (metin katmanlı PDF) için ayrıştırıcı.

Tanınan sayfa tipleri:
  - "OKUL TYT NET LİSTESİ"            -> ders bazlı D/Y/N + ortalamalar (doğrulama ve ortalama)
  - "OKUL TYT TEST BAZLI NET LİSTESİ" -> (şu an yalnızca tanınır)
  - Öğrenci karnesi                    -> cevap anahtarı, öğrenci cevapları, kazanım tablosu
  - "KURUM SORU ANALİZİ"              -> soru-kazanım eşlemesi, kitapçık eşlemesi, şık dağılımı
"""
from __future__ import annotations

import re
from collections import defaultdict

import pdfplumber

from ..pdfutil import Run, courier_lines, num, page_runs, page_tokens
from ..taxonomy import norm, section_code, subject_code

PARSER_NAME = "bes_cap"
PARSER_VERSION = "0.1.0"
PUBLISHER = "BES Yayınları (ÇAP)"

OPTIONS = ["A", "B", "C", "D", "E"]


def cluster_lines(runs, tol=1.5):
    """Yakın 'top' değerli run'ları aynı satırda topla."""
    out = []
    for r in sorted(runs, key=lambda r: r.top):
        if out and r.top - out[-1][0].top <= tol:
            out[-1].append(r)
        else:
            out.append([r])
    return out


# ----------------------------------------------------------------------------- tanıma
def page_kind(runs: list[Run], page) -> str:
    titles = " ".join(r.text for r in runs if r.top < 45 and r.bold)
    if "KURUM SORU ANALİZİ" in titles:
        return "question_analysis"
    if "TEST BAZLI NET LİSTESİ" in titles:
        return "test_net_list"
    if "NET LİSTESİ" in titles:
        return "net_list"
    if any(r.text.startswith("Cevap Anahtar") for r in runs) and courier_lines(page):
        return "student_card"
    return "unknown"


def detect(pdf) -> float:
    """0-1 arası güven skoru."""
    kinds = [page_kind(page_runs(p), p) for p in pdf.pages[: min(10, len(pdf.pages))]]
    score = 0.0
    if "student_card" in kinds:
        score += 0.6
    if any(k.endswith("net_list") for k in kinds):
        score += 0.3
    return min(score + 0.1, 1.0) if score else 0.0


# ----------------------------------------------------------------------------- öğrenci karnesi
def _join_decimal(int_run: Run | None, frac_run: Run | None) -> float | None:
    if int_run is None:
        return None
    s = int_run.text + (frac_run.text.replace(" ", "") if frac_run else "")
    return num(s)


def _row_numbers(runs: list[Run], ref: Run, xmin: float) -> list[Run]:
    return sorted([r for r in runs if abs(r.top - ref.top) < 1.5 and r.x0 > xmin and r is not ref],
                  key=lambda r: r.x0)


def parse_student_card(page, page_no: int) -> dict:
    runs = page_runs(page)
    W = page.width
    mid = W / 2
    d: dict = {"page": page_no}

    # --- başlık
    d["exam_name"] = " ".join(r.text for r in runs if r.top < 35 and r.bold and r.size >= 9)
    puan = next(r for r in runs if r.size == 14 and r.top < 80)
    d["points"] = num(puan.text)
    pint = next((r for r in runs if r.size == 10 and r.top < 80 and r.x0 > puan.x1), None)
    pfrac = next((r for r in runs if r.top < 80 and r.text.startswith(",") and pint and r.x0 >= pint.x1 - 1), None)
    d["percentile"] = _join_decimal(pint, pfrac)

    loc = next((r for r in runs if r.size == 8 and "/" in r.text and r.top < 120), None)
    if loc:
        city, _, district = loc.text.partition("/")
        d["city"], d["district"] = city.strip(), district.strip()
    school = [r for r in runs if r.size == 8 and not r.bold and r.top < 120 and r is not loc and r.x0 < mid]
    d["school"] = school[0].text if school else None

    bold8 = sorted([r for r in runs if r.size == 8 and r.bold and r.x0 < 170 and r.top < 170],
                   key=lambda r: (round(r.top), r.x0))
    lines = defaultdict(list)
    for r in bold8:
        lines[round(r.top)].append(r.text)
    ls = [" ".join(v) for _, v in sorted(lines.items())]
    cls_line = ls[0] if ls else ""
    m = re.match(r"(.*)\s+-\s+(\S*)$", cls_line)
    d["class_name"], d["school_no"] = (m.group(1).strip(), m.group(2)) if m else (cls_line, None)
    d["name"] = " ".join(ls[1:]).strip()

    big = sorted([r for r in runs if r.size == 18 and r.bold], key=lambda r: r.x0)
    q, c, w, b = (int(num(r.text)) for r in big[:4])
    net_int = next(r for r in runs if r.size == 14 and r.top > 120 and r.top < 160)
    net_frac = next((r for r in runs if r.text.startswith(",") and abs(r.top - net_int.top) < 5 and r.x0 >= net_int.x1 - 1), None)
    d["totals"] = {"questions": q, "correct": c, "wrong": w, "blank": b,
                   "net": _join_decimal(net_int, net_frac)}

    def row_after(label):
        lab = next(r for r in runs if label in r.text)
        vals = [r for r in _row_numbers(runs, lab, lab.x1) if re.fullmatch(r"\d+", r.text)]
        return [int(v.text) for v in vals[:5]]

    rk = row_after("Sıra No")
    d["ranks"] = dict(zip(["sube", "kurum", "ilce", "il", "genel"], rk))
    pp = row_after("Katılan")
    d["participation"] = dict(zip(["sube", "kurum", "ilce", "il", "genel"], pp))

    # --- ders/bölüm satırları (punto 7)
    rows = []
    by_line = defaultdict(list)
    # bu tabloda harf aralıklı yazımlar var; kelime çıkarımı daha güvenli
    for w in page.extract_words(extra_attrs=["size", "fontname"]):
        if round(w["size"], 1) == 7 and w["top"] > 260:
            r = Run(w["x0"], w["x1"], w["top"], 7.0, w["fontname"], w["text"])
            by_line[(r.x0 >= mid - 10, round(r.top))].append(r)
    for (right, top), rs in by_line.items():
        rs.sort(key=lambda r: r.x0)
        k = next((i for i, r in enumerate(rs) if re.fullmatch(r"-?\d[\d,]*", r.text)), None)
        if not k:
            continue
        name = " ".join(r.text for r in rs[:k])
        vals = [r.text for r in rs[k:]]
        if len(vals) < 5:
            continue
        soru, dd, yy, bb, net = vals[:5]
        rest = vals[5:]
        if rest and rest[0] == "%":
            rest = rest[1:]
        pct = rest[0].replace("%", "").strip() if rest else ""
        if len(rest) > 1:
            raise ValueError(f"Beklenmeyen ders satırı (s.{page_no}): {name} {vals}")
        rows.append({"right": right, "top": top, "name": name, "questions": int(soru),
                     "correct": int(dd), "wrong": int(yy), "blank": int(bb), "net": num(net),
                     "success_pct": num(pct) if pct else None,
                     "section": section_code(name)})

    # bölüm satırının üstündeki ders satırları o bölüme aittir
    sections = []
    for half in (False, True):
        hr = sorted([r for r in rows if r["right"] == half], key=lambda r: r["top"])
        pending = []
        for r in hr:
            if r["section"]:
                subs = pending or [dict(r, name=r["name"].replace("TYT ", ""))]
                sections.append({"code": r["section"], "name": r["name"], "top": r["top"], "right": half,
                                 "row": r, "subjects": subs})
                pending = []
            else:
                pending.append(r)

    # --- cevap anahtarı / cevaplar
    cl = courier_lines(page)
    used = set()
    for i, (top, x0, chars) in enumerate(cl):
        if i in used:
            continue
        key = "".join(ch["text"] for ch in chars).strip()
        pitch = (chars[-1]["x0"] - chars[0]["x0"]) / max(len(chars) - 1, 1)
        xend = x0 + pitch * len(key)
        # hemen altındaki (≈14pt) aynı sütundaki satır öğrencinin cevabıdır; hiç yoksa tümü boş
        j = next((k for k in range(i + 1, len(cl))
                  if 8 < cl[k][0] - top < 20 and x0 - 1 <= cl[k][1] < xend), None)
        used.add(i)
        given = [None] * len(key)
        if j is not None:
            used.add(j)
        for ch in (cl[j][2] if j is not None else []):
            t = ch["text"].strip()
            if not t:
                continue
            idx = round((ch["x0"] - x0) / pitch)
            if 0 <= idx < len(key):
                given[idx] = t
        right = x0 >= mid - 10
        sec = max((s for s in sections if s["right"] == right and s["top"] < top), key=lambda s: s["top"])
        bk = next((r.text for r in runs if abs(r.top - top) < 3 and r.x1 < x0 and r.x0 > x0 - 45
                   and re.fullmatch(r"[A-F]", r.text)), None)
        sec["key"], sec["given"], sec["booklet"] = key, given, bk

    # --- kazanım tablosu (punto 4)
    d["kazanim_rows"] = _parse_kazanim_tables(page, runs, mid)
    d["sections"] = sections
    return d


def _parse_kazanim_tables(page, runs, mid):
    out = []
    small = [r for r in runs if r.size == 4]
    headers = [r for r in small if r.text == "S" and r.bold]
    for h in headers:
        right = h.x0 >= mid - 10
        cols = {}
        default_off = {"S": 0.0, "D": 7.0, "Y": 14.2, "B%": 23.4}  # bazen başlık taşan metinle birleşiyor
        for lab in ("S", "D", "Y", "B%"):
            rr = next((r for r in small if abs(r.top - h.top) < 0.5 and r.text == lab and r.x0 >= h.x0 - 0.5), None)
            cols[lab] = rr.cx if rr else h.cx + default_off[lab]
        xs = h.x0 - 2
        name_x0 = 20 if not right else mid
        # aynı yarıdaki bir sonraki başlığa kadar
        nxt = min([o.top for o in headers if (o.x0 >= mid - 10) == right and o.top > h.top] + [1e9])
        line_tops = sorted({round(r.top, 1) for r in small
                            if h.top + 1 < r.top < nxt and name_x0 <= r.x0 < xs})
        subject = None
        for t in line_tops:
            name_runs = [r for r in small if abs(r.top - t) < 0.3 and name_x0 <= r.x0 < xs]
            name_runs.sort(key=lambda r: r.x0)
            nr = name_runs[0]
            # gerçek boşluklar karakter olarak var; run'lar arası boşluk yalnızca harf aralığıdır
            name = "".join(r.text if i == 0 or r.x0 - name_runs[i - 1].x1 < 2.5 else " " + r.text
                           for i, r in enumerate(name_runs))
            if max(r.x1 for r in name_runs) > xs:  # taşan satır sayıları yutmuş olabilir
                name = re.sub(r"\d+$", "", name).strip()
            digits = sorted([c for c in page.chars if abs(c["top"] - t) < 0.3 and c["size"] < 4.5
                             and xs <= c["x0"] <= cols["B%"] + 8 and c["text"].isdigit()],
                            key=lambda c: c["x0"])
            nums, cur, last = [], "", None
            for c in digits:
                if last is not None and c["x0"] - last > 1.0:
                    nums.append((cur, cx0)); cur = ""
                if not cur:
                    cx0 = c["x0"]
                cur += c["text"]; last = c["x1"]
            if cur:
                nums.append((cur, cx0))
            vals = {}
            for v, x in nums:
                lab = min(cols, key=lambda k: abs(cols[k] - (x + 1.3 * len(v))))
                vals[lab] = int(v)
            if nr.bold:
                subject = name
                continue
            if len(vals) < 4:
                continue
            out.append({"subject": subject, "kazanim": name, "questions": vals["S"], "correct": vals["D"],
                        "wrong": vals["Y"], "success_pct": float(vals["B%"])})
    return out


# ----------------------------------------------------------------------------- kurum soru analizi
def parse_question_analysis(pages_runs: list[tuple[int, list[Run]]]) -> list[dict]:
    out = []
    section = None
    for page_no, runs in pages_runs:
        sec_titles = [r for r in runs if r.bold and r.size == 9]
        headers = sorted([r for r in runs if r.text == "Soru" and r.size == 6], key=lambda r: r.top)
        seen_tops = []
        sec_first = []
        for r in sorted(sec_titles, key=lambda x: x.top):
            if not any(abs(r.top - t) < 1 for t in seen_tops):
                seen_tops.append(r.top); sec_first.append(r)
        events = sorted([("sec", r.top, r) for r in sec_first] + [("hdr", r.top, r) for r in headers],
                        key=lambda e: e[1])
        for i, (kind, top, r) in enumerate(events):
            if kind == "sec":
                title = " ".join(x.text for x in sorted(sec_titles, key=lambda x: x.x0) if abs(x.top - r.top) < 1)
                section = section_code(title) or section_code(title.replace(" ", "")) or title
                continue
            if i > 0 and events[i - 1][0] == "sec" and abs(events[i - 1][1] - top) < 1:
                pass
            bottom = next((e[1] for e in events[i + 1:]), 1e9)
            blk = [x for x in runs if top - 0.5 <= x.top < bottom - 0.5]
            hdr = [x for x in blk if abs(x.top - top) < 0.5]
            col = {x.text: x for x in hdr}
            centers = {k: col[k].cx for k in OPTIONS + ["Boş"] if k in col}
            dc_col = col["D.C."]
            hat = col.get("Hatalı (*)") or col.get("Hatalı")
            # soru no hücresi bazen harf aralıklı yazılıyor ("A","-","2","0") -> satır bazında birleştir
            qcell = defaultdict(list)
            for x in blk:
                if x.x0 < 45 and x.top > top + 1:
                    qcell[round(x.top)].append(x)
            labels = ["".join(y.text for y in sorted(v, key=lambda y: y.x0)) for _, v in sorted(qcell.items())]
            a_top = [t for t, v in sorted(qcell.items())][next(i for i, t in enumerate(labels) if re.fullmatch(r"A-\d+", t))]
            a = Run(0, 0, a_top, 6, "", next(t for t in labels if re.fullmatch(r"A-\d+", t)))
            bnums = [Run(0, 0, 0, 6, "", t) for t in labels if re.fullmatch(r"[B-F]-\d+", t)]
            body = [x for x in blk if x.top > top + 1]
            kaz_runs = sorted([x for x in body if 45 < x.x0 < dc_col.x0 - 2 and x.x1 < dc_col.x0 + 2],
                              key=lambda x: (x.top, x.x0))
            dc = next(x.text for x in body if dc_col.x0 - 2 <= x.x0 <= dc_col.x1 + 2 and re.fullmatch(r"[A-E]", x.text))

            def nearest(x):
                return min(centers, key=lambda k: abs(centers[k] - x.cx))

            counts, pcts = {}, {}
            lo = min(centers.values()) - 15
            hi = max(centers.values()) + 15
            for x in body:
                if not (lo <= x.cx <= hi):
                    continue
                if re.fullmatch(r"\d+", x.text):
                    if x.top < a.top:  # sayı satırı soru etiketinin üstünde; alttakiler taşan yüzde parçaları
                        counts[nearest(x)] = int(x.text)
                elif re.fullmatch(r"%[\d,]+", x.text):
                    pcts[nearest(x)] = num(x.text)
            flagged = bool(hat and any(abs(x.cx - hat.cx) < 12 and x.text.strip() for x in body if x.x0 < hat.x1 + 20))
            legend = {}
            leg_lines = defaultdict(list)
            for x in blk:
                if x.x0 > (hat.x1 + 40 if hat else 480):
                    leg_lines[round(x.top)].append(x)
            for v in leg_lines.values():
                m = re.match(r"(Doğru|Yanlış|Boş)\s*\(%([\d,]+)\)", " ".join(y.text for y in sorted(v, key=lambda y: y.x0)))
                if m:
                    legend[m.group(1)] = num(m.group(2))
            out.append({
                "page": page_no, "section": section, "a_no": int(a.text[2:]),
                "booklets": {"A": int(a.text[2:]), **{x.text[0]: int(x.text[2:]) for x in bnums}},
                "kazanim": " ".join(x.text for x in kaz_runs),
                "dc": dc, "counts": counts, "pcts": pcts, "legend": legend, "flagged": flagged,
            })
    return out


# ----------------------------------------------------------------------------- okul net listesi
NET_LIST_GROUPS = ["TURKCE", "TARIH", "COGRAFYA", "FELSEFE", "DIN", "FELSEFE_SECMELI",
                   "MATEMATIK", "GEOMETRI", "FIZIK", "KIMYA", "BIYOLOJI", "TOPLAM"]


def parse_net_list(pages_runs) -> dict:
    students, averages = [], {}
    for page_no, runs in pages_runs:
        hdr_top = next(r.top for r in runs if r.text == "Puan")
        dyn = sorted([r for r in runs if abs(r.top - hdr_top) < 0.5 and r.text in ("D", "Y", "N")],
                     key=lambda r: r.x0)
        cols = []
        for i, r in enumerate(dyn):
            cols.append((NET_LIST_GROUPS[i // 3], r.text, r.cx))
        puan_x = next(r.cx for r in runs if r.text == "Puan")
        genel_x = next(r.cx for r in runs if r.text == "Genel" and abs(r.top - hdr_top) < 0.5)
        num_x0 = dyn[0].x0 - 6
        lines = cluster_lines([r for r in runs if r.top > hdr_top + 5], tol=1.5)
        for rs in lines:
            fixed = []
            for r in rs:
                m = re.match(r"^(.*?[^\d,\-])(-?\d[\d,]*)$", r.text)
                if r.x0 < num_x0 - 3 and r.x1 > num_x0 + 1 and m:  # sınıf hücresi sayıyı yutmuş
                    w = (r.x1 - r.x0) / len(r.text)
                    fixed.append(Run(r.x0, r.x1 - w * len(m.group(2)), r.top, r.size, r.font, m.group(1)))
                    fixed.append(Run(r.x1 - w * len(m.group(2)), r.x1, r.top, r.size, r.font, m.group(2)))
                else:
                    fixed.append(r)
            rs = sorted(fixed, key=lambda r: r.x0)
            label = " ".join(r.text for r in rs if r.x0 < num_x0 - 3)
            if "Ortalama" in label:
                key = "genel" if "Genel" in label else "kurum"
                pr = [r for r in rs if abs(r.cx - puan_x) < 15]
                puan = pr[0].text if pr else None
                txt = " ".join(r.text for r in rs if r.x0 >= num_x0 - 3 and r not in pr)
                vals = re.findall(r"-?\d+,\d{2}", txt)
                if len(vals) < 36:
                    raise ValueError(f"ortalama satırı okunamadı s.{page_no}: {label!r} {txt!r}")
                avg = {}
                for i, g in enumerate(NET_LIST_GROUPS):
                    avg[g] = {"correct": num(vals[3 * i]), "wrong": num(vals[3 * i + 1]), "net": num(vals[3 * i + 2])}
                if puan:
                    avg["PUAN"] = num(puan)
                averages[key] = avg
                continue
            if not rs or not re.fullmatch(r"\d+", rs[0].text) or rs[0].x0 > 40:
                continue
            sira = int(rs[0].text)
            name = " ".join(r.text for r in rs if 55 < r.x0 < 128)
            if not name:
                continue
            vals = defaultdict(dict)
            puan = genel = None
            for r in rs:
                if r.x0 < num_x0 or not re.fullmatch(r"-?\d[\d,]*", r.text):
                    continue
                if abs(r.cx - puan_x) < 15 and "," in r.text and len(r.text) > 6:
                    puan = num(r.text); continue
                if abs(r.cx - genel_x) < 15:
                    genel = int(r.text); continue
                g, k, _ = min(cols, key=lambda c: abs(c[2] - r.cx))
                vals[g][k] = num(r.text)
            students.append({"page": page_no, "order": sira, "name": name, "points": puan,
                             "genel_rank": genel, "values": dict(vals)})
    return {"students": students, "averages": averages}


def net_list_tokens(p, runs=None):
    """Okul net listesi sayfası için token'lar. Sınıf hücresi ("Mezun-XX") kırpılmış ama karakterleri
    ilk sayı sütununa taşıyor; bu karakterler ayıklanır."""
    runs = runs or page_runs(p)
    hdr = next(r for r in runs if r.text == "Puan")
    d0 = min(r.x0 for r in runs if r.text == "D" and abs(r.top - hdr.top) < 0.5)
    pf = p.filter(lambda o: not (o.get("object_type") == "char" and d0 - 3 < o["x0"] < d0 + 12
                                 and o["top"] > hdr.top + 5
                                 and not (o["text"].isdigit() or o["text"] == ",")))
    return page_tokens(pf)


# ----------------------------------------------------------------------------- giriş noktası
def parse(path: str) -> dict:
    """Ham (yayınevine özgü) ara çıktı döndürür; ortak şemaya dönüştürme builder.py'de."""
    raw = {"cards": [], "analysis_pages": [], "net_list_pages": [], "unknown_pages": [], "kinds": {}}
    with pdfplumber.open(path) as pdf:
        raw["page_count"] = len(pdf.pages)
        for i, p in enumerate(pdf.pages, start=1):
            runs = page_runs(p)
            kind = page_kind(runs, p)
            raw["kinds"][i] = kind
            if kind == "student_card":
                raw["cards"].append(parse_student_card(p, i))
            elif kind == "question_analysis":
                raw["analysis_pages"].append((i, page_tokens(p)))
            elif kind == "net_list":
                raw["net_list_pages"].append((i, net_list_tokens(p, runs)))
            elif kind == "unknown":
                raw["unknown_pages"].append(i)
    raw["questions"] = parse_question_analysis(raw.pop("analysis_pages"))
    raw["net_list"] = parse_net_list(raw.pop("net_list_pages"))
    return raw
