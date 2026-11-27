# Lectura de fichas de FutbolFantasy (modo Biwenger Picas). La usa el robot de puntos en directo.
import re
from bs4 import BeautifulSoup

def _num(row, c):
    e = row.select_one('.stat-' + c)
    try: return int(float(e.get_text(strip=True))) if e else 0
    except ValueError: return 0

def fila_jornada(html, J):
    """Datos del jugador en la jornada J, o None si aún no hay fila (no ha jugado su equipo)."""
    soup = BeautifulSoup(html, 'lxml')
    row = None
    for r in soup.select('table.tablestats tr.plegable'):
        jt = r.select_one('.jorn-td')
        if jt and jt.get_text(strip=True) == str(J): row = r; break
    if row is None: return None
    sc = row.select_one('strong.score'); score = sc.get_text(strip=True) if sc else ''
    local = row.get('data-local') == '1'
    try: a, b = [int(x) for x in score.split('-')]
    except ValueError: a = b = None
    gf, ge = (a, b) if local else (b, a)
    cls = (sc.get('class') or []) if sc else []
    if 'won' in cls: res = 'G'
    elif 'lost' in cls: res = 'P'
    elif 'draw' in cls or 'tied' in cls: res = 'E'
    elif gf is None: res = None
    else: res = 'G' if gf > ge else 'P' if gf < ge else 'E'
    des = row.find_next_sibling('tr')
    t = re.sub(r'\s+', ' ', des.get_text(' ')) if des is not None and 'desglose' in (des.get('class') or []) else ''
    mm = re.search(r'(\d+)\s*Minutos jugados', t); enc = re.search(r'Goles encajados \((\d+)\)', t)
    td = row.select_one('td.picas'); n = len(td.select('img.pica')) if td else 0
    tp = td.get_text(strip=True) if td else ''
    goles, gp = _num(row, 'goles'), _num(row, 'goles-penalti')
    return {'min': int(mm.group(1)) if mm else 0, 'g': max(0, goles - gp), 'gp': gp, 'pf': _num(row, 'penaltis-fallados'),
            'a': _num(row, 'asistencias'), 'tr': _num(row, 'tarjeta-roja'), 'res': res, 'ge': ge if ge is not None else 0,
            'gec': int(enc.group(1)) if enc else 0, 'picas': n if n else (tp or '-'), 'score': score}

def buscar_slug(html_equipo, nombre):
    """En la página de un equipo, el slug de la ficha del jugador con ese nombre (o None)."""
    soup = BeautifulSoup(html_equipo, 'lxml'); textos = {}
    for a in soup.select('a[href*="/jugadores/"]'):
        m = re.search(r'/jugadores/([^/"?#]+)', a['href'])
        if m: textos.setdefault(m.group(1), set()).add(norm(a.get_text(' ', strip=True)))
    n = norm(nombre); toks = n.split()
    for slug, ts in textos.items():
        if n in ts: return slug
    for slug, ts in textos.items():
        if any(t and len(t) < 40 and all(x in t.split() for x in toks) for t in ts): return slug
    return None

def norm(s):
    import unicodedata
    return re.sub(r'[^a-z0-9]+', ' ', unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower()).strip()
