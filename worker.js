/**
 * Karne Analiz Sistemi - Cloudflare Worker
 * Dünyanın her yerinden milisaniyeler içinde çalışan Edge Uygulaması
 */

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const SUPABASE_URL = env.SUPABASE_URL || "https://vuswxiapsonwmnszwldx.supabase.co";
    const SUPABASE_KEY = env.SUPABASE_KEY || "sb_publishable_HcYxrFjEKe8B7q7PsL6P_A_YD19Ccmn";

    // 1. API: Sınavları Listele
    if (url.pathname === "/api/exams") {
      try {
        const res = await fetch(`${SUPABASE_URL}/rest/v1/exams?select=*&order=created_at.desc`, {
          headers: {
            "apikey": SUPABASE_KEY,
            "Authorization": `Bearer ${SUPABASE_KEY}`
          }
        });
        const data = await res.json();
        return new Response(JSON.stringify(data), {
          headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" }
        });
      } catch (err) {
        return new Response(JSON.stringify({ error: err.message }), { status: 500 });
      }
    }

    // 2. API: Bir Sınavdaki Öğrencileri Getir
    if (url.pathname.startsWith("/api/students")) {
      const examId = url.searchParams.get("exam_id");
      const search = url.searchParams.get("q") || "";
      let queryUrl = `${SUPABASE_URL}/rest/v1/exam_students?select=id,exam_id,name,class_name,school_no,booklet,score,totals,ranks`;
      if (examId) queryUrl += `&exam_id=eq.${encodeURIComponent(examId)}`;
      if (search) queryUrl += `&name=ilike.*${encodeURIComponent(search)}*`;
      queryUrl += `&order=totals->net.desc&limit=150`;

      try {
        const res = await fetch(queryUrl, {
          headers: {
            "apikey": SUPABASE_KEY,
            "Authorization": `Bearer ${SUPABASE_KEY}`
          }
        });
        const data = await res.json();
        return new Response(JSON.stringify(data), {
          headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" }
        });
      } catch (err) {
        return new Response(JSON.stringify({ error: err.message }), { status: 500 });
      }
    }

    // 3. API: Tekil Öğrenci Detayı (Cevaplar & Kazanımlar Dahil)
    if (url.pathname.startsWith("/api/student/")) {
      const studentId = url.pathname.replace("/api/student/", "");
      try {
        const res = await fetch(`${SUPABASE_URL}/rest/v1/exam_students?id=eq.${encodeURIComponent(studentId)}&select=*`, {
          headers: {
            "apikey": SUPABASE_KEY,
            "Authorization": `Bearer ${SUPABASE_KEY}`
          }
        });
        const data = await res.json();
        if (!data || data.length === 0) {
          return new Response(JSON.stringify({ error: "Öğrenci bulunamadı" }), { status: 404 });
        }
        return new Response(JSON.stringify(data[0]), {
          headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" }
        });
      } catch (err) {
        return new Response(JSON.stringify({ error: err.message }), { status: 500 });
      }
    }

    // 4. Ön Yüz Web Sayfası (SPA)
    return new Response(renderHTML(SUPABASE_URL, SUPABASE_KEY), {
      headers: { "Content-Type": "text/html; charset=utf-8" }
    });
  }
};

function renderHTML(supabaseUrl, supabaseKey) {
  return `<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Karne Analiz Portalı — Cloudflare Edge</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-main: #0B0F19;
      --bg-card: rgba(18, 24, 38, 0.75);
      --bg-card-hover: rgba(28, 36, 56, 0.85);
      --border-color: rgba(255, 255, 255, 0.08);
      --border-focus: rgba(99, 102, 241, 0.5);
      --primary: #6366F1;
      --primary-light: #818CF8;
      --primary-gradient: linear-gradient(135deg, #6366F1 0%, #A855F7 100%);
      --accent: #06B6D4;
      --success: #10B981;
      --warning: #F59E0B;
      --danger: #EF4444;
      --text-main: #F3F4F6;
      --text-muted: #9CA3AF;
      --text-dim: #6B7280;
      --radius: 16px;
      --radius-sm: 8px;
      --shadow: 0 10px 30px -10px rgba(0, 0, 0, 0.5);
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Plus Jakarta Sans', sans-serif;
      background-color: var(--bg-main);
      color: var(--text-main);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      background-image: 
        radial-gradient(at 0% 0%, rgba(99, 102, 241, 0.15) 0px, transparent 50%),
        radial-gradient(at 100% 100%, rgba(168, 85, 247, 0.15) 0px, transparent 50%);
      background-attachment: fixed;
    }

    header {
      border-bottom: 1px solid var(--border-color);
      backdrop-filter: blur(12px);
      background: rgba(11, 15, 25, 0.8);
      position: sticky;
      top: 0;
      z-index: 100;
    }

    .header-container {
      max-width: 1300px;
      margin: 0 auto;
      padding: 1rem 1.5rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .logo-group {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .logo-badge {
      background: var(--primary-gradient);
      width: 40px;
      height: 40px;
      border-radius: 10px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 20px;
      font-weight: 800;
      box-shadow: 0 4px 15px rgba(99, 102, 241, 0.4);
    }

    .logo-title h1 {
      font-size: 1.15rem;
      font-weight: 700;
      background: linear-gradient(135deg, #fff 0%, #cbd5e1 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    .logo-title p {
      font-size: 0.75rem;
      color: var(--accent);
      font-weight: 500;
    }

    .status-badge {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 6px 14px;
      background: rgba(16, 185, 129, 0.1);
      border: 1px solid rgba(16, 185, 129, 0.3);
      border-radius: 999px;
      font-size: 0.75rem;
      color: var(--success);
      font-weight: 600;
    }
    .status-dot {
      width: 8px;
      height: 8px;
      background: var(--success);
      border-radius: 50%;
      box-shadow: 0 0 8px var(--success);
      animation: pulse 2s infinite;
    }

    @keyframes pulse {
      0% { opacity: 0.6; transform: scale(0.95); }
      50% { opacity: 1; transform: scale(1.1); }
      100% { opacity: 0.6; transform: scale(0.95); }
    }

    main {
      max-width: 1300px;
      width: 100%;
      margin: 2rem auto;
      padding: 0 1.5rem;
      flex: 1;
    }

    /* Filtre Barı */
    .controls-grid {
      display: grid;
      grid-template-columns: 1fr 2fr;
      gap: 1rem;
      margin-bottom: 2rem;
    }

    @media (max-width: 768px) {
      .controls-grid { grid-template-columns: 1fr; }
    }

    .select-card, .search-card {
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: var(--radius);
      padding: 1rem 1.25rem;
      backdrop-filter: blur(10px);
      box-shadow: var(--shadow);
    }

    .control-label {
      font-size: 0.75rem;
      text-transform: uppercase;
      font-weight: 700;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      margin-bottom: 8px;
      display: block;
    }

    select, input[type="text"] {
      width: 100%;
      padding: 0.75rem 1rem;
      background: rgba(0, 0, 0, 0.3);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-sm);
      color: var(--text-main);
      font-size: 0.95rem;
      font-family: inherit;
      outline: none;
      transition: all 0.2s ease;
    }
    select:focus, input[type="text"]:focus {
      border-color: var(--primary);
      box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.2);
    }

    /* Ana Bölüm: Sol Öğrenci Listesi, Sağ Karne Kartı */
    .portal-layout {
      display: grid;
      grid-template-columns: 340px 1fr;
      gap: 1.5rem;
    }

    @media (max-width: 992px) {
      .portal-layout { grid-template-columns: 1fr; }
    }

    /* Öğrenci Listesi */
    .student-list-card {
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: var(--radius);
      backdrop-filter: blur(10px);
      display: flex;
      flex-direction: column;
      max-height: 800px;
      overflow: hidden;
    }
    .student-list-header {
      padding: 1rem 1.25rem;
      border-bottom: 1px solid var(--border-color);
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: rgba(255, 255, 255, 0.02);
    }
    .student-list-header h3 {
      font-size: 0.95rem;
      font-weight: 700;
    }
    .student-count-badge {
      background: rgba(99, 102, 241, 0.15);
      color: var(--primary-light);
      padding: 2px 8px;
      border-radius: 6px;
      font-size: 0.75rem;
      font-weight: 600;
    }
    .student-items {
      overflow-y: auto;
      flex: 1;
      padding: 0.5rem;
    }
    .student-item {
      padding: 0.85rem 1rem;
      border-radius: var(--radius-sm);
      cursor: pointer;
      transition: all 0.2s ease;
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 4px;
      border: 1px solid transparent;
    }
    .student-item:hover {
      background: var(--bg-card-hover);
      border-color: var(--border-color);
    }
    .student-item.active {
      background: rgba(99, 102, 241, 0.2);
      border-color: var(--primary);
    }
    .student-item-info h4 {
      font-size: 0.9rem;
      font-weight: 600;
      color: #fff;
    }
    .student-item-info p {
      font-size: 0.75rem;
      color: var(--text-dim);
    }
    .student-item-net {
      text-align: right;
    }
    .net-value {
      font-size: 1rem;
      font-weight: 800;
      color: var(--primary-light);
      font-family: 'JetBrains Mono', monospace;
    }
    .net-label {
      font-size: 0.65rem;
      color: var(--text-dim);
      text-transform: uppercase;
    }

    /* Karne Detay Kartı */
    .karne-card {
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: var(--radius);
      backdrop-filter: blur(10px);
      padding: 2rem;
      box-shadow: var(--shadow);
    }

    .karne-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      border-bottom: 1px solid var(--border-color);
      padding-bottom: 1.5rem;
      margin-bottom: 1.5rem;
      flex-wrap: wrap;
      gap: 1rem;
    }
    .karne-student-info h2 {
      font-size: 1.5rem;
      font-weight: 800;
      margin-bottom: 4px;
    }
    .karne-student-meta {
      display: flex;
      gap: 12px;
      font-size: 0.85rem;
      color: var(--text-muted);
      flex-wrap: wrap;
    }
    .karne-student-meta span {
      background: rgba(255, 255, 255, 0.05);
      padding: 3px 8px;
      border-radius: 4px;
    }

    .print-btn {
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid var(--border-color);
      color: var(--text-main);
      padding: 0.6rem 1.2rem;
      border-radius: var(--radius-sm);
      cursor: pointer;
      font-size: 0.85rem;
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 8px;
      transition: all 0.2s;
    }
    .print-btn:hover {
      background: var(--primary);
      border-color: var(--primary);
    }

    /* Puan ve Derece İstatistik Kutuları */
    .stats-row {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
      gap: 1rem;
      margin-bottom: 2rem;
    }
    .stat-box {
      background: rgba(0, 0, 0, 0.25);
      border: 1px solid var(--border-color);
      border-radius: var(--radius-sm);
      padding: 1rem;
      text-align: center;
    }
    .stat-title {
      font-size: 0.7rem;
      color: var(--text-dim);
      text-transform: uppercase;
      font-weight: 700;
      margin-bottom: 4px;
    }
    .stat-number {
      font-size: 1.4rem;
      font-weight: 800;
      font-family: 'JetBrains Mono', monospace;
      color: #fff;
    }
    .stat-box.highlight {
      background: linear-gradient(135deg, rgba(99, 102, 241, 0.15) 0%, rgba(168, 85, 247, 0.15) 100%);
      border-color: var(--primary);
    }
    .stat-box.highlight .stat-number {
      color: var(--primary-light);
    }

    /* Dersler Tablosu */
    .table-responsive {
      overflow-x: auto;
      margin-bottom: 2rem;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 0.9rem;
    }
    th {
      background: rgba(255, 255, 255, 0.03);
      padding: 0.85rem 1rem;
      font-weight: 700;
      color: var(--text-muted);
      border-bottom: 1px solid var(--border-color);
      font-size: 0.75rem;
      text-transform: uppercase;
    }
    td {
      padding: 0.85rem 1rem;
      border-bottom: 1px solid rgba(255, 255, 255, 0.04);
    }
    tr:hover td {
      background: rgba(255, 255, 255, 0.02);
    }
    .net-cell {
      font-family: 'JetBrains Mono', monospace;
      font-weight: 700;
      color: var(--accent);
    }

    /* Sekmeler */
    .tab-bar {
      display: flex;
      gap: 1rem;
      border-bottom: 1px solid var(--border-color);
      margin-bottom: 1.5rem;
    }
    .tab-btn {
      background: none;
      border: none;
      color: var(--text-muted);
      font-size: 0.9rem;
      font-weight: 600;
      padding: 0.75rem 0.5rem;
      cursor: pointer;
      position: relative;
    }
    .tab-btn.active {
      color: var(--text-main);
    }
    .tab-btn.active::after {
      content: '';
      position: absolute;
      bottom: -1px;
      left: 0;
      right: 0;
      height: 2px;
      background: var(--primary-gradient);
    }

    /* Soru Izgarası */
    .answer-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(70px, 1fr));
      gap: 8px;
    }
    .answer-badge {
      background: rgba(0, 0, 0, 0.3);
      border: 1px solid var(--border-color);
      border-radius: 6px;
      padding: 6px 4px;
      text-align: center;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.75rem;
    }
    .answer-badge.correct {
      border-color: var(--success);
      background: rgba(16, 185, 129, 0.15);
      color: #6EE7B7;
    }
    .answer-badge.wrong {
      border-color: var(--danger);
      background: rgba(239, 68, 68, 0.15);
      color: #FCA5A5;
    }
    .answer-badge.blank {
      border-color: rgba(255, 255, 255, 0.1);
      color: var(--text-dim);
    }
    .badge-no { font-weight: 700; font-size: 0.7rem; color: var(--text-muted); margin-bottom: 2px; }
    .badge-keys { display: flex; justify-content: center; gap: 4px; }
    .key-given { font-weight: 800; }
    .key-real { color: var(--text-dim); font-size: 0.65rem; }

    /* Kazanım Başarı Çubuğu */
    .progress-bar-bg {
      background: rgba(255, 255, 255, 0.08);
      height: 6px;
      border-radius: 999px;
      overflow: hidden;
      width: 100px;
    }
    .progress-bar-fill {
      height: 100%;
      border-radius: 999px;
      background: var(--primary-gradient);
    }

    .empty-state {
      text-align: center;
      padding: 4rem 1rem;
      color: var(--text-muted);
    }
    .empty-state svg {
      width: 64px;
      height: 64px;
      stroke: var(--text-dim);
      margin-bottom: 1rem;
    }

    @media print {
      body { background: #fff !important; color: #000 !important; }
      header, .controls-grid, .student-list-card, .tab-bar, .print-btn { display: none !important; }
      .portal-layout { grid-template-columns: 1fr !important; }
      .karne-card { border: none !important; box-shadow: none !important; padding: 0 !important; }
      .stat-box { border: 1px solid #ccc !important; color: #000 !important; }
      .stat-number { color: #000 !important; }
      table { border: 1px solid #ccc !important; }
      th, td { border: 1px solid #eee !important; color: #000 !important; }
    }
  </style>
</head>
<body>

  <header>
    <div class="header-container">
      <div class="logo-group">
        <div class="logo-badge">📊</div>
        <div class="logo-title">
          <h1>Karne Analiz Portalı</h1>
          <p>Cloudflare Edge + Supabase</p>
        </div>
      </div>
      <div class="status-badge">
        <span class="status-dot"></span>
        <span id="system-status">Supabase Bağlı</span>
      </div>
    </div>
  </header>

  <main>
    <!-- Filtreler -->
    <div class="controls-grid">
      <div class="select-card">
        <label class="control-label" for="exam-select">Sınav Seçimi</label>
        <select id="exam-select">
          <option value="">Sınavlar yükleniyor...</option>
        </select>
      </div>
      <div class="search-card">
        <label class="control-label" for="student-search">Öğrenci Ara</label>
        <input type="text" id="student-search" placeholder="Öğrenci adı, şube veya numara yazın...">
      </div>
    </div>

    <!-- Ana Panel -->
    <div class="portal-layout">
      <!-- Sol Öğrenci Listesi -->
      <div class="student-list-card">
        <div class="student-list-header">
          <h3>Öğrenci Listesi</h3>
          <span class="student-count-badge" id="student-count">0 Öğrenci</span>
        </div>
        <div class="student-items" id="student-list-container">
          <div class="empty-state">Öğrenciler yükleniyor...</div>
        </div>
      </div>

      <!-- Sağ Karne Kartı -->
      <div class="karne-card" id="karne-details-card">
        <div class="empty-state">
          <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          <h3>Karne Görüntülemek İçin Bir Öğrenci Seçin</h3>
          <p style="margin-top: 6px; font-size: 0.85rem;">Soldaki listeden bir öğrenciye tıklayarak detaylı soru ve kazanım analizini inceleyebilirsiniz.</p>
        </div>
      </div>
    </div>
  </main>

  <script>
    let currentExams = [];
    let currentStudents = [];
    let selectedStudentId = null;

    // Sayfa yüklendiğinde sınavları çek
    window.addEventListener('DOMContentLoaded', async () => {
      await loadExams();
    });

    async function loadExams() {
      try {
        const res = await fetch('/api/exams');
        const exams = await res.json();
        currentExams = exams;
        const select = document.getElementById('exam-select');
        select.innerHTML = '';

        if (!exams || exams.length === 0) {
          select.innerHTML = '<option value="">Henüz yüklenmiş sınav yok</option>';
          return;
        }

        exams.forEach(exam => {
          const opt = document.createElement('option');
          opt.value = exam.id;
          opt.textContent = \`\${exam.name} (\${exam.institution_name || 'Kurum Yok'})\`;
          select.appendChild(opt);
        });

        // İlk sınavın öğrencilerini getir
        select.addEventListener('change', () => loadStudents(select.value));
        await loadStudents(exams[0].id);
      } catch (err) {
        console.error("Sınavlar yüklenemedi:", err);
      }
    }

    async function loadStudents(examId, query = '') {
      const container = document.getElementById('student-list-container');
      container.innerHTML = '<div class="empty-state">Yükleniyor...</div>';
      try {
        let url = \`/api/students?exam_id=\${encodeURIComponent(examId)}\`;
        if (query) url += \`&q=\${encodeURIComponent(query)}\`;
        const res = await fetch(url);
        const students = await res.json();
        currentStudents = students;
        document.getElementById('student-count').textContent = \`\${students.length} Öğrenci\`;

        if (!students || students.length === 0) {
          container.innerHTML = '<div class="empty-state">Öğrenci bulunamadı.</div>';
          return;
        }

        container.innerHTML = '';
        students.forEach((s, idx) => {
          const div = document.createElement('div');
          div.className = \`student-item \${s.id === selectedStudentId ? 'active' : ''}\`;
          div.onclick = () => selectStudent(s.id);
          div.innerHTML = \`
            <div class="student-item-info">
              <h4>\${s.name}</h4>
              <p>Şube: \${s.class_name || '-'} | Kitapçık: \${s.booklet || '-'}</p>
            </div>
            <div class="student-item-net">
              <div class="net-value">\${s.totals?.net?.toFixed(2) || '0.00'}</div>
              <div class="net-label">Toplam Net</div>
            </div>
          \`;
          container.appendChild(div);

          // İlk öğrenciyi otomatik seç
          if (idx === 0 && !selectedStudentId) {
            selectStudent(s.id);
          }
        });
      } catch (err) {
        console.error("Öğrenciler yüklenemedi:", err);
      }
    }

    // Canlı arama
    let debounceTimer;
    document.getElementById('student-search').addEventListener('input', (e) => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        const examId = document.getElementById('exam-select').value;
        loadStudents(examId, e.target.value.trim());
      }, 250);
    });

    async function selectStudent(studentId) {
      selectedStudentId = studentId;
      document.querySelectorAll('.student-item').forEach(el => el.classList.remove('active'));

      const detailsCard = document.getElementById('karne-details-card');
      detailsCard.innerHTML = '<div class="empty-state">Karne detayları alınıyor...</div>';

      try {
        const res = await fetch(\`/api/student/\${studentId}\`);
        const s = await res.json();
        renderKarne(s);
      } catch (err) {
        detailsCard.innerHTML = '<div class="empty-state">Karne bilgisi alınamadı.</div>';
      }
    }

    function renderKarne(s) {
      const card = document.getElementById('karne-details-card');
      const score = s.score?.points ? s.score.points.toFixed(2) : '-';
      const net = s.totals?.net ? s.totals.net.toFixed(2) : '0.00';
      const rankKurum = s.ranks?.kurum || '-';
      const rankIl = s.ranks?.il || '-';
      const rankGenel = s.ranks?.genel || '-';

      card.innerHTML = \`
        <div class="karne-header">
          <div class="karne-student-info">
            <h2>\${s.name}</h2>
            <div class="karne-student-meta">
              <span>Şube: <strong>\${s.class_name || '-'}</strong></span>
              <span>No: <strong>\${s.school_no || '-'}</strong></span>
              <span>Kitapçık: <strong>\${s.booklet || 'A'}</strong></span>
            </div>
          </div>
          <button class="print-btn" onclick="window.print()">
            🖨️ Yazdır / PDF İndir
          </button>
        </div>

        <!-- İstatistik Kutuları -->
        <div class="stats-row">
          <div class="stat-box highlight">
            <div class="stat-title">TYT Puanı</div>
            <div class="stat-number">\${score}</div>
          </div>
          <div class="stat-box highlight">
            <div class="stat-title">Toplam Net</div>
            <div class="stat-number">\${net}</div>
          </div>
          <div class="stat-box">
            <div class="stat-title">Doğru / Yanlış / Boş</div>
            <div class="stat-number" style="font-size:1.1rem;">
              <span style="color:var(--success);">\${s.totals?.correct || 0}</span> / 
              <span style="color:var(--danger);">\${s.totals?.wrong || 0}</span> / 
              <span style="color:var(--text-dim);">\${s.totals?.blank || 0}</span>
            </div>
          </div>
          <div class="stat-box">
            <div class="stat-title">Kurum Derecesi</div>
            <div class="stat-number">\${rankKurum}</div>
          </div>
          <div class="stat-box">
            <div class="stat-title">Genel Derece</div>
            <div class="stat-number">\${rankGenel}</div>
          </div>
        </div>

        <!-- Ders Bazlı Tablo -->
        <div class="table-responsive">
          <table>
            <thead>
              <tr>
                <th>Ders</th>
                <th>Soru</th>
                <th>Doğru</th>
                <th>Yanlış</th>
                <th>Boş</th>
                <th>Net</th>
                <th>Başarı (%)</th>
              </tr>
            </thead>
            <tbody>
              \${(s.subjects || []).map(sub => \`
                <tr>
                  <td><strong>\${sub.subject}</strong></td>
                  <td>\${sub.questions}</td>
                  <td style="color:var(--success); font-weight:600;">\${sub.correct}</td>
                  <td style="color:var(--danger); font-weight:600;">\${sub.wrong}</td>
                  <td style="color:var(--text-dim);">\${sub.blank}</td>
                  <td class="net-cell">\${sub.net?.toFixed(2) || '0.00'}</td>
                  <td>
                    <div style="display:flex; align-items:center; gap:8px;">
                      <div class="progress-bar-bg">
                        <div class="progress-bar-fill" style="width: \${Math.max(0, Math.min(100, sub.success_pct || ((sub.net/sub.questions)*100)))}%;"></div>
                      </div>
                      <span style="font-size:0.8rem; font-family:'JetBrains Mono';">\${Math.round(sub.success_pct || ((sub.net/sub.questions)*100))}%</span>
                    </div>
                  </td>
                </tr>
              \`).join('')}
            </tbody>
          </table>
        </div>

        <!-- Sekmeler -->
        <div class="tab-bar">
          <button class="tab-btn active" id="tab-answers-btn" onclick="switchTab('answers')">📝 Soru Cevap Analizi (\${(s.answers || []).length} Soru)</button>
          <button class="tab-btn" id="tab-kazanim-btn" onclick="switchTab('kazanim')">🎯 Kazanım & Konu Analizi (\${(s.kazanim_report || []).length} Konu)</button>
        </div>

        <!-- Soru Cevap Tabı -->
        <div id="tab-answers-content">
          <div class="answer-grid">
            \${(s.answers || []).map((ans, i) => {
              const statusClass = ans.status === 'correct' ? 'correct' : (ans.status === 'wrong' ? 'wrong' : 'blank');
              return \`
                <div class="answer-badge \${statusClass}">
                  <div class="badge-no">S.\${ans.booklet_no || (i + 1)}</div>
                  <div class="badge-keys">
                    <span class="key-given">\${ans.given || '-'}</span>
                    <span class="key-real">(\${ans.key || '?'})</span>
                  </div>
                </div>
              \`;
            }).join('')}
          </div>
        </div>

        <!-- Kazanım Tabı -->
        <div id="tab-kazanim-content" style="display: none;">
          <div class="table-responsive">
            <table>
              <thead>
                <tr>
                  <th>Ders</th>
                  <th>Kazanım / Konu</th>
                  <th>Soru</th>
                  <th>Doğru</th>
                  <th>Yanlış</th>
                  <th>Başarı Oranı</th>
                </tr>
              </thead>
              <tbody>
                \${(s.kazanim_report || []).map(k => \`
                  <tr>
                    <td><span style="font-size:0.75rem; background:rgba(255,255,255,0.05); padding:2px 6px; border-radius:4px;">\${k.subject}</span></td>
                    <td><strong>\${k.kazanim}</strong></td>
                    <td>\${k.questions}</td>
                    <td style="color:var(--success);">\${k.correct}</td>
                    <td style="color:var(--danger);">\${k.wrong}</td>
                    <td>
                      <div style="display:flex; align-items:center; gap:8px;">
                        <div class="progress-bar-bg" style="width: 80px;">
                          <div class="progress-bar-fill" style="width: \${k.success_pct}%;"></div>
                        </div>
                        <span style="font-family:'JetBrains Mono'; font-size:0.8rem;">%\${Math.round(k.success_pct)}</span>
                      </div>
                    </td>
                  </tr>
                \`).join('')}
              </tbody>
            </table>
          </div>
        </div>
      \`;
    }

    function switchTab(tab) {
      const answersBtn = document.getElementById('tab-answers-btn');
      const kazanimBtn = document.getElementById('tab-kazanim-btn');
      const answersContent = document.getElementById('tab-answers-content');
      const kazanimContent = document.getElementById('tab-kazanim-content');

      if (tab === 'answers') {
        answersBtn.classList.add('active');
        kazanimBtn.classList.remove('active');
        answersContent.style.display = 'block';
        kazanimContent.style.display = 'none';
      } else {
        kazanimBtn.classList.add('active');
        answersBtn.classList.remove('active');
        kazanimContent.style.display = 'block';
        answersContent.style.display = 'none';
      }
    }
  </script>
</body>
</html>`;
}
