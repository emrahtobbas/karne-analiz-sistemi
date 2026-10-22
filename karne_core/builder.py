"""Ham ayrıştırıcı çıktısını ortak şemaya (ExamReport) dönüştürür ve çapraz doğrulama yapar."""
from __future__ import annotations

import hashlib
import os
import re
from collections import Counter, defaultdict

from .schema import (Answer, Check, Exam, ExamReport, Institution, KazanimRow, OptionStats, Participation,
                     Question, QuestionInference, QuestionStats, Ranks, Score, SectionDef, Source, Student,
                     SubjectAverage, SubjectDef, SubjectResult, Totals)
from .taxonomy import OPTIONAL_GROUPS, SECTION_ALIASES, norm, subject_code

WRONG_PENALTY = {"TYT": 4, "AYT": 4, "LGS": 3}


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", norm(s)).strip("-")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def close(a, b, tol=0.011):
    return a is not None and b is not None and abs(a - b) <= tol


def build(raw: dict, path: str, parser_mod) -> ExamReport:
    cards = raw["cards"]
    c0 = cards[0]
    exam_type = next((t for t in WRONG_PENALTY if t in c0["exam_name"].upper()), "BILINMIYOR")
    penalty = WRONG_PENALTY.get(exam_type, 4)
    exam_checks: list[Check] = []

    # ---------- yapı (bölüm/ders) - ilk karneden
    sections: list[SectionDef] = []
    subj_ranges: dict[str, list[tuple[int, int, str]]] = {}  # bölüm -> [(başlangıç, bitiş, ders)]
    # Bölümü tamamen boş bırakan öğrencinin karnesinde ders kırılımı basılmıyor; yapı en ayrıntılı karneden alınır
    best = {}
    for c in cards:
        for s in c["sections"]:
            if s["code"] not in best or len(s["subjects"]) > len(best[s["code"]]["subjects"]):
                best[s["code"]] = s
    # bazı formatlar girilmeyen bölümü hiç basmıyor -> tüm karnelerdeki bölümlerin birleşimi, standart sırada
    order = list(SECTION_ALIASES)
    sec_codes = sorted(best, key=lambda c: order.index(c) if c in order else 99)
    for s in (best[c] for c in sec_codes):
        subs, ranges, start = [], [], 1
        for r in s["subjects"]:
            code = subject_code(r["name"])
            subs.append(SubjectDef(code=code, name=r["name"], question_count=r["questions"],
                                   optional_group=OPTIONAL_GROUPS.get(code)))
            if start > len(s["key"]) and OPTIONAL_GROUPS.get(code):
                continue  # ızgarada yer almayan seçmeli ders (eşi çözülmüş)
            ranges.append((start, start + r["questions"] - 1, code))
            start += r["questions"]
        sections.append(SectionDef(code=s["code"], name=s["name"], question_count=len(s["key"]), subjects=subs))
        subj_ranges[s["code"]] = ranges

    def subject_of(sec, no):
        return next(c for a, b, c in subj_ranges[sec] if a <= no <= b)

    # ---------- kitapçık anahtarları (karnelerden)
    keys: dict[tuple[str, str], str] = {}
    key_conflicts = 0
    for c in cards:
        for s in c["sections"]:
            k = (s["booklet"], s["code"])
            if k in keys and keys[k] != s["key"]:
                key_conflicts += 1
            keys.setdefault(k, s["key"])
    exam_checks.append(Check(name="cevap_anahtari_tutarliligi", ok=key_conflicts == 0,
                             detail=f"{len(keys)} kitapçık/bölüm anahtarı, {key_conflicts} çelişki"))

    # ---------- sorular (kurum soru analizinden)
    questions: list[Question] = []
    inv: dict[tuple[str, str, int], int] = {}  # (bölüm, kitapçık, kitapçık no) -> A no
    aq = raw.get("questions") or []
    if not aq:  # soru analizi raporu yok -> karnelerden çıkarım
        from .inference import infer_questions
        aq, summary = infer_questions(cards)
        for bk, sec, subj, txt in summary["kazanim"]:
            exam_checks.append(Check(name=f"cikarim_kazanim_{bk}_{subj}", ok=True, detail=txt))
        for sec, bk, txt in summary["eslesme"]:
            exam_checks.append(Check(name=f"cikarim_kitapcik_{sec}_{bk}", ok="kurulamadı" not in txt, detail=txt))
    dc_mismatch, subj_mismatch = [], []
    if aq:
        for q in aq:
            sec = q["section"]
            subj = subject_of(sec, q["a_no"])
            ak = {"A": q["dc"]}
            for bk, no in q["booklets"].items():
                inv[(sec, bk, no)] = q["a_no"]
                if bk != "A" and (bk, sec) in keys:
                    ak[bk] = keys[(bk, sec)][no - 1]
                    if ak[bk] != q["dc"]:
                        dc_mismatch.append(f"{sec}-{q['a_no']}")
                if subject_of(sec, no) != subj:
                    subj_mismatch.append(f"{sec} A-{q['a_no']} / {bk}-{no}")
            cnt = q["counts"]
            n = sum(cnt.values())
            stats = QuestionStats(
                answered_n=n,
                options={o: OptionStats(count=cnt.get(o, 0), pct=q["pcts"].get(o)) for o in "ABCDE"},
                blank=OptionStats(count=cnt.get("Boş", 0), pct=q["pcts"].get("Boş")),
                correct_rate=q["legend"].get("Doğru", 0.0), wrong_rate=q["legend"].get("Yanlış", 0.0),
                blank_rate=q["legend"].get("Boş", 0.0), flagged_erroneous=q["flagged"],
                source=q.get("stats_source", "publisher"))
            questions.append(Question(qid=f"{sec}-{q['a_no']:02d}", section=sec, subject=subj,
                                      order_in_section=q["a_no"], booklet_numbers=q["booklets"], answer_key=ak,
                                      kazanim=q["kazanim"] or None, institution_stats=stats,
                                      inference=QuestionInference(**q["inference"]) if q.get("inference") else None))
        exam_checks.append(Check(name="analiz_dogru_cevap_vs_karne_anahtari", ok=not dc_mismatch,
                                 detail=", ".join(dc_mismatch) or f"{len(aq)} sorunun tamamı tutarlı"))
        exam_checks.append(Check(name="kitapcik_eslemesi_ders_icinde", ok=not subj_mismatch,
                                 detail=", ".join(subj_mismatch[:10]) or "tüm eşlemeler aynı ders bloğunda"))
    else:  # analiz sayfası yoksa: ilk kitapçık sırası esas alınır, kazanım bilinmez
        for (bk, sec), key in keys.items():
            if any(q.section == sec for q in questions):
                continue
            for i, ch in enumerate(key, 1):
                inv[(sec, bk, i)] = i
                questions.append(Question(qid=f"{sec}-{i:02d}", section=sec, subject=subject_of(sec, i),
                                          order_in_section=i, booklet_numbers={bk: i}, answer_key={bk: ch}))
    qmap = {q.qid: q for q in questions}
    inferred = any(q.inference for q in questions)

    # ---------- öğrenciler
    nl = raw.get("net_list", {})
    nl_by_name = defaultdict(list)
    for s in nl.get("students", []):
        nl_by_name[norm(s["name"])].append(s)

    students = []
    for c in cards:
        sid = hashlib.sha1(f"{c['school']}|{c['class_name']}|{c['name']}".encode()).hexdigest()[:12]
        answers, subj_results, checks = [], [], []
        booklet = None
        bad_upper = 0
        card_secs = {s["code"]: s for s in c["sections"]}
        bk0 = next((s["booklet"] for s in c["sections"] if s.get("booklet")), None)
        for sd in sections:
            s = card_secs.get(sd.code)
            if s is None:  # karnede basılmamış bölüm = tamamen boş
                key = keys.get((bk0, sd.code)) or next(v for (b_, c_), v in keys.items() if c_ == sd.code)
                s = {"code": sd.code, "booklet": bk0, "key": key, "given": [None] * len(key), "subjects": [],
                     "row": {"correct": 0, "wrong": 0}}
            booklet = booklet or s["booklet"]
            for i, (k, g) in enumerate(zip(s["key"], s["given"]), 1):
                a_no = inv.get((s["code"], s["booklet"], i), i)
                if g is None:
                    st, gv = "blank", None
                elif g == "*":  # çift / geçersiz işaretleme: yanlış sayılır
                    st, gv = "wrong", "*"
                elif g.islower():
                    st, gv = "wrong", g.upper()
                else:
                    st, gv = "correct", g
                    if g != k:
                        bad_upper += 1
                answers.append(Answer(qid=f"{s['code']}-{a_no:02d}", booklet_no=i, key=k, given=gv, status=st))
            sec_subjects = s["subjects"]
            struct = next(x for x in sections if x.code == s["code"]).subjects
            def _sc(n):
                try:
                    return subject_code(n)
                except KeyError:
                    return None
            if [_sc(r["name"]) for r in sec_subjects] != [x.code for x in struct]:
                row = s["row"]
                if row["correct"] == 0 and row["wrong"] == 0:  # tamamen boş bölüm -> yapıya göre aç
                    sec_subjects = [{"name": x.name, "questions": x.question_count, "correct": 0, "wrong": 0,
                                     "blank": x.question_count, "net": 0.0, "success_pct": 0.0} for x in struct]
                else:
                    raise ValueError(f"s.{c['page']}: {s['code']} ders kırılımı yapıyla uyuşmuyor")
            for r in sec_subjects:
                subj_results.append(SubjectResult(section=s["code"], subject=subject_code(r["name"]),
                                                  questions=r["questions"], correct=r["correct"], wrong=r["wrong"],
                                                  blank=r["blank"], net=r["net"], success_pct=r["success_pct"]))
        # seçmeli grup: tamamen boş bırakılan alternatif "not_taken"
        by_subj = defaultdict(list)
        for a in answers:
            by_subj[qmap[a.qid].subject if a.qid in qmap else None].append(a)
        groups = defaultdict(list)
        for sr in subj_results:
            if OPTIONAL_GROUPS.get(sr.subject):
                groups[OPTIONAL_GROUPS[sr.subject]].append(sr)
        for g, srs in groups.items():
            answered = [sr for sr in srs if sr.blank < sr.questions]
            keep = answered[0] if len(answered) == 1 else (srs[0] if not answered else None)
            if keep is not None:  # hiçbiri çözülmediyse grubun ilk dersi sayılır (yayınevi uygulaması)
                for sr in srs:
                    if sr is not keep:
                        sr.taken = False
                        for a in by_subj[sr.subject]:
                            a.status = "not_taken"

        checks.append(Check(name="buyuk_harf_dogru_cevap", ok=bad_upper == 0, detail=f"{bad_upper} uyumsuz"))
        # ders sayıları cevap dizisinden yeniden hesaplanır
        diffs = []
        for sr in subj_results:
            al = by_subj[sr.subject]
            if not al and not sr.taken:
                continue  # ızgarada yer almayan, çözülmemiş seçmeli ders
            cc = Counter(a.status for a in al)
            calc = (cc["correct"], cc["wrong"], cc["blank"] + cc["not_taken"])
            if calc != (sr.correct, sr.wrong, sr.blank):
                diffs.append(f"{sr.subject}: karne {sr.correct}/{sr.wrong}/{sr.blank} hesap {calc}")
            if not close(sr.correct - sr.wrong / penalty, sr.net):
                diffs.append(f"{sr.subject}: net formülü tutmuyor ({sr.net})")
        checks.append(Check(name="cevaplar_vs_ders_ozeti", ok=not diffs, detail="; ".join(diffs) or None))
        t = c["totals"]
        tk = [s for s in subj_results if s.taken]  # çözülmeyen seçmeli ders genel toplama girmez
        sums = (sum(s.questions for s in tk), sum(s.correct for s in tk), sum(s.wrong for s in tk),
                sum(s.blank for s in tk), round(sum(s.net for s in tk), 2))
        ok = sums[:4] == (t["questions"], t["correct"], t["wrong"], t["blank"]) and close(sums[4], t["net"])
        checks.append(Check(name="ders_toplamlari_vs_genel", ok=ok, detail=None if ok else f"{sums} vs {t}"))

        # okul net listesi ile çapraz kontrol
        cand = nl_by_name.get(norm(c["name"]), [])
        cand = [x for x in cand if close(x["points"], c["points"], 0.0005)] or cand
        if len(cand) == 1:
            x = cand[0]
            d2 = []
            for sr in subj_results:
                v = x["values"].get(sr.subject)
                if v is None:
                    if sr.correct or sr.wrong:
                        d2.append(f"{sr.subject}: listede yok")
                    continue
                if (v.get("D", 0), v.get("Y", 0)) != (sr.correct, sr.wrong) or not close(v.get("N", 0), sr.net):
                    d2.append(f"{sr.subject}: liste {v} karne {sr.correct}/{sr.wrong}/{sr.net}")
            if not close(x["points"], c["points"], 0.0005):
                d2.append(f"puan: liste {x['points']} karne {c['points']}")
            if x["genel_rank"] != c["ranks"].get("genel"):
                d2.append(f"genel sıra: liste {x['genel_rank']} karne {c['ranks'].get('genel')}")
            checks.append(Check(name="okul_net_listesi_eslesmesi", ok=not d2, detail="; ".join(d2) or None))
        else:
            checks.append(Check(name="okul_net_listesi_eslesmesi", ok=False,
                                detail=f"listede {len(cand)} eşleşme"))

        # karnedeki kazanım tablosu vs soru-kazanım eşlemesinden hesap
        if aq:
            agg = defaultdict(lambda: [0, 0, 0])
            for a in answers:
                q = qmap.get(a.qid)
                if q and q.kazanim:
                    kk = (q.subject, norm(q.kazanim).replace(" ", ""))
                    agg[kk][0] += 1
                    agg[kk][1] += a.status == "correct"
                    agg[kk][2] += a.status == "wrong"
            d3 = []
            for kr in c["kazanim_rows"]:
                try:
                    kk = (subject_code(kr["subject"]), norm(kr["kazanim"]).replace(" ", ""))
                except KeyError:
                    d3.append(f"bilinmeyen ders {kr['subject']}")
                    continue
                if kk not in agg:
                    if not inferred:  # çıkarımda karnede tam basılmayan kazanımlar atanamayabilir
                        d3.append(f"eşleşmeyen kazanım: {kr['kazanim'][:40]}")
                elif tuple(agg[kk]) != (kr["questions"], kr["correct"], kr["wrong"]):
                    d3.append(f"{kr['kazanim'][:40]}: karne {kr['questions']}/{kr['correct']}/{kr['wrong']} hesap {agg[kk]}")
            checks.append(Check(name="kazanim_tablosu_vs_soru_eslemesi", ok=not d3,
                                detail="; ".join(d3[:8]) or f"{len(c['kazanim_rows'])} kazanım satırı tutarlı"))

        students.append(Student(
            student_id=sid, name=c["name"], class_name=c["class_name"], school_no=c["school_no"], booklet=booklet,
            score=Score(type=exam_type, points=c["points"], percentile=c["percentile"]),
            totals=Totals(**t), ranks=Ranks(**c["ranks"]), subjects=subj_results, answers=answers,
            kazanim_report=[KazanimRow(subject=subject_code(k["subject"]), kazanim=k["kazanim"],
                                       questions=k["questions"], correct=k["correct"], wrong=k["wrong"],
                                       success_pct=k["success_pct"]) for k in c["kazanim_rows"]],
            source_page=c["page"], checks=checks))

    # ---------- sınav düzeyi: soru istatistikleri öğrenci cevaplarından yeniden üretilebiliyor mu?
    if aq and not inferred:  # hesaplanmış istatistikte bu kontrol anlamsız (aynı veriden üretildi)
        agg = defaultdict(Counter)
        sec_active = {}
        for st in students:
            for a in st.answers:
                sec = qmap[a.qid].section
                sec_active.setdefault((st.student_id, sec), False)
                if a.given:
                    sec_active[(st.student_id, sec)] = True
        for st in students:
            for a in st.answers:
                q = qmap[a.qid]
                if not sec_active[(st.student_id, q.section)]:  # bölüme hiç girmeyen öğrenci sayılmaz
                    continue
                agg[a.qid][a.given or "Boş"] += 1
        bad = []
        for q in questions:
            s = q.institution_stats
            exp = {o: s.options[o].count for o in "ABCDE"} | {"Boş": s.blank.count}
            got = {o: agg[q.qid].get(o, 0) for o in exp}
            if exp != got:
                bad.append(q.qid)
        # not: yayınevi çözülmeyen seçmeli dersi "Boş" sayıyor; aynı kural uygulanır
        exam_checks.append(Check(name="kurum_sik_dagilimi_vs_ogrenci_cevaplari", ok=not bad,
                                 detail=f"{len(bad)} soru uyumsuz: {', '.join(bad[:10])}" if bad
                                 else f"{len(questions)} sorunun şık dağılımı öğrenci cevaplarından birebir üretildi"))

    nl_n = len(nl.get("students", []))
    exam_checks.append(Check(name="karne_sayisi_vs_liste", ok=nl_n in (0, len(students)),
                             detail=f"{len(students)} karne, listede {nl_n} öğrenci"))

    averages, average_points = {}, {}
    for k, v in (nl.get("averages") or {}).items():
        averages[k] = {g: SubjectAverage(**x) for g, x in v.items() if isinstance(x, dict)}
        if "PUAN" in v:
            average_points[k] = v["PUAN"]

    inst = Institution(name=c0["school"], city=c0.get("city"), district=c0.get("district"))
    part = c0["participation"]
    school_slug = "-".join(slug(c0["school"]).split("-")[:3])
    exam = Exam(exam_id=f"{slug(parser_mod.PARSER_NAME)}-{slug(c0['exam_name'])}-{school_slug}",
                name=c0["exam_name"], type=exam_type, institution=inst,
                participation=Participation(kurum=part.get("kurum"), ilce=part.get("ilce"), il=part.get("il"),
                                            genel=part.get("genel")))
    source = Source(publisher=parser_mod.PUBLISHER, parser=parser_mod.PARSER_NAME,
                    parser_version=parser_mod.PARSER_VERSION, file_name=os.path.basename(path),
                    file_sha256=sha256(path), page_count=raw["page_count"], extraction="text_layer")
    if raw.get("unknown_pages"):
        exam_checks.append(Check(name="taninmayan_sayfalar", ok=False, detail=str(raw["unknown_pages"])))
    return ExamReport(source=source, exam=exam, sections=sections, questions=questions, averages=averages,
                      average_points=average_points, students=students, checks=exam_checks)
