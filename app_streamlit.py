# -*- coding: utf-8 -*-
import streamlit as st
import tempfile
from pathlib import Path
import pandas as pd
from detector_core import detect_from_filelike

FUTURISTIC_CSS = """
<style>
.stApp {
  background: radial-gradient(1200px 800px at 20% 10%, rgba(0,255,240,0.10), transparent 50%),
              radial-gradient(900px 700px at 80% 30%, rgba(155,81,224,0.12), transparent 55%),
              linear-gradient(180deg, #070A12 0%, #060816 40%, #050616 100%);
  color: #E7F6FF;
}
[data-testid="stMetric"] {
  background: rgba(255,255,255,0.06);
  border: 1px solid rgba(0,255,240,0.18);
  border-radius: 14px;
  padding: 14px;
  box-shadow: 0 0 0 1px rgba(155,81,224,0.10) inset,
              0 12px 35px rgba(0,0,0,0.45);
}
[data-testid="stDataFrame"] {
  border: 1px solid rgba(0,255,240,0.16);
  border-radius: 14px;
  overflow: hidden;
  box-shadow: 0 12px 30px rgba(0,0,0,0.35);
}
.stDownloadButton button, .stButton button {
  border-radius: 12px;
  border: 1px solid rgba(0,255,240,0.30);
  background: linear-gradient(90deg, rgba(0,255,240,0.20), rgba(155,81,224,0.16));
  color: #E7F6FF;
  box-shadow: 0 10px 24px rgba(0,0,0,0.35);
}
textarea, input {
  border-radius: 12px !important;
  border: 1px solid rgba(0,255,240,0.20) !important;
  background: rgba(255,255,255,0.05) !important;
  color: #E7F6FF !important;
}
</style>
"""

st.set_page_config(page_title='Detector de Pedidos Duplicados', page_icon='📦', layout='wide')
st.markdown(FUTURISTIC_CSS, unsafe_allow_html=True)

st.title('📦 Detector de pedidos duplicados / similares')
st.caption('Compara por fecha de entrega. Estados: RET/PRC. Prioridad ALTA cuando un duplicado es PRC vs RET.')

uploaded = st.file_uploader('Subí el archivo (CSV del reporte)', type=['csv'])

colA, colB, colC, colD = st.columns([1,1,1,2])
with colA:
    solo_alta = st.checkbox('Solo PRIORIDAD ALTA', value=False)
with colB:
    mostrar_firma = st.checkbox('Mostrar firma_productos completa', value=False)
with colC:
    incluir_exactos_clientes = st.checkbox('Incluir EXACTOS en clientes únicos', value=True)
with colD:
    st.info('Tip: Se detecta separador ; , o tab (como TextToColumns) y se ignoran encabezados antes de F.Pedido.')


def _normalize_client_series(s: pd.Series) -> pd.Series:
    # deja solo dígitos y quita espacios/caracteres raros
    s = s.fillna('').astype(str).str.strip()
    return s.apply(lambda v: ''.join([c for c in v if c.isdigit()]))


def _apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    if solo_alta and 'prioridad' in df.columns:
        df = df[df['prioridad'].astype(str).str.upper() == 'ALTA']
    return df


def _split_clients(text: str):
    if not text:
        return []
    raw = text.replace(';','\n').replace(',','\n').replace(' ','\n')
    vals = [v.strip() for v in raw.splitlines() if v.strip()]
    out=[]
    for v in vals:
        d=''.join([c for c in v if c.isdigit()])
        out.append(d if d else v)
    seen=set(); uniq=[]
    for v in out:
        if v not in seen:
            uniq.append(v); seen.add(v)
    return uniq


def _suppress_repeated(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Vista DETALLE: muestra el valor de 'col' solo en la primera fila del bloque.
    Importante: requiere que el DF esté ordenado por esa columna.
    """
    if df.empty or col not in df.columns:
        return df
    out = df.copy()
    vals = out[col].fillna('').astype(str)
    out.loc[vals.eq(vals.shift(1)), col] = ''
    return out


if not uploaded:
    st.warning('Subí un CSV para empezar.')
    st.stop()

with tempfile.TemporaryDirectory() as td:
    out_exact, out_sim = detect_from_filelike(uploaded, td)
    out_exact, out_sim = Path(out_exact), Path(out_sim)

    df_exact = pd.read_csv(out_exact, dtype=str) if out_exact.exists() else pd.DataFrame()
    df_sim = pd.read_csv(out_sim, dtype=str) if out_sim.exists() else pd.DataFrame()

    for df in (df_exact, df_sim):
        if not df.empty:
            if 'prioridad' in df.columns:
                df['prioridad'] = df['prioridad'].astype(str).str.upper()
            if 'Client' in df.columns:
                df['Client'] = _normalize_client_series(df['Client'])

    df_exact_f = _apply_filters(df_exact)
    df_sim_f = _apply_filters(df_sim)

    alta_exact = int((df_exact.get('prioridad','') == 'ALTA').sum()) if not df_exact.empty else 0
    alta_sim = int((df_sim.get('prioridad','') == 'ALTA').sum()) if not df_sim.empty else 0

    # Clientes únicos
    frames=[]
    if not df_sim_f.empty:
        frames.append(df_sim_f[['Client','Razon social','prioridad']].copy())
    if incluir_exactos_clientes and not df_exact_f.empty:
        frames.append(df_exact_f[['Client','Razon social','prioridad']].copy())

    if frames:
        df_clients = pd.concat(frames, ignore_index=True)
        df_clients['Client'] = _normalize_client_series(df_clients['Client'])
        df_clients['prioridad'] = df_clients['prioridad'].astype(str).str.upper()
        df_clients['Razon social'] = df_clients.get('Razon social','').astype(str).str.strip()
        df_clients['prio_rank'] = df_clients['prioridad'].apply(lambda p: 2 if str(p).upper()=='ALTA' else 1)
        g = df_clients.groupby('Client', dropna=False)
        df_clients_sum = g.agg(
            razon_social=('Razon social', lambda x: next((v for v in x if v and v!='nan'), '')),
            casos=('Client','size'),
            prioridad_max=('prio_rank','max')
        ).reset_index()
        df_clients_sum['prioridad_max'] = df_clients_sum['prioridad_max'].map({2:'ALTA',1:'MEDIA'}).fillna('MEDIA')
        df_clients_sum = df_clients_sum.sort_values(['prioridad_max','casos','Client'], ascending=[False,False,True])
    else:
        df_clients_sum = pd.DataFrame(columns=['Client','razon_social','casos','prioridad_max'])

    m1,m2,m3,m4,m5 = st.columns(5)
    m1.metric('EXACTOS', str(len(df_exact)))
    m2.metric('SIMILARES', str(len(df_sim)))
    m3.metric('ALTA (exactos)', str(alta_exact))
    m4.metric('ALTA (similares)', str(alta_sim))
    m5.metric('Clientes únicos', str(len(df_clients_sum)))

    st.markdown('---')

    tab1,tab2,tab3,tab4 = st.tabs(['🟡 Similares', '✅ Exactos', '🧾 Clientes únicos', '📨 Preventivos'])

    with tab1:
        st.subheader('🟡 Duplicados similares')
        vista = st.radio('Vista', ['Detalle (sin repetir Client)', 'Agrupada por cliente (1 fila por Client)'], horizontal=True)

        if df_sim_f.empty:
            st.info('No hay similares con los criterios actuales.')
        else:
            if vista.startswith('Detalle'):
                df_detail = df_sim_f.sort_values(['prioridad','Client'], ascending=[False, True]) if 'prioridad' in df_sim_f.columns else df_sim_f.sort_values(['Client'])
                df_detail = _suppress_repeated(df_detail, 'Client')
                st.dataframe(df_detail, use_container_width=True, hide_index=True)
            else:
                df_tmp = df_sim_f.copy()
                df_tmp['prio_rank'] = df_tmp.get('prioridad','MEDIA').apply(lambda p: 2 if str(p).upper()=='ALTA' else 1)
                g = df_tmp.groupby('Client', dropna=False)
                df_group = g.agg(
                    pares=('Client','size'),
                    prioridad_max=('prio_rank','max'),
                    ejemplo_pedido_1=('Pedido_1', lambda x: next((v for v in x if str(v)!='nan'), '')),
                    ejemplo_pedido_2=('Pedido_2', lambda x: next((v for v in x if str(v)!='nan'), '')),
                ).reset_index()
                df_group['prioridad_max'] = df_group['prioridad_max'].map({2:'ALTA',1:'MEDIA'}).fillna('MEDIA')
                df_group = df_group.sort_values(['prioridad_max','pares','Client'], ascending=[False,False,True])
                st.dataframe(df_group, use_container_width=True, hide_index=True)
                st.download_button('Descargar similares_agrupado_por_cliente.csv', data=df_group.to_csv(index=False).encode('utf-8'),
                                   file_name='similares_agrupado_por_cliente.csv', mime='text/csv')

        st.download_button('Descargar duplicados_similares.csv', data=out_sim.read_bytes(), file_name='duplicados_similares.csv', mime='text/csv')

    with tab2:
        st.subheader('✅ Duplicados exactos (sin repetir Client)')
        df_show = df_exact_f.copy()
        if not mostrar_firma and not df_show.empty and 'firma_productos' in df_show.columns:
            df_show['firma_productos'] = df_show['firma_productos'].astype(str).str.slice(0,120) + '…'
        if not df_show.empty:
            df_detail = df_show.sort_values(['prioridad','Client'], ascending=[False, True]) if 'prioridad' in df_show.columns else df_show.sort_values(['Client'])
            df_detail = _suppress_repeated(df_detail, 'Client')
            st.dataframe(df_detail, use_container_width=True, hide_index=True)
        else:
            st.info('No hay exactos con los criterios actuales.')
        st.download_button('Descargar duplicados_exactos.csv', data=out_exact.read_bytes(), file_name='duplicados_exactos.csv', mime='text/csv')

    with tab3:
        st.subheader('🧾 Clientes únicos (para bloquear)')
        st.caption('Acá SIEMPRE es 1 fila por Client (normalizado a solo dígitos).')
        st.dataframe(df_clients_sum, use_container_width=True, hide_index=True)
        st.download_button('Descargar lista_clientes_unicos.csv', data=df_clients_sum.to_csv(index=False).encode('utf-8'),
                           file_name='lista_clientes_unicos.csv', mime='text/csv')

    with tab4:
        st.subheader('📨 Enviar a preventivos')
        prefill = '\n'.join(df_clients_sum['Client'].astype(str).tolist()) if not df_clients_sum.empty else ''
        clientes_texto = st.text_area('Clientes (uno por línea / coma / espacio / ;)', value=prefill, height=220)
        formato = st.selectbox('Formato', ['Líneas', 'Coma', 'Punto y coma'], index=0)
        solo_alta_msg = st.checkbox('Solo ALTA en mensaje', value=False)

        clientes_list = _split_clients(clientes_texto)
        df_sel = df_clients_sum[df_clients_sum['Client'].astype(str).isin(clientes_list)].copy() if not df_clients_sum.empty else pd.DataFrame()
        if solo_alta_msg and not df_sel.empty:
            df_sel = df_sel[df_sel['prioridad_max'] == 'ALTA']

        st.dataframe(df_sel, use_container_width=True, hide_index=True)

        if not df_sel.empty:
            ids = df_sel['Client'].astype(str).tolist()
            if formato == 'Líneas':
                mensaje = '\n'.join(ids)
            elif formato == 'Coma':
                mensaje = ', '.join(ids)
            else:
                mensaje = '; '.join(ids)
            st.code(mensaje, language='text')
            st.download_button('Descargar mensaje_preventivos.txt', data=mensaje.encode('utf-8'),
                               file_name='mensaje_preventivos.txt', mime='text/plain')
