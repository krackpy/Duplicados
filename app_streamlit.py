# -*- coding: utf-8 -*-
import streamlit as st
import tempfile
from pathlib import Path
from detector_core import detect_from_filelike

st.set_page_config(page_title='Detector de Pedidos Duplicados', page_icon='📦', layout='wide')

st.title('📦 Detector de pedidos duplicados / similares')
st.caption('Reglas: compara por fecha de entrega y considera estados RET/PRC. Prioridad ALTA cuando hay PRC vs RET.')

with st.expander('⚙️ Parámetros (por ahora en el código)', expanded=False):
    st.write('Si querés que estos parámetros se puedan cambiar desde la pantalla, lo agrego.')

uploaded = st.file_uploader('Subí el archivo PEDIDOS.csv', type=['csv'])

if uploaded:
    with tempfile.TemporaryDirectory() as td:
        out_exact, out_sim = detect_from_filelike(uploaded, td)
        out_exact = Path(out_exact)
        out_sim = Path(out_sim)

        col1, col2 = st.columns(2)
        with col1:
            st.subheader('✅ Duplicados exactos')
            st.download_button('Descargar duplicados_exactos.csv', data=out_exact.read_bytes(), file_name='duplicados_exactos.csv', mime='text/csv')
            st.info('Incluye prioridad: ALTA si el grupo tiene PRC y RET.')

        with col2:
            st.subheader('🟡 Duplicados similares')
            st.download_button('Descargar duplicados_similares.csv', data=out_sim.read_bytes(), file_name='duplicados_similares.csv', mime='text/csv')
            st.info('Incluye prioridad: ALTA si el par es PRC vs RET.')

        st.divider()
        st.subheader('👀 Vista rápida (primeras filas)')
        # Vista rápida sin pandas: mostramos texto
        st.text('--- duplicados_exactos.csv (primeras 20 líneas) ---')
        st.text(out_exact.read_text(encoding='utf-8', errors='ignore').splitlines()[:20])
        st.text('--- duplicados_similares.csv (primeras 20 líneas) ---')
        st.text(out_sim.read_text(encoding='utf-8', errors='ignore').splitlines()[:20])
else:
    st.warning('Subí un CSV para empezar.')
