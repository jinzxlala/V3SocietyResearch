#!/usr/bin/env python3
"""Build per-sport injury-rate tables for Summer Olympic Games 2012/2016/2020.

Sources
-------
London 2012 : Engebretsen L, et al. Br J Sports Med 2013;47:407-414, Table 1.
              Text layer parsed from the archived PDF (raw/london2012_engebretsen.pdf).
Rio 2016   : Soligard T, et al. Br J Sports Med 2017;51:1265-1271, Figure 1.
              Bars digitised from the archived PDF image (raw/rio2016_soligard_fig1_img0.png).
Tokyo 2020 : Soligard T, et al. Br J Sports Med 2023;57:46-54, Figure 1.
              Bars digitised from the archived PDF image (raw/tokyo2020_soligard_fig1_img0.png).

Figure decoding rule (Rio & Tokyo Figure 1)
-------------------------------------------
Each sport row is one outlined bar + two overlaid filled bars:
  outline length  = % of athletes with any injury
  grey fill end   = % of athletes with injury and estimated time loss >= 1 day
  black fill end  = % of athletes with injury and estimated time loss > 7 days
Calibration used the 0% / 40% (Rio) and 0% / 30% (Tokyo) axis ticks.
Validation: digitised values match every per-sport number quoted in the article
text (Rio BMX 37.5, boxing 30.1, MTB 23.8, taekwondo 23.6, water polo 19.4,
rugby 18.6; Tokyo BMX freestyle 22, skateboarding 21, karate 19, sport climbing
15, surfing 13, table tennis 12, 3x3 basketball 11, baseball/softball 8, ...).
"""
import csv
import json
import os
import re
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RAW = os.path.join(ROOT, "raw")


# ----------------------------------------------------------------------------
# Figure 1 digitisation
# ----------------------------------------------------------------------------
def run_from(profile, x0, thr, maxgap=2, minlen=3):
    x0 = int(round(x0))
    x, end, gap = x0, x0, 0
    while x < len(profile):
        if profile[x] < thr:
            end, gap = x, 0
        else:
            gap += 1
            if gap > maxgap:
                break
        x += 1
    length = end - x0 + 1
    return length if length >= minlen else 0


def digitise_figure(path, x0, px_per_pct):
    """Return the y-extent of every sport row (see module docstring)."""
    a = np.array(Image.open(path).convert("L")).astype(float)
    h, w = a.shape
    bands, cur = [], None
    for y in range(h):
        if run_from(a[y], x0, 200, 2, 15) > 15:
            cur = [y, y] if cur is None else [cur[0], y]
        else:
            if cur is not None:
                bands.append(tuple(cur))
                cur = None
    if cur:
        bands.append(tuple(cur))
    keep = []
    for b in bands:
        mx = max(run_from(a[y], x0, 200, 2, 15) for y in range(b[0], b[1] + 1))
        if 30 < b[0] and b[1] < h - 40 and mx < 0.92 * (w - x0):
            keep.append(b)
    bands = keep
    full = [b for b in bands if b[1] - b[0] + 1 >= 15]
    pitch = float(np.median(np.diff([(b[0] + b[1]) / 2 for b in full]))) if len(full) >= 2 \
        else float(np.median([b[1] - b[0] + 1 for b in bands]) + 12)
    rows = []
    for b in bands:
        if rows and b[0] - rows[-1][0] <= 0.7 * pitch:
            rows[-1][1] = max(rows[-1][1], b[1])
        else:
            rows.append([b[0], b[1]])
    out = []
    for yt, yb in rows:
        seg = a[yt:yb + 1]
        all_length = max(run_from(row, x0, 200, 2, 15) for row in seg)
        inter = seg[3:-3] if yb - yt >= 8 else seg
        med = np.median(inter, axis=0)
        out.append(dict(
            y_top=yt, y_bot=yb, y_center=(yt + yb) / 2.0,
            all=round(all_length / px_per_pct, 1),
            ge1d=round(run_from(med, x0, 235, 2, 8) / px_per_pct, 1),
            gt7d=round(run_from(med, x0, 90, 2, 8) / px_per_pct, 1),
        ))
    return out


# OCR labels were produced with macOS Vision (raw/ocr.m); several labels next to
# long bars were merged into bar art, so the sport names below are the verified
# label sequence read from the figure (see raw/*_ocr.tsv and the article text).
RIO_NAMES = [
    "Cycling - BMX", "Boxing", "Cycling - MTB", "Taekwondo", "Water polo",
    "Rugby", "Football", "Handball", "Gymnastics - Artistic", "Weightlifting",
    "Wrestling", "Hockey", "Judo", "Triathlon", "Tennis", "Athletics",
    "Diving", "Badminton", "Fencing", "Basketball", "Volleyball",
    "Beach volleyball", "Gymnastics - Rhythmic", "Synchronised swimming",
    "Cycling - Road", "Sailing", "Cycling - Track", "Equestrian",
    "Modern pentathlon", "Canoe - Sprint", "Gymnastics - Trampoline",
    "Table tennis", "Swimming", "Golf", "Open-water marathon", "Archery",
    "Shooting", "Rowing",
]

# Canoe slalom had no visible bar (0 injuries per 100 athletes in Rio 2016; the
# article text lists it among the sports with the lowest injury incidence,
# "ranging from 0 to 3 injuries per 100 athletes").
RIO_EXTRA = [dict(y_top=1345, y_bot=1382, y_center=1363.5, all=0.0, ge1d=0.0, gt7d=0.0,
                  sport="Canoe - Slalom")]

TOKYO_NAMES = [
    "Cycling - BMX Racing", "Boxing", "Cycling - BMX Freestyle", "Skateboarding",
    "Karate", "Handball", "Wrestling", "Sport climbing", "Golf", "Taekwondo",
    "Judo", "Modern pentathlon", "Rugby", "Surfing", "Triathlon",
    "Table tennis", "Volleyball - Indoor", "Water polo", "Basketball - 3x3",
    "Weightlifting", "Artistic gymnastics", "Athletics", "Volleyball - Beach",
    "Hockey", "Fencing", "Trampoline gymnastics", "Football",
    "Baseball/softball", "Basketball - 5x5", "Cycling - MTB",
    "Artistic swimming", "Sailing", "Rhythmic gymnastics", "Badminton",
    "Cycling - Track", "Tennis", "Canoe - Slalom", "Equestrian", "Swimming",
    "Archery", "Canoe - Sprint", "Shooting", "Marathon swimming", "Rowing",
    "Cycling - Road", "Diving",
]


def figure_rows(image, x0, px_per_pct, names, extra=None):
    rows = digitise_figure(os.path.join(RAW, image), x0, px_per_pct)
    if len(rows) != len(names):
        raise SystemExit(f"{image}: digitised {len(rows)} rows but have {len(names)} names")
    for row, name in zip(rows, names):
        row["sport"] = name
    if extra:
        rows.extend(extra)
    return rows


# ----------------------------------------------------------------------------
# London 2012 Table 1
# ----------------------------------------------------------------------------
LONDON_SOURCE = ("Engebretsen L, et al. Sports injuries and illnesses during the "
                 "London Summer Olympic Games 2012. Br J Sports Med 2013;47:407-414, Table 1.")
LONDON_URL = "https://doi.org/10.1136/bjsports-2013-092380"

GROUPS = {"Aquatics", "Cycling", "Gymnastics"}
SUBSPORT_GROUP = {
    "Diving": "Aquatics", "Swimming": "Aquatics",
    "Synchronised swimming": "Aquatics", "Water polo": "Aquatics",
    "BMX": "Cycling", "MTB": "Cycling", "Road": "Cycling", "Track": "Cycling",
    "Artistic": "Gymnastics", "Rhythmic": "Gymnastics", "Trampoline": "Gymnastics",
}
LONDON_ROW = re.compile(
    r"^(?P<sport>[A-Za-z][A-Za-z \-]*?)\s+"
    r"(?P<ath>\d+)\s+"
    r"(?P<inj>\d+)\s*\((?P<inj_pct>[\d.]+)\)\s+"
    r"(?P<d1>\d+)\s*\((?P<d1_pct>[\d.]+)\)\s+"
    r"(?P<d7>\d+)\s*\((?P<d7_pct>[\d.]+)\)\s+"
    r"(?P<comp>\d+)\*?\s*\((?P<comp_pct>[\d.]+)\)\s+"
    r"(?P<train>\d+)\*?\s*\((?P<train_pct>[\d.]+)\)\s+"
    r"(?P<ill>\d+)\s*\((?P<ill_pct>[\d.]+)\)$"
)


def parse_london():
    txt = open(os.path.join(RAW, "london2012_engebretsen.txt")).read()
    lines = txt.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("Table 1 Rates of overall injuries"))
    end = next(i for i, l in enumerate(lines) if l.startswith("Values are numbers"))
    group = None
    rows = []
    for line in lines[start:end]:
        line = line.strip()
        if line in GROUPS:
            group = line
            continue
        m = LONDON_ROW.match(line)
        if not m:
            continue
        d = m.groupdict()
        sport = d["sport"].strip()
        if sport == "Total":
            continue
        label = f"{SUBSPORT_GROUP[sport]} - {sport}" if sport in SUBSPORT_GROUP else sport
        rows.append(dict(
            sport=label, discipline="", athletes=int(d["ath"]),
            injuries=int(d["inj"]),
            all=float(d["inj_pct"]), ge1d=float(d["d1_pct"]), gt7d=float(d["d7_pct"]),
            illness=float(d["ill_pct"]), comp=float(d["comp_pct"]),
            train=float(d["train_pct"]),
        ))
    return rows


def main():
    out = []

    for r in parse_london():
        out.append(dict(games="London 2012", sport=r["sport"], athletes=r["athletes"],
                        injuries=r["injuries"], unit="injuries per 100 registered athletes",
                        all=r["all"], ge1d=r["ge1d"], gt7d=r["gt7d"], illness=r["illness"],
                        source="Engebretsen 2013 (BJSM 47:407-414) Table 1",
                        source_url=LONDON_URL))

    for r in figure_rows("rio2016_soligard_fig1_img0.png", 214, 19.81, RIO_NAMES, RIO_EXTRA):
        out.append(dict(games="Rio 2016", sport=r["sport"], athletes="", injuries="",
                        unit="% of athletes injured",
                        all=r["all"], ge1d=r["ge1d"], gt7d=r["gt7d"], illness="",
                        source="Soligard 2017 (BJSM 51:1265-1271) Figure 1",
                        source_url="https://doi.org/10.1136/bjsports-2017-097956"))

    for r in figure_rows("tokyo2020_soligard_fig1_img0.png", 483, 65.48, TOKYO_NAMES):
        out.append(dict(games="Tokyo 2020", sport=r["sport"], athletes="", injuries="",
                        unit="% of athletes injured",
                        all=r["all"], ge1d=r["ge1d"], gt7d=r["gt7d"], illness="",
                        source="Soligard 2023 (BJSM 57:46-54) Figure 1",
                        source_url="https://doi.org/10.1136/bjsports-2022-106155"))

    path = os.path.join(ROOT, "injury_by_games_sport.csv")
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["games", "sport", "athletes", "injuries", "unit",
                                          "all", "ge1d", "gt7d", "illness",
                                          "source", "source_url"])
        w.writeheader()
        w.writerows(out)
    print(f"wrote {path}: {len(out)} rows")

    # sanity check against values quoted in the article text
    checks = {
        ("Rio 2016", "Cycling - BMX"): 37.5, ("Rio 2016", "Boxing"): 30.1,
        ("Rio 2016", "Cycling - MTB"): 23.8, ("Rio 2016", "Taekwondo"): 23.6,
        ("Rio 2016", "Water polo"): 19.4, ("Rio 2016", "Rugby"): 18.6,
        ("Tokyo 2020", "Cycling - BMX Freestyle"): 22, ("Tokyo 2020", "Skateboarding"): 21,
        ("Tokyo 2020", "Karate"): 19, ("Tokyo 2020", "Sport climbing"): 15,
        ("Tokyo 2020", "Surfing"): 13, ("Tokyo 2020", "Table tennis"): 12,
        ("Tokyo 2020", "Basketball - 3x3"): 11, ("Tokyo 2020", "Baseball/softball"): 8,
    }
    idx = {(r["games"], r["sport"]): r["all"] for r in out}
    bad = 0
    for k, v in checks.items():
        got = idx.get(k)
        ok = got is not None and abs(got - v) <= 1.0
        bad += not ok
        print(f"  check {k}: digitised={got} text={v} {'OK' if ok else 'MISMATCH'}")
    print("all checks passed" if bad == 0 else f"{bad} mismatches")


if __name__ == "__main__":
    main()
