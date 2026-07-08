# Alur Semantic Cache

Dokumen ini menjelaskan cara kerja semantic cache di endpoint `/query`: kapan cache dipakai, kapan dilewati, dan bagaimana cache tetap aman saat dokumen SOP berubah.

## Gambaran Singkat

Semantic cache dipakai untuk mempercepat jawaban RAG ketika user menanyakan pertanyaan yang maknanya sama dengan pertanyaan sebelumnya.

Contoh:

```text
Q1: Seberapa besar uang saku dan uang makan?
Q2: Nominal uang makan dan uang saku perjalanan dinas berapa?
```

Kalau Q1 sudah pernah dijawab dengan citation yang valid, Q2 bisa langsung memakai jawaban cache tanpa generate ulang lewat LLM.

Semantic cache tidak menggantikan RAG. Cache hanya shortcut jika jawaban lama masih terbukti aman dipakai.

## Storage yang Dipakai

```text
backend/cache/app_state.db
  -> SQLite app state
  -> conversation_messages
  -> semantic_cache_entries

backend/cache/semantic_chroma
  -> Chroma khusus semantic cache
  -> menyimpan embedding pertanyaan cache

backend/chroma_db
  -> Chroma utama knowledge base SOP
  -> menyimpan chunk dokumen SOP
```

Pembagian ini sengaja dipisah:

- SQLite menyimpan payload yang harus presisi: jawaban, citation, form, model, active index.
- Chroma semantic cache hanya dipakai untuk mencari pertanyaan lama yang maknanya mirip.
- Chroma SOP tetap menjadi sumber retrieval utama.

## Alur Utama `/query`

```text
User bertanya
  |
  v
Ambil conversation context dari SQLite
  |
  v
Rewrite pertanyaan menjadi standalone question
  |
  v
Lookup semantic cache
  |
  +-- HIT valid --> return cached answer + citations + forms
  |
  +-- MISS ------> retrieve SOP chunks dari Chroma utama
                    |
                    v
                  generate jawaban dengan LLM
                    |
                    v
                  finalisasi citation dan form
                    |
                    v
                  simpan semantic cache jika jawaban valid
                    |
                    v
                  return jawaban baru
```

Response API tidak berubah:

```json
{
  "answer": "...",
  "citations": [],
  "form_downloads": [],
  "conversation_id": "..."
}
```

## Kenapa Lookup Setelah Rewrite?

Semantic cache memakai `standalone_question`, bukan raw question.

Alasannya: follow-up question sering ambigu.

Contoh:

```text
Conversation sebelumnya: user membahas uang saku perjalanan dinas
Raw question: "Kalau itu nominalnya berapa?"
Standalone question: "Nominal uang saku perjalanan dinas berapa?"
```

Kalau cache lookup memakai raw question, pertanyaan "itu" bisa salah match ke topik lain. Dengan rewrite dulu, cache key menjadi lebih jelas dan aman.

## Alur Cache Hit

Cache hit terjadi kalau pertanyaan baru mirip secara makna dengan pertanyaan lama dan semua guard valid.

```text
standalone_question
  |
  v
Cari pertanyaan paling mirip di backend/cache/semantic_chroma
  |
  v
Ambil entry_id kandidat
  |
  v
Ambil payload jawaban dari SQLite semantic_cache_entries
  |
  v
Validasi guard:
  similarity cukup?
  active_index sama?
  MODEL sama?
  EMBED_MODEL sama?
  citation ada?
  jawaban bukan fallback?
  |
  v
Update hit_count + last_hit_at
  |
  v
Return cached answer
```

Jadi walaupun vector search menemukan pertanyaan mirip, jawaban belum tentu langsung dipakai. Payload tetap harus lolos validasi.

## Alur Cache Miss

Cache miss berarti sistem lanjut ke RAG normal.

Penyebab miss yang normal:

- `SEMANTIC_CACHE_ENABLED=false`.
- Belum ada entry semantic cache.
- Similarity di bawah `SEMANTIC_CACHE_THRESHOLD`.
- Entry vector ada, tapi payload SQLite tidak ada.
- `active_index` beda karena SOP sudah direindex.
- `MODEL` atau `EMBED_MODEL` beda.
- Citation kosong.
- Jawaban lama adalah fallback/unsupported answer.

Setelah miss:

```text
retrieve SOP chunks
-> generate answer
-> finalisasi citation
-> kalau valid, simpan cache baru
```

## Guard Keamanan Cache

Sebuah cache entry hanya boleh dipakai kalau semua syarat ini terpenuhi:

| Guard | Tujuan |
| --- | --- |
| `similarity >= SEMANTIC_CACHE_THRESHOLD` | Mencegah pertanyaan beda maksud dianggap sama |
| `active_index` sama | Mencegah jawaban lama dipakai setelah SOP berubah |
| `MODEL` sama | Mencegah reuse jawaban dari model berbeda |
| `EMBED_MODEL` sama | Mencegah similarity beda embedding model dianggap valid |
| Citation tidak kosong | Mencegah return jawaban tanpa sumber |
| Jawaban bukan fallback | Mencegah cache menyimpan "tidak ditemukan" sebagai jawaban permanen |

Guard paling penting: semantic cache tidak boleh return jawaban tanpa citation.

## Saat SOP Di-update

Kalau file SOP berubah, vector DB SOP harus direbuild.

```text
SOP/PDF berubah
  |
  v
Rebuild vector DB SOP
  |
  v
Active Chroma index berubah
  |
  v
Cache entry lama otomatis stale
  |
  v
Pertanyaan yang sama persis akan miss karena active_index mismatch
  |
  v
Sistem retrieve dari SOP terbaru dan generate jawaban baru
```

Cache lama tidak dihapus otomatis. Entry lama tetap ada untuk audit, tapi tidak dipakai lagi selama `active_index` berbeda.

## SQLite Conversation Store

Conversation history juga dipindahkan ke SQLite supaya request tidak perlu load dan rewrite seluruh `conversations.json`.

Tabel:

```text
conversation_messages(
  id,
  conversation_id,
  role,
  content,
  created_at
)
```

Alur saat request masuk:

```text
conversation_id
-> ambil message terbaru dari SQLite
-> format menjadi context User/Assistant
-> kirim context ke query rewrite
```

Alur saat request selesai:

```text
question + answer
-> insert message user
-> insert message assistant
-> cleanup conversation expired
-> pruning sesuai MAX_CONVERSATIONS dan MAX_CONVERSATION_MESSAGES
```

File lama `backend/cache/conversations.json` hanya dibaca sekali saat migrasi awal. Setelah itu tidak ada write baru ke file tersebut.

## Konfigurasi

Default:

```env
APP_STATE_DB=backend/cache/app_state.db
SEMANTIC_CACHE_ENABLED=true
SEMANTIC_CACHE_DIR=backend/cache/semantic_chroma
SEMANTIC_CACHE_THRESHOLD=0.92
SEMANTIC_CACHE_TOP_K=1
```

Untuk mematikan semantic cache sementara:

```env
SEMANTIC_CACHE_ENABLED=false
```

## Cara Debug

Cek jumlah row SQLite:

```powershell
python -m backend.scripts.storage_status app-state
```

Contoh output:

```text
conversation_messages=138 semantic_cache_entries=0
```

Log yang penting dicari:

```text
semantic_cache=hit similarity=... entry=... active_index=...
semantic_cache=miss reason=empty
semantic_cache=miss reason=below_threshold similarity=...
semantic_cache=miss reason=index_mismatch cached_index=... active_index=...
semantic_cache=miss reason=model_mismatch
semantic_cache=miss reason=uncacheable_payload
semantic_cache=stored entry=... active_index=...
```

Makna cepat:

- `hit`: jawaban diambil dari cache.
- `empty`: belum ada kandidat cache.
- `below_threshold`: pertanyaan mirip, tapi belum cukup dekat.
- `index_mismatch`: SOP sudah berubah/reindex, cache lama tidak dipakai.
- `model_mismatch`: model berubah, cache lama tidak dipakai.
- `uncacheable_payload`: entry ada, tapi payload tidak aman dipakai.
- `stored`: jawaban valid berhasil disimpan ke semantic cache.

## Testing

Unit test:

```powershell
python -m unittest tests.test_cache_db tests.test_semantic_cache -v
```

Full test:

```powershell
python -m unittest discover -s tests -v
```

Regression manual:

```text
1. Tanya: Seberapa besar uang saku dan uang makan?
2. Pastikan jawaban punya citation.
3. Tanya paraphrase: Nominal uang makan dan uang saku perjalanan dinas berapa?
4. Pastikan log pertanyaan kedua: semantic_cache=hit.
5. Tanya pertanyaan mirip tapi beda maksud: Berapa reimbursement transport?
6. Pastikan tidak salah hit ke jawaban uang makan/uang saku.
7. Rebuild vector DB SOP.
8. Tanya paraphrase lagi.
9. Pastikan cache lama miss dengan reason=index_mismatch.
```

## Checklist Acceptance

- Public response `/query` tetap sama.
- Conversation context tetap bekerja untuk follow-up question.
- Tidak ada write baru ke `conversations.json`.
- Semantic cache hanya return jawaban dengan citation.
- Cache lama tidak dipakai setelah reindex.
- Pertanyaan paraphrase yang setara bisa hit.
- Pertanyaan mirip tapi beda maksud tetap miss.
