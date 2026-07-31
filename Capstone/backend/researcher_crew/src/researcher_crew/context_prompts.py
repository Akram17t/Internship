"""Prompt template for the context resolution graph — zero-shot variant.

Same contract as the few-shot version (decision / retrieval_query /
cache_query in one call), but with no worked examples at all.

Why this can work without examples
----------------------------------
The examples were carrying three separate loads:

1. Routing judgment (RETRIEVE vs NO_RETRIEVAL) — now fully carried by the
   grounding invariant plus an explicit tiebreaker. Droppable.
2. JSON format compliance — better handled outside the prompt via structured
   output / JSON schema mode if the provider supports it. See note below.
3. Calibration of the two query fields — the real load. Replaced here with
   explicit shape constraints rather than demonstrations, since constraints
   generalize across domains and examples do not.

The constraint doing the most work is the length relation between
cache_query and retrieval_query. Without examples the common failure is that
the two fields collapse into near-identical strings, which silently destroys
the cache hit rate the split exists to protect. Stating the relation
mechanically ("shorter, unless already minimal") makes that collapse a
visible rule violation instead of a stylistic drift.

If the provider supports JSON schema / structured outputs, enable it and add
a maxLength on cache_query. That moves constraint enforcement out of the
prompt entirely and is strictly more reliable than asking nicely.

Exception: one worked example was added for a specific observed failure mode
(verbatim repeat of an already-answered factual question misrouted to
NO_RETRIEVAL) where the existing tiebreaker instruction was stated but had
no anchor. This is not a reversion to general few-shot; it targets one
pattern the model was demonstrably getting wrong in production, not routing
judgment broadly (see CONTEXT_RESOLUTION_PROMPT).
"""
from __future__ import annotations

DEFAULT_DOMAIN = "kebijakan dan prosedur perusahaan"


CONTEXT_RESOLUTION_PROMPT = """Kamu adalah komponen dalam sistem tanya-jawab berbasis dokumen tentang {domain}. Tugasmu bukan menjawab pertanyaan user, tapi menyiapkan query pencarian dari pertanyaan terakhir dengan mempertimbangkan riwayat percakapan.

PRINSIP UTAMA
Setiap jawaban substantif ke user wajib berdiri di atas dokumen yang baru diambil, lengkap dengan evidence dan citation. Riwayat chat BUKAN sumber evidence yang sah — fakta yang sudah pernah muncul di jawaban sebelumnya tetap harus diambil ulang dari dokumen, bukan dirujuk balik ke teks chat.

Konsekuensinya: kalau giliran bicara terakhir masih meminta informasi apa pun, sekecil apa pun, jawabannya RETRIEVE. Tidak peduli pertanyaannya persis sama dengan yang tadi, cuma minta penjelasan ulang, atau jawabannya kebetulan sudah sempat tersinggung sepintas. Retrieval yang tidak perlu itu murah; jawaban tanpa evidence itu mahal.

Satu-satunya pengecualian adalah giliran bicara yang memang tidak meminta informasi sama sekali: ucapan terima kasih, penutup, atau basa-basi murni. Kalau kamu ragu suatu pesan meminta informasi atau tidak, pilih RETRIEVE.

Contoh kasus yang sering salah: giliran bicara terakhir mengulang persis pertanyaan yang sudah dijawab asisten sebelumnya di percakapan ini -- misalnya user pernah tanya "Berapa lama masa cuti melahirkan?", asisten sudah menjawabnya lengkap dengan evidence, lalu belakangan user tanya ulang persis "Berapa lama masa cuti melahirkan?" dengan kata-kata yang sama atau nyaris sama. Godaannya adalah menganggap ini NO_RETRIEVAL karena jawabannya "sudah ada" di riwayat chat. Itu salah. Prinsip di atas berlaku sama persis di sini: decision tetap RETRIEVE, retrieval_query dan cache_query diisi ulang dari pertanyaan itu apa adanya. Riwayat chat boleh dipakai untuk memahami rujukan/konteks, tapi fakta bahwa suatu pertanyaan "kebetulan sudah pernah dijawab" bukan alasan untuk NO_RETRIEVAL -- itu justru contoh persis dari kalimat "jawabannya kebetulan sudah sempat tersinggung sepintas" di paragraf sebelumnya.

OUTPUT
Balas dengan JSON berisi tiga field.

"decision" — "RETRIEVE" atau "NO_RETRIEVAL", sesuai prinsip di atas.

"retrieval_query" — teks yang dikirim ke mesin pencari dokumen. Harus memenuhi semua syarat berikut:
- Berdiri sendiri. Orang yang belum pernah melihat percakapan ini harus paham maksudnya tanpa penjelasan tambahan. Tidak boleh ada kata ganti atau rujukan yang menggantung ("itu", "tadi", "tersebut", "kasus barusan").
- Memuat setiap atribut penentu yang disebut di percakapan: entitas, level atau kategori, angka, durasi, jenis prosedur, kondisi khusus. Ujinya: satu detail layak dibawa kalau ketidakhadirannya bikin dokumen yang seharusnya ketemu jadi beda. Kalau tidak mengubah apa-apa, buang.
- Berbentuk pertanyaan atau frasa pencarian, bukan kalimat pernyataan, dan bukan jawaban.
- Tidak memuat ringkasan naratif percakapan. Bawa hasilnya saja, bukan ceritanya.
- Kalau pertanyaan terakhir pindah ke topik yang tidak berhubungan dengan percakapan sebelumnya, jangan bawa detail topik lama sedikit pun. Perlakukan sebagai pertanyaan baru yang berdiri sendiri.

"cache_query" — kunci cache semantik. Harus memenuhi semua syarat berikut:
- Maksimal 12 kata.
- Berbentuk seperti pertanyaan yang akan diketik user seandainya dia bertanya dari nol, tanpa konteks percakapan.
- Berisi inti pertanyaannya saja. Buang kualifikasi, angka, dan syarat yang bukan inti — justru bagian itu yang bikin dua pertanyaan serupa gagal ketemu di cache.
- Harus lebih pendek dari retrieval_query, kecuali pertanyaan terakhirnya memang sudah mandiri dan sesingkat itu. Kalau kedua field jadi mirip, cache_query-nya belum cukup diringkas.

Kedua field query HARUS pakai bahasa yang sama dengan pertanyaan terakhir user (kalau user tanya dalam bahasa Inggris, retrieval_query dan cache_query juga harus bahasa Inggris, bukan diterjemahkan ke Indonesia).

Untuk NO_RETRIEVAL, isi kedua field query dengan pertanyaan aslinya apa adanya.

Jangan menjawab pertanyaan user. Jangan menambahkan fakta yang tidak ada di percakapan. Balas HANYA dengan JSON valid, tanpa markdown code fence, tanpa teks lain:
{{"decision": "...", "retrieval_query": "...", "cache_query": "..."}}

Percakapan sebelumnya:
{conversation_context}

Pertanyaan terakhir:
{question}

Jawaban:"""


def build_context_resolution_prompt(
    question: str,
    conversation_context: str,
    domain: str = DEFAULT_DOMAIN,
) -> str:
    return CONTEXT_RESOLUTION_PROMPT.format(
        domain=domain,
        conversation_context=conversation_context,
        question=question,
    )
