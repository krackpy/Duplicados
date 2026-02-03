# -*- coding: utf-8 -*-
"""Núcleo del detector (reutilizable).

✅ Replica la lógica de tu macro LIMPIEZA:
- "TextToColumns" equivalente: soporta separadores ',', ';' o '\t' (auto-detecta)
- Elimina encabezados del reporte: busca la fila que empieza con 'F.Pedido' y procesa desde ahí

Reglas de negocio:
- Comparación por FECHA DE ENTREGA (Entrega)
- Estados válidos: RET, PRC
- Prioridad ALTA: cuando un duplicado involucra PRC y RET

Expone:
- run_detector(in_path) -> (path_exact, path_sim)
- detect_from_filelike(fileobj, out_dir) -> (path_exact, path_sim)
"""

import csv
import math
from collections import defaultdict
from datetime import datetime
from io import StringIO
from pathlib import Path

# ---------------- CONFIG (ajustable) ----------------
MAX_DIAS = 2
MIN_SIM_IMPORTE = 0.95
MIN_SIM_PRODUCTOS = 0.85
REDONDEO_IMPORTE = 2
REDONDEO_CANT = 3

COL_CLIENTE = 'Client'
COL_PEDIDO = 'Pedido'
COL_ENTREGA = 'Entrega'
COL_IMPORTE = 'Importe Total'
COL_CPRD = 'C.Prd'
COL_CANT = 'Cant'
COL_RAZON = 'Razon social'
COL_STS = 'Sts'

ESTADOS_VALIDOS = {'RET', 'PRC'}

# ---------------- Utilidades ----------------

def _strip(s):
    return (s or '').strip()


def parse_fecha_entrega(s):
    s = _strip(s)
    try:
        return datetime.strptime(s, '%d/%m/%y').date()
    except Exception:
        return None


def parse_float(s):
    s = _strip(s).replace(' ', '')
    if not s:
        return None
    try:
        return float(s)
    except Exception:
        return None


def cosine_sim(d1, d2):
    if not d1 or not d2:
        return 0.0
    inter = set(d1).intersection(d2)
    dot = sum(d1[k] * d2[k] for k in inter)
    n1 = math.sqrt(sum(v * v for v in d1.values()))
    n2 = math.sqrt(sum(v * v for v in d2.values()))
    if n1 == 0 or n2 == 0:
        return 0.0
    return dot / (n1 * n2)


def sim_importe(a, b):
    if a is None or b is None or a == 0 or b == 0:
        return 0.0
    return 1.0 - abs(a - b) / max(a, b)


def prioridad(sts_a, sts_b):
    sts_a = (sts_a or '').strip()
    sts_b = (sts_b or '').strip()
    return 'ALTA' if ({sts_a, sts_b} == {'PRC', 'RET'}) else 'MEDIA'


def _find_header_index(lines):
    # Busca la fila que inicia la cabecera real del reporte
    for i, line in enumerate(lines[:2000]):
        if line.strip().startswith('F.Pedido'):
            return i
    return None


def _detect_delimiter(sample_line: str) -> str:
    """Auto-detección simple (tipo TextToColumns).
    Si el archivo viene con ';' (Excel ES) o ',' o tab, elegimos el más probable.
    """
    # Normalizar tabs visibles
    c_comma = sample_line.count(',')
    c_semi = sample_line.count(';')
    c_tab = sample_line.count('\t')

    if c_tab > max(c_comma, c_semi):
        return '\t'
    if c_semi > c_comma:
        return ';'
    return ','


def _rows_from_text(text: str):
    lines = text.splitlines(True)
    header_idx = _find_header_index(lines)
    if header_idx is None:
        raise RuntimeError("No se encontró la cabecera (línea que inicia con 'F.Pedido')")

    content = ''.join(lines[header_idx:])

    # Elegimos delimitador basado en la línea de cabecera
    header_line = lines[header_idx]
    delim = _detect_delimiter(header_line)

    # Si viene con TAB, lo dejamos; si viene con ';' o ',', csv.DictReader lo maneja.
    # También aplicamos un fallback: si el header queda con 1 sola columna, probamos el otro delimiter.
    def parse_with(d):
        reader = csv.DictReader(StringIO(content), delimiter=d)
        if reader.fieldnames:
            reader.fieldnames = [fn.strip() for fn in reader.fieldnames]
        for row in reader:
            yield {k.strip(): _strip(v) for k, v in row.items()}

    # Intento 1
    parsed = list(parse_with(delim))
    if parsed and (len(parsed[0].keys()) <= 2):
        # fallback al alternativo
        alt = ',' if delim == ';' else ';'
        parsed = list(parse_with(alt))

    for row in parsed:
        yield row


def iter_rows_from_path(path: Path):
    raw = path.read_bytes()
    text = raw.decode('latin1', errors='ignore')
    yield from _rows_from_text(text)


def iter_rows_from_filelike(fileobj):
    data = fileobj.read()
    if isinstance(data, bytes):
        text = data.decode('latin1', errors='ignore')
    else:
        text = data
    yield from _rows_from_text(text)


def write_csv(path: Path, rows, fieldnames):
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            rr = dict(r)
            for k, v in rr.items():
                if hasattr(v, 'isoformat'):
                    rr[k] = v.isoformat()
            w.writerow(rr)


def _detect(rows_iter, out_exact: Path, out_sim: Path):
    orders = {}

    # 1) Armar pedidos desde líneas
    for row in rows_iter:
        sts = _strip(row.get(COL_STS))
        if sts and sts not in ESTADOS_VALIDOS:
            continue

        client = _strip(row.get(COL_CLIENTE))
        pedido = _strip(row.get(COL_PEDIDO))
        if not client or not pedido:
            continue

        key = (client, pedido)
        entrega = parse_fecha_entrega(row.get(COL_ENTREGA))
        imp = parse_float(row.get(COL_IMPORTE))
        prd = _strip(row.get(COL_CPRD))
        cant = parse_float(row.get(COL_CANT))
        razon = _strip(row.get(COL_RAZON))

        if key not in orders:
            orders[key] = {
                'Client': client,
                'Pedido': pedido,
                'Razon social': razon,
                'Sts': sts,
                'Entrega': entrega,
                'Importe': imp,
                'prd_qty': defaultdict(float),
            }

        o = orders[key]
        if not o.get('Razon social') and razon:
            o['Razon social'] = razon
        if not o.get('Sts') and sts:
            o['Sts'] = sts
        if o.get('Entrega') is None and entrega is not None:
            o['Entrega'] = entrega
        if imp is not None:
            if o.get('Importe') is None or imp > o['Importe']:
                o['Importe'] = imp
        if prd:
            o['prd_qty'][prd] += (cant or 0.0)

    orders_list = list(orders.values())

    # 2) Firmas
    for o in orders_list:
        o['Importe_r'] = round(o['Importe'] or 0.0, REDONDEO_IMPORTE)
        o['prd_tuple'] = tuple(sorted((p, round(q, REDONDEO_CANT)) for p, q in o['prd_qty'].items() if p))

    # 3) Exactos
    exact_groups = defaultdict(list)
    for o in orders_list:
        k = (o['Client'], o['Entrega'], o['Importe_r'], o['prd_tuple'])
        exact_groups[k].append(o)

    exact_rows = []
    for k, items in exact_groups.items():
        if len(items) > 1:
            sts_set = {it.get('Sts', '') for it in items}
            prio = 'ALTA' if ('PRC' in sts_set and 'RET' in sts_set) else 'MEDIA'
            for o in items:
                exact_rows.append({
                    'Client': o['Client'],
                    'Razon social': o.get('Razon social', ''),
                    'Sts': o.get('Sts', ''),
                    'Pedido': o['Pedido'],
                    'Entrega': o.get('Entrega'),
                    'Importe': o.get('Importe'),
                    'prioridad': prio,
                    'n_productos': len(o['prd_tuple']),
                    'firma_productos': o['prd_tuple'],
                })

    if exact_rows:
        write_csv(out_exact, exact_rows, list(exact_rows[0].keys()))
    else:
        write_csv(out_exact, [], ['Client','Razon social','Sts','Pedido','Entrega','Importe','prioridad','n_productos','firma_productos'])

    # 4) Similares
    by_client = defaultdict(list)
    for o in orders_list:
        if o.get('Entrega') is not None:
            by_client[o['Client']].append(o)

    similar_pairs = []
    for client, lst in by_client.items():
        lst.sort(key=lambda x: (x['Entrega'], x['Pedido']))
        for i in range(len(lst)):
            a = lst[i]
            for j in range(i + 1, len(lst)):
                b = lst[j]
                if (b['Entrega'] - a['Entrega']).days > MAX_DIAS:
                    break
                s_imp = sim_importe(a.get('Importe') or 0.0, b.get('Importe') or 0.0)
                if s_imp < (MIN_SIM_IMPORTE - 0.05):
                    continue
                s_prd = cosine_sim(a.get('prd_qty'), b.get('prd_qty'))
                if s_imp >= MIN_SIM_IMPORTE and s_prd >= MIN_SIM_PRODUCTOS:
                    similar_pairs.append({
                        'Client': client,
                        'Razon social': a.get('Razon social') or b.get('Razon social'),
                        'Sts_1': a.get('Sts', ''),
                        'Sts_2': b.get('Sts', ''),
                        'Pedido_1': a['Pedido'],
                        'Pedido_2': b['Pedido'],
                        'Entrega_1': a.get('Entrega'),
                        'Entrega_2': b.get('Entrega'),
                        'Importe_1': a.get('Importe'),
                        'Importe_2': b.get('Importe'),
                        'sim_importe': round(s_imp, 4),
                        'sim_productos': round(s_prd, 4),
                        'prioridad': prioridad(a.get('Sts'), b.get('Sts')),
                    })

    if similar_pairs:
        write_csv(out_sim, similar_pairs, list(similar_pairs[0].keys()))
    else:
        write_csv(out_sim, [], ['Client','Razon social','Sts_1','Sts_2','Pedido_1','Pedido_2','Entrega_1','Entrega_2','Importe_1','Importe_2','sim_importe','sim_productos','prioridad'])

    return out_exact, out_sim


def run_detector(in_path: str | Path):
    in_path = Path(in_path)
    out_exact = in_path.with_name('duplicados_exactos.csv')
    out_sim = in_path.with_name('duplicados_similares.csv')
    return _detect(iter_rows_from_path(in_path), out_exact, out_sim)


def detect_from_filelike(fileobj, out_dir: str | Path):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_exact = out_dir / 'duplicados_exactos.csv'
    out_sim = out_dir / 'duplicados_similares.csv'
    return _detect(iter_rows_from_filelike(fileobj), out_exact, out_sim)
