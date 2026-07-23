"""
pdf_generator.py
Modul pembuat PDF laporan UMKM & Koperasi Kabupaten Semarang
Digunakan oleh dashboard Streamlit via tombol Export PDF
"""

import io
from datetime import datetime
import pandas as pd

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from reportlab.platypus import Image as RLImage


# ── Warna tema ──────────────────────────────────────────────
BIRU     = colors.HexColor("#185FA5")
BIRU_MUD = colors.HexColor("#E6F1FB")
ABU      = colors.HexColor("#F1EFE8")
ABU_TUA  = colors.HexColor("#5F5E5A")
HIJAU    = colors.HexColor("#1D9E75")
AMBER    = colors.HexColor("#BA7517")
MERAH    = colors.HexColor("#A32D2D")
PUTIH    = colors.white
HITAM    = colors.HexColor("#2C2C2A")


def buat_styles():
    """Buat kumpulan style teks untuk laporan."""
    base = getSampleStyleSheet()

    styles = {
        "judul": ParagraphStyle(
            "judul",
            fontSize=18, fontName="Helvetica-Bold",
            textColor=BIRU, alignment=TA_CENTER,
            spaceAfter=4,
        ),
        "subjudul": ParagraphStyle(
            "subjudul",
            fontSize=11, fontName="Helvetica",
            textColor=ABU_TUA, alignment=TA_CENTER,
            spaceAfter=2,
        ),
        "heading": ParagraphStyle(
            "heading",
            fontSize=12, fontName="Helvetica-Bold",
            textColor=BIRU, spaceBefore=14, spaceAfter=6,
            borderPad=4,
        ),
        "normal": ParagraphStyle(
            "normal",
            fontSize=10, fontName="Helvetica",
            textColor=HITAM, leading=15, spaceAfter=4,
        ),
        "kecil": ParagraphStyle(
            "kecil",
            fontSize=8, fontName="Helvetica",
            textColor=ABU_TUA,
        ),
        "tabel_header": ParagraphStyle(
            "tabel_header",
            fontSize=9, fontName="Helvetica-Bold",
            textColor=PUTIH, alignment=TA_CENTER,
        ),
        "tabel_isi": ParagraphStyle(
            "tabel_isi",
            fontSize=9, fontName="Helvetica",
            textColor=HITAM,
        ),
    }
    return styles


def buat_kpi_tabel(data_kpi):
    """
    Buat tabel KPI ringkasan (2 kolom x 2 baris).
    data_kpi = [
        {"label": "Total UMKM", "nilai": "19.180", "delta": "+4,2%", "naik": True},
        ...
    ]
    """
    # Susun grid 2x2
    baris = []
    for i in range(0, len(data_kpi), 2):
        sel = []
        for kpi in data_kpi[i:i+2]:
            tanda  = "▲" if kpi.get("naik", True) else "▼"
            warna_delta = HIJAU if kpi.get("naik", True) else MERAH
            isi = Table(
                [
                    [Paragraph(kpi["label"],
                               ParagraphStyle("kl", fontSize=8,
                                              textColor=ABU_TUA,
                                              fontName="Helvetica"))],
                    [Paragraph(kpi["nilai"],
                               ParagraphStyle("kv", fontSize=16,
                                              fontName="Helvetica-Bold",
                                              textColor=HITAM))],
                    [Paragraph(f"{tanda} {kpi['delta']}",
                               ParagraphStyle("kd", fontSize=8,
                                              fontName="Helvetica",
                                              textColor=warna_delta))],
                ],
                colWidths=[7.5*cm],
            )
            isi.setStyle(TableStyle([
                ("BACKGROUND",  (0,0), (-1,-1), ABU),
                ("ROUNDEDCORNERS", [6]),
                ("TOPPADDING",  (0,0), (-1,-1), 8),
                ("BOTTOMPADDING",(0,0), (-1,-1), 8),
                ("LEFTPADDING", (0,0), (-1,-1), 10),
                ("RIGHTPADDING",(0,0), (-1,-1), 10),
                ("ROWBACKGROUNDS",(0,0),(-1,-1),[ABU]),
            ]))
            sel.append(isi)
        # Tambah sel kosong jika ganjil
        while len(sel) < 2:
            sel.append("")
        baris.append(sel)

    tabel = Table(baris, colWidths=[8*cm, 8*cm], hAlign="LEFT")
    tabel.setStyle(TableStyle([
        ("VALIGN",  (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING",  (0,0), (-1,-1), 0),
        ("RIGHTPADDING", (0,0), (-1,-1), 0),
        ("TOPPADDING",   (0,0), (-1,-1), 0),
        ("BOTTOMPADDING",(0,0), (-1,-1), 8),
        ("COLPADDING",   (0,0), (-1,-1), 6),
    ]))
    return tabel


def buat_tabel_data(df, kolom_tampil, judul_kolom, warna_header=BIRU):
    """
    Buat tabel data dari DataFrame.
    kolom_tampil  : list nama kolom di df yang ingin ditampilkan
    judul_kolom   : list judul header yang ramah baca
    """
    styles = buat_styles()

    # Header
    header = [Paragraph(j, styles["tabel_header"]) for j in judul_kolom]
    baris  = [header]

    # Isi
    for _, row in df[kolom_tampil].iterrows():
        baris.append([
            Paragraph(str(row[k]), styles["tabel_isi"])
            for k in kolom_tampil
        ])

    lebar_halaman = A4[0] - 4*cm
    lebar_per_kol = lebar_halaman / len(kolom_tampil)
    tabel = Table(baris, colWidths=[lebar_per_kol] * len(kolom_tampil))

    tabel.setStyle(TableStyle([
        # Header
        ("BACKGROUND",    (0,0), (-1,0), warna_header),
        ("TEXTCOLOR",     (0,0), (-1,0), PUTIH),
        ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",      (0,0), (-1,0), 9),
        ("ALIGN",         (0,0), (-1,0), "CENTER"),
        ("TOPPADDING",    (0,0), (-1,0), 7),
        ("BOTTOMPADDING", (0,0), (-1,0), 7),
        # Isi — baris selang-seling
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [PUTIH, BIRU_MUD]),
        ("FONTNAME",      (0,1), (-1,-1), "Helvetica"),
        ("FONTSIZE",      (0,1), (-1,-1), 9),
        ("TOPPADDING",    (0,1), (-1,-1), 5),
        ("BOTTOMPADDING", (0,1), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
        ("RIGHTPADDING",  (0,0), (-1,-1), 8),
        # Border tipis
        ("GRID",          (0,0), (-1,-1), 0.3, colors.HexColor("#D3D1C7")),
        ("BOX",           (0,0), (-1,-1), 0.5, colors.HexColor("#B4B2A9")),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
    ]))
    return tabel


# ── Fungsi utama ────────────────────────────────────────────

def buat_laporan_pdf(
    df_umkm: pd.DataFrame,
    df_koperasi: pd.DataFrame,
    kpi: list,
    filter_info: dict,
    chart_images: dict = None,
) -> bytes:
    """
    Buat laporan PDF lengkap dan kembalikan sebagai bytes.

    Parameter:
        df_umkm      : DataFrame data UMKM per kecamatan
        df_koperasi  : DataFrame data koperasi
        kpi          : list dict KPI (label, nilai, delta, naik)
        filter_info  : dict filter aktif (kecamatan, tahun, sektor)
        chart_images : dict nama -> bytes (PNG dari fig.to_image())

    Contoh pemakaian di Streamlit:
        pdf_bytes = buat_laporan_pdf(df_umkm, df_kop, kpi_list, filter_dict)
        st.download_button("Download PDF", pdf_bytes, "laporan_umkm.pdf",
                           mime="application/pdf")
    """
    buffer = io.BytesIO()
    styles = buat_styles()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm,  bottomMargin=2*cm,
        title="Laporan UMKM & Koperasi Kabupaten Semarang",
        author="Dinas Koperasi UMKM Perindustrian dan Perdagangan",
    )

    cerita = []   # daftar elemen yang akan dirender

    # ── HEADER ───────────────────────────────────────────────
    cerita.append(Paragraph(
        "LAPORAN ANALITIK UMKM & KOPERASI",
        styles["judul"]
    ))
    cerita.append(Paragraph(
        "Dinas Koperasi, UMKM, Perindustrian dan Perdagangan",
        styles["subjudul"]
    ))
    cerita.append(Paragraph(
        "Kabupaten Semarang, Provinsi Jawa Tengah",
        styles["subjudul"]
    ))
    cerita.append(Spacer(1, 6))
    cerita.append(HRFlowable(width="100%", thickness=2, color=BIRU))
    cerita.append(Spacer(1, 4))

    # Tanggal cetak & filter aktif
    tgl = datetime.now().strftime("%d %B %Y, %H:%M WIB")
    kec_aktif    = filter_info.get("kecamatan", "Semua kecamatan")
    tahun_aktif  = filter_info.get("tahun",     "2024")
    sektor_aktif = filter_info.get("sektor",    "Semua sektor")

    meta = Table(
        [
            ["Dicetak pada", f": {tgl}"],
            ["Kecamatan",    f": {kec_aktif}"],
            ["Tahun data",   f": {tahun_aktif}"],
            ["Sektor",       f": {sektor_aktif}"],
        ],
        colWidths=[4*cm, 13*cm],
    )
    meta.setStyle(TableStyle([
        ("FONTNAME",  (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME",  (1,0), (1,-1), "Helvetica"),
        ("FONTSIZE",  (0,0), (-1,-1), 9),
        ("TEXTCOLOR", (0,0), (-1,-1), ABU_TUA),
        ("TOPPADDING",(0,0), (-1,-1), 2),
        ("BOTTOMPADDING",(0,0),(-1,-1), 2),
        ("LEFTPADDING",(0,0),(-1,-1), 0),
    ]))
    cerita.append(meta)
    cerita.append(Spacer(1, 12))

    # ── RINGKASAN KPI ────────────────────────────────────────
    cerita.append(Paragraph("1. Ringkasan indikator utama", styles["heading"]))
    cerita.append(buat_kpi_tabel(kpi))
    cerita.append(Spacer(1, 10))

    # ── CHART (jika ada) ────────────────────────────────────
    if chart_images:
        cerita.append(Paragraph("2. Visualisasi data", styles["heading"]))
        for nama_chart, img_bytes in chart_images.items():
            cerita.append(Paragraph(
                nama_chart, ParagraphStyle("cap", fontSize=9,
                textColor=ABU_TUA, fontName="Helvetica-Oblique",
                spaceAfter=4)
            ))
            img_buf = io.BytesIO(img_bytes)
            img = RLImage(img_buf, width=16*cm, height=7*cm)
            cerita.append(img)
            cerita.append(Spacer(1, 8))

    # ── TABEL UMKM ───────────────────────────────────────────
    nomor = 3 if chart_images else 2
    cerita.append(Paragraph(
        f"{nomor}. Data UMKM per kecamatan", styles["heading"]
    ))
    if not df_umkm.empty:
        kolom    = ["kecamatan", "jumlah_umkm", "sektor_dominan",
                    "industri_kecil", "klaster"]
        judul_k  = ["Kecamatan", "Jumlah UMKM", "Sektor dominan",
                    "Industri kecil", "Klaster"]
        # Tambahkan format angka
        df_print = df_umkm.copy()
        df_print["jumlah_umkm"] = df_print["jumlah_umkm"].apply(
            lambda x: f"{x:,}".replace(",",".")
        )
        df_print["industri_kecil"] = df_print["industri_kecil"].apply(
            lambda x: f"{x:,}".replace(",",".")
        )
        cerita.append(buat_tabel_data(df_print, kolom, judul_k))
    else:
        cerita.append(Paragraph("Tidak ada data tersedia.", styles["normal"]))
    cerita.append(Spacer(1, 10))

    # ── TABEL KOPERASI ───────────────────────────────────────
    nomor += 1
    cerita.append(Paragraph(
        f"{nomor}. Data koperasi", styles["heading"]
    ))
    if not df_koperasi.empty:
        kolom_k   = list(df_koperasi.columns)
        judul_k2  = [k.replace("_", " ").title() for k in kolom_k]
        cerita.append(buat_tabel_data(df_koperasi, kolom_k, judul_k2,
                                      warna_header=HIJAU))
    else:
        cerita.append(Paragraph("Tidak ada data tersedia.", styles["normal"]))
    cerita.append(Spacer(1, 10))

    # ── CATATAN & FOOTER ─────────────────────────────────────
    cerita.append(HRFlowable(width="100%", thickness=0.5, color=ABU_TUA))
    cerita.append(Spacer(1, 4))
    cerita.append(Paragraph(
        "Catatan: Laporan ini dibuat secara otomatis dari Dashboard Analitik UMKM "
        "& Koperasi. Data bersumber dari Portal Satu Data Kabupaten Semarang "
        "(data.semarangkab.go.id) dan BPS Kabupaten Semarang. "
        "Segmentasi klaster menggunakan metode K-Means Clustering.",
        ParagraphStyle("catatan", fontSize=8, textColor=ABU_TUA,
                       fontName="Helvetica-Oblique", leading=12)
    ))

    # ── Render PDF ───────────────────────────────────────────
    doc.build(cerita)
    buffer.seek(0)
    return buffer.read()
