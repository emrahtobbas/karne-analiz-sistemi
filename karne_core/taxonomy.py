"""Yayınevlerinin farklı ders/bölüm adlarını ortak kodlara eşler."""
import re
import unicodedata


def norm(s: str) -> str:
    s = s.replace("İ", "i").replace("I", "ı").lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("ı", "i")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


SUBJECT_ALIASES = {
    "TURKCE": ["turkce", "tyt turkce", "turk dili ve edebiyati"],
    "TARIH": ["tarih", "tarih 1"],
    "COGRAFYA": ["cografya", "cografya 1"],
    "FELSEFE": ["felsefe"],
    "DIN": ["din kul ve ahl bil", "din kulturu", "din kulturu ve ahlak bilgisi", "din"],
    "FELSEFE_SECMELI": ["felsefe secmeli"],
    "MATEMATIK": ["matematik", "matematik 1", "temel matematik"],
    "GEOMETRI": ["geometri"],
    "FIZIK": ["fizik"],
    "KIMYA": ["kimya"],
    "BIYOLOJI": ["biyoloji"],
}
_SUBJ = {a.replace(" ", ""): code for code, al in SUBJECT_ALIASES.items() for a in al}

SECTION_ALIASES = {
    "TYT_TURKCE": ["tyt turkce"],
    "TYT_SOSYAL": ["tyt sosyal", "tyt sosyal bilimler"],
    "TYT_MATEMATIK": ["tyt matematik", "tyt temel matematik"],
    "TYT_FEN": ["tyt fen", "tyt fen bilimleri"],
}
_SEC = {a.replace(" ", ""): code for code, al in SECTION_ALIASES.items() for a in al}

# Seçmeli gruplar: öğrenci gruptan yalnızca birini çözer
OPTIONAL_GROUPS = {"DIN": "TYT_DIN_FELSEFE", "FELSEFE_SECMELI": "TYT_DIN_FELSEFE"}


def subject_code(name: str) -> str:
    n = norm(name).replace(" ", "")  # harf aralıklı yazımlara dayanıklı
    if n in _SUBJ:
        return _SUBJ[n]
    raise KeyError(f"Bilinmeyen ders adı: {name!r} ({n})")


def section_code(name: str) -> str | None:
    return _SEC.get(norm(name).replace(" ", ""))
