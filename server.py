"""Karne Analiz Sistemi - FastAPI Web Servisi.

PDF yüklemelerini kabul eder, yayınevini otomatik tanır,
karne verilerini JSON'a dönüştürür ve isteğe bağlı olarak Supabase'e kaydeder.
"""
import os
import shutil
import tempfile
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from karne_core.builder import build
from karne_core.parsers import detect
from karne_core.schema import ExamReport, StudentExamFile

# Supabase istemcisi (ortam değişkenleri varsa aktifleşir)
supabase = None
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")

if SUPABASE_URL and SUPABASE_KEY:
    try:
        from supabase import create_client
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"Supabase bağlantısı kurulamadı: {e}")

app = FastAPI(
    title="Karne Analiz Sistemi API",
    description="Deneme sınavı PDF karnelerini ayrıştırıp Supabase veritabanına aktaran API servisi",
    version="1.0.0"
)

# CORS ayarları (Cloudflare Pages ve yerel geliştirme için)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "status": "online",
        "service": "Karne Analiz Sistemi API",
        "supabase_connected": supabase is not None
    }


@app.get("/health")
def health():
    return {"status": "ok"}


def save_to_supabase(rep: ExamReport) -> dict:
    """Ayrıştırılan sınav raporunu Supabase veritabanına yazar."""
    if not supabase:
        raise HTTPException(
            status_code=500,
            detail="Supabase bağlantısı yapılandırılmamış (SUPABASE_URL veya SUPABASE_KEY eksik)."
        )

    # 1. Sınav kaydı
    exam_payload = {
        "id": rep.exam.exam_id,
        "name": rep.exam.name,
        "type": rep.exam.type,
        "exam_date": rep.exam.date,
        "institution_name": rep.exam.institution.name,
        "city": rep.exam.institution.city,
        "district": rep.exam.institution.district,
        "participation": rep.exam.participation.model_dump(),
        "sections": [s.model_dump() for s in rep.sections],
        "questions": [q.model_dump() for q in rep.questions],
        "averages": rep.averages,
        "average_points": rep.average_points,
        "source": rep.source.model_dump(),
    }
    supabase.table("exams").upsert(exam_payload).execute()

    # 2. Öğrenci kayıtları (batch halinde)
    students_payload = []
    for s in rep.students:
        students_payload.append({
            "id": f"{rep.exam.exam_id}_{s.student_id}",
            "exam_id": rep.exam.exam_id,
            "name": s.name,
            "class_name": s.class_name,
            "school_no": s.school_no,
            "booklet": s.booklet,
            "score": s.score.model_dump(),
            "totals": s.totals.model_dump(),
            "ranks": s.ranks.model_dump(),
            "subjects": [sub.model_dump() for sub in s.subjects],
            "answers": [ans.model_dump() for ans in s.answers],
            "kazanim_report": [k.model_dump() for k in s.kazanim_report],
        })

    # 50'şerli paketler halinde upsert
    batch_size = 50
    for i in range(0, len(students_payload), batch_size):
        batch = students_payload[i:i + batch_size]
        supabase.table("exam_students").upsert(batch).execute()

    return {
        "exam_id": rep.exam.exam_id,
        "students_count": len(students_payload),
        "status": "synced"
    }


@app.post("/api/parse")
async def parse_pdf(
    file: UploadFile = File(...),
    sync_to_supabase: bool = Query(default=False, description="Sonuçlar doğrudan Supabase'e kaydedilsin mi?")
):
    """Yüklenen PDF karnesini ayrıştırır ve yapılandırılmış JSON çıktısı üretir."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Sadece PDF dosyaları desteklenmektedir.")

    # Geçici dosyaya kaydet
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        mod, score = detect(tmp_path)
        if not mod:
            raise HTTPException(status_code=422, detail="PDF formatı veya yayınevi tanınamadı.")

        raw = mod.parse(tmp_path)
        rep = build(raw, tmp_path, mod)

        result = {
            "parser": mod.PARSER_NAME,
            "confidence": round(score, 2),
            "exam": rep.exam.model_dump(),
            "students_count": len(rep.students),
            "questions_count": len(rep.questions),
            "report": rep.model_dump()
        }

        if sync_to_supabase:
            sync_res = save_to_supabase(rep)
            result["supabase_sync"] = sync_res

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ayrıştırma hatası: {str(e)}")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
