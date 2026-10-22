-- ========================================================
-- KARNE ANALİZ SİSTEMİ - SUPABASE VERİTABANI ŞEMASI (v1)
-- ========================================================

-- 1. Sınavlar Tablosu (Exams)
CREATE TABLE IF NOT EXISTS public.exams (
    id TEXT PRIMARY KEY,                       -- exam_id (örn: supara-supara-alfa-seri-tyt)
    name TEXT NOT NULL,                        -- Sınav adı
    type TEXT NOT NULL,                        -- TYT, AYT, LGS vb.
    exam_date TEXT,                            -- Sınav tarihi
    institution_name TEXT,                     -- Kurum adı
    city TEXT,
    district TEXT,
    participation JSONB DEFAULT '{}'::jsonb,   -- Katılım sayıları (kurum, il, genel)
    sections JSONB DEFAULT '[]'::jsonb,        -- Sınav bölümleri ve dersler
    questions JSONB DEFAULT '[]'::jsonb,       -- Soru analizi ve kazanımlar
    averages JSONB DEFAULT '{}'::jsonb,        -- Genel/kurum ders ortalamaları
    average_points JSONB DEFAULT '{}'::jsonb,  -- Ortalama puanlar
    source JSONB DEFAULT '{}'::jsonb,          -- Ayrıştırıcı ve dosya bilgisi
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 2. Öğrenciler ve Sınav Sonuçları Tablosu (Student Exam Results)
CREATE TABLE IF NOT EXISTS public.exam_students (
    id TEXT PRIMARY KEY,                       -- student_id (sha256 hash veya benzersiz id)
    exam_id TEXT NOT NULL REFERENCES public.exams(id) ON DELETE CASCADE,
    name TEXT NOT NULL,                        -- Öğrenci Adı Soyadı
    class_name TEXT,                           -- Şube / Sınıf
    school_no TEXT,                            -- Okul Numarası
    booklet TEXT,                              -- Kitapçık Türü (A, B)
    score JSONB DEFAULT '{}'::jsonb,           -- Puan ve yüzdelik dilim
    totals JSONB DEFAULT '{}'::jsonb,          -- Toplam Doğru, Yanlış, Boş, Net
    ranks JSONB DEFAULT '{}'::jsonb,           -- Şube, kurum, ilçe, il, genel dereceler
    subjects JSONB DEFAULT '[]'::jsonb,        -- Ders bazlı sonuçlar
    answers JSONB DEFAULT '[]'::jsonb,         -- Soru soru öğrenci cevapları ve durumu
    kazanim_report JSONB DEFAULT '[]'::jsonb,  -- Karnedeki kazanım tablosu
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- İndeksler (Hızlı sorgulama için)
CREATE INDEX IF NOT EXISTS idx_exam_students_exam_id ON public.exam_students(exam_id);
CREATE INDEX IF NOT EXISTS idx_exam_students_name ON public.exam_students(name);
CREATE INDEX IF NOT EXISTS idx_exams_created_at ON public.exams(created_at DESC);

-- ========================================================
-- ROW LEVEL SECURITY (RLS) POLİTİKALARI
-- ========================================================
ALTER TABLE public.exams ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.exam_students ENABLE ROW LEVEL SECURITY;

-- Okuma Politikası: Herkes (öğrenci, öğretmen, veli) sonuçları görüntüleyebilir
CREATE POLICY "Herkes sınavları görebilir" 
ON public.exams FOR SELECT 
USING (true);

CREATE POLICY "Herkes öğrenci sonuçlarını görebilir" 
ON public.exam_students FOR SELECT 
USING (true);

-- Yazma/Güncelleme Politikası: Servis anahtarı (Service Role) veya giriş yapmış yetkili kullanıcılar ekleyebilir
CREATE POLICY "Yetkili kullanıcılar sınav ekleyebilir" 
ON public.exams FOR ALL 
USING (auth.role() = 'service_role' OR auth.uid() IS NOT NULL)
WITH CHECK (auth.role() = 'service_role' OR auth.uid() IS NOT NULL);

CREATE POLICY "Yetkili kullanıcılar öğrenci sonucu ekleyebilir" 
ON public.exam_students FOR ALL 
USING (auth.role() = 'service_role' OR auth.uid() IS NOT NULL)
WITH CHECK (auth.role() = 'service_role' OR auth.uid() IS NOT NULL);

-- ========================================================
-- STORAGE BUCKET (PDF Karneler İçin)
-- ========================================================
-- Supabase Dashboard > Storage üzerinden "karneler" adında bir Public bucket oluşturabilirsiniz.
