import sys, re, csv, json, collections
sys.path.insert(0, '/tmp/doping')
import pdfplumber

def num(s):
    s = s.replace(',', '')
    return int(s) if re.fullmatch(r'\d+', s) else None

HEADER_HINTS = ('Type of', 'Samples Collected', 'Tests conducted', 'Sport/Discipline',
                'Sport Discipline', 'Sport \u2013 Discipline', 'Number of Athletes',
                'Athletes Tested', 'In-Competition', 'Out-of-', 'Total number',
                'Paris 2024', 'Page ', 'IO Report', 'that are collected', 'Data attributed')
VOCAB = {'urine','blood','abp','dbs','total','ic','ooc','grand','sport','discipline',
         'in-competition','out-of-','competition','type','of','analyses','by','samples',
         'collected','during','the','games','period','tests','conducted','dried','passport',
         'spot','(dbs)','number','athletes','tested','%','participating'}

def drop_orphan(t):
    if t.strip().lower() == 'grand total':
        return False
    if any(h in t for h in HEADER_HINTS):
        return True
    if len(t) > 85:
        return True
    toks = [w.lower() for w in t.split()]
    return bool(toks) and all(w in VOCAB for w in toks)

def parse(pdfpath, pages, label_x):
    """pages: list of (page_number, y0, y1)."""
    out = []
    with pdfplumber.open(pdfpath) as pdf:
        for pn, y0, y1 in pages:
            page = pdf.pages[pn - 1]
            ws = [w for w in page.extract_words() if y0 + 2 <= w['top'] <= y1 - 2]
            lines, cur, start = [], [], None
            for w in sorted(ws, key=lambda w: w['top']):
                if start is None or w['top'] - start <= 4:
                    start = w['top'] if start is None else start
                    cur.append(w)
                else:
                    lines.append(cur); cur = [w]; start = w['top']
            if cur: lines.append(cur)
            rows = []
            for line in lines:
                line = sorted(line, key=lambda w: w['x0'])
                label, nums = [], []
                for w in line:
                    v = num(w['text'])
                    if v is not None and w['x0'] >= label_x:
                        nums.append((v, w['x1']))
                    else:
                        label.append(w['text'])
                label = " ".join(label).strip()
                if not nums:
                    if label and not drop_orphan(label):
                        rows.append({'label': label, 'nums': [], 'bold': False})
                    continue
                cs = [c for c in page.chars if abs(c['top'] - line[0]['top']) <= 3 and c['x1'] <= label_x]
                bold = any('Bold' in c['fontname'] for c in cs)
                rows.append({'label': label, 'nums': nums, 'bold': bold})
            # merge short orphan label lines into following data row
            merged, pending = [], ""
            for r in rows:
                if not r['nums']:
                    pending = (pending + " " + r['label']).strip(); continue
                r = dict(r, label=(pending + " " + r['label']).strip()); pending = ""
                if drop_orphan(r['label']): continue
                merged.append(r)
            for r in merged:
                r['page'] = pn
            out += merged
    return out

def to_columns(rows, labels, tol=15):
    vals = sorted(x for r in rows for _, x in r['nums'])
    groups, cur = [], [vals[0]]
    for v in vals[1:]:
        if v - cur[-1] <= tol: cur.append(v)
        else: groups.append(cur); cur = [v]
    groups.append(cur)
    centers = [sum(g) / len(g) for g in groups]
    assert len(centers) == len(labels), \
        f"{len(centers)} numeric columns found, expected {len(labels)}: {[round(c) for c in centers]}"
    out = []
    for r in rows:
        slot = [None] * len(centers); ok = True
        for v, x in r['nums']:
            i = min(range(len(centers)), key=lambda k: abs(centers[k] - x))
            if slot[i] is not None: ok = False
            slot[i] = v
        d = dict(zip(labels, slot))
        # carry running sport name down from bold rows
        out.append(dict(r, data=d if ok else None))
    sport = None
    for r in out:
        if r['bold'] and r['label'] != 'Grand Total': sport = r['label']
        r['sport'] = r['label'] if (r['bold'] and r['label'] != 'Grand Total') else sport
    return out
