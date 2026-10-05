"""KeyCore-v43b.epru (立创EDA Pro 文档 JSON, mil) → geometry.json
抽出 PCB 文档的全部铜皮: tracks/vias/pads/placement, 单位 mm, EDA 帧与 epru 相同(y 负值).
坐标系标定与 07-PCB/output/KeyCore.kicad_pcb 的封装位置比对.
"""
import json, re, math, sys

EPRU = '/tmp/eprj_probe/KeyCore-v43b.epru'
U = 0.0254  # mil → mm

def load_records():
    raw = open(EPRU, encoding='utf-8').read()
    segs = raw.split('|')
    recs = []  # (header_dict, payload_dict_or_None)
    i = 0
    n = len(segs)
    while i < n:
        s = segs[i].strip()
        if s.startswith('{"type"'):
            h = json.loads(s)
            # payload: 跳过空段, 下一段若以 {"type" 开头则无 payload
            j = i + 1
            payload = None
            while j < n:
                t = segs[j].strip()
                if not t:
                    j += 1
                    continue
                if t.startswith('{"type"'):
                    break
                try:
                    payload = json.loads(t)
                except Exception:
                    payload = None
                break
            recs.append((h, payload))
            i = j
        else:
            i += 1
    return recs

def segment_docs(recs):
    """按 DOCHEAD 切文档: [(docType, uuid, [records])]"""
    docs = []
    cur_type, cur_uuid, cur = None, None, []
    for h, p in recs:
        if h.get('type') == 'DOCHEAD':
            if cur_type:
                docs.append((cur_type, cur_uuid, cur))
            cur_type = (p or {}).get('docType')
            cur_uuid = (p or {}).get('uuid')
            cur = []
        else:
            cur.append((h, p))
    if cur_type:
        docs.append((cur_type, cur_uuid, cur))
    return docs

def main():
    recs = load_records()
    docs = segment_docs(recs)
    pcbs = [(u, rs) for t, u, rs in docs if t == 'PCB']
    fps = {u: rs for t, u, rs in docs if t == 'FOOTPRINT'}
    print(f"docs: {len(docs)}, PCB docs: {[u for u,_ in pcbs]}, footprints: {len(fps)}")
    # 取 updateTime 新的 PCB
    pcb_uuid, pcb_recs = None, None
    best = -1
    for t, u, rs in docs:
        if t != 'PCB':
            continue
        for h, p in rs:
            if h.get('type') == 'META' and p and 'updateTime' in json.dumps(p):
                pass
    # DOCHEAD payload 里有 version, 回头从 load_records 拿 —— 简化: project_structures 说 52caa9452ee66dee 最新
    pcb_uuid = '52caa9452ee66dee'
    pcb_recs = dict((u, rs) for t, u, rs in docs if t == 'PCB')[pcb_uuid]

    L = lambda h, p, ty: h.get('type') == ty and p is not None

    # 层映射
    layers = {}
    for h, p in pcb_recs:
        if L(h, p, 'LAYER'):
            m = re.match(r'\["LAYER",(\d+)\]', h.get('id', ''))
            if m:
                layers[int(m.group(1))] = p.get('layerName')
    print("layers:", layers)

    tracks, vias, pours, comps = [], [], [], []
    padnets = {}  # (comp_id, pad_id) -> net
    for h, p in pcb_recs:
        t = h.get('type')
        if t == 'LINE' and p.get('layerName') is None:
            lid = p.get('layerId')
            if lid in (1, 2, 15, 16):  # 铜层
                tracks.append(dict(layer=lid, net=p.get('netName', ''),
                    x1=p['startX']*U, y1=p['startY']*U,
                    x2=p['endX']*U, y2=p['endY']*U, w=p['width']*U))
        elif t == 'VIA':
            vias.append(dict(x=p['centerX']*U, y=p['centerY']*U,
                dia=p['viaDiameter']*U, drill=p['holeDiameter']*U,
                net=p.get('netName', ''), id=h.get('id')))
        elif t == 'POUR':
            path = p['path'][0]
            pts = [(path[i]*U, path[i+1]*U) for i in range(0, len(path)-2, 4)]
            pours.append(dict(layer=p['layerId'], net=p.get('netName', ''), pts=pts))
        elif t == 'COMPONENT':
            comps.append(dict(id=h.get('id'), x=p['x']*U, y=p['y']*U,
                angle=p.get('angle', 0), layer=p.get('layerId')))
        elif t == 'PAD_NET':
            m = re.match(r'\["PAD_NET","([^"]+)","([^"]*)","([^"]+)"\]', h.get('id', ''))
            if m:
                padnets[(m.group(1), m.group(3))] = p.get('padNet', '')
    # ATTR: 设计ator + 封装链接
    for h, p in pcb_recs:
        if L(h, p, 'ATTR') and p.get('parentId'):
            for c in comps:
                if c['id'] == p['parentId']:
                    if p.get('key') == 'Designator':
                        c['ref'] = p.get('value')
                    elif p.get('key') == 'FootprintName':
                        c['fp'] = p.get('value')

    # 封装焊盘 (footprint 帧, mil)
    fp_pads = {}
    for fu, rs in fps.items():
        pads = []
        for h, p in rs:
            if L(h, p, 'PAD'):
                hole = p.get('hole') or {}
                dp = p.get('defaultPad') or {}
                hd = max(hole.get('width', 0), hole.get('height', 0))*U
                ht = hole.get('holeType')
                thru = bool(ht and ht != 'NONE' and hd > 0.05)
                pads.append(dict(id=h.get('id'), num=p.get('num'),
                    x=p['centerX']*U, y=p['centerY']*U,
                    w=dp.get('width', 0)*U, h=dp.get('height', 0)*U,
                    shape=dp.get('padType', 'RECT'),
                    angle=(p.get('padAngle') or 0),   # relativeAngle 是编辑器记账值, 不参与几何
                    hole_t=(ht if thru else None), hole_d=hd))
        fp_pads[fu] = pads

    # 组装实例化焊盘
    all_pads = []
    for c in comps:
        for pd in fp_pads.get(c.get('fp', ''), []):
            net = padnets.get((c['id'], pd['id']), '')
            a = math.radians(c['angle'])
            px, py = pd['x'], pd['y']
            rx = px*math.cos(a) - py*math.sin(a) + c['x']
            ry = px*math.sin(a) + py*math.cos(a) + c['y']
            all_pads.append(dict(ref=c.get('ref'), num=pd['num'], net=net,
                x=round(rx, 4), y=round(ry, 4), w=pd['w'], h=pd['h'],
                shape=pd['shape'], angle=(pd['angle'] + c['angle']) % 360,
                hole_t=pd['hole_t'], hole_d=pd['hole_d'], layer=c['layer']))

    out = dict(tracks=tracks, vias=vias, pours=pours, pads=all_pads,
               comps=[dict(ref=c.get('ref'), x=c['x'], y=c['y'], angle=c['angle']) for c in comps if c.get('ref')])
    json.dump(out, open('/tmp/eprj_probe/geometry.json', 'w'))
    print(f"tracks={len(tracks)} vias={len(vias)} pads={len(all_pads)} pours={len(pours)} comps={len(comps)}")
    # 网络统计
    from collections import Counter
    tn = Counter(t['net'] for t in tracks)
    print("top track nets:", tn.most_common(8))
    print("track layers:", Counter(t['layer'] for t in tracks))
    print("via diams:", Counter(round(v['dia'], 3) for v in vias))

if __name__ == '__main__':
    main()
