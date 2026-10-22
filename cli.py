"""Kullanım: python cli.py <karne.pdf> [--out out/]

Çıktılar:
  out/<exam_id>/exam_report.json         tüm sınav (ortak şema, ExamReport)
  out/<exam_id>/students/<id>.json       öğrenci başına dosya (StudentExamFile)
  out/<exam_id>/dogrulama_raporu.md      doğrulama özeti
"""
import argparse
import json
import os
from collections import Counter

from karne_core.builder import build
from karne_core.parsers import detect
from karne_core.schema import ExamReport, StudentExamFile


def write_validation(rep: ExamReport, path: str):
    lines = [f"# Doğrulama raporu — {rep.exam.name} / {rep.exam.institution.name}", "",
             f"Kaynak: `{rep.source.file_name}` ({rep.source.page_count} sayfa), ayrıştırıcı "
             f"`{rep.source.parser} {rep.source.parser_version}`", "",
             f"Öğrenci: **{len(rep.students)}**, soru: **{len(rep.questions)}**", "", "## Sınav düzeyi", ""]
    for c in rep.checks:
        lines.append(f"- {'✅' if c.ok else '❌'} `{c.name}` — {c.detail or ''}")
    lines += ["", "## Öğrenci düzeyi", ""]
    agg = Counter()
    fails = []
    for s in rep.students:
        for c in s.checks:
            agg[(c.name, c.ok)] += 1
            if not c.ok:
                fails.append(f"- s.{s.source_page} {s.name}: `{c.name}` — {c.detail}")
    names = sorted({k[0] for k in agg})
    lines.append("| Kontrol | Geçen | Kalan |")
    lines.append("|---|---|---|")
    for n in names:
        lines.append(f"| `{n}` | {agg[(n, True)]} | {agg[(n, False)]} |")
    if fails:
        lines += ["", "### Hatalar", ""] + fails
    open(path, "w").write("\n".join(lines) + "\n")
    return not fails and all(c.ok for c in rep.checks)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    mod, score = detect(a.pdf)
    raw = mod.parse(a.pdf)
    rep = build(raw, a.pdf, mod)
    d = os.path.join(a.out, rep.exam.exam_id)
    os.makedirs(os.path.join(d, "students"), exist_ok=True)
    with open(os.path.join(d, "exam_report.json"), "w") as f:
        f.write(rep.model_dump_json(indent=1))
    for s in rep.students:
        sf = StudentExamFile(source=rep.source, exam=rep.exam, sections=rep.sections, questions=rep.questions,
                             averages=rep.averages, average_points=rep.average_points, student=s)
        with open(os.path.join(d, "students", f"{s.student_id}.json"), "w") as f:
            f.write(sf.model_dump_json(indent=1))
    ok = write_validation(rep, os.path.join(d, "dogrulama_raporu.md"))
    print(f"{mod.PARSER_NAME} (güven {score:.2f}) -> {d}  | {len(rep.students)} öğrenci | doğrulama: {'TAMAM' if ok else 'SORUN VAR'}")


if __name__ == "__main__":
    main()
