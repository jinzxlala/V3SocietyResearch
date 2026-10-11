import collections, re

def num(s):
    s = s.replace(',', '')
    return int(s) if re.fullmatch(r'\d+', s) else None

def rows_of(page, name_x_max, y_min, y_max=10 ** 9):
    """Group page words into visual lines; split into sport label (left) and numbers (right)."""
    ws = [w for w in page.extract_words() if y_min <= w['top'] <= y_max]
    lines, cur, start = [], [], None
    for w in sorted(ws, key=lambda w: w['top']):
        if start is None or w['top'] - start <= 4:
            start = w['top'] if start is None else start
            cur.append(w)
        else:
            lines.append(cur); cur = [w]; start = w['top']
    if cur: lines.append(cur)
    out = []
    for line in lines:
        line = sorted(line, key=lambda w: w['x0'])
        lab = [w for w in line if w['x1'] <= name_x_max]
        sport = " ".join(w['text'] for w in lab).strip()
        sport_x0 = lab[0]['x0'] if lab else None
        nums = []
        for w in line:
            if w['x0'] >= name_x_max:
                v = num(w['text'])
                if v is not None:
                    nums.append((v, w['x1']))
        out.append({'top': line[0]['top'], 'sport': sport, 'sport_x0': sport_x0, 'nums': nums})
    return out

def centers_from(rowset, tol=13):
    vals = sorted(x for r in rowset for _, x in r['nums'])
    groups, cur = [], [vals[0]]
    for v in vals[1:]:
        if v - cur[-1] <= tol:
            cur.append(v)
        else:
            groups.append(cur); cur = [v]
    groups.append(cur)
    return [sum(g) / len(g) for g in groups]

def assign(row, centers):
    slots = [None] * len(centers)
    for v, x in row['nums']:
        i = min(range(len(centers)), key=lambda k: abs(centers[k] - x))
        if slots[i] is not None:
            return None
        slots[i] = v
    return slots
