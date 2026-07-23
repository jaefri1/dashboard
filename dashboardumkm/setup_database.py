"""
setup_database.py
Membangun database UMKM & Koperasi Kabupaten Semarang (SQLite)

Kenapa SQLite (bukan MySQL) sebagai default:
  - Tidak perlu install & jalankan server database terpisah — cukup Python
  - File .db bisa langsung dibuka pakai DB Browser for SQLite (gratis, GUI)
  - Tetap relational database sungguhan: PRIMARY KEY, FOREIGN KEY, JOIN,
    semua konsep normalisasi tetap berlaku sama seperti MySQL/PostgreSQL
  - Kalau dosen/dinas mewajibkan MySQL, skema setara ada di
    database_schema_mysql.sql — tinggal import lewat phpMyAdmin/Workbench

Skema (5 tabel, 1 tabel master + 4 tabel turunan):
  kecamatan       → tabel master, 19 baris
  sektor_umkm     → UMKM per kecamatan x sektor KBLI x tahun x semester
  koperasi        → koperasi per kecamatan x jenis x tahun x semester
  industri_kecil  → industri kecil per kecamatan x tahun x semester
  aset_koperasi   → aset koperasi per jenis x tahun x semester (level kabupaten)
  hasil_klaster   → OUTPUT dari data mining (K-Means), disimpan balik ke database

Jalankan:
    python setup_database.py
"""

import sqlite3
import pandas as pd
from pathlib import Path

DATA_DIR = Path("data")
DB_PATH  = DATA_DIR / "db" / "umkm_semarang.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


# ════════════════════════════════════════════════════════════
# LANGKAH 1: Buat skema (DDL)
# ════════════════════════════════════════════════════════════
def buat_skema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    PRAGMA foreign_keys = ON;

    DROP TABLE IF EXISTS profil_klaster;
    DROP TABLE IF EXISTS hasil_klaster;
    DROP TABLE IF EXISTS aset_koperasi;
    DROP TABLE IF EXISTS industri_kecil;
    DROP TABLE IF EXISTS koperasi;
    DROP TABLE IF EXISTS sektor_umkm;
    DROP TABLE IF EXISTS kecamatan;

    -- Tabel master: satu baris per kecamatan
    CREATE TABLE kecamatan (
        kecamatan_id   INTEGER PRIMARY KEY AUTOINCREMENT,
        nama_kecamatan TEXT NOT NULL UNIQUE
    );

    -- UMKM per kecamatan, per sektor KBLI, per periode
    CREATE TABLE sektor_umkm (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        kecamatan_id  INTEGER NOT NULL,
        sektor_kbli   TEXT    NOT NULL,
        tahun         INTEGER NOT NULL,
        semester      TEXT    NOT NULL,
        jumlah_usaha  INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (kecamatan_id) REFERENCES kecamatan(kecamatan_id)
    );

    -- Koperasi per kecamatan, per jenis, per periode
    CREATE TABLE koperasi (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        kecamatan_id     INTEGER NOT NULL,
        jenis_koperasi   TEXT    NOT NULL,
        tahun            INTEGER NOT NULL,
        semester         TEXT    NOT NULL,
        jumlah_koperasi  INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (kecamatan_id) REFERENCES kecamatan(kecamatan_id)
    );

    -- Industri kecil per kecamatan, per periode
    CREATE TABLE industri_kecil (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        kecamatan_id     INTEGER NOT NULL,
        tahun            INTEGER NOT NULL,
        semester         TEXT    NOT NULL,
        jumlah_industri  INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (kecamatan_id) REFERENCES kecamatan(kecamatan_id)
    );

    -- Aset koperasi per jenis (level kabupaten, bukan per kecamatan)
    CREATE TABLE aset_koperasi (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        jenis_koperasi  TEXT    NOT NULL,
        tahun           INTEGER NOT NULL,
        semester        TEXT    NOT NULL,
        aset_rupiah     REAL    NOT NULL DEFAULT 0
    );

    -- Hasil K-Means clustering (output Data Mining, disimpan ke Database)
    CREATE TABLE hasil_klaster (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        kecamatan_id     INTEGER NOT NULL,
        tahun            INTEGER NOT NULL,
        klaster_id       INTEGER,
        klaster          TEXT,
        total_umkm       INTEGER,
        jumlah_industri  INTEGER,
        total_koperasi   INTEGER,
        total_usaha      INTEGER,
        sektor_dominan   TEXT,
        warna            TEXT,
        FOREIGN KEY (kecamatan_id) REFERENCES kecamatan(kecamatan_id)
    );

    -- Profil ringkas tiap klaster: rata-rata & peringkat per indikator.
    -- Tabel rangkuman (bukan data transaksi), jadi kolom "kecamatan" di
    -- sini sengaja berupa daftar bertulisan (comma-separated) untuk
    -- ditampilkan langsung — relasi rincinya sendiri sudah ada dan
    -- ternormalisasi lewat tabel hasil_klaster di atas.
    CREATE TABLE profil_klaster (
        klaster             TEXT PRIMARY KEY,
        jumlah_kecamatan    INTEGER,
        kecamatan           TEXT,
        rata_umkm           REAL,
        peringkat_umkm      INTEGER,
        rata_industri       REAL,
        peringkat_industri  INTEGER,
        rata_koperasi       REAL,
        peringkat_koperasi  INTEGER
    );
    """)
    conn.commit()
    print("  Skema dibuat: 7 tabel (kecamatan, sektor_umkm, koperasi, "
          "industri_kecil, aset_koperasi, hasil_klaster, profil_klaster)")


# ════════════════════════════════════════════════════════════
# LANGKAH 2: Isi tabel kecamatan (master) lebih dulu
# ════════════════════════════════════════════════════════════
def isi_kecamatan(conn: sqlite3.Connection) -> dict:
    df = pd.read_csv(DATA_DIR / "clean" / "master_gabungan.csv")
    nama_list = sorted(df["kecamatan"].dropna().unique())

    conn.executemany(
        "INSERT INTO kecamatan (nama_kecamatan) VALUES (?)",
        [(n,) for n in nama_list],
    )
    conn.commit()

    # Kembalikan mapping nama -> id untuk dipakai isi tabel lain
    rows = conn.execute("SELECT kecamatan_id, nama_kecamatan FROM kecamatan").fetchall()
    mapping = {nama: kid for kid, nama in rows}
    print(f"  Tabel kecamatan: {len(mapping)} baris")
    return mapping


# ════════════════════════════════════════════════════════════
# LANGKAH 3: Isi tabel-tabel turunan
# ════════════════════════════════════════════════════════════
def isi_sektor_umkm(conn: sqlite3.Connection, kec_map: dict) -> None:
    df = pd.read_csv(DATA_DIR / "clean" / "umkm_kbli_flat.csv")
    df["kecamatan_id"] = df["kecamatan"].map(kec_map)
    df = df.dropna(subset=["kecamatan_id"])
    df["kecamatan_id"] = df["kecamatan_id"].astype(int)

    df[["kecamatan_id", "sektor_kbli", "tahun", "semester", "jumlah_usaha"]].to_sql(
        "sektor_umkm", conn, if_exists="append", index=False
    )
    print(f"  Tabel sektor_umkm: {len(df):,} baris")


def isi_koperasi(conn: sqlite3.Connection, kec_map: dict) -> None:
    df = pd.read_csv(DATA_DIR / "clean" / "koperasi_flat.csv")
    df = df[df["jenis_koperasi"] != "TOTAL"].copy()   # baris TOTAL tak perlu disimpan, bisa dihitung dari SUM
    df["kecamatan_id"] = df["kecamatan"].map(kec_map)
    df = df.dropna(subset=["kecamatan_id"])
    df["kecamatan_id"] = df["kecamatan_id"].astype(int)

    df[["kecamatan_id", "jenis_koperasi", "tahun", "semester", "jumlah_koperasi"]].to_sql(
        "koperasi", conn, if_exists="append", index=False
    )
    print(f"  Tabel koperasi: {len(df):,} baris")


def isi_industri_kecil(conn: sqlite3.Connection, kec_map: dict) -> None:
    df = pd.read_csv(DATA_DIR / "clean" / "industri_kecil.csv")
    df["kecamatan_id"] = df["kecamatan"].map(kec_map)
    df = df.dropna(subset=["kecamatan_id"])
    df["kecamatan_id"] = df["kecamatan_id"].astype(int)

    df[["kecamatan_id", "tahun", "semester", "jumlah_industri"]].to_sql(
        "industri_kecil", conn, if_exists="append", index=False
    )
    print(f"  Tabel industri_kecil: {len(df):,} baris")


def isi_aset_koperasi(conn: sqlite3.Connection) -> None:
    df = pd.read_csv(DATA_DIR / "clean" / "aset_koperasi.csv")
    df[["jenis_koperasi", "tahun", "semester", "aset_rupiah"]].to_sql(
        "aset_koperasi", conn, if_exists="append", index=False
    )
    print(f"  Tabel aset_koperasi: {len(df):,} baris")


def isi_hasil_klaster(conn: sqlite3.Connection, kec_map: dict) -> None:
    df = pd.read_csv(DATA_DIR / "processed" / "umkm_klaster.csv")
    df["kecamatan_id"] = df["kecamatan"].map(kec_map)
    df = df.dropna(subset=["kecamatan_id"])
    df["kecamatan_id"] = df["kecamatan_id"].astype(int)

    kolom = ["kecamatan_id", "tahun", "klaster_id", "klaster", "total_umkm",
              "jumlah_industri", "total_koperasi", "total_usaha",
              "sektor_dominan", "warna"]
    df[kolom].to_sql("hasil_klaster", conn, if_exists="append", index=False)
    print(f"  Tabel hasil_klaster: {len(df):,} baris")


def isi_profil_klaster(conn: sqlite3.Connection) -> None:
    df = pd.read_csv(DATA_DIR / "processed" / "klaster_profil.csv")
    kolom = ["klaster", "jumlah_kecamatan", "kecamatan",
              "rata_umkm", "peringkat_umkm",
              "rata_industri", "peringkat_industri",
              "rata_koperasi", "peringkat_koperasi"]
    df[kolom].to_sql("profil_klaster", conn, if_exists="append", index=False)
    print(f"  Tabel profil_klaster: {len(df):,} baris")


# ════════════════════════════════════════════════════════════
# LANGKAH 4: Verifikasi — jalankan beberapa query contoh
# ════════════════════════════════════════════════════════════
def verifikasi(conn: sqlite3.Connection) -> None:
    print("\n" + "=" * 55)
    print("VERIFIKASI — JUMLAH BARIS TIAP TABEL")
    print("=" * 55)
    tabel_list = ["kecamatan", "sektor_umkm", "koperasi",
                   "industri_kecil", "aset_koperasi", "hasil_klaster",
                   "profil_klaster"]
    for t in tabel_list:
        n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t:<18} {n:>6,} baris")

    print("\n" + "=" * 55)
    print("CONTOH QUERY — JOIN kecamatan + hasil_klaster")
    print("=" * 55)
    hasil = conn.execute("""
        SELECT k.nama_kecamatan, h.klaster, h.total_umkm, h.total_koperasi
        FROM hasil_klaster h
        JOIN kecamatan k ON k.kecamatan_id = h.kecamatan_id
        ORDER BY h.total_umkm DESC
        LIMIT 5
    """).fetchall()
    print(f"  {'Kecamatan':<16}{'Klaster':<12}{'UMKM':>8}{'Koperasi':>10}")
    for row in hasil:
        print(f"  {row[0]:<16}{row[1]:<12}{row[2]:>8}{row[3]:>10}")


# ════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════
def main():
    print("=" * 55)
    print("SETUP DATABASE — UMKM & Koperasi Kabupaten Semarang")
    print("=" * 55)

    conn = sqlite3.connect(DB_PATH)

    print("\nLangkah 1: Membuat skema")
    buat_skema(conn)

    print("\nLangkah 2: Mengisi tabel kecamatan (master)")
    kec_map = isi_kecamatan(conn)

    print("\nLangkah 3: Mengisi tabel turunan")
    isi_sektor_umkm(conn, kec_map)
    isi_koperasi(conn, kec_map)
    isi_industri_kecil(conn, kec_map)
    isi_aset_koperasi(conn)
    isi_hasil_klaster(conn, kec_map)
    isi_profil_klaster(conn)

    verifikasi(conn)

    conn.close()
    print(f"\nSelesai! Database tersimpan di: {DB_PATH}")
    print("Bisa dibuka pakai DB Browser for SQLite (gratis, GUI) untuk dicek visual.")


if __name__ == "__main__":
    main()
