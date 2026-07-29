"""Prompt template for the context resolution graph.

Single unified prompt replaces the two-branch regex+LLM system in the old
_rewrite_query. The LLM decides NO_RETRIEVAL vs RETRIEVE purely on semantic
grounds (no regex pre-filtering) and produces two outputs in one call:

- retrieval_query: a richer, context-synthesized query for document retrieval
  (per SELF-multi-RAG / conversation-summary research: richer context beats
  terse single-question rewrites for retrieval effectiveness)
- cache_query: a short standalone question, used as the semantic cache key
  (kept separate so cache hit rates aren't hurt by longer synthesized queries)
"""
from __future__ import annotations

CONTEXT_RESOLUTION_PROMPT = """Kamu adalah asisten yang menentukan apakah pertanyaan terakhir user butuh pencarian dokumen baru, dengan mempertimbangkan riwayat percakapan.

Tugasmu: baca riwayat percakapan dan pertanyaan terakhir, lalu hasilkan JSON dengan tiga field:

1. "decision": salah satu dari:
   - "NO_RETRIEVAL" — pertanyaan tidak butuh pencarian dokumen (basa-basi, ucapan terima kasih, atau follow-up murni seperti "maksudnya gimana?"/"jelasin lebih detail" yang bisa dijawab ulang dari jawaban sebelumnya di percakapan tanpa dokumen baru)
   - "RETRIEVE" — pertanyaan butuh pencarian dokumen, baik itu topik baru, follow-up yang merujuk konteks sebelumnya (eksplisit seperti 'itu', 'tadi', 'tersebut', atau implisit seperti 'kalau luar negeri gimana?'), MAUPUN pertanyaan yang sama persis/mengulang pertanyaan substantif yang sudah pernah ditanyakan sebelumnya di percakapan ini — pengulangan pertanyaan SOP/prosedur BUKAN basa-basi, jadi tetap harus RETRIEVE supaya user dapat jawaban lengkap dengan evidence dan citation lagi, bukan cuma dirujuk ke jawaban lama

2. "retrieval_query": query yang akan dipakai untuk mencari dokumen. Sintesiskan konteks yang relevan dari percakapan ke dalam query ini secara kaya — jangan hanya mengganti kata ganti, tapi sertakan detail penting (nama entitas, durasi, jumlah, jenis prosedur) yang disebut di percakapan supaya pencarian dokumen lebih akurat. Kalau decision adalah NO_RETRIEVAL, isi field ini dengan pertanyaan aslinya saja.

3. "cache_query": versi ringkas dan mandiri dari pertanyaan (satu kalimat pendek), dipakai sebagai kunci cache. Berbeda dari retrieval_query yang bisa lebih panjang dan detail, cache_query harus tetap singkat.

Jangan menjawab pertanyaan user. Jangan menambah fakta yang tidak ada di percakapan.

Balas HANYA dengan JSON valid, tanpa markdown code fence, tanpa teks lain. Format:
{{"decision": "NO_RETRIEVAL atau RETRIEVE", "retrieval_query": "...", "cache_query": "..."}}

Contoh 1 (rujukan eksplisit):
Percakapan sebelumnya: membahas prosedur resign.
Pertanyaan terakhir: Form apa aja yang harus diisi buat itu?
Jawaban: {{"decision": "RETRIEVE", "retrieval_query": "form yang harus diisi untuk prosedur resign atau pengunduran diri karyawan", "cache_query": "form untuk resign"}}

Contoh 2 (rujukan implisit, kalimat lanjutan):
Percakapan sebelumnya: membahas perjalanan dinas dalam negeri.
Pertanyaan terakhir: Kalau luar negeri gimana?
Jawaban: {{"decision": "RETRIEVE", "retrieval_query": "aturan dan prosedur perjalanan dinas luar negeri", "cache_query": "perjalanan dinas luar negeri gimana"}}

Contoh 3 (detail spesifik harus disintesis ke retrieval_query):
Percakapan sebelumnya: membahas perjalanan dinas Manager ke luar negeri selama 3 hari.
Pertanyaan terakhir: Dari kasus tadi, uang makan dan uang sakunya itu dihitung per hari atau langsung total?
Jawaban: {{"decision": "RETRIEVE", "retrieval_query": "perhitungan uang makan dan uang saku untuk perjalanan dinas Manager ke luar negeri selama 3 hari, dihitung per hari atau total", "cache_query": "uang makan dan uang saku dihitung per hari atau total"}}

Contoh 4 (perubahan angka/parameter dari kasus sebelumnya):
Percakapan sebelumnya: membahas perjalanan dinas Manager ke luar negeri selama 3 hari dengan total USD 345.
Pertanyaan terakhir: Kalau durasinya berubah jadi 5 hari, total yang diterima jadi berapa?
Jawaban: {{"decision": "RETRIEVE", "retrieval_query": "total uang makan dan uang saku perjalanan dinas Manager ke luar negeri jika durasi berubah menjadi 5 hari", "cache_query": "total uang saku kalau durasi jadi 5 hari"}}

Contoh 5 (pertanyaan mandiri, tidak butuh konteks):
Percakapan sebelumnya: membahas prosedur resign.
Pertanyaan terakhir: HRIS tuh apa sih?
Jawaban: {{"decision": "RETRIEVE", "retrieval_query": "HRIS itu apa", "cache_query": "HRIS itu apa"}}

Contoh 6 (basa-basi, tidak butuh dokumen):
Percakapan sebelumnya: membahas prosedur resign.
Pertanyaan terakhir: Oke makasih ya infonya.
Jawaban: {{"decision": "NO_RETRIEVAL", "retrieval_query": "Oke makasih ya infonya.", "cache_query": "Oke makasih ya infonya."}}

Contoh 7 (pertanyaan substantif yang sama diulang lagi, bukan basa-basi):
Percakapan sebelumnya: user sudah tanya "Gimana sih alurnya kalau mau rekrut orang baru buat suatu posisi?" dan sudah dijawab lengkap dengan evidence.
Pertanyaan terakhir: Gimana sih alurnya klo misal mau rekrut orang baru gitu buat di suatu posisi
Jawaban: {{"decision": "RETRIEVE", "retrieval_query": "alur rekrutmen karyawan baru untuk mengisi suatu posisi", "cache_query": "alur rekrutmen karyawan baru untuk suatu posisi"}}

Percakapan sebelumnya:
{conversation_context}

Pertanyaan terakhir:
{question}

Jawaban:"""


def build_context_resolution_prompt(question: str, conversation_context: str) -> str:
    return CONTEXT_RESOLUTION_PROMPT.format(
        conversation_context=conversation_context,
        question=question,
    )
