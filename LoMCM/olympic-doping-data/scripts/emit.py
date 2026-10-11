import json, csv, os, re

OUT = os.environ['OUTDIR']
os.makedirs(OUT, exist_ok=True)

SPECS = {
 'tokyo': dict(game='Tokyo 2020 (Summer, 2021)', unit='analyses',
   cols=['urine_ic','urine_ooc','urine_total','blood_ic','blood_ooc','blood_total','abp_ic','abp_ooc','abp_total','grand']),
 'paris_tests': dict(game='Paris 2024 (Summer) - controls', unit='doping controls (tests)',
   cols=['ic','ooc','grand']),
 'paris_samples': dict(game='Paris 2024 (Summer) - samples', unit='samples',
   cols=['dbs_ic','blood_ic','abp_ic','urine_ic','ic_total','blood_ooc','abp_ooc','dbs_ooc','urine_ooc','ooc_total','grand']),
 'beijing': dict(game='Beijing 2022 (Winter)', unit='samples',
   cols=['urine_ic','urine_ooc','urine_total','blood_ic','blood_ooc','blood_total','abp_ic','abp_ooc','abp_total','dbs_ic','dbs_ooc','dbs_total','grand']),
}

def ic_ooc(key, cols, d):
    if key in ('paris_tests',): return d['ic'], d['ooc'], d['grand']
    if key == 'tokyo':
        ic = sum(d[x] or 0 for x in ('urine_ic','blood_ic','abp_ic'))
        ooc = sum(d[x] or 0 for x in ('urine_ooc','blood_ooc','abp_ooc'))
        return ic, ooc, d['grand']
    if key == 'paris_samples':
        return d['ic_total'], d['ooc_total'], d['grand']
    if key == 'beijing':
        ic = sum(d[x] or 0 for x in ('urine_ic','blood_ic','abp_ic','dbs_ic'))
        ooc = sum(d[x] or 0 for x in ('urine_ooc','blood_ooc','abp_ooc','dbs_ooc'))
        return ic, ooc, d['grand']

rows_all = []
for key, spec in SPECS.items():
    recs = json.load(open(f'{key}_final.json'))
    cols = spec['cols']
    fn = os.path.join(OUT, f'{key}.csv')
    with open(fn, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['sport','discipline','level','source_page'] + cols)
        for r in recs:
            lvl = 'sport' if r['is_sport'] else ('TOTAL' if r['label']=='Grand Total' else 'discipline')
            w.writerow([r['sport'], r['label'], lvl, r.get('page','')] + [(r['data'][c] if r['data'] and r['data'][c] is not None else '') for c in cols])
            if r['label'] != 'Grand Total':
                ic, ooc, tot = ic_ooc(key, cols, {c:(r['data'][c] or 0) for c in cols})
                rows_all.append(dict(game=spec['game'], unit=spec['unit'], sport=r['sport'],
                                     discipline=r['label'], level=lvl, ic=ic, ooc=ooc, total=tot))
    print("wrote", fn)

with open(os.path.join(OUT, 'combined_by_sport.csv'), 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=['game','unit','sport','discipline','level','in_competition','out_of_competition','total'])
    w.writeheader()
    for r in rows_all:
        w.writerow({'game':r['game'],'unit':r['unit'],'sport':r['sport'],'discipline':r['discipline'],
                    'level':r['level'],'in_competition':r['ic'],'out_of_competition':r['ooc'],'total':r['total']})
print("wrote combined_by_sport.csv")
