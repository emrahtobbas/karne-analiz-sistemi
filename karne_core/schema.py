"""Yayınevinden bağımsız ortak karne şeması (v1).

Her yayınevi ayrıştırıcısı çıktısını bu modellere dönüştürür. API sözleşmesi bu şemadır.
Soru kimliği (qid) her zaman A kitapçığı sırasına göre verilir: "<BÖLÜM>-<A numarası>"
örn. "TYT_TURKCE-07". Öğrencinin kitapçığındaki numara ayrıca tutulur.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0"

AnswerStatus = Literal["correct", "wrong", "blank", "not_taken"]


class Institution(BaseModel):
    name: str
    city: Optional[str] = None
    district: Optional[str] = None


class Participation(BaseModel):
    kurum: Optional[int] = None
    ilce: Optional[int] = None
    il: Optional[int] = None
    genel: Optional[int] = None


class SubjectDef(BaseModel):
    code: str = Field(description="Ortak ders kodu, örn. MATEMATIK, FELSEFE_SECMELI")
    name: str = Field(description="Karnede yazan ad")
    question_count: int
    optional_group: Optional[str] = Field(
        None, description="Seçmeli dersler aynı grup adını taşır (öğrenci birini çözer)")


class SectionDef(BaseModel):
    code: str = Field(description="örn. TYT_TURKCE, TYT_SOSYAL")
    name: str
    question_count: int
    subjects: list[SubjectDef]


class SubjectAverage(BaseModel):
    correct: float
    wrong: float
    net: float


class OptionStats(BaseModel):
    count: int
    pct: Optional[float] = None


class QuestionStats(BaseModel):
    """Kurum geneli soru istatistiği (yayınevi raporundan)."""
    answered_n: int = Field(description="Bu bölümü çözen öğrenci sayısı")
    options: dict[str, OptionStats]
    blank: OptionStats
    correct_rate: float
    wrong_rate: float
    blank_rate: float
    flagged_erroneous: bool = False
    source: Literal["publisher", "computed"] = Field(
        "publisher", description="publisher: yayınevi raporundan; computed: öğrenci cevaplarından hesaplandı")


class QuestionInference(BaseModel):
    kazanim: Literal["kesin", "belirsiz", "yok"] = Field(
        description="kesin: tüm öğrenci kazanım tablolarıyla tek tutarlı atama; yok: karnede basılmamış")
    kazanim_alternatives: list[str] = Field(default_factory=list)
    booklet_map: dict[str, str] = Field(
        default_factory=dict, description="Kitapçık -> 'kesin' ya da 'tahmini (fark x)'")


class Question(BaseModel):
    qid: str
    section: str
    subject: str
    order_in_section: int = Field(description="A kitapçığındaki sıra")
    booklet_numbers: dict[str, int] = Field(description="Kitapçık -> soru no, örn. {'A': 1, 'B': 4}")
    answer_key: dict[str, str] = Field(description="Kitapçık -> doğru şık")
    kazanim: Optional[str] = None
    kazanim_code: Optional[str] = None
    inference: Optional[QuestionInference] = Field(
        None, description="Yalnızca soru analizi raporu olmayan formatlarda: bilginin nasıl çıkarıldığı")
    institution_stats: Optional[QuestionStats] = None


class Score(BaseModel):
    type: str
    points: Optional[float] = None
    percentile: Optional[float] = Field(None, description="Karnede yazan yüzdelik (%)")


class Totals(BaseModel):
    questions: int
    correct: int
    wrong: int
    blank: int
    net: float


class Ranks(BaseModel):
    sube: Optional[int] = None
    kurum: Optional[int] = None
    ilce: Optional[int] = None
    il: Optional[int] = None
    genel: Optional[int] = None


class SubjectResult(BaseModel):
    section: str
    subject: str
    questions: int
    correct: int
    wrong: int
    blank: int
    net: float
    success_pct: Optional[float] = None
    taken: bool = True


class Answer(BaseModel):
    qid: str
    booklet_no: int
    key: str
    given: Optional[str] = Field(None, description="İşaretlenen şık (büyük harf); boşsa null; '*' = çift/geçersiz işaretleme")
    status: AnswerStatus


class KazanimRow(BaseModel):
    subject: str
    kazanim: str
    questions: int
    correct: int
    wrong: int
    success_pct: float


class Check(BaseModel):
    name: str
    ok: bool
    detail: Optional[str] = None


class Student(BaseModel):
    student_id: str
    name: str
    class_name: Optional[str] = None
    school_no: Optional[str] = None
    booklet: Optional[str] = None
    score: Score
    totals: Totals
    ranks: Ranks
    subjects: list[SubjectResult]
    answers: list[Answer]
    kazanim_report: list[KazanimRow] = Field(
        default_factory=list, description="Karnede basılı kazanım tablosu (ham)")
    source_page: Optional[int] = None
    checks: list[Check] = Field(default_factory=list)


class Source(BaseModel):
    publisher: str
    parser: str
    parser_version: str
    file_name: str
    file_sha256: str
    page_count: int
    extraction: Literal["text_layer", "vision", "manual"]


class Exam(BaseModel):
    exam_id: str
    name: str
    type: str = Field(description="TYT, AYT, LGS, ...")
    date: Optional[str] = None
    institution: Institution
    participation: Participation


class ExamReport(BaseModel):
    schema_version: str = SCHEMA_VERSION
    source: Source
    exam: Exam
    sections: list[SectionDef]
    questions: list[Question]
    averages: dict[str, dict[str, SubjectAverage]] = Field(
        default_factory=dict, description="'genel' / 'kurum' -> ders kodu -> ortalama")
    average_points: dict[str, float] = Field(default_factory=dict, description="'genel' / 'kurum' -> ortalama puan")
    students: list[Student]
    checks: list[Check] = Field(default_factory=list)


class StudentExamFile(BaseModel):
    """Öğrenci başına tek dosya: sınav bağlamı + öğrencinin sonucu (API'nin döndüreceği birim)."""
    schema_version: str = SCHEMA_VERSION
    source: Source
    exam: Exam
    sections: list[SectionDef]
    questions: list[Question]
    averages: dict[str, dict[str, SubjectAverage]] = Field(default_factory=dict)
    average_points: dict[str, float] = Field(default_factory=dict)
    student: Student
