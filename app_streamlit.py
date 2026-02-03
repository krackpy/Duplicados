# -*- coding: utf-8 -*-
import streamlit as st
import tempfile
from pathlib import Path
import pandas as pd
from detector_core import detect_from_filelike

# ----------------- Estilo futurista (CSS) -----------------
FUTURISTIC_CSS = """
<style>
/* Fondo */
.stApp {
  background: radial-gradient(1200px 800px at 20% 10%, rgba(0,255,240,0.10), transparent 50%),
              radial-gradient(900px 700px at 80% 30%, rgba(155,81,224,0.12), transparent 55%),
              linear-gradient(180deg, #070A12 0%, #060816 40%, #050616 100%);
  color: #E7F6FF;
}

/* Títulos */
h1, h2, h3 {
  letter-spacing: 0.4px;
}

/* Tarjetas métricas */
[data-testid="stMetric"] {
  background: rgba(255,255,255,0.06);
  border: 1px solid rgba(0,255,240,0.18);
  border-radius: 14px;
  padding: 14px 14px 10px 14px;
  box-shadow: 0 0 0 1px rgba(155,81,224,0.10) inset,
              0 12px 35px rgba(0,0,0,0.45);
}

/* Dataframes */
[data-testid="stDataFrame"] {
  border: 1px solid rgba(0,255,240,0.16);
  border-radius: 14px;
  overflow: hidden;
  box-shadow: 0 12px 30px rgba(0,0,0,0.35);
}

/* Botones */
.stDownloadButton button, .stButton button {
  border-radius: 12px;
  border: 1px solid rgba(0,255,240,0.30);
  background: linear-gradient(90deg, rgba(0,255,240,0.20), rgba(155,81,224,0.16));
  color: #E7F6FF;
  box-shadow: 0 10px 24px rgba(0,0,0,0.35);
}
.stDownloadButton button:hover, .stButton button:hover {
  border: 1px solid rgba(0,255,240,0.55);
  filter: brightness(1.06);
}

/* Inputs */
textarea, input {
  border-radius: 12px !important;
  border: 1px solid rgba(0,255,240,0.20) !important;
  background: rgba(255,255,255,0.05) !important;
  color: #E7F6FF !important;
}

/* Etiquetas neon */
.badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 12px;
  border: 1px solid rgba(0,255,240,0.35);
  background: rgba(0,255,240,0.10);
}
.badge.alta {
  border-color: rgba(255,77,109,0.65);
  background: rgba(255,77,109,0.12);
}

hr { border: none; height: 1px; background: rgba(0,255,240,0.12); }
</style>
"""

st.set_page_config(page_title='Detector de Pedidos Duplicados', page_icon='📦', layout='wide')
st.markdown(FUTURISTIC_CSS, unsafe_allow_html=True)

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
    incluir_exactos_clientes = st.checkbox('Incluir EXACTOS en clientes únicos', value=True)
with colD:
    st.info('Tip: La app detecta si el CSV está separado por ";", "," o tab (como tu macro TextToColumns) y limpia encabezados automáticamente.')


def _safe_read_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path, dtype=str)
    except Exception:
        return pd.read_csv(path, dtype=str, sep=',', engine='python')


def _apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    if solo_alta and 'prioridad' in df.columns:
        df = df[df['prioridad'].astype(str).str.upper() == 'ALTA']
    return df


def _split_clients(text: str):
    # Acepta separadores: salto de línea, coma, punto y coma, espacio
    if not text:
        return []
    raw = text.replace(';', '\n').replace(',', '\n').replace(' ', '\n')
    vals = [v.strip() for v in raw.splitlines() if v.strip()]
    # deja solo dígitos si vinieron con texto
    out = []
    for v in vals:
        digits = ''.join([c for c in v if c.isdigit()])
        out.append(digits if digits else v)
    # únicos manteniendo orden
    seen = set()
    uniq = []
    for v in out:
        if v not in seen:
            uniq.append(v)
            seen.add(v)
    return uniq


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
        for df in (df_exact, df_sim):
            if not df.empty:
                if 'prioridad' in df.columns:
                    df['prioridad'] = df['prioridad'].astype(str).str.upper()
                if 'Client' in df.columns:
                    df['Client'] = df['Client'].astype(str).str.strip()

        df_exact_f = _apply_filters(df_exact)
        df_sim_f = _apply_filters(df_sim)

        # ---------- Resumen ----------
        total_exact = len(df_exact)
        total_sim = len(df_sim)
        alta_exact = int((df_exact.get('prioridad','') == 'ALTA').sum()) if not df_exact.empty else 0
        alta_sim = int((df_sim.get('prioridad','') == 'ALTA').sum()) if not df_sim.empty else 0

        # Clientes únicos para bloquear
        frames = []
        if not df_sim_f.empty:
            frames.append(df_sim_f[['Client','Razon social','prioridad']].copy())
        if incluir_exactos_clientes and not df_exact_f.empty:
            frames.append(df_exact_f[['Client','Razon social','prioridad']].copy())

        if frames:
            df_clients = pd.concat(frames, ignore_index=True)
            df_clients['prioridad'] = df_clients['prioridad'].astype(str).str.upper()
            df_clients['Razon social'] = df_clients.get('Razon social','').astype(str).str.strip()

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
        m1.metric('EXACTOS', f'{total_exact}')
        m2.metric('SIMILARES', f'{total_sim}')
        m3.metric('ALTA (exactos)', f'{alta_exact}')
        m4.metric('ALTA (similares)', f'{alta_sim}')
        m5.metric('Clientes únicos', f'{len(df_clients_sum)}')

        st.markdown('---')

        # ---------- Tabs ----------
        tab1, tab2, tab3, tab4 = st.tabs([
            '🟡 Pares similares (Opción A)',
            '✅ Exactos',
            '🧾 Clientes únicos (para bloquear)',
            '📨 Enviar a preventivos'
        ])

        with tab1:
            st.subheader('🟡 Pares similares (misma entrega cercana + similitud)')
            if df_sim_f.empty:
                st.info('No se detectaron pares similares con los criterios actuales.')
            else:
                df_show = df_sim_f.sort_values(['prioridad'], ascending=False) if 'prioridad' in df_sim_f.columns else df_sim_f
                st.dataframe(df_show, use_container_width=True, hide_index=True)
            st.download_button('Descargar duplicados_similares.csv', data=out_sim.read_bytes(), file_name='duplicados_similares.csv', mime='text/csv')

        with tab2:
            st.subheader('✅ Duplicados exactos')
            if df_exact_f.empty:
                st.info('No se detectaron duplicados exactos con los criterios actuales.')
            else:
                df_show = df_exact_f.copy()
                if not mostrar_firma and 'firma_productos' in df_show.columns:
                    df_show['firma_productos'] = df_show['firma_productos'].astype(str).str.slice(0, 120) + '…'
                df_show = df_show.sort_values(['prioridad'], ascending=False) if 'prioridad' in df_show.columns else df_show
                st.dataframe(df_show, use_container_width=True, hide_index=True)
            st.download_button('Descargar duplicados_exactos.csv', data=out_exact.read_bytes(), file_name='duplicados_exactos.csv', mime='text/csv')

        with tab3:
            st.subheader('🧾 Clientes únicos (lista para bloquear sin confusión)')
            st.caption('Acá NO se repite el número de cliente. Se agrupa y te muestra cantidad de casos y prioridad máxima.')
            if df_clients_sum.empty:
                st.info('No hay clientes para listar con los filtros actuales.')
            else:
                st.dataframe(df_clients_sum, use_container_width=True, hide_index=True)
                csv_bytes = df_clients_sum.to_csv(index=False).encode('utf-8')
                st.download_button('Descargar lista_clientes_unicos.csv', data=csv_bytes, file_name='lista_clientes_unicos.csv', mime='text/csv')

        with tab4:
            st.subheader('📨 Envío a preventivos (lista editable de clientes)')
            st.caption('Pegá o editá la lista de clientes que querés enviar. La app te arma el mensaje y una tabla resumida.')

            # Prellenar con clientes únicos actuales
            prefill = ''
            if not df_clients_sum.empty:
                prefill = '\n'.join(df_clients_sum['Client'].astype(str).tolist())

            colx, coly = st.columns([2,1])
            with colx:
                clientes_texto = st.text_area('Clientes (uno por línea o separados por coma/espacio)', value=prefill, height=220)
            with coly:
                formato = st.selectbox('Formato de salida', ['Líneas (uno debajo de otro)', 'Separados por coma', 'Separados por ;'], index=0)
                solo_alta_en_mensaje = st.checkbox('Solo ALTA en el mensaje', value=False)

            clientes_list = _split_clients(clientes_texto)

            # Armar tabla de esos clientes
            if df_clients_sum.empty or not clientes_list:
                st.warning('No hay clientes para procesar todavía.')
            else:
                df_sel = df_clients_sum[df_clients_sum['Client'].astype(str).isin(clientes_list)].copy()

                if solo_alta_en_mensaje:
                    df_sel = df_sel[df_sel['prioridad_max'] == 'ALTA']

                # Orden: ALTA primero, luego por casos
                if not df_sel.empty:
                    df_sel = df_sel.sort_values(['prioridad_max','casos','Client'], ascending=[False,False,True])

                st.markdown('**Resumen para preventivos**')
                st.dataframe(df_sel, use_container_width=True, hide_index=True)

                # Mensaje
                if formato.startswith('Líneas'):
                    msg_list = df_sel['Client'].astype(str).tolist()
                    mensaje = '\n'.join(msg_list)
                elif 'coma' in formato:
                    mensaje = ', '.join(df_sel['Client'].astype(str).tolist())
                else:
                    mensaje = '; '.join(df_sel['Client'].astype(str).tolist())

                badge = 'ALTA' if solo_alta_en_mensaje else 'ALTA+MEDIA'
                st.markdown(f"<span class='badge {'alta' if solo_alta_en_mensaje else ''}'>LISTA {badge}</span>", unsafe_allow_html=True)
                st.code(mensaje, language='text')

                st.download_button('Descargar mensaje.txt', data=mensaje.encode('utf-8'), file_name='mensaje_preventivos.txt', mime='text/plain')

                # También un CSV solo de esos clientes
                csv_sel = df_sel.to_csv(index=False).encode('utf-8')
                st.download_button('Descargar clientes_seleccionados.csv', data=csv_sel, file_name='clientes_seleccionados.csv', mime='text/csv')

        st.markdown('---')
        st.caption('Si querés, en el próximo paso agrego filtros por rango de fecha de entrega, búsqueda por cliente/razón social y sliders para umbrales de similitud.')

else:
    st.warning('Subí un CSV para empezar.')
