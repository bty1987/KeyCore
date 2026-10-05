"""Minimal KiCad s-expression parse/emit for .kicad_mod / .kicad_pcb / .kicad_sch."""
import re


def parse(text):
    """Parse s-expression text -> nested [token, ...] lists (strings for atoms)."""
    tokens = re.findall(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()]+', text)
    pos = 0

    def walk():
        nonlocal pos
        assert tokens[pos] == '(', f"expected ( at {pos}"
        pos += 1
        out = []
        while pos < len(tokens):
            t = tokens[pos]
            if t == '(':
                out.append(walk())
            elif t == ')':
                pos += 1
                return out
            else:
                if t.startswith('"'):
                    s = t[1:-1]
                    s = s.replace('\\"', '"').replace('\\n', '\n').replace('\\\\', '\\')
                    out.append(s)
                else:
                    out.append(t)
                pos += 1
        return out

    return walk()


def emit(node):
    """Emit nested lists back to KiCad s-expression text."""
    if isinstance(node, str):
        if node == '' or re.search(r'[\s"()]', node) or node and node[0].isdigit() and False:
            pass
        # quote if it contains whitespace/parens/quotes or is empty or looks like it must stay a string
        if node == '' or re.search(r'[\s()]', node) or '"' in node:
            return '"' + node.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'
        return node
    if isinstance(node, (int, float)):
        s = f"{node:.6f}" if isinstance(node, float) else str(node)
        return s
    inner = ' '.join(emit(x) for x in node)
    return f'({inner})'


def find(node, key):
    """First child list whose head == key."""
    for c in node:
        if isinstance(c, list) and c and c[0] == key:
            return c
    return None


def find_all(node, key):
    return [c for c in node if isinstance(c, list) and c and c[0] == key]


def pad_at(pad):
    """(x, y, rot) of a pad sexpr, defaults 0."""
    at = find(pad, 'at')
    if not at:
        return 0.0, 0.0, 0.0
    x = float(at[1])
    y = float(at[2]) if len(at) > 2 else 0.0
    r = float(at[3]) if len(at) > 3 else 0.0
    return x, y, r


def pad_size(pad):
    sz = find(pad, 'size')
    return float(sz[1]), float(sz[2])


def pad_shape(pad):
    sh = find(pad, 'shape')
    if sh:
        return sh[1]
    return pad[3]  # KiCad5: (pad <num> <type> <shape> ...)


def pad_layers(pad):
    return [str(x) for x in find(pad, 'layers')[1:]]


def set_net(pad, net_num, net_name):
    n = find(pad, 'net')
    if n:
        n[1] = str(net_num)
        n[2] = net_name
    else:
        # insert before (tstamp)/(uuid) or append
        pad.append(['net', str(net_num), net_name])
