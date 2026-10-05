"""计划驱动写回: 按 fix_plan.json 精确修改 KeyCore-v43b.epru 记录, 重打包 .epro2.
操作类型:
  via_moves: VIA centerX/centerY 改坐标
  weave[*] (无 kind): 原线段 → pts[0]-pts[1], 其余 pts 段作为新 LINE 记录插在本记录后
  weave[*] kind=reconnect: 新增垂直短段记录
  end_moves kind=endpoint: 原线段一端改坐标
  end_moves kind=reroute_sw1: 原线段 → pts[0]-pts[1], 其余插入
"""
import json, math, zipfile, os

SRC_EPRU = '/tmp/eprj_probe/KeyCore-v43b.epru'
SRC_EPRO2 = '/tmp/eprj_probe/KeyCore-v43b_2026-10-04-16-30.epro2'
PLAN = json.load(open('/tmp/eprj_probe/fix_plan.json'))
U2M = 1 / 0.0254
PCB_UUID = '52caa9452ee66dee'

def m2mil(v):
    return round(v * U2M, 4)

def near(a, b, tol=0.1):
    return abs(a - b) < tol

raw = open(SRC_EPRU, encoding='utf-8').read()
segs = raw.split('|')

def is_hdr(s):
    return s.strip().startswith('{"type"')

max_ticket = 0
for s in segs:
    if is_hdr(s):
        try:
            max_ticket = max(max_ticket, json.loads(s).get('ticket', 0))
        except Exception:
            pass
ticket = max_ticket + 1000

via_moves = PLAN['via_moves']
weaves = [w for w in PLAN['weave'] if not w.get('kind')]
reconns = [w for w in PLAN['weave'] if w.get('kind') == 'reconnect']
ends = PLAN['end_moves']

n_via = n_mod = n_new = 0
used_via = set()
used_weave = set()
used_end = set()
out = []
i = 0
in_pcb = False
while i < len(segs):
    s = segs[i]
    if not is_hdr(s):
        out.append(s)
        i += 1
        continue
    h = json.loads(s)
    # payload 定位
    j = i + 1
    payload = None
    pay_idx = None
    while j < len(segs):
        t2 = segs[j].strip()
        if not t2:
            j += 1
            continue
        if not t2.startswith('{"type"'):
            try:
                payload = json.loads(t2)
                pay_idx = j
            except Exception:
                payload = None
            break
        break
    if h.get('type') == 'DOCHEAD' and payload is not None:
        in_pcb = payload.get('uuid') == PCB_UUID

    mod = False
    insert_after = []

    if in_pcb and h.get('type') == 'VIA' and payload is not None:
        for mv in via_moves:
            key = (mv['net'], round(mv['old'][0], 2), round(mv['old'][1], 2))
            if key in used_via:
                continue
            if (mv['net'] == payload.get('netName') and
                    near(payload['centerX'], m2mil(mv['old'][0]), 0.1) and
                    near(payload['centerY'], m2mil(mv['old'][1]), 0.1)):
                payload['centerX'] = m2mil(mv['new'][0])
                payload['centerY'] = m2mil(mv['new'][1])
                used_via.add(key)
                n_via += 1
                mod = True
                break

    if in_pcb and h.get('type') == 'LINE' and payload is not None:
        ps = (payload['startX'], payload['startY'])
        pe = (payload['endX'], payload['endY'])
        # weave
        for wv in weaves:
            key = (wv['net'], tuple(wv['orig']))
            if key in used_weave:
                continue
            if wv['net'] != payload.get('netName'):
                continue
            o = [m2mil(v) for v in wv['orig']]
            if not ((near(ps[0], o[0]) and near(ps[1], o[1]) and near(pe[0], o[2]) and near(pe[1], o[3])) or
                    (near(ps[0], o[2]) and near(ps[1], o[3]) and near(pe[0], o[0]) and near(pe[1], o[1]))):
                continue
            pts = wv['pts']
            payload['startX'] = m2mil(pts[0][0])
            payload['startY'] = m2mil(pts[0][1])
            payload['endX'] = m2mil(pts[1][0])
            payload['endY'] = m2mil(pts[1][1])
            for k in range(1, len(pts) - 1):
                ticket += 1
                hdr2 = json.dumps(dict(type='LINE', ticket=ticket, id=f'zfix{ticket}'))
                pay2 = json.dumps(dict(layerId=wv['layer'], groupId='', locked=False, zIndex=ticket,
                                       partitionId=None, netName=wv['net'],
                                       startX=m2mil(pts[k][0]), startY=m2mil(pts[k][1]),
                                       endX=m2mil(pts[k+1][0]), endY=m2mil(pts[k+1][1]),
                                       width=m2mil(wv['w'])))
                insert_after.append((hdr2, pay2))
                n_new += 1
            used_weave.add(key)
            n_mod += 1
            mod = True
            break
        # end_moves (endpoint / reroute)
        if not mod:
            for ed in ends:
                key = (ed['net'], tuple(ed['orig']))
                if key in used_end:
                    continue
                if ed['net'] != payload.get('netName'):
                    continue
                o = [m2mil(v) for v in ed['orig']]
                fwd = near(ps[0], o[0]) and near(ps[1], o[1]) and near(pe[0], o[2]) and near(pe[1], o[3])
                rev = near(ps[0], o[2]) and near(ps[1], o[3]) and near(pe[0], o[0]) and near(pe[1], o[1])
                if not (fwd or rev):
                    continue
                if ed.get('kind') == 'reroute_sw1':
                    pts = ed['pts']
                    payload['startX'] = m2mil(pts[0][0])
                    payload['startY'] = m2mil(pts[0][1])
                    payload['endX'] = m2mil(pts[1][0])
                    payload['endY'] = m2mil(pts[1][1])
                    for k in range(1, len(pts) - 1):
                        ticket += 1
                        hdr2 = json.dumps(dict(type='LINE', ticket=ticket, id=f'zfix{ticket}'))
                        pay2 = json.dumps(dict(layerId=ed['layer'], groupId='', locked=False, zIndex=ticket,
                                               partitionId=None, netName=ed['net'],
                                               startX=m2mil(pts[k][0]), startY=m2mil(pts[k][1]),
                                               endX=m2mil(pts[k+1][0]), endY=m2mil(pts[k+1][1]),
                                               width=m2mil(ed['w'])))
                        insert_after.append((hdr2, pay2))
                        n_new += 1
                else:  # endpoint
                    new = (m2mil(ed['new'][0]), m2mil(ed['new'][1]))
                    dfwd = math.hypot(ps[0]-new[0], ps[1]-new[1])
                    drev = math.hypot(pe[0]-new[0], pe[1]-new[1])
                    if dfwd <= drev:
                        payload['startX'], payload['startY'] = new
                    else:
                        payload['endX'], payload['endY'] = new
                used_end.add(key)
                n_mod += 1
                mod = True
                break

    # 输出本记录
    out.append(s)
    j2 = i + 1
    while j2 < len(segs):
        t2 = segs[j2]
        if t2.strip() and not is_hdr(t2):
            out.append(json.dumps(payload, ensure_ascii=False) if (mod and payload is not None and pay_idx == j2) else t2)
            break
        out.append(t2)
        j2 += 1
    # 插入新记录 (仅 PCB 文档内)
    if in_pcb:
        for (hdr2, pay2) in insert_after:
            out += [hdr2, '', pay2]
        if h.get('type') == 'LINE' and reconns:
            for rc in reconns:
                ticket += 1
                hdr2 = json.dumps(dict(type='LINE', ticket=ticket, id=f'zfix{ticket}'))
                pay2 = json.dumps(dict(layerId=rc['layer'], groupId='', locked=False, zIndex=ticket,
                                       partitionId=None, netName=rc['net'],
                                       startX=m2mil(rc['at'][0]), startY=m2mil(rc['at'][1]),
                                       endX=m2mil(rc['at'][0]), endY=m2mil(rc['to_go']),
                                       width=m2mil(rc['w'])))
                out += [hdr2, '', pay2]
                n_new += 1
            reconns = []
    i = j2 + 1

print(f"写回: via {n_via}/6, line 改 {n_mod}/5, line 增 {n_new}")
new_raw = '|'.join(out)
open('/tmp/eprj_probe/KeyCore-v43b-fix.epru', 'w', encoding='utf-8').write(new_raw)

dst = '/tmp/eprj_probe/KeyCore-v43b-fixed.epro2'
with zipfile.ZipFile(SRC_EPRO2) as zin, zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as zout:
    for item in zin.infolist():
        data = zin.read(item.filename)
        if item.filename.endswith('.epru'):
            data = new_raw.encode('utf-8')
        zout.writestr(item, data)
print("epro2:", dst, os.path.getsize(dst), "bytes")
