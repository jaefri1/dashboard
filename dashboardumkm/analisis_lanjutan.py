"""
analisis_lanjutan.py
Analisis Data Mining tambahan:
  1. Tren multi-tahun aset koperasi (satu-satunya data yang punya
     riwayat tahun jamak asli — UMKM/koperasi/industri hanya lengkap
     di tahun 2024)
  2. Korelasi antar indikator (UMKM, industri kecil, koperasi) across
     19 kecamatan, data cross-sectional tahun 2024

Output:
  - data/processed/tren_aset_koperasi.csv
  - data/processed/korelasi_indikator.csv

Jalankan:
    python analisis_lanjutan.py
"""

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path

DB_PATH = Path("data/db/umkm_semarang.db")
OUT_DIR = Path("data/processed")
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ════════════════════════════════════════════════════════════
# BAGIAN 1: TREN MULTI-TAHUN ASET KOPERASI
# ════════════════════════════════════════════════════════════
def analisis_tren_aset(conn: sqlite3.Connection) -> pd.DataFrame:
    print("=" * 55)
    print("BAGIAN 1: TREN ASET KOPERASI 2017-2023")
    print("=" * 55)

    df = pd.read_sql_query("""
        SELECT jenis_koperasi, tahun, aset_rupiah
        FROM aset_koperasi
        WHERE semester = 'Semester II'
        ORDER BY jenis_koperasi, tahun
    """, conn)

    # Deteksi lompatan skala secara otomatis (bukan angka hardcode) —
    # tahun mana pun yang totalnya melonjak >50x dari tahun sebelumnya
    # ditandai sebagai kemungkinan perubahan satuan/metodologi laporan.
    total_tahun = df.groupby("tahun")["aset_rupiah"].sum()
    total_tahun = total_tahun[total_tahun > 0].sort_index()
    rasio = total_tahun / total_tahun.shift(1)
    tahun_lompatan = rasio[rasio > 50].index.tolist()

    print(f"\n  Total aset per tahun (miliar Rp):")
    print((total_tahun / 1e9).round(2).to_string())

    if tahun_lompatan:
        print(f"\n  ⚠ Terdeteksi lompatan skala tidak wajar di tahun: {tahun_lompatan}")
        print(f"    Rasio kenaikan: {rasio[tahun_lompatan].round(1).to_dict()}")
        print(f"    Kemungkinan besar bukan pertumbuhan riil — lebih mungkin")
        print(f"    perubahan satuan/metodologi pelaporan di sumber data.")
        print(f"    → Perlu dikonfirmasi ke dinas sebelum dipakai sebagai")
        print(f"      klaim 'pertumbuhan aset' di laporan.")

    # Tandai tiap baris: masuk periode mana (sebelum/sesudah lompatan,
    # atau memang tidak ada data sama sekali di tahun tsb)
    batas = min(tahun_lompatan) if tahun_lompatan else None
    df["periode"] = "Tidak terklasifikasi"
    if batas:
        df.loc[df["tahun"] < batas, "periode"] = f"Sebelum {batas} (skala berbeda)"
        df.loc[(df["tahun"] >= batas) & (df["aset_rupiah"] > 0), "periode"] = \
            f"{batas} dan sesudahnya (skala konsisten)"
        df.loc[(df["tahun"] >= batas) & (df["aset_rupiah"] == 0), "periode"] = \
            "Tidak ada data dilaporkan"

    # Hitung tren HANYA pada periode yang skalanya konsisten DAN
    # benar-benar punya data (bukan 0 karena belum dilaporkan)
    if batas:
        df_reliable = df[(df["tahun"] >= batas) & (df["aset_rupiah"] > 0)]
        tahun_min = df_reliable["tahun"].min()
        tahun_maks = df_reliable["tahun"].max()
        print(f"\n  Tren dihitung hanya untuk periode konsisten & berdata "
              f"({tahun_min}-{tahun_maks}):")
        for jenis in sorted(df_reliable["jenis_koperasi"].unique()):
            sub = df_reliable[df_reliable["jenis_koperasi"] == jenis].sort_values("tahun")
            if len(sub) >= 2 and sub["aset_rupiah"].iloc[0] > 0:
                pertumbuhan = (
                    (sub["aset_rupiah"].iloc[-1] / sub["aset_rupiah"].iloc[0]) - 1
                ) * 100
                print(f"    {jenis:<12} {sub['tahun'].iloc[0]}→{sub['tahun'].iloc[-1]}: "
                      f"{pertumbuhan:+.1f}%")

    df.to_csv(OUT_DIR / "tren_aset_koperasi.csv", index=False, encoding="utf-8-sig")
    print(f"\n  Disimpan: data/processed/tren_aset_koperasi.csv")
    return df


# ════════════════════════════════════════════════════════════
# BAGIAN 2: KORELASI ANTAR INDIKATOR (cross-sectional, 2024)
# ════════════════════════════════════════════════════════════
def analisis_korelasi(conn: sqlite3.Connection) -> pd.DataFrame:
    print("\n" + "=" * 55)
    print("BAGIAN 2: KORELASI ANTAR INDIKATOR (19 kecamatan, 2024)")
    print("=" * 55)

    df = pd.read_sql_query("""
        SELECT k.nama_kecamatan AS kecamatan, h.total_umkm,
               h.jumlah_industri, h.total_koperasi
        FROM hasil_klaster h
        JOIN kecamatan k ON k.kecamatan_id = h.kecamatan_id
    """, conn)

    kolom = ["total_umkm", "jumlah_industri", "total_koperasi"]
    korelasi = df[kolom].corr(method="pearson").round(3)

    print(f"\n  Matriks korelasi Pearson (n=19 kecamatan):")
    print(korelasi.to_string())

    print(f"\n  ⚠ Catatan penting: n=19 itu sampel kecil, dan Pringapus adalah")
    print(f"    outlier jelas (UMKM jauh di atas kecamatan lain). Cek dulu")
    print(f"    apakah korelasinya bergantung pada satu titik itu saja:")

    df_tanpa_outlier = df[df["kecamatan"] != "Pringapus"]
    korelasi_tanpa_outlier = df_tanpa_outlier[kolom].corr(method="pearson").round(3)
    print(f"\n  Korelasi TANPA Pringapus (n=18):")
    print(korelasi_tanpa_outlier.to_string())

    selisih = (korelasi - korelasi_tanpa_outlier).abs()
    selisih_maks = selisih.values[~np.eye(len(kolom), dtype=bool)].max()
    print(f"\n  Selisih terbesar akibat exclude outlier: {selisih_maks:.3f}")
    if selisih_maks > 0.15:
        print(f"    → Selisih cukup besar. Korelasi di atas SENSITIF terhadap")
        print(f"      Pringapus — jangan disimpulkan sebagai pola umum tanpa")
        print(f"      menyebutkan bahwa satu kecamatan ini pengaruhnya besar.")
    else:
        print(f"    → Selisih kecil, korelasi relatif stabil dengan/tanpa outlier.")

    # Simpan kedua versi
    korelasi_gabung = korelasi.copy()
    korelasi_gabung.columns = [f"{c}_dgn_outlier" for c in korelasi_gabung.columns]
    korelasi_tanpa2 = korelasi_tanpa_outlier.copy()
    korelasi_tanpa2.columns = [f"{c}_tanpa_outlier" for c in korelasi_tanpa2.columns]
    hasil = pd.concat([korelasi_gabung, korelasi_tanpa2], axis=1)
    hasil.to_csv(OUT_DIR / "korelasi_indikator.csv", encoding="utf-8-sig")
    print(f"\n  Disimpan: data/processed/korelasi_indikator.csv")
    return korelasi


# ════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════
def main():
    conn = sqlite3.connect(DB_PATH)
    analisis_tren_aset(conn)
    analisis_korelasi(conn)
    conn.close()
    print("\nSelesai.")


if __name__ == "__main__":
    main()
