"""
dashboard.py
Dashboard Analitik UMKM & Koperasi Kabupaten Semarang
Data: dibaca langsung dari database SQLite (data/db/umkm_semarang.db),
hasil cleaning & K-Means clustering yang sudah diimport lewat setup_database.py

Sebelum menjalankan dashboard ini, database harus sudah dibuat:
    python setup_database.py

Jalankan: streamlit run dashboard.py
"""

import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import json
import folium
from streamlit_folium import st_folium
import plotly.express as px
from datetime import datetime
from pathlib import Path

from pdf_generator import buat_laporan_pdf

DB_PATH     = Path(__file__).parent / "data" / "db" / "umkm_semarang.db"
GEOJSON_PATH= Path(__file__).parent / "data" / "geo" / "kecamatan_semarang.geojson"
TAHUN_UTAMA = 2024   # tahun data terlengkap (hasil audit ketersediaan data)

WARNA_KLASTER = {
    "Klaster 1": "#378ADD",
    "Klaster 2": "#1D9E75",
    "Klaster 3": "#EF9F27",
    "Klaster 4": "#7F77DD",
}

# Nama sektor KBLI dipersingkat agar enak dibaca di chart
SEKTOR_SINGKAT = {
    "Industri Pengolahan": "Industri Pengolahan",
    "Perdagangan Besar Dan Eceran Reparasi Dan Perawatan Mobil Dan Sepeda Motor": "Perdagangan & Reparasi",
    "Penyediaan Akomodasi Dan Penyediaan Makan Minum": "Akomodasi & Kuliner",
    "Pertanian, Kehutanan, dan Perikanan": "Pertanian & Perikanan",
    "Konstruksi": "Konstruksi",
    "Aktivitas Penyewaan dan Sewa Guna Usaha Tanpa Hak Opsi, Ketenagakerjaan, Agen Perjalanan dan Penunjang Usaha Lainnya": "Jasa Penunjang Usaha",
    "Pendidikan": "Pendidikan",
    "Pengangkutan dan Pergudangan": "Transportasi & Pergudangan",
}

# ── Konfigurasi halaman ──────────────────────────────────────
st.set_page_config(
    page_title="Dashboard UMKM Kab. Semarang",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .section-title  { font-size: 16px; font-weight: 600;
                      color: #185FA5; margin: 16px 0 8px; }
    .sumber-note { font-size: 11px; color: #8a8a86; margin-top: -6px; }
</style>
""", unsafe_allow_html=True)


# ── Pastikan file database ada sebelum lanjut ────────────────
# Tanpa pengecekan ini, error yang muncul adalah traceback teknis
# sqlite3 yang membingungkan ("unable to open database file").
if not DB_PATH.exists():
    st.error(
        f"File database tidak ditemukan di:\n\n`{DB_PATH}`\n\n"
        "**Cara memperbaiki:**\n"
        "1. Pastikan folder `data/db/` ada di dalam folder project ini "
        "(sejajar dengan `dashboard.py`)\n"
        "2. Pastikan file `umkm_semarang.db` ada di dalam folder tersebut\n"
        "3. Kalau belum punya file databasenya, jalankan "
        "`python setup_database.py` terlebih dahulu"
    )
    st.stop()


# ── Muat data dari database (hasil cleaning & clustering) ────
@st.cache_data
def load_data():
    conn = sqlite3.connect(DB_PATH)

    # Data UMKM + hasil klaster, di-JOIN dengan tabel kecamatan
    df_klaster = pd.read_sql_query("""
        SELECT k.nama_kecamatan AS kecamatan, h.tahun, h.total_umkm,
               h.jumlah_industri, h.total_koperasi, h.total_usaha,
               h.sektor_dominan, h.klaster_id, h.klaster, h.warna
        FROM hasil_klaster h
        JOIN kecamatan k ON k.kecamatan_id = h.kecamatan_id
    """, conn)

    # UMKM per sektor KBLI, tahun & semester terbaru
    df_sektor = pd.read_sql_query(f"""
        SELECT k.nama_kecamatan AS kecamatan, s.sektor_kbli, s.tahun,
               s.semester, s.jumlah_usaha
        FROM sektor_umkm s
        JOIN kecamatan k ON k.kecamatan_id = s.kecamatan_id
        WHERE s.tahun = {TAHUN_UTAMA} AND s.semester = 'Semester II'
    """, conn)
    df_sektor["sektor_label"] = df_sektor["sektor_kbli"].map(
        lambda s: SEKTOR_SINGKAT.get(s, s[:28])
    )

    # Koperasi per jenis, tahun & semester terbaru (baris TOTAL tak
    # ikut ter-import ke database — sudah bisa dihitung ulang dari SUM)
    df_kop_jenis = pd.read_sql_query(f"""
        SELECT k.nama_kecamatan AS kecamatan, kp.jenis_koperasi, kp.tahun,
               kp.semester, kp.jumlah_koperasi
        FROM koperasi kp
        JOIN kecamatan k ON k.kecamatan_id = kp.kecamatan_id
        WHERE kp.tahun = {TAHUN_UTAMA} AND kp.semester = 'Semester II'
    """, conn)

    # Profil klaster (hasil GROUP BY + RANK, sudah dihitung saat clustering)
    df_profil = pd.read_sql_query("SELECT * FROM profil_klaster", conn)

    # Aset koperasi per jenis, seluruh tahun (untuk analisis tren)
    df_aset = pd.read_sql_query("""
        SELECT jenis_koperasi, tahun, aset_rupiah
        FROM aset_koperasi WHERE semester = 'Semester II'
        ORDER BY tahun
    """, conn)

    conn.close()
    return df_klaster, df_sektor, df_kop_jenis, df_profil, df_aset


df_klaster, df_sektor, df_kop_jenis, df_profil, df_aset = load_data()


# ── Peta choropleth: gabungkan GeoJSON dengan data klaster ───
@st.cache_data
def siapkan_geojson(df_klaster: pd.DataFrame) -> dict:
    with open(GEOJSON_PATH, encoding="utf-8") as f:
        geojson_data = json.load(f)

    df_dict = df_klaster.set_index("kecamatan").to_dict("index")

    for feature in geojson_data["features"]:
        nama  = feature["properties"]["name"]
        info  = df_dict.get(nama, {})
        warna = info.get("warna", "#888888")

        feature["properties"]["total_umkm"]      = int(info.get("total_umkm", 0))
        feature["properties"]["jumlah_industri"] = int(info.get("jumlah_industri", 0))
        feature["properties"]["total_koperasi"]  = int(info.get("total_koperasi", 0))
        feature["properties"]["klaster"]         = info.get("klaster", "-")

        feature["properties"]["popup_html"] = (
            f'<div style="font-family:sans-serif;min-width:190px">'
            f'<h4 style="margin:0 0 6px;border-bottom:2px solid {warna};'
            f'padding-bottom:4px">{nama}</h4>'
            f'<table style="font-size:13px;width:100%">'
            f'<tr><td>UMKM</td><td style="text-align:right;font-weight:600">'
            f'{info.get("total_umkm", 0):,}</td></tr>'
            f'<tr><td>Industri kecil</td><td style="text-align:right;font-weight:600">'
            f'{info.get("jumlah_industri", 0):,}</td></tr>'
            f'<tr><td>Koperasi</td><td style="text-align:right;font-weight:600">'
            f'{info.get("total_koperasi", 0):,}</td></tr>'
            f'<tr><td>Klaster</td><td style="text-align:right">'
            f'<span style="background:{warna};color:white;padding:1px 8px;'
            f'border-radius:8px;font-size:11px">{info.get("klaster", "-")}</span>'
            f'</td></tr></table></div>'
        )
    return geojson_data


def buat_peta_choropleth(df_klaster: pd.DataFrame):
    geojson_data = siapkan_geojson(df_klaster)

    peta = folium.Map(
        location=[-7.2067, 110.4414],
        zoom_start=10.4,
        tiles="CartoDB positron",
    )

    folium.Choropleth(
        geo_data=geojson_data,
        data=df_klaster,
        columns=["kecamatan", "total_umkm"],
        key_on="feature.properties.name",
        fill_color="YlOrRd",
        fill_opacity=0.75,
        line_opacity=0.6,
        line_color="white",
        legend_name="Jumlah UMKM per kecamatan",
        highlight=True,
        nan_fill_color="lightgray",
    ).add_to(peta)

    folium.GeoJson(
        geojson_data,
        style_function=lambda f: {"fillOpacity": 0, "weight": 0, "color": "transparent"},
        highlight_function=lambda f: {"fillOpacity": 0.15, "weight": 2, "color": "#333"},
        tooltip=folium.GeoJsonTooltip(fields=["name"], aliases=["Kecamatan:"]),
        popup=folium.GeoJsonPopup(
            fields=["popup_html"], labels=False, parse_html=True, max_width=280
        ),
    ).add_to(peta)

    return peta


# ── Sidebar: filter ──────────────────────────────────────────
with st.sidebar:
    st.image(
        "https://upload.wikimedia.org/wikipedia/commons/"
        "thumb/8/8e/Seal_of_Semarang_Regency.svg/200px-"
        "Seal_of_Semarang_Regency.svg.png",
        width=80,
    )
    st.title("Dashboard UMKM")
    st.caption("Kab. Semarang · Dinas Koperasi, UMKM, Perindustrian & Perdagangan")
    st.divider()

    kec_list     = ["Semua kecamatan"] + sorted(df_klaster["kecamatan"].unique())
    klaster_list = ["Semua klaster"] + sorted(df_klaster["klaster"].unique())

    filter_kec     = st.selectbox("Kecamatan", kec_list)
    filter_klaster = st.selectbox("Klaster",   klaster_list)

    st.divider()
    st.caption(f"Tahun data: **{TAHUN_UTAMA}** (data terlengkap)")
    st.caption("Sumber: data.semarangkab.go.id")
    st.caption(f"Terakhir dibuka: {datetime.now().strftime('%d %b %Y')}")


# ── Terapkan filter ──────────────────────────────────────────
df_filtered = df_klaster.copy()
if filter_kec != "Semua kecamatan":
    df_filtered = df_filtered[df_filtered["kecamatan"] == filter_kec]
if filter_klaster != "Semua klaster":
    df_filtered = df_filtered[df_filtered["klaster"] == filter_klaster]


# ── Header halaman ───────────────────────────────────────────
st.title("Analitik UMKM & Koperasi")
st.caption(f"Kabupaten Semarang · Provinsi Jawa Tengah · Data tahun {TAHUN_UTAMA}")


# ── KPI cards ────────────────────────────────────────────────
st.markdown('<p class="section-title">Indikator utama</p>', unsafe_allow_html=True)
k1, k2, k3, k4 = st.columns(4)

total_umkm      = int(df_filtered["total_umkm"].sum())
total_koperasi  = int(df_filtered["total_koperasi"].sum())
total_industri  = int(df_filtered["jumlah_industri"].sum())
rata_umkm_kec   = total_umkm / len(df_filtered) if len(df_filtered) else 0

k1.metric("Total UMKM",       f"{total_umkm:,}".replace(",", "."))
k2.metric("Total Koperasi",   f"{total_koperasi:,}".replace(",", "."))
k3.metric("Industri Kecil",   f"{total_industri:,}".replace(",", "."))
k4.metric("Rata-rata UMKM / Kecamatan", f"{rata_umkm_kec:,.0f}".replace(",", "."))

st.caption(
    f"Berdasarkan {len(df_filtered)} dari 19 kecamatan · "
    "seluruh kecamatan didominasi sektor Industri Pengolahan"
)


# ── Chart row 1 ──────────────────────────────────────────────
st.markdown('<p class="section-title">Distribusi & segmentasi</p>', unsafe_allow_html=True)
c1, c2 = st.columns(2)

with c1:
    df_sektor_agg = (
        df_sektor.groupby("sektor_label")["jumlah_usaha"]
        .sum().reset_index()
        .sort_values("jumlah_usaha", ascending=False)
        .head(8)
        .sort_values("jumlah_usaha")
    )
    fig_sektor = px.bar(
        df_sektor_agg, x="jumlah_usaha", y="sektor_label", orientation="h",
        title="UMKM per sektor (8 teratas dari 19 kategori KBLI)",
        color_discrete_sequence=["#378ADD"],
        labels={"jumlah_usaha": "Jumlah UMKM", "sektor_label": ""},
    )
    fig_sektor.update_layout(
        showlegend=False, margin=dict(l=0, r=0, t=40, b=0),
        height=280, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig_sektor, width='stretch')

with c2:
    df_klaster_agg = (
        df_filtered.groupby("klaster")["total_umkm"].sum().reset_index()
    )
    fig_klaster = px.pie(
        df_klaster_agg, values="total_umkm", names="klaster",
        title="Sebaran UMKM per klaster",
        color="klaster", color_discrete_map=WARNA_KLASTER, hole=0.45,
    )
    fig_klaster.update_layout(
        margin=dict(l=0, r=0, t=40, b=0), height=280,
        paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=-0.25),
    )
    st.plotly_chart(fig_klaster, width='stretch')

st.caption(
    "Klaster bernomor 1-4 tanpa urutan/peringkat kualitas — lihat bagian "
    "\"Profil klaster\" di bawah untuk detail tiap klaster."
)


# ── Chart row 2 ──────────────────────────────────────────────
c3, c4 = st.columns(2)

with c3:
    fig_top = px.bar(
        df_filtered.sort_values("total_umkm", ascending=False).head(10),
        x="total_umkm", y="kecamatan", orientation="h",
        title="Top 10 kecamatan berdasarkan jumlah UMKM",
        color="klaster", color_discrete_map=WARNA_KLASTER,
        labels={"total_umkm": "Jumlah UMKM", "kecamatan": ""},
    )
    fig_top.update_layout(
        margin=dict(l=0, r=0, t=40, b=0), height=320,
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=-0.35),
        yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(fig_top, width='stretch')

with c4:
    fig_scatter = px.scatter(
        df_filtered,
        x="total_umkm", y="jumlah_industri",
        size="total_koperasi", color="klaster",
        hover_name="kecamatan",
        color_discrete_map=WARNA_KLASTER,
        title="UMKM vs industri kecil (ukuran = jml. koperasi)",
        labels={"total_umkm": "Jumlah UMKM", "jumlah_industri": "Jumlah industri kecil"},
    )
    fig_scatter.update_layout(
        margin=dict(l=0, r=0, t=40, b=0), height=320,
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=-0.35),
    )
    st.plotly_chart(fig_scatter, width='stretch')


# ── Peta sebaran ─────────────────────────────────────────────
st.markdown('<p class="section-title">Peta sebaran</p>', unsafe_allow_html=True)
st.caption(
    "Warna wilayah menunjukkan jumlah UMKM (semakin gelap = semakin banyak). "
    "Klik kecamatan untuk detail lengkap. Peta menampilkan seluruh 19 "
    "kecamatan, tidak terpengaruh filter di sidebar."
)
peta = buat_peta_choropleth(df_klaster)
st_folium(peta, width=None, height=460, returned_objects=[])


# ── Profil klaster ───────────────────────────────────────────
st.markdown('<p class="section-title">Profil klaster</p>', unsafe_allow_html=True)
st.caption(
    "Klaster diberi nomor urut saja, bukan nama. Karakteristiknya dibaca "
    "langsung dari rata-rata & peringkat tiap indikator (1 = tertinggi, "
    "4 = terendah dari 4 klaster) — data 3 indikator ini menunjukkan pola, "
    "bukan kesimpulan tentang baik-buruknya suatu kecamatan."
)

st.dataframe(
    df_profil[["klaster", "jumlah_kecamatan",
               "rata_umkm", "peringkat_umkm",
               "rata_industri", "peringkat_industri",
               "rata_koperasi", "peringkat_koperasi"]],
    width='stretch', hide_index=True,
    column_config={
        "klaster":            st.column_config.TextColumn("Klaster"),
        "jumlah_kecamatan":   st.column_config.NumberColumn("Jml. kecamatan", format="%d"),
        "rata_umkm":          st.column_config.NumberColumn("Rata² UMKM", format="%.0f"),
        "peringkat_umkm":     st.column_config.NumberColumn("Peringkat", format="%d"),
        "rata_industri":      st.column_config.NumberColumn("Rata² industri", format="%.0f"),
        "peringkat_industri": st.column_config.NumberColumn("Peringkat", format="%d"),
        "rata_koperasi":      st.column_config.NumberColumn("Rata² koperasi", format="%.0f"),
        "peringkat_koperasi": st.column_config.NumberColumn("Peringkat", format="%d"),
    },
)

pc1, pc2, pc3 = st.columns(3)
grafik_profil = [
    (pc1, "rata_umkm",     "Rata-rata UMKM"),
    (pc2, "rata_industri", "Rata-rata industri kecil"),
    (pc3, "rata_koperasi", "Rata-rata koperasi"),
]
for kolom_ui, kolom_data, judul in grafik_profil:
    with kolom_ui:
        fig_p = px.bar(
            df_profil, x="klaster", y=kolom_data, title=judul,
            color="klaster", color_discrete_map=WARNA_KLASTER,
            labels={kolom_data: "", "klaster": ""},
        )
        fig_p.update_layout(
            showlegend=False, margin=dict(l=0, r=0, t=32, b=0), height=200,
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(tickfont=dict(size=10)),
        )
        st.plotly_chart(fig_p, width='stretch')

for _, row in df_profil.iterrows():
    with st.expander(f"{row['klaster']} — daftar kecamatan ({row['jumlah_kecamatan']})"):
        st.write(row["kecamatan"])


# ── Analisis lanjutan: tren & korelasi ────────────────────────
st.markdown('<p class="section-title">Analisis lanjutan</p>', unsafe_allow_html=True)

al1, al2 = st.columns(2)

with al1:
    st.markdown("**Tren aset koperasi**")

    # Deteksi otomatis lompatan skala pelaporan (bukan pertumbuhan riil)
    total_tahun = df_aset.groupby("tahun")["aset_rupiah"].sum()
    total_tahun = total_tahun[total_tahun > 0].sort_index()
    rasio = total_tahun / total_tahun.shift(1)
    tahun_lompatan = rasio[rasio > 50].index.tolist()
    batas = min(tahun_lompatan) if tahun_lompatan else total_tahun.index.min()

    df_aset_reliable = df_aset[
        (df_aset["tahun"] >= batas) & (df_aset["aset_rupiah"] > 0)
    ].copy()
    df_aset_reliable["aset_miliar"] = df_aset_reliable["aset_rupiah"] / 1e9

    fig_tren = px.line(
        df_aset_reliable, x="tahun", y="aset_miliar", color="jenis_koperasi",
        markers=True,
        labels={"aset_miliar": "Aset (miliar Rp)", "tahun": "", "jenis_koperasi": ""},
    )
    fig_tren.update_layout(
        margin=dict(l=0, r=0, t=10, b=0), height=280,
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=-0.4, font=dict(size=10)),
        xaxis=dict(dtick=1),
    )
    st.plotly_chart(fig_tren, width='stretch')
    st.caption(
        f"Hanya {int(batas)}-{int(df_aset_reliable['tahun'].max())} yang ditampilkan. "
        f"Data sebelum {int(batas)} dikecualikan karena totalnya melonjak "
        f"~{rasio.get(batas, 0):.0f}x dalam satu tahun secara serentak di "
        "semua jenis koperasi — kemungkinan besar perubahan satuan/metodologi "
        "pelaporan sumber data, bukan pertumbuhan riil."
    )

with al2:
    st.markdown("**Korelasi antar indikator (19 kecamatan, 2024)**")

    kolom_korelasi = ["total_umkm", "jumlah_industri", "total_koperasi"]
    label_korelasi = ["UMKM", "Industri kecil", "Koperasi"]
    matriks = df_klaster[kolom_korelasi].corr(method="pearson").round(2)

    fig_heatmap = px.imshow(
        matriks.values,
        x=label_korelasi, y=label_korelasi,
        color_continuous_scale="RdBu_r", zmin=-1, zmax=1,
        text_auto=True, aspect="auto",
    )
    fig_heatmap.update_layout(
        margin=dict(l=0, r=0, t=10, b=0), height=280,
        coloraxis_showscale=False,
    )
    st.plotly_chart(fig_heatmap, width='stretch')

    # Cek sensitivitas terhadap outlier Pringapus
    korelasi_tanpa = (
        df_klaster[df_klaster["kecamatan"] != "Pringapus"][kolom_korelasi]
        .corr(method="pearson")
    )
    selisih_maks = (matriks - korelasi_tanpa).abs().values[
        ~np.eye(3, dtype=bool)
    ].max()
    st.caption(
        "Sampel cuma 19 kecamatan, dan Pringapus adalah outlier UMKM yang "
        f"jelas. Tanpa Pringapus, angka korelasi bergeser hingga "
        f"{selisih_maks:.2f} poin — jadi pola di atas belum tentu berlaku "
        "umum, sensitif terhadap satu titik data itu."
    )


# ── Tabel data ───────────────────────────────────────────────
st.markdown('<p class="section-title">Data detail</p>', unsafe_allow_html=True)

tab1, tab2 = st.tabs(["Data UMKM & klaster", "Koperasi per jenis"])

with tab1:
    st.dataframe(
        df_filtered[["kecamatan", "total_umkm", "jumlah_industri",
                     "total_koperasi", "sektor_dominan", "klaster"]]
        .sort_values("total_umkm", ascending=False),
        width='stretch', hide_index=True,
        column_config={
            "kecamatan":       st.column_config.TextColumn("Kecamatan"),
            "total_umkm":      st.column_config.NumberColumn("Jumlah UMKM", format="%d"),
            "jumlah_industri": st.column_config.NumberColumn("Industri kecil", format="%d"),
            "total_koperasi":  st.column_config.NumberColumn("Koperasi", format="%d"),
            "sektor_dominan":  st.column_config.TextColumn("Sektor dominan"),
            "klaster":         st.column_config.TextColumn("Klaster"),
        },
    )

with tab2:
    pivot_kop = df_kop_jenis.pivot_table(
        index="kecamatan", columns="jenis_koperasi",
        values="jumlah_koperasi", aggfunc="sum", fill_value=0
    ).reset_index()
    st.dataframe(pivot_kop, width='stretch', hide_index=True)
    st.caption(f"Jenis koperasi: {', '.join(sorted(df_kop_jenis['jenis_koperasi'].unique()))}")


# ═══════════════════════════════════════════════════════════════
# FITUR EXPORT PDF
# ═══════════════════════════════════════════════════════════════
st.divider()
st.markdown('<p class="section-title">Export laporan</p>', unsafe_allow_html=True)

col_opt1, col_opt2, col_opt3 = st.columns(3)

with col_opt1:
    sertakan_chart = st.checkbox("Sertakan chart", value=True)
with col_opt2:
    sertakan_koperasi = st.checkbox("Sertakan data koperasi", value=True)
with col_opt3:
    nama_file = st.text_input(
        "Nama file",
        value=f"laporan_umkm_{datetime.now().strftime('%Y%m%d')}.pdf",
    )

if st.button("Generate & download PDF", type="primary"):
    with st.spinner("Membuat laporan PDF..."):

        chart_images = {}
        if sertakan_chart:
            try:
                chart_images["UMKM per sektor"] = \
                    fig_sektor.to_image(format="png", width=900, height=400, scale=2)
                chart_images["Sebaran UMKM per klaster"] = \
                    fig_klaster.to_image(format="png", width=900, height=400, scale=2)
                chart_images["Top 10 kecamatan"] = \
                    fig_top.to_image(format="png", width=900, height=400, scale=2)
            except Exception:
                st.warning(
                    "Chart tidak bisa diekspor (butuh kaleido: "
                    "`pip install kaleido`). PDF tetap dibuat tanpa chart."
                )
                chart_images = {}

        kpi_list = [
            {"label": "Total UMKM",     "nilai": f"{total_umkm:,}".replace(",", "."),
             "delta": f"dari {len(df_filtered)} kecamatan", "naik": True},
            {"label": "Total Koperasi", "nilai": f"{total_koperasi:,}".replace(",", "."),
             "delta": "5 jenis koperasi", "naik": True},
            {"label": "Industri Kecil", "nilai": f"{total_industri:,}".replace(",", "."),
             "delta": "unit usaha", "naik": True},
            {"label": "Rata-rata UMKM/Kecamatan", "nilai": f"{rata_umkm_kec:,.0f}".replace(",", "."),
             "delta": "per kecamatan tercakup", "naik": True},
        ]

        filter_info = {
            "kecamatan": filter_kec,
            "tahun":     str(TAHUN_UTAMA),
            "sektor":    "Seluruh sektor (Industri Pengolahan dominan)",
        }

        df_umkm_pdf = df_filtered.rename(columns={
            "total_umkm": "jumlah_umkm",
            "jumlah_industri": "industri_kecil",
        })[["kecamatan", "jumlah_umkm", "sektor_dominan", "industri_kecil", "klaster"]]

        pdf_bytes = buat_laporan_pdf(
            df_umkm     = df_umkm_pdf,
            df_koperasi = pivot_kop if sertakan_koperasi else pd.DataFrame(),
            kpi         = kpi_list,
            filter_info = filter_info,
            chart_images= chart_images if sertakan_chart else None,
        )

    st.success("Laporan siap didownload!")
    st.download_button(
        label     = "⬇ Download PDF sekarang",
        data      = pdf_bytes,
        file_name = nama_file,
        mime      = "application/pdf",
    )
    st.caption(
        f"Laporan mencakup {len(df_filtered)} kecamatan · "
        f"Filter: {filter_kec} · {filter_klaster} · Tahun {TAHUN_UTAMA}"
    )
