"""Yayınevi ayrıştırıcı kaydı. Yeni yayınevi = yeni modül + buraya ekleme."""
import pdfplumber

from . import bes_cap, supara

PARSERS = [bes_cap, supara]


def detect(path: str):
    with pdfplumber.open(path) as pdf:
        scored = [(m.detect(pdf), m) for m in PARSERS]
    score, mod = max(scored, key=lambda x: x[0])
    if score < 0.5:
        raise ValueError("Tanınan bir karne formatı bulunamadı (görüntü tabanlı okuma Aşama 3'te).")
    return mod, score
