"""Soru analizi raporu olmayan formatlar için soru düzeyi bilgisini öğrenci karnelerinden çıkarır.

1) Soru -> kazanım (kitapçık başına):
   Her öğrencinin karnesindeki kazanım tablosu (S, D, Y) bir kısıttır: "bu kazanıma ait S soru içinden
   D'sini doğru, Y'sini yanlış yaptı". Tüm öğrencilerin kısıtlarını aynı anda sağlayan tek bir
   soru->kazanım ataması aranır (CP-SAT). Her soru için alternatif atama mümkün mü diye ayrıca denenir;
   mümkün değilse eşleme "kesin"dir.

2) Kitapçık eşlemesi (A <-> B):
   Aday çiftler: aynı ders, aynı doğru cevap harfi, uyumlu kazanım. Aralarından, iki kitapçık
   grubundaki şık dağılımı en çok benzeyen tam eşleme seçilir (Macar algoritması). Bir çift, onu
   çıkarınca tam eşleme kurulamıyorsa "kesin"; değilse "tahmini" (maliyet farkıyla).
"""
from __future__ import annotations

from collections import Counter, defaultdict

import numpy as np
from ortools.sat.python import cp_model
from scipy.optimize import linear_sum_assignment

from .taxonomy import OPTIONAL_GROUPS, subject_code

OPTS = ["A", "B", "C", "D", "E", "Boş", "*"]
BIG = 1e6
LOCALITY = 0.01


def _status(g):
    if g is None:
        return "blank"
    if g == "*" or g.islower():
        return "wrong"
    return "correct"


def section_ranges(cards) -> dict[str, list[tuple[str, int, int]]]:
    """Bölüm -> [(ders, ilk, son)] (ızgara/cevap dizisi konumları). Izgaraya sığmayan seçmeli ders,
    aynı gruptaki dersin konumlarını paylaşır (öğrenci ikisinden birini çözer)."""
    out = {}
    for c in cards:
        for s in c["sections"]:
            if s["code"] in out or "key" not in s:
                continue
            st, rr = 1, []
            for r in s["subjects"]:
                code = subject_code(r["name"])
                if st > len(s["key"]) and OPTIONAL_GROUPS.get(code):
                    partner = next(x for x in rr if OPTIONAL_GROUPS.get(x[0]) == OPTIONAL_GROUPS[code])
                    rr.append((code, partner[1], partner[2]))
                    continue
                rr.append((code, st, st + r["questions"] - 1))
                st += r["questions"]
            out[s["code"]] = rr
    return out


def _subject_taken(card, subj):
    for s in card["sections"]:
        for r in s["subjects"]:
            try:
                if subject_code(r["name"]) == subj:
                    return r["correct"] + r["wrong"] > 0 or not OPTIONAL_GROUPS.get(subj)
            except KeyError:
                pass
    return False


REST = "__DIGER__"  # karnede basılmayan (sayfaya sığmayan) kazanımların toplamı


def _subject_row(card, subj):
    for s in card["sections"]:
        for r in s["subjects"]:
            if _safe_code(r["name"]) == subj:
                return r
    return None


def infer_kazanim(cards, booklet, sec, subj, a, b, time_limit=20.0):
    """Döndürür: (atama {konum: kazanım}, alternatifler {konum: [kazanım]}, öğrenci sayısı, model) ya da None.
    Bazı yayınevleri kazanım tablosunu sayfaya sığdığı kadar basıyor; eksik kalan kazanımlar öğrenci
    bazında "diğer" kovasıyla (ders toplamı - basılanlar) kısıtlanır."""
    studs = []
    for c in cards:
        s = next((x for x in c["sections"] if x["code"] == sec and x.get("booklet") == booklet), None)
        if not s or not _subject_taken(c, subj):
            continue
        kz = [k for k in c["kazanim_rows"] if _safe_code(k["subject"]) == subj]
        row = _subject_row(c, subj)
        if kz and row:
            studs.append((s, {k["kazanim"]: k for k in kz}, row))
    if not studs:
        return None
    Q = list(range(a, b + 1))
    # en uzun liste esas; S değerleri tüm karnelerde aynı olmalı
    full = max((st[1] for st in studs), key=len)
    names = list(full)
    S = {k: full[k]["questions"] for k in names}
    rest = len(Q) - sum(S.values())
    if rest < 0:
        return None
    if rest:
        names = names + [REST]
        S[REST] = rest
    m = cp_model.CpModel()
    x = {(q, k): m.NewBoolVar(f"x{q}_{i}") for q in Q for i, k in enumerate(names)}
    for q in Q:
        m.AddExactlyOne(x[q, k] for k in names)
    for k in names:
        m.Add(sum(x[q, k] for q in Q) == S[k])
    used = 0
    for s, kd, row in studs:
        if any(k not in S or S[k] != kd[k]["questions"] for k in kd):
            continue
        used += 1
        st = {q: _status(s["given"][q - 1]) for q in Q}
        for k in kd:
            m.Add(sum(x[q, k] for q in Q if st[q] == "correct") == kd[k]["correct"])
            m.Add(sum(x[q, k] for q in Q if st[q] == "wrong") == kd[k]["wrong"])
        hidden = [k for k in names if k not in kd]
        if hidden:  # basılmayanlar: ders toplamından kalan
            m.Add(sum(x[q, k] for q in Q for k in hidden if st[q] == "correct")
                  == row["correct"] - sum(v["correct"] for v in kd.values()))
            m.Add(sum(x[q, k] for q in Q for k in hidden if st[q] == "wrong")
                  == row["wrong"] - sum(v["wrong"] for v in kd.values()))
    sol = _solve(m, time_limit)
    if sol is None:
        return None
    assign = {q: next(k for k in names if sol.Value(x[q, k])) for q in Q}
    alts = {}
    for q in Q:
        for k in names:
            if k == assign[q]:
                continue
            m2 = m.Clone()
            m2.Add(x[q, k] == 1)
            if _solve(m2, 5.0) is not None:
                alts.setdefault(q, []).append(k)
    assign = {q: (None if k == REST else k) for q, k in assign.items()}
    alts = {q: [k for k in v if k != REST] or ["?"] for q, v in alts.items()}
    return assign, alts, used, (m, x, names)


def _safe_code(name):
    try:
        return subject_code(name)
    except KeyError:
        return None


def _solve(m, tl=20.0):
    s = cp_model.CpSolver()
    s.parameters.max_time_in_seconds = tl
    s.parameters.num_workers = 4
    r = s.Solve(m)
    return s if r in (cp_model.OPTIMAL, cp_model.FEASIBLE) else None


def option_profile(cards, booklet, sec, n):
    """Konum -> şık dağılımı (bölüme giren öğrenciler)."""
    prof = defaultdict(Counter)
    for c in cards:
        s = next((x for x in c["sections"] if x["code"] == sec and x.get("booklet") == booklet), None)
        if not s or not any(s["given"]):
            continue
        for i, g in enumerate(s["given"], 1):
            prof[i]["Boş" if g is None else ("*" if g == "*" else g.upper())] += 1
    return prof


def _dist(p1: Counter, p2: Counter):
    n1, n2 = sum(p1.values()) or 1, sum(p2.values()) or 1
    return sum(abs(p1[o] / n1 - p2[o] / n2) for o in OPTS)


def match_booklets(ref_bk, other_bk, sec, ranges, keys, kaz, profiles, locality=LOCALITY):
    """ref kitapçık konumu -> diğer kitapçık konumu, güven bilgisiyle."""
    kr, ko = keys[(ref_bk, sec)], keys[(other_bk, sec)]
    n = len(kr)
    subj_of = {}
    for subj, a, b in ranges[sec]:
        for q in range(a, b + 1):
            subj_of.setdefault(q, subj)
    allowed = lambda bk, q: {kaz[(bk, sec)].get(q)} | set(kaz.get((bk, sec, "alts"), {}).get(q, []))
    C = np.full((n, n), BIG)
    for i in range(1, n + 1):
        for j in range(1, n + 1):
            if subj_of[i] != subj_of[j] or kr[i - 1] != ko[j - 1]:
                continue
            ka, kb = allowed(ref_bk, i), allowed(other_bk, j)
            if None not in ka and None not in kb and not (ka & kb):
                continue
            # kitapçıklar genelde küçük bloklar içinde karıştırılır: yakın konum hafifçe tercih edilir
            C[i - 1, j - 1] = _dist(profiles[ref_bk][i], profiles[other_bk][j]) + locality * abs(i - j)
    rows, cols = linear_sum_assignment(C)
    if C[rows, cols].max() >= BIG:
        return None
    base = C[rows, cols].sum()
    out = {}
    for r, c in zip(rows, cols):
        C2 = C.copy()
        C2[r, c] = BIG
        r2, c2 = linear_sum_assignment(C2)
        alt = C2[r2, c2].sum()
        forced = C2[r2, c2].max() >= BIG
        out[r + 1] = {"to": c + 1, "forced": bool(forced), "margin": None if forced else round(float(alt - base), 3),
                      "distance": round(float(C[r, c]), 3)}
    return out


def infer_questions(cards) -> tuple[list[dict], dict]:
    """bes_cap.parse_question_analysis çıktısıyla uyumlu soru listesi + özet döndürür."""
    ranges = section_ranges(cards)
    keys = {}
    for c in cards:
        for s in c["sections"]:
            if s.get("key"):
                keys.setdefault((s["booklet"], s["code"]), s["key"])
    booklets = sorted({bk for bk, _ in keys})
    ref = "A" if "A" in booklets else booklets[0]
    kaz, summary = {}, {"kazanim": [], "eslesme": []}
    for bk in booklets:
        for sec, rr in ranges.items():
            if (bk, sec) not in keys:
                continue
            kaz[(bk, sec)] = {}
            kaz[(bk, sec, "alts")] = {}
            seen = set()
            for subj, a, b in rr:
                if (a, b) in seen:  # seçmeli ders aynı konumları paylaşıyor; çözülen ders esas alınır
                    continue
                res = infer_kazanim(cards, bk, sec, subj, a, b)
                if res is None:
                    summary["kazanim"].append((bk, sec, subj, "çözümsüz"))
                    continue
                seen.add((a, b))
                assign, alts, n, _ = res
                kaz[(bk, sec)].update(assign)
                kaz[(bk, sec, "alts")].update(alts)
                summary["kazanim"].append((bk, sec, subj, f"{b - a + 1} soru, {n} öğrenci, {len(alts)} belirsiz"))
    questions = []
    for sec, rr in ranges.items():
        if (ref, sec) not in keys:
            continue
        n = len(keys[(ref, sec)])
        pr = {bk: option_profile(cards, bk, sec, n) for bk in booklets if (bk, sec) in keys}
        maps = {}
        for bk in booklets:
            if bk == ref or (bk, sec) not in keys:
                continue
            maps[bk] = match_booklets(ref, bk, sec, ranges, keys, kaz, pr)
            if maps[bk] is None:
                summary["eslesme"].append((sec, bk, "kurulamadı"))
            else:
                f = sum(v["forced"] for v in maps[bk].values())
                summary["eslesme"].append((sec, bk, f"{f}/{n} kesin"))
        for q in range(1, n + 1):
            booklets_no = {ref: q}
            conf = {}
            for bk, mp in maps.items():
                if mp and q in mp:
                    booklets_no[bk] = mp[q]["to"]
                    conf[bk] = "kesin" if mp[q]["forced"] else f"tahmini (fark {mp[q]['margin']})"
            k = kaz.get((ref, sec), {}).get(q)
            kalts = kaz.get((ref, sec, "alts"), {}).get(q)
            if kalts:  # referans belirsizse diğer kitapçıktaki kesin eşlemeyi dene
                for bk, no in booklets_no.items():
                    if bk != ref and not kaz.get((bk, sec, "alts"), {}).get(no):
                        k, kalts = kaz[(bk, sec)].get(no, k), None
                        break
            cnt = Counter()
            for bk, no in booklets_no.items():
                cnt.update(pr[bk][no])
            tot = sum(cnt.values()) or 1
            key = keys[(ref, sec)][q - 1]
            questions.append({
                "section": sec, "a_no": q, "booklets": booklets_no, "kazanim": k, "dc": key,
                "counts": {o: cnt.get(o, 0) for o in ["A", "B", "C", "D", "E", "Boş"]},
                "pcts": {o: round(100 * cnt.get(o, 0) / tot, 2) for o in ["A", "B", "C", "D", "E", "Boş"]},
                "legend": {"Doğru": round(100 * cnt.get(key, 0) / tot, 2),
                           "Boş": round(100 * cnt.get("Boş", 0) / tot, 2),
                           "Yanlış": round(100 * (tot - cnt.get(key, 0) - cnt.get("Boş", 0)) / tot, 2)},
                "flagged": False, "stats_source": "computed",
                "inference": {"kazanim": "belirsiz" if kalts else ("kesin" if k else "yok"),
                              "kazanim_alternatives": kalts or [], "booklet_map": conf},
            })
    return questions, summary
