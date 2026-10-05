#!/usr/bin/env python3
"""迭代布线补线器：在 design.py 完成首轮布线后，对失败网做多轮重试。
结构不变：不加层、不动器件坐标，只在 B.Cu 加线/过孔 + 拆线重布。
用法：venv/bin/python tools/iter_fix.py
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
import design
from design import (build, route_bottom, MOUNT_HOLES, GROUPS, MUX_XS, MUX_Y,
                    STUB_S, RAILS, LANE_3V3, P, MUX_PIN, modp)
from board import Track
from router import BottomRouter
from checks import Checker


def main():
    b, keys, mux_of, out_vias, pullup_pos, reps = build()
    design.by_x = {k['id']: k['x'] for k in keys}   # route_bottom 依赖的模块级全局
    fails, rt = route_bottom(b, keys, mux_of, out_vias, pullup_pos)
    fails = sorted(set(fails))
    print(f'首轮未通: {len(fails)}')

    # ---- 迭代补线：对失败网重试，难度递增（放宽逃生轴/更小净距）----
    # 找到失败网的起终点：从 route_bottom 的作业重建
    # (与 design.route_bottom 相同的作业表)
    kx = {k['id']: k['x'] for k in keys}

    def mux_via(gi, sig):
        ref, mx = mux_of[gi]
        num, dx, dy = MUX_PIN[sig]
        if dy < 0:
            return (mx + dx, MUX_Y + dy)
        return (mx + dx, STUB_S)

    jobs = {}
    for gi, ids in enumerate(GROUPS):
        gk = sorted(ids, key=lambda i: kx[i])
        for ci, kid in enumerate(gk):
            jobs[f'HO_{kid}'] = (out_vias[kid], mux_via(gi, f'X{ci}'), f'HO_{kid}', 0.25)
    for gi in range(9):
        gx, gy = P[design.E_GPIO[gi + 1]]
        px, py = pullup_pos[gi + 1]
        jobs[f'EN_{gi+1}'] = (mux_via(gi, 'E'), (px, py - 0.95), f'EN_{gi+1}', 0.25)
    for sig, g in (('A', 5), ('B', 6), ('C', 7)):
        gx, gy = P[g]
        for gi in range(9):
            jobs[f'MUX_{sig}-{gi}'] = ((gx, gy), mux_via(gi, sig), f'MUX_{sig}', 0.3)
    anchor = (110, LANE_3V3)
    for gi in range(9):
        jobs[f'VDD-{gi}'] = (anchor, mux_via(gi, 'VDD'), '3V3', 0.4)
    rz1, rz2 = (43.7, 3.4), (46.3, 3.4)
    for gi in range(9):
        jobs[f'Z_COM-{gi}'] = (mux_via(gi, 'Z'), rz1, 'Z_COM', 0.3)
    jobs['Z_F-gpio'] = (P[4], rz2, 'Z_F', 0.3)
    jobs['Z_F-cap'] = ((53.5, 3.55), rz2, 'Z_F', 0.3)
    mp_dn, mp_dp = modp(13), modp(14)
    for pads, mp, pref in ((('A6','B6'), mp_dp, 'USB_DP'), (('A7','B7'), mp_dn, 'USB_DN')):
        for pd in pads:
            vx, vy = b._usb_vias[pd]
            jobs[f'{pref}-{pd}'] = ((vx, vy), mp, b.pad('J1', pd)['net'], 0.3)
    vt = (71.85, 9.2)
    for pd in ('A4','B4','A9','B9'):
        vx, vy = b._usb_vias[pd]
        jobs[f'VBUS-{pd}'] = ((vx, vy), vt, 'VBUS', 0.4)
    jobs['CC1'] = (b._usb_vias['A5'], (16.5875, 14.75), 'CC1', 0.3)
    jobs['CC2'] = (b._usb_vias['B5'], (16.5875, 17.75), 'CC2', 0.3)
    misc = [
        (P[2], (95, 28.212), 'LED', 0.3), ((30, 10.4), (110, LANE_3V3), '3V3', 0.4),
        ((24, 6.95), (110, LANE_3V3), '3V3', 0.3), ((69, 15.55), (110, LANE_3V3), '3V3', 0.4),
        ((72, 15.55), (110, LANE_3V3), '3V3', 0.4),
    ]
    j2dq = b.pad('J2', '2')
    misc.append((P[21], (j2dq['x'], 146 - j2dq['y']), 'ONE_WIRE', 0.3))
    for g, pad, net in ((17, '1', 'U1TX'), (18, '2', 'U1RX')):
        jp = b.pad('J3', pad)
        misc.append((P[g], (jp['x'], 146 - jp['y']), net, 0.3))
    for i, (a, c, net, w) in enumerate(misc):
        jobs[f'MISC{i}'] = (a, c, net, w)

    def emit(pts, net, width=0.25):
        from board import Track
        for a, c in zip(pts, pts[1:]):
            b.tracks.append(Track(a[0], a[1], c[0], c[1], width, 'B.Cu', net, eda_frame=True))
        rt.mark_routed(pts, width)
        rt.remember(net, pts, width)

    jobs_saved = dict(jobs)
    jobs_saved = dict(jobs)
    # 网络名回退索引：fails 里存的可能是裸网络名（如 '3V3'）
    net_jobs = {}
    for nm, jb in jobs.items():
        net_jobs.setdefault(jb[2], []).append(nm)

    def try_job(name, rip_depth=0):
        """布一条；被挡时拆线重布，任何情况下被拆网都会被恢复。"""
        job = jobs.get(name) or (jobs[net_jobs[name][0]] if name in net_jobs else None)
        if job is None:
            return False
        a, c, net, w = job
        pts = rt.route(a, c, esc_s=(1, 0), esc_g=(1, 0))
        if pts is not None and not rt.violation(net, pts, w):
            emit(pts, net, w)
            return True
        # 拆线重布
        relaxed = rt.route_relaxed(a, c, esc_s=(1, 0), esc_g=(1, 0))
        if relaxed is None:
            return False
        bl = rt.blockers(net, relaxed, w)
        nets = sorted({x for x in bl if not isinstance(x, tuple)})
        if not nets or len(nets) > 3 or rip_depth > 0:
            return False
        ripped = [n2 for n2 in nets if n2 != net]
        for bn in ripped:
            rt.remove_route(bn)
        ok = False
        pts2 = rt.route(a, c, esc_s=(1, 0), esc_g=(1, 0))
        if pts2 is not None and not rt.violation(net, pts2, w):
            emit(pts2, net, w)
            ok = True
        # 无论自己成败，先恢复被拆网（保持板面完整性）
        for bn in ripped:
            jb2 = jobs.get(bn) or (jobs[net_jobs[bn][0]] if bn in net_jobs else None)
            if jb2 is None:
                fails.append(bn)
                continue
            rp = rt.route(*jb2[:2], esc_s=(1, 0), esc_g=(1, 0))
            if rp is not None and not rt.violation(jb2[2], rp, jb2[3]):
                emit(rp, jb2[2], jb2[3])
            else:
                fails.append(bn)   # 恢复失败必须记账，否则静默丟网
        return ok

    history = [len(fails)]
    for rnd in range(1, 9):
        if not fails:
            break
        retry, fails = fails, []
        retry = retry[::-1] if rnd <= 4 else sorted(
            retry, key=lambda n: (lambda jb: abs(jb[0][0]-jb[1][0])+abs(jb[0][1]-jb[1][1]))(jobs.get(n) or jobs[net_jobs[n][0]]) if n in net_jobs or n in jobs else 0)
        print(f'迭代轮 {rnd}: 待补 {len(retry)} 网（历史 {history}）', flush=True)
        for name in retry:
            if not try_job(name):
                fails.append(name)
        history.append(len(fails))
        if rnd >= 4 and history[-1] == history[-2] == history[-3] == history[-4]:
            print('收敛停滞，提前结束', flush=True); break

    print(f'最终未通: {len(fails)} {sorted(fails)[:10]}')

    # ---- 全量校验 ----
    ck = Checker(b, [])  # PCB 无磁铁位，rep 约束移除
    ck._holes = [(x, y, 2.7) for x, y in MOUNT_HOLES]
    ck.add_all()
    ck.check_edge(); ck.check_rep(); n0 = len(ck.issues)
    ck.check_holes(); n_h = len(ck.issues)
    ck.check_clearance(); n1 = len(ck.issues)
    conn = ck.check_connectivity(skip_nets=('GND', '3V3', 'VBUS'))
    print(f'自检: edge/rep {n0}, hole {n_h-n0}, clearance {n1-n_h}')
    for it in ck.issues[:12]: print('  !', it)
    print(f'连通失败网: {len(conn)}')
    for net, groups, sizes in conn[:10]: print(f'  ! {net}: {groups} 岛 {sizes}')

    # ---- 发射 ----
    outdir = os.path.join(os.path.dirname(__file__), '..', 'output')
    b.emit_kicad_pcb(os.path.join(outdir, 'KeyCore.kicad_pcb'))
    with open(os.path.join(outdir, 'route_report.json'), 'w') as f:
        json.dump({'fails': sorted(set(fails)), 'issues': ck.issues,
                   'islands': [{'net': n, 'groups': g, 'sizes': s} for n, g, s in conn],
                   'history': history}, f, ensure_ascii=False, indent=1)
    from render import render
    render(b, [(x, y, 2.2) for x, y in reps], os.path.join(outdir, 'preview_top.png'),
           os.path.join(outdir, 'preview_bot.png'))
    print('已发射 kicad_pcb + report + preview')


if __name__ == '__main__':
    main()
