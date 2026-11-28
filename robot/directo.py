# Robot de puntos en directo: lee en FutbolFantasy los datos de la jornada en juego de los jugadores
# que tienen los equipos de la liga y los deja en directo.json (la web lo lee cada pocos minutos).
import json, os, re, sys, time, datetime, pathlib, urllib.request, urllib.error
from zoneinfo import ZoneInfo
import ff

AQUI = pathlib.Path(__file__).parent
RAIZ = AQUI.parent
FF = 'https://www.futbolfantasy.com'
FS = 'https://firestore.googleapis.com/v1/projects/liga-inmortales/databases/(default)/documents/'
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36'
MADRID = ZoneInfo('Europe/Madrid')

def get(url, intentos=3):
    for i in range(intentos):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': UA}), timeout=40) as r:
                return r.read().decode('utf-8', 'replace')
        except urllib.error.HTTPError as e:
            if e.code == 404: return None
            time.sleep(3 * (i + 1))
        except Exception:
            time.sleep(3 * (i + 1))
    return None

def valor(x):
    k, v = next(iter(x.items()))
    if k == 'mapValue': return {a: valor(b) for a, b in v.get('fields', {}).items()}
    if k == 'arrayValue': return [valor(b) for b in v.get('values', [])]
    if k == 'integerValue': return int(v)
    if k == 'doubleValue': return float(v)
    if k == 'nullValue': return None
    return v

def firestore(ruta):
    t = get(FS + ruta)
    if not t: return None
    d = json.loads(t)
    if 'documents' in d: return [{a: valor(b) for a, b in doc.get('fields', {}).items()} for doc in d['documents']]
    if 'fields' in d: return {a: valor(b) for a, b in d['fields'].items()}
    return None

def fecha_partido(f):
    m = re.search(r'(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})', f or '')
    if not m: return None
    dd, mm, hh, mi = map(int, m.groups())
    return datetime.datetime(2026 if mm >= 7 else 2027, mm, dd, hh, mi, tzinfo=MADRID)

def main():
    liga = json.loads((AQUI / 'liga.json').read_text())
    forzar = os.environ.get('FORZAR') == '1'
    ajustes = firestore('liga/ajustes') or {}
    ahora = datetime.datetime.now(MADRID)
    J = int(ajustes.get('jornadaAbierta') or liga['jornadaAbierta'])
    # Si ya ha empezado una jornada posterior a la abierta (según el calendario), esa es la que está en juego.
    empezadas = [m['j'] for m in liga['calendario'] if (fecha_partido(m['f']) or ahora + datetime.timedelta(days=1)) <= ahora]
    if empezadas: J = max(J, max(empezadas))
    if os.environ.get('JORNADA'): J = int(os.environ['JORNADA'])
    partidos = [m for m in liga['calendario'] if m['j'] == J]
    inicio = {}
    for m in partidos:
        fp = fecha_partido(m['f'])
        for c in (m['l'], m['v']): inicio[c] = fp
    # Sin partidos de la jornada empezados en las últimas 40 horas, no hay nada nuevo que leer.
    if not forzar and partidos and not any(fp and ahora - datetime.timedelta(hours=40) <= fp <= ahora for fp in inicio.values()):
        print(f'Jornada {J}: ningún partido reciente. Nada que hacer.'); return
    # Jugadores de los equipos en la jornada J (plantillas + fichajes guardados en la web).
    movs = firestore('movimientos?pageSize=300') or []
    movs = liga['movimientos'] + movs
    movs.sort(key=lambda m: (int(m.get('desdeJornada') or 0), m.get('creado') or ''))
    tienen = set()
    for eid, pl in liga['plantillas'].items():
        pl = list(pl)
        for m in movs:
            if m.get('equipo') != eid or int(m.get('desdeJornada') or 0) > J: continue
            if m.get('sale') in pl: pl.remove(m['sale'])
            if m.get('entra') and m['entra'] not in pl: pl.append(m['entra'])
        tienen.update(pl)
    slugs_f = AQUI / 'slugs.json'
    slugs = {**liga['slugs'], **(json.loads(slugs_f.read_text()) if slugs_f.exists() else {})}
    salida_f = RAIZ / 'directo.json'
    previo = json.loads(salida_f.read_text()) if salida_f.exists() else {}
    stats = dict(previo.get('stats', {})) if previo.get('jornada') == J else {}
    sin_fila, errores, paginas_equipo = [], [], {}
    for jid in sorted(tienen):
        j = liga['jugadores'].get(jid)
        if not j: continue
        nombre, club = j
        fp = inicio.get(club)
        if fp and fp > ahora: stats.pop(jid, None); continue   # su partido aún no ha empezado: no hay datos válidos
        slug = slugs.get(jid) or jid.split('.')[0]
        html = get(f'{FF}/jugadores/{slug}/laliga-26-27')
        if html is None or 'tablestats' not in html:
            ce = liga['clubSlug'].get(club)
            if ce and ce not in paginas_equipo: paginas_equipo[ce] = get(f'{FF}/laliga/equipos/{ce}') or ''
            nuevo = ff.buscar_slug(paginas_equipo.get(ce, ''), nombre) if ce else None
            if nuevo and nuevo != slug:
                slug = slugs[jid] = nuevo; html = get(f'{FF}/jugadores/{slug}/laliga-26-27')
        if not html: errores.append(jid); continue
        fila = ff.fila_jornada(html, J)
        if fila is None: sin_fila.append(jid)
        else: stats[jid] = fila
        time.sleep(0.8)
    nuevos = {k: v for k, v in slugs.items() if liga['slugs'].get(k) != v}
    if nuevos: slugs_f.write_text(json.dumps(nuevos, ensure_ascii=False, indent=0, sort_keys=True))
    if previo.get('jornada') == J and previo.get('stats') == stats:
        print(f'Jornada {J}: sin cambios ({len(stats)} jugadores con datos).'); return
    salida = {'jornada': J, 'actualizado': ahora.isoformat(timespec='minutes'), 'fuente': 'FutbolFantasy (Biwenger Picas)',
              'stats': stats, 'sinDatos': sorted(sin_fila), 'errores': sorted(errores)}
    salida_f.write_text(json.dumps(salida, ensure_ascii=False, separators=(',', ':')))
    print(f'Jornada {J}: {len(stats)} con datos, {len(sin_fila)} sin datos aún, {len(errores)} errores: {errores[:10]}')

if __name__ == '__main__':
    main()
