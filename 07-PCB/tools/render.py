"""Render board top/bottom to PNG (for visual inspection). EDA frame, y flipped for image."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from PIL import Image, ImageDraw

SCALE = 4  # px per mm


def render(b, reps, path_top, path_bot):
    W, H = 300 * SCALE, 146 * SCALE
    def Y(ey): return (146 - ey) * SCALE

    for layer, path in (('F', path_top), ('B', path_bot)):
        img = Image.new('RGB', (W, H), (18, 20, 26))
        d = ImageDraw.Draw(img)
        # board outline
        d.rectangle([0, 0, W - 1, H - 1], outline=(90, 100, 120), width=2)
        # rep circles (top only)
        if layer == 'F':
            for (cx, cy, r) in reps:
                d.ellipse([(cx - r) * SCALE, (146 - cy - r) * SCALE,
                           (cx + r) * SCALE, (146 - cy + r) * SCALE],
                          outline=(90, 60, 20), width=1)
        # tracks (kpts 是 KiCad 帧 -> 转 EDA)
        for t in b.tracks:
            tl = 'F' if t.layer == 'F.Cu' else 'B'
            if tl != layer:
                continue
            kx1, ky1, kx2, ky2 = t.kpts()
            x1, y1, x2, y2 = kx1, 146 - ky1, kx2, 146 - ky2
            w = max(1, int(t.width * SCALE))
            color = (230, 120, 40) if tl == 'F' else (60, 160, 230)
            if t.net == '3V3':
                color = (240, 70, 70) if tl == 'F' else (200, 60, 60)
            d.line([x1 * SCALE, (146 - y1) * SCALE, x2 * SCALE, (146 - y2) * SCALE],
                   fill=color, width=w)
        # pads
        for c, p in b.pads_flat():
            onF = 'F.Cu' in ''.join(p['layers'])
            onB = 'B.Cu' in ''.join(p['layers'])
            if layer == 'F' and not onF:
                continue
            if layer == 'B' and not onB:
                continue
            w, h = p['w'], p['h']
            if p['rot'] % 180 == 90:
                w, h = h, w
            pey = 146 - p['y']
            x0, y0 = (p['x'] - w / 2) * SCALE, (146 - (pey + h / 2)) * SCALE
            x1, y1 = (p['x'] + w / 2) * SCALE, (146 - (pey - h / 2)) * SCALE
            color = (200, 200, 90) if p['net'] == 'GND' else (255, 220, 120)
            d.rectangle([x0, y0, x1, y1], fill=color)
        # vias
        for v in b.vias:
            x, y = v.x, v.y
            r = v.size / 2 * SCALE
            color = (255, 140, 200) if v.net == 'GND' else (150, 255, 150)
            d.ellipse([x * SCALE - r, (146 - y) * SCALE - r,
                       x * SCALE + r, (146 - y) * SCALE + r], fill=color)
        # silk texts
        for (tx, ty, text, size, slayer, eda) in b.texts:
            if not slayer.endswith('SilkS'):
                continue
            d.text((tx * SCALE, (146 - ty) * SCALE), text, fill=(220, 220, 220))
        # mounting holes
        for hx, hy, dia in b.holes:
            r = dia / 2 * SCALE
            d.ellipse([hx * SCALE - r, (146 - hy) * SCALE - r,
                       hx * SCALE + r, (146 - hy) * SCALE + r],
                      outline=(255, 255, 255), width=2)
        img.save(path)
        print('saved', path)


def render_from_design():
    import design
    b, keys, mux_of, out_vias, pullup_pos, reps = design.build()
    design.by_x = {k['id']: k['x'] for k in keys}
    design.route_bottom(b, keys, mux_of, out_vias, pullup_pos)
    outdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'output')
    os.makedirs(outdir, exist_ok=True)
    render(b, [(x, y, 2.5) for x, y in reps],
           os.path.join(outdir, 'preview_top.png'), os.path.join(outdir, 'preview_bot.png'))


if __name__ == '__main__':
    render_from_design()
