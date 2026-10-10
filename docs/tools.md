# Panduan Menambah Tool (Tool Calling)

Gemini Live API memungkinkan model memanggil fungsi di sisi klien. Alur:

1. Model memutuskan memanggil tool → server mengirim `tool_call`
   (`id`, `name`, `args`).
2. Telegent mengeksekusi handler (`ToolRegistry.execute`) dengan timeout.
3. Hasil dikirim kembali via `send_tool_response`; model melanjutkan jawaban.

## 1. Buat handler

Handler boleh sinkron atau asinkron, menerima `ToolContext` dan `dict` argumen,
mengembalikan `dict`.

```python
from datetime import datetime
from zoneinfo import ZoneInfo
from telegent.ai.tools.spec import ToolContext


async def get_current_datetime(ctx: ToolContext, args: dict) -> dict:
    tz = args.get("timezone", "Asia/Jakarta")
    now = datetime.now(ZoneInfo(tz))
    return {"iso": now.isoformat(), "human": now.strftime("%A, %d %B %Y %H:%M"), "timezone": tz}
```

## 2. Deklarasikan ToolSpec

```python
from telegent.ai.tools.spec import ToolSpec

spec = ToolSpec(
    name="get_current_datetime",
    description="Mengambil tanggal & waktu saat ini untuk zona waktu tertentu.",
    handler=get_current_datetime,
    parameters_json_schema={
        "type": "object",
        "properties": {
            "timezone": {"type": "string", "description": "Zona waktu IANA, mis. Asia/Jakarta"}
        },
    },
    timeout=2.0,
    behavior="BLOCKING",   # "BLOCKING" | "NON_BLOCKING"
)
```

- `name` harus valid: huruf/underscore di awal, a-z A-Z 0-9 _ . : -.
- `description` menentukan kapan model memanggil tool — tulis jelas.
- `parameters_json_schema` mengikuti JSON Schema objek.
- `timeout` (detik) → bila lewat, registry mengembalikan `{"error": "..."}`.
- `behavior`:
  - `BLOCKING` — model menunggu hasil (cocok karena persona sudah bilang "saya cek dulu ya").
  - `NON_BLOCKING` — model tetap dapat berbicara saat tool berjalan.

## 3. Daftarkan

Tambahkan ke daftar bawaan di `telegent/ai/tools/builtin.py`:

```python
def default_tools() -> list[ToolSpec]:
    return [make_datetime_tool(), spec]     # tool baru di sini
```

Registry otomatis membentuk deklarasi ke `LiveConnectConfig.tools`.

## Hasil & Error

- Sukses: `return {"...": ...}` → dikirim sebagai `{"output": {...}}`.
- Gagal: `raise Exception("pesan")` → dikirim sebagai `{"error": "pesan"}`.
  Jangan biarkan exception menembus; registry sudah menangkapnya.

## Aksi Sesi (contoh: mengakhiri panggilan)

Tool tidak hanya mengembalikan data — lewat `ToolContext` ia bisa memicu aksi sesi.
Contoh bawaan: `end_call`.

```python
async def _end_call(ctx: ToolContext, args: dict) -> dict:
    if ctx.hangup is None:
        return {"error": "Fitur tidak tersedia."}
    ctx.hangup()                     # sinkron: menjadwalkan, tidak memblokir
    return {"status": "ending_call"}
```

`ctx.hangup()` memanggil `CallSession.schedule_hangup()`, yang:

1. Menunggu audio jawaban **selesai diputar** (antrean kosong + tidak ada
   aktivitas audio/giliran selama `HANGUP_QUIET_SEC` ≈ 0,5 dtk) agar pamitan
   tidak terpotong.
2. Memanggil callback `on_hangup` milik aplikasi → mengirim `phone.DiscardCall`
   ke Telegram lalu menutup sesi.

Persona sudah diarahkan: bila penelpon berpamitan, AI mengucapkan pamitan singkat
lalu memanggil `end_call`. Tambahkan aksi sesi lain dengan pola yang sama
(tambahkan field di `ToolContext` + sediakan callback dari `TelegentApp`).

## Perilaku Barge-in

Bila penelpon memotong saat tool berjalan, server mengirim `tool_call_cancellation`;
`CallSession._cancel_tool` membatalkan tugas tool yang belum selesai secara otomatis.

## Pengujian

Uji handler/registry tanpa jaringan:

```python
from telegent.ai.tools.registry import ToolRegistry
from telegent.ai.tools.spec import ToolContext, ToolRequest

registry = ToolRegistry().register(spec)
result = await registry.execute(ToolContext(user_id=1, call_id=1), ToolRequest(id="1", name="get_current_datetime", args={}))
assert "output" in result.response
```

Lihat `tests/test_tools.py` sebagai contoh lengkap.
