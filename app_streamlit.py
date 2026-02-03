# -*- coding: utf-8 -*-
import streamlit as st
import tempfile
from pathlib import Path
import pandas as pd
from detector_core import detect_from_filelike

st.set_page_config(page_title='Detector de Pedidos Duplicados', page_icon='📦', layout='wide')

st.title('📦 Detector de pedidos duplicados / similares')
st.caption('Compara por fecha de entrega. Estados: RET/PRC. Prioridad ALTA cuando un duplicado es PRC vs RET.')

uploaded = st.file_uploader('Subí el archivo (CSV del reporte)', type=['csv'])

colA, colB, colC = st.columns([1,1,2])
with colA:
    solo_alta = st.checkbox('Mostrar solo PRIORIDAD ALTA', value=False)
with colB:
    mostrar_detalle_firma = st.checkbox('Mostrar firma_productos completa (puede ser larga)', value=False)
with colC:
    st.info('Tip: Si el archivo viene separado por ";" o por "," (o incluso tab), la app lo detecta como tu macro de TextToColumns.')

if uploaded:
    with tempfile.TemporaryDirectory() as td:
        out_exact, out_sim = detect_from_filelike(uploaded, td)
        out_exact = Path(out_exact)
        out_sim = Path(out_sim)

        df_exact = pd.read_csv(out_exact, dtype=str)
        df_sim = pd.read_csv(out_sim, dtype=str)

        if not mostrar_detalle_firma and 'firma_productos' in df_exact.columns:
            df_exact['firma_productos'] = df_exact['firma_productos'].astype(str).str.slice(0, 120) + '…'

        if solo_alta:
            if 'prioridad' in df_exact.columns:
                df_exact = df_exact[df_exact['prioridad'] == 'ALTA']
            if 'prioridad' in df_sim.columns:
                df_sim = df_sim[df_sim['prioridad'] == 'ALTA']

        st.subheader('✅ Duplicados exactos (por entrega)')
        st.dataframe(df_exact, use_container_width=True, hide_index=True)
        st.download_button('Descargar duplicados_exactos.csv', data=out_exact.read_bytes(), file_name='duplicados_exactos.csv', mime='text/csv')

        st.subheader('🟡 Duplicados similares (por entrega y similitud)')
        st.dataframe(df_sim, use_container_width=True, hide_index=True)
        st.download_button('Descargar duplicados_similares.csv', data=out_sim.read_bytes(), file_name='duplicados_similares.csv', mime='text/csv')

        st.divider()
        st.caption('Si querés: agrego filtros por Cliente, rango de fechas de entrega y umbrales de similitud en pantalla.')
else:
    st.warning('Subí un CSV para empezar.')
