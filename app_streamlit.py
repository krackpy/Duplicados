# -*- coding: utf-8 -*-
import streamlit as st
import tempfile
from pathlib import Path
from datetime import date, timedelta

import pandas as pd
import altair as alt

from detector_core import detect_from_fileli

# ---------------- UI / Estilos ----------------
FUTURISTIC_CSS = """
<style>
:root {
  --bg1: #0b1220;
  --bg2: #0e1b33;
  --card: rgba(255,255,255,0.06);
  --card2: rgba(255,255,255,0.10);
  --border: rgba(255,255,255,0.14);
  --accent: #00d4ff;
  --accent2:#00ffa3;
}

.stApp {
  background: radial-gradient(1200px 900px at 10% 10%, #10254e 0%, var(--bg1) 60%),
              radial-gradient(1000px 600px at 90% 20%, #0b3a5a 0%, var(--bg2) 60%);
}

.block-container {padding-top: 1.3rem; padding-bottom: 1.8rem;}

h1, h2, h3, h4, h5, p, span, label {color: rgba(255,255,255,0.92) !important;}

div[data-testid="stMetric"] {
  background: linear-gradient(135deg, var(--card), var(--card2));
  border: 1px solid var(--border);
  padding: 14px 16px;
  border-radius: 14px;
}

hr {border-color: rgba(255,255,255,0.18) !important;}

div[data-testid="stDataFrame"] {
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 14px;
  overflow: hidden;
}
</style>
"""

st.set_page_config(
    page_title='Control de pedidos • Duplicados & Salidas',
    page_icon='📦',
    layout='wide'
)

st.markdown(FUTURISTIC_CSS, unsafe_allow_html=True)

# ---------------- Sidebar: logo + parámetros ----------------
st.sidebar.markdown("## Cervepar")
logo_path = Path('assets/cervepar_logo.png')
if logo_path.exists():
    st.sidebar.image(str(logo_path), use_container_width=True)
else:
    st.sidebar.caption("💡 Tip: agregá el logo en **assets/cervepar_logo.png**")

st.sidebar.markdown('---')
st.sidebar.markdown('### Parámetros del detector')

max_dias = st.sidebar.slider('Ventana de días (Entrega)', 0, 7, 2)
min_sim_importe = st.sidebar.slider('Similitud de importe (mín)', 0.80, 0.99, 0.95, 0.01)
min_sim_productos = st.sidebar.slider('Similitud de productos (mín)', 0.50, 0.99, 0.85, 0.01)
red_imp = st.sidebar.select_slider('Redondeo importe (decimales)', options=[0, 1, 2, 3, 4], value=2)
red_cant = st.sidebar.select_slider('Redondeo cantidad (decimales)', options=[0, 1, 2, 3, 4], value=3)
exact_only_ret = st.sidebar.checkbox('Exactos solo RET', value=True)

cfg = DetectorConfig(
    max_dias=max_dias,
    min_sim_importe=min_sim_importe,
    min_sim_productos=min_sim_productos,
    redondeo_importe=red_imp,
    redondeo_cant=red_cant,
    exact_only_ret=exact_only_ret,
)

st.sidebar.markdown('---')
st.sidebar.markdown('### Filtros de visualización')
solo_alta = st.sidebar.checkbox('Solo PRIORIDAD ALTA', value=False)
mostrar_firma = st.sidebar.checkbox('Mostrar firma_productos completa', value=False)
incluir_exactos_clientes = st.sidebar.checkbox('Incluir EXACTOS en clientes únicos', value=True)

# ---------------- Main ----------------
st.title('📦 Control de pedidos: duplicados / similares + salidas del día siguiente')
st.caption('Compara por fecha de entrega. Estados: RET/PRC. Prioridad **ALTA** cuando un duplicado es PRC vs RET.')

uploaded = st.file_uploader('Subí el archivo (CSV del reporte)', type=['csv'])


def _normalize_client_series(s: pd.Series) -> pd.Series:
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
    raw = text.replace(';', '\n').replace(',', '\n').replace(' ', '\n')
    vals = [v.strip() for v in raw.splitlines() if v.strip()]
    out = []
    for v in vals:
        d = ''.join([c for c in v if c.isdigit()])
        out.append(d if d else v)
    seen, uniq = set(), []
    for v in out:
        if v not in seen:
            uniq.append(v)
            seen.add(v)
    return uniq


def _suppress_repeated(df: pd.DataFrame, col: str) -> pd.DataFrame:
    if df.empty or col not in df.columns:
        return df
    out = df.copy()
    vals = out[col].fillna('').astype(str)
    out.loc[vals.eq(vals.shift(1)), col] = ''
    return out


def _chart_prioridad(df: pd.DataFrame, title: str):
    if df.empty or 'prioridad' not in df.columns:
        st.info('Sin datos para graficar.')
        return
    tmp = df.copy()
    tmp['prioridad'] = tmp['prioridad'].astype(str).str.upper().fillna('MEDIA')
    c = tmp.groupby('prioridad', as_index=False).size().rename(columns={'size': 'casos'})
    c['prioridad'] = pd.Categorical(c['prioridad'], categories=['ALTA', 'MEDIA'], ordered=True)
    chart = (
        alt.Chart(c)
        .mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6)
        .encode(
            x=alt.X('prioridad:N', title='Prioridad'),
            y=alt.Y('casos:Q', title='Casos'),
            color=alt.Color('prioridad:N', scale=alt.Scale(domain=['ALTA', 'MEDIA'], range=['#00ffa3', '#00d4ff']), legend=None),
            tooltip=['prioridad', 'casos'],
        )
        .properties(height=220, title=title)
    )
    st.altair_chart(chart, use_container_width=True)


def _chart_top_clients_sim(df_sim: pd.DataFrame):
    if df_sim.empty:
        st.info('Sin similares para graficar.')
        return
    top = df_sim.groupby('Client', as_index=False).size().rename(columns={'size': 'pares'})
    top = top.sort_values('pares', ascending=False).head(15)
    chart = (
        alt.Chart(top)
        .mark_bar(cornerRadiusEnd=6)
        .encode(
            x=alt.X('pares:Q', title='Pares similares'),
            y=alt.Y('Client:N', sort='-x', title='Client'),
            color=alt.value('#00d4ff'),
            tooltip=['Client', 'pares'],
        )
        .properties(height=420, title='Top clientes con más pares similares')
    )
    st.altair_chart(chart, use_container_width=True)


def _chart_sim_por_fecha(df_sim: pd.DataFrame):
    if df_sim.empty or 'Entrega_1' not in df_sim.columns:
        return
    tmp = df_sim.copy()
    tmp['Entrega_1'] = pd.to_datetime(tmp['Entrega_1'], errors='coerce')
    tmp = tmp.dropna(subset=['Entrega_1'])
    if tmp.empty:
        return
    by = tmp.groupby(tmp['Entrega_1'].dt.date, as_index=False).size().rename(columns={'size': 'pares'})
    by['Entrega_1'] = pd.to_datetime(by['Entrega_1'])
    chart = (
        alt.Chart(by)
        .mark_area(opacity=0.25, color='#00ffa3')
        .encode(
            x=alt.X('Entrega_1:T', title='Entrega (fecha)'),
            y=alt.Y('pares:Q', title='Pares similares'),
            tooltip=[alt.Tooltip('Entrega_1:T', title='Fecha'), 'pares'],
        )
        .properties(height=220, title='Evolución de pares similares por fecha de entrega')
    )
    st.altair_chart(chart, use_container_width=True)


if not uploaded:
    st.warning('Subí un CSV para empezar.')
    st.stop()

# Ejecutar detector
with tempfile.TemporaryDirectory() as td:
    out_exact, out_sim = detect_from_filelike(uploaded, td, config=cfg)
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

    # Clientes únicos
    frames = []
    if not df_sim_f.empty:
        frames.append(df_sim_f[['Client', 'Razon social', 'prioridad']].copy())
    if incluir_exactos_clientes and not df_exact_f.empty:
        frames.append(df_exact_f[['Client', 'Razon social', 'prioridad']].copy())

    if frames:
        df_clients = pd.concat(frames, ignore_index=True)
        df_clients['Client'] = _normalize_client_series(df_clients['Client'])
        df_clients['prioridad'] = df_clients['prioridad'].astype(str).str.upper()
        df_clients['Razon social'] = df_clients.get('Razon social', '').astype(str).str.strip()
        df_clients['prio_rank'] = df_clients['prioridad'].apply(lambda p: 2 if str(p).upper() == 'ALTA' else 1)

        g = df_clients.groupby('Client', dropna=False)
        df_clients_sum = g.agg(
            razon_social=('Razon social', lambda x: next((v for v in x if v and v != 'nan'), '')),
            casos=('Client', 'size'),
            prioridad_max=('prio_rank', 'max'),
        ).reset_index()

        df_clients_sum['prioridad_max'] = df_clients_sum['prioridad_max'].map({2: 'ALTA', 1: 'MEDIA'}).fillna('MEDIA')
        df_clients_sum = df_clients_sum.sort_values(['prioridad_max', 'casos', 'Client'], ascending=[False, False, True])
    else:
        df_clients_sum = pd.DataFrame(columns=['Client', 'razon_social', 'casos', 'prioridad_max'])

    # Pedidos para salidas (se recalcula desde el CSV)
    uploaded.seek(0)
    orders = orders_from_filelike(uploaded, config=cfg)
    df_orders = pd.DataFrame(orders)
    if not df_orders.empty:
        df_orders['Entrega'] = pd.to_datetime(df_orders['Entrega'], errors='coerce').dt.date
        df_orders['Importe'] = pd.to_numeric(df_orders['Importe'], errors='coerce')
        df_orders['Sts'] = df_orders['Sts'].astype(str).str.upper()

# KPIs
alta_exact = int((df_exact_f.get('prioridad', '') == 'ALTA').sum()) if not df_exact_f.empty else 0
alta_sim = int((df_sim_f.get('prioridad', '') == 'ALTA').sum()) if not df_sim_f.empty else 0

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric('EXACTOS', str(len(df_exact_f)))
m2.metric('SIMILARES', str(len(df_sim_f)))
m3.metric('ALTA (exactos)', str(alta_exact))
m4.metric('ALTA (similares)', str(alta_sim))
m5.metric('Clientes únicos', str(len(df_clients_sum)))

st.markdown('---')

(tab_sim, tab_exact, tab_clients, tab_salidas, tab_prev) = st.tabs([
    '🟡 Similares',
    '✅ Exactos',
    '🧾 Clientes únicos',
    '🚚 Salidas (día siguiente)',
    '📨 Preventivos',
])

with tab_sim:
    st.subheader('🟡 Duplicados similares')

    left, right = st.columns([1.25, 1])
    with left:
        vista = st.radio('Vista', ['Detalle (sin repetir Client)', 'Agrupada por cliente (1 fila por Client)'], horizontal=True)

        if df_sim_f.empty:
            st.info('No hay similares con los criterios actuales.')
        else:
            if vista.startswith('Detalle'):
                df_detail = df_sim_f.sort_values(['prioridad', 'Client'], ascending=[False, True])
                df_detail = _suppress_repeated(df_detail, 'Client')
                st.dataframe(df_detail, use_container_width=True, hide_index=True)
            else:
                df_tmp = df_sim_f.copy()
                df_tmp['prio_rank'] = df_tmp.get('prioridad', 'MEDIA').apply(lambda p: 2 if str(p).upper() == 'ALTA' else 1)
                g = df_tmp.groupby('Client', dropna=False)
                df_group = g.agg(
                    pares=('Client', 'size'),
                    prioridad_max=('prio_rank', 'max'),
                    ejemplo_pedido_1=('Pedido_1', lambda x: next((v for v in x if str(v) != 'nan'), '')),
                    ejemplo_pedido_2=('Pedido_2', lambda x: next((v for v in x if str(v) != 'nan'), '')),
                ).reset_index()
                df_group['prioridad_max'] = df_group['prioridad_max'].map({2: 'ALTA', 1: 'MEDIA'}).fillna('MEDIA')
                df_group = df_group.sort_values(['prioridad_max', 'pares', 'Client'], ascending=[False, False, True])
                st.dataframe(df_group, use_container_width=True, hide_index=True)

                st.download_button(
                    'Descargar similares_agrupado_por_cliente.csv',
                    data=df_group.to_csv(index=False).encode('utf-8'),
                    file_name='similares_agrupado_por_cliente.csv',
                    mime='text/csv',
                )

            st.download_button(
                'Descargar duplicados_similares.csv',
                data=out_sim.read_bytes(),
                file_name='duplicados_similares.csv',
                mime='text/csv',
            )

    with right:
        st.markdown('#### Resumen gráfico')
        _chart_prioridad(df_sim_f, 'Similares por prioridad')
        _chart_sim_por_fecha(df_sim_f)
        _chart_top_clients_sim(df_sim_f)

with tab_exact:
    st.subheader('✅ Duplicados exactos (sin repetir Client)')

    if df_exact_f.empty:
        st.info('No hay exactos con los criterios actuales.')
    else:
        df_show = df_exact_f.copy()
        if not mostrar_firma and 'firma_productos' in df_show.columns:
            df_show['firma_productos'] = df_show['firma_productos'].astype(str).str.slice(0, 120) + '…'

        df_detail = df_show.sort_values(['prioridad', 'Client'], ascending=[False, True])
        df_detail = _suppress_repeated(df_detail, 'Client')
        st.dataframe(df_detail, use_container_width=True, hide_index=True)

    c1, c2 = st.columns([1, 1])
    with c1:
        st.download_button(
            'Descargar duplicados_exactos.csv',
            data=out_exact.read_bytes(),
            file_name='duplicados_exactos.csv',
            mime='text/csv',
        )
    with c2:
        _chart_prioridad(df_exact_f, 'Exactos por prioridad')

with tab_clients:
    st.subheader('🧾 Clientes únicos (para bloquear)')
    st.caption('Acá SIEMPRE es 1 fila por Client (normalizado a solo dígitos).')

    st.dataframe(df_clients_sum, use_container_width=True, hide_index=True)
    st.download_button(
        'Descargar lista_clientes_unicos.csv',
        data=df_clients_sum.to_csv(index=False).encode('utf-8'),
        file_name='lista_clientes_unicos.csv',
        mime='text/csv',
    )

with tab_salidas:
    st.subheader('🚚 Clientes / pedidos que deben salir al día siguiente')
    st.caption('Por defecto muestra **mañana**, pero podés elegir la fecha. Se calcula desde el mismo CSV (1 fila por pedido agregado).')

    if df_orders.empty:
        st.info('No se pudieron armar pedidos desde el archivo.')
    else:
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            fecha_obj = st.date_input('Fecha de entrega objetivo', value=date.today() + timedelta(days=1))
        with col2:
            estados = st.multiselect('Estados', options=['RET', 'PRC'], default=['RET', 'PRC'])
        with col3:
            buscar = st.text_input('Buscar (Client / Razón social / Pedido)', value='')

        df_out = df_orders.copy()
        df_out = df_out[df_out['Entrega'] == fecha_obj]
        if estados:
            df_out = df_out[df_out['Sts'].isin([e.upper() for e in estados])]
        if buscar:
            b = buscar.strip().lower()
            mask = (
                df_out['Client'].astype(str).str.lower().str.contains(b, na=False)
                | df_out.get('Razon social', '').astype(str).str.lower().str.contains(b, na=False)
                | df_out['Pedido'].astype(str).str.lower().str.contains(b, na=False)
            )
            df_out = df_out[mask]

        total_pedidos = len(df_out)
        total_clientes = df_out['Client'].nunique() if not df_out.empty else 0
        total_importe = float(df_out['Importe'].fillna(0).sum()) if not df_out.empty and 'Importe' in df_out.columns else 0.0

        k1, k2, k3 = st.columns(3)
        k1.metric('Pedidos', f'{total_pedidos:,}'.replace(',', '.'))
        k2.metric('Clientes', f'{total_clientes:,}'.replace(',', '.'))
        k3.metric('Importe total', f"{total_importe:,.0f}".replace(',', '.'))

        cols = [c for c in ['Client', 'Razon social', 'Pedido', 'Sts', 'Entrega', 'Importe', 'n_productos'] if c in df_out.columns]
        st.dataframe(df_out[cols].sort_values(['Client', 'Pedido']), use_container_width=True, hide_index=True)

        st.markdown('#### Resumen gráfico (salidas)')
        g1, g2 = st.columns([1, 1.2])

        with g1:
            sts_counts = df_out.groupby('Sts', as_index=False).size().rename(columns={'size': 'pedidos'}) if not df_out.empty else pd.DataFrame({'Sts': [], 'pedidos': []})
            if not sts_counts.empty:
                chart = (
                    alt.Chart(sts_counts)
                    .mark_arc(innerRadius=55)
                    .encode(
                        theta='pedidos:Q',
                        color=alt.Color('Sts:N', scale=alt.Scale(range=['#00d4ff', '#00ffa3'])),
                        tooltip=['Sts', 'pedidos'],
                    )
                    .properties(height=260, title='Pedidos por estado')
                )
                st.altair_chart(chart, use_container_width=True)
            else:
                st.info('Sin datos para el gráfico de estados.')

        with g2:
            top = df_out.groupby('Client', as_index=False).agg(pedidos=('Pedido', 'nunique'), importe=('Importe', 'sum')) if not df_out.empty else pd.DataFrame({'Client': [], 'pedidos': [], 'importe': []})
            top = top.sort_values('importe', ascending=False).head(15)
            if not top.empty:
                chart = (
                    alt.Chart(top)
                    .mark_bar(cornerRadiusEnd=6)
                    .encode(
                        x=alt.X('importe:Q', title='Importe total'),
                        y=alt.Y('Client:N', sort='-x', title='Client'),
                        color=alt.value('#00ffa3'),
                        tooltip=['Client', 'pedidos', alt.Tooltip('importe:Q', format=',.0f')],
                    )
                    .properties(height=360, title='Top clientes por importe (salidas)')
                )
                st.altair_chart(chart, use_container_width=True)
            else:
                st.info('Sin datos para el gráfico de top clientes.')

        st.download_button(
            'Descargar salidas_fecha_objetivo.csv',
            data=df_out.to_csv(index=False).encode('utf-8'),
            file_name=f'salidas_{fecha_obj.isoformat()}.csv',
            mime='text/csv',
        )

with tab_prev:
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
        st.download_button(
            'Descargar mensaje_preventivos.txt',
            data=mensaje.encode('utf-8'),
            file_name='mensaje_preventivos.txt',
            mime='text/plain',
        )
