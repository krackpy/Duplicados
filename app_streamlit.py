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

# --- UI Controls ---
colA, colB, colC, colD = st.columns([1,1,1,2])
with colA:
    solo_alta = st.checkbox('Solo PRIORIDAD ALTA', value=False)
with colB:
    mostrar_firma = st.checkbox('Mostrar firma_productos completa', value=False)
with colC:
    mostrar_exactos = st.checkbox('Incluir EXACTOS en resumen de clientes', value=True)
with colD:
    st.info('Tip: La app detecta si el CSV está separado por ";", "," o tab (como tu macro TextToColumns) y limpia encabezados automáticamente.')


def _safe_read_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path, dtype=str)
    except Exception:
        # fallback por si hay separador raro
        return pd.read_csv(path, dtype=str, sep=',', engine='python')


def _apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    if solo_alta and 'prioridad' in df.columns:
        df = df[df['prioridad'].astype(str).str.upper() == 'ALTA']
    return df


def _as_date(series: pd.Series) -> pd.Series:
    # fechas ISO (yyyy-mm-dd) que produce el core
    return pd.to_datetime(series, errors='coerce')


if uploaded:
    with tempfile.TemporaryDirectory() as td:
        try:
            out_exact, out_sim = detect_from_filelike(uploaded, td)
        except Exception as e:
            st.error(f'No pude procesar el archivo: {e}')
            st.stop()

        out_exact = Path(out_exact)
        out_sim = Path(out_sim)

        df_exact = _safe_read_csv(out_exact)
        df_sim = _safe_read_csv(out_sim)

        # Normalización básica
        if not df_exact.empty:
            df_exact['prioridad'] = df_exact.get('prioridad', '').astype(str).str.upper()
            df_exact['Client'] = df_exact.get('Client', '').astype(str).str.strip()
        if not df_sim.empty:
            df_sim['prioridad'] = df_sim.get('prioridad', '').astype(str).str.upper()
            df_sim['Client'] = df_sim.get('Client', '').astype(str).str.strip()

        # Filtros globales
        df_exact_f = _apply_filters(df_exact)
        df_sim_f = _apply_filters(df_sim)

        # --- Resumen "pro" ---
        total_exact = len(df_exact)
        total_sim = len(df_sim)
        total_exact_f = len(df_exact_f)
        total_sim_f = len(df_sim_f)

        alta_exact = int((df_exact['prioridad'] == 'ALTA').sum()) if not df_exact.empty and 'prioridad' in df_exact.columns else 0
        alta_sim = int((df_sim['prioridad'] == 'ALTA').sum()) if not df_sim.empty and 'prioridad' in df_sim.columns else 0

        # Clientes únicos (para bloquear)
        frames = []
        if not df_sim_f.empty:
            frames.append(df_sim_f[['Client','Razon social','prioridad']].copy())
        if mostrar_exactos and not df_exact_f.empty:
            frames.append(df_exact_f[['Client','Razon social','prioridad']].copy())

        if frames:
            df_clients = pd.concat(frames, ignore_index=True)
            df_clients['prioridad'] = df_clients['prioridad'].astype(str).str.upper()
            df_clients['Razon social'] = df_clients.get('Razon social','').astype(str).str.strip()

            # resumen por cliente
            def prio_rank(p):
                return 2 if str(p).upper() == 'ALTA' else 1

            df_clients['prio_rank'] = df_clients['prioridad'].apply(prio_rank)
            g = df_clients.groupby('Client', dropna=False)
            df_clients_sum = g.agg(
                razon_social=('Razon social', lambda x: next((v for v in x if v and v != 'nan'), '')),
                casos=('Client','size'),
                prioridad_max=('prio_rank','max')
            ).reset_index()
            df_clients_sum['prioridad_max'] = df_clients_sum['prioridad_max'].map({2:'ALTA',1:'MEDIA'}).fillna('MEDIA')
            df_clients_sum = df_clients_sum.sort_values(['prioridad_max','casos','Client'], ascending=[False,False,True])
        else:
            df_clients_sum = pd.DataFrame(columns=['Client','razon_social','casos','prioridad_max'])

        # Métricas
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric('Pedidos EXACTOS detectados', f'{total_exact}')
        m2.metric('Pedidos SIMILARES detectados', f'{total_sim}')
        m3.metric('PRIORIDAD ALTA (exactos)', f'{alta_exact}')
        m4.metric('PRIORIDAD ALTA (similares)', f'{alta_sim}')
        m5.metric('Clientes únicos a revisar', f'{len(df_clients_sum)}')

        st.divider()

        # --- Tabs ---
        tab1, tab2, tab3 = st.tabs(['🟡 Pares similares (Opción A)', '✅ Exactos', '🧾 Clientes únicos (para bloquear)'])

        with tab1:
            st.subheader('🟡 Pares similares (misma entrega cercana + similitud)')
            if df_sim_f.empty:
                st.info('No se detectaron pares similares con los criterios actuales.')
            else:
                # ordenar para que ALTA quede arriba
                if 'prioridad' in df_sim_f.columns:
                    df_show = df_sim_f.sort_values(['prioridad'], ascending=False)
                else:
                    df_show = df_sim_f
                st.dataframe(df_show, use_container_width=True, hide_index=True)

            st.download_button('Descargar duplicados_similares.csv', data=out_sim.read_bytes(), file_name='duplicados_similares.csv', mime='text/csv')

        with tab2:
            st.subheader('✅ Duplicados exactos (mismo cliente + misma entrega + mismo importe + mismos productos)')
            if df_exact_f.empty:
                st.info('No se detectaron duplicados exactos con los criterios actuales.')
            else:
                df_show = df_exact_f.copy()
                if not mostrar_firma and 'firma_productos' in df_show.columns:
                    df_show['firma_productos'] = df_show['firma_productos'].astype(str).str.slice(0, 120) + '…'
                if 'prioridad' in df_show.columns:
                    df_show = df_show.sort_values(['prioridad'], ascending=False)
                st.dataframe(df_show, use_container_width=True, hide_index=True)

            st.download_button('Descargar duplicados_exactos.csv', data=out_exact.read_bytes(), file_name='duplicados_exactos.csv', mime='text/csv')

        with tab3:
            st.subheader('🧾 Clientes únicos (lista para bloquear sin confusión)')
            st.caption('Acá NO se repite el número de cliente. Se agrupa y te muestra cantidad de casos y prioridad máxima.')
            if df_clients_sum.empty:
                st.info('No hay clientes para listar con los filtros actuales.')
            else:
                st.dataframe(df_clients_sum, use_container_width=True, hide_index=True)
                # Descarga
                csv_bytes = df_clients_sum.to_csv(index=False).encode('utf-8')
                st.download_button('Descargar lista_clientes_unicos.csv', data=csv_bytes, file_name='lista_clientes_unicos.csv', mime='text/csv')

        st.divider()
        st.caption('Si querés, agrego filtros por rango de fecha de entrega, búsqueda por cliente/razón social y sliders para umbrales de similitud.')

else:
    st.warning('Subí un CSV para empezar.')
