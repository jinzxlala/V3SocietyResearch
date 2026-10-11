#!/usr/bin/env python3
"""对 data/interim/ 做数据质量校验，输出 data_quality_report.csv。

每一条检查至少给出：检查ID、对象、预期、实际、结果(PASS/FAIL)、说明。

校验分八类：
    RUN  运行元数据（manifest、版本、指纹、分组标签）
    TBL  表级（存在性、行数守恒、列结构）
    PRV  溯源列（run_id / fingerprint / replicate / 分组标签是否落全）
    CNT  内容一致性（interim 与原始包是否逐行对得上）
    DAT  日期（可解析性、文件名与存档内是否相符、年度缺口）
    FLD  字段（关键字段齐全、哨兵值、空值是否被篡改）
    REF  引用完整性（pop.workplace_building_id 能否对上 building.building_id）
    GOV  边界（是否越界生成了研究变量）

用法
----
    python3 scripts/validate_interim.py

默认同时写两份完全相同的报告：

    reports/validation/data_quality_report.csv   # 主路径，进版本库留存
    data/interim/data_quality_report.csv         # 与合并表放在一起，便于查看

两份由同一次运行写出，不会不同步。用 --out / --mirror-out 可改路径，
把 --mirror-out 传空字符串即可只写一份：

    python3 scripts/validate_interim.py --mirror-out ""

需要 Python 3.11+。
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_interim as bi  # noqa: E402

REPO_ROOT = bi.REPO_ROOT

REPORT_FIELDS = ["检查ID", "类别", "对象", "预期", "实际", "结果", "说明"]

# 关键原始字段：这些列若大面积为空，说明导出或合并出了问题
CRITICAL_FIELDS = {
    "pop_records_raw.csv": ["pop_id", "location_state_id", "pop_type", "workforce",
                            "dependents", "workplace_building_id",
                            "loyalists_and_radicals", "social_class"],
    "building_records_raw.csv": ["building_id", "state_id", "building_key", "levels"],
    "state_records_raw.csv": ["state_id", "state_key"],
    "institutions_raw.csv": ["institution_record_id", "institution_key", "investment"],
    "laws_raw.csv": ["law_record_id", "law_key"],
    "construction_queue_raw.csv": ["queue_kind", "position", "building_key"],
}

# 不允许出现在原始层的派生研究变量 / 篮子列
FORBIDDEN_PREFIXES = ("basket",)
FORBIDDEN_COLUMNS = {
    "radicals_share", "loyalists_share", "net_balance", "growth_rate",
    "total_population", "total_workforce", "building_by_type", "building_by_state",
    "project_summary", "sol_gap", "weighted_sol",
}


class Report:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add(self, check_id: str, category: str, obj: str, expected: str,
            actual: str, ok: bool | None, notes: str = "") -> None:
        if ok is None:
            result = "SKIP"
        else:
            result = "PASS" if ok else "FAIL"
        self.rows.append({
            "检查ID": check_id,
            "类别": category,
            "对象": obj,
            "预期": expected,
            "实际": actual,
            "结果": result,
            "说明": notes,
        })

    def counts(self) -> Counter:
        return Counter(r["结果"] for r in self.rows)


def load_interim(interim_dir: Path) -> dict[str, tuple[list[str], list[dict]]]:
    out = {}
    for path in sorted(interim_dir.glob("*.csv")):
        if path.name.startswith("_"):
            continue
        out[path.name] = bi.read_csv_rows(path)
    return out


def manifest_saves(info: dict) -> dict[str, dict]:
    return {s["source_file"]: s for s in info["saves"]}


# --------------------------------------------------------------------------- #
def check_runs(rep: Report, packages: list[Path], runs: dict, config: dict) -> None:
    raw_names = [p.name for p in packages]

    rep.add("RUN-01", "运行元数据", f"data/raw 下的 {len(packages)} 个导出包",
            "每个包都能解析出 manifest 与 run_id",
            f"解析出 {len(runs)} 个 run: {sorted(runs)}",
            len(runs) > 0,
            f"扫描到: {raw_names}")

    versions = sorted({i["tool_version"] for i in runs.values()})
    rep.add("RUN-02", "运行元数据", "各 run 的 tool_version",
            f"全部为 {bi.EXPECTED_TOOL_VERSION}", ", ".join(versions),
            versions == [bi.EXPECTED_TOOL_VERSION],
            "工具版本不一致会导致字段含义变化，不可直接合并")

    contracts = sorted({i["data_contract"] for i in runs.values()})
    rep.add("RUN-03", "运行元数据", "各 run 的 data_contract",
            "全部为 raw_only", ", ".join(contracts), contracts == ["raw_only"],
            "raw_only 表示工具只导出原始记录，未代算研究变量")

    failed = {rid: i["failed_files"] for rid, i in runs.items()}
    rep.add("RUN-04", "运行元数据", "各 run 的 failed_files",
            "全部为 0", json.dumps(failed, ensure_ascii=False),
            all(v == 0 for v in failed.values()),
            "出现失败文件则该 run 的记录不完整")

    bad_match = []
    for rid, info in runs.items():
        for entry in info["manifest"].get("files", []):
            if entry.get("definition_version_match") is not True:
                bad_match.append(f"{rid}/{entry.get('name')}")
    rep.add("RUN-05", "运行元数据", "每份存档的 definition_version_match",
            "全部为 True", f"不匹配 {len(bad_match)} 份",
            not bad_match,
            "; ".join(bad_match[:5]) or "存档游戏版本与本机 game/common 一致")

    fps = {rid: i["fingerprint"] for rid, i in runs.items()}
    uniq = sorted(set(fps.values()))
    rep.add("RUN-06", "运行元数据", "各 run 的定义指纹",
            "全部相同", f"{len(uniq)} 个不同指纹: {[u[:12] + '…' for u in uniq]}",
            len(uniq) == 1,
            "指纹不同说明用了不同版本的游戏规则，跨 run 解释存档会失真")

    rep.add("RUN-07", "运行元数据", "run 是否登记在 config/runs.toml",
            f"{sorted(runs)} 全部登记", f"已登记 {sorted(config)}",
            set(runs) <= set(config),
            "未登记的 run 拿不到 speed/protection 标签")

    speed = {rid: str(config.get(rid, {}).get("speed_assignment", "") or "")
             for rid in sorted(runs)}
    rep.add("RUN-08", "运行元数据", "各 run 的 speed_assignment",
            "全部非空", json.dumps(speed, ensure_ascii=False),
            all(v.strip() for v in speed.values()),
            "无法从数据推断，必须人工填写；留空会让该列在 interim 里全为空字符串")

    prot = {rid: str(config.get(rid, {}).get("protection_assignment", "") or "")
            for rid in sorted(runs)}
    rep.add("RUN-09", "运行元数据", "各 run 的 protection_assignment",
            "全部非空", json.dumps(prot, ensure_ascii=False),
            all(v.strip() for v in prot.values()),
            "社会保护分组标签")

    # protection 标签用数据反查
    log = bi.AnomalyLog()
    derived = {}
    for rid, info in runs.items():
        d, _ = bi.verify_protection(info["package"], log, rid, prot.get(rid, ""))
        derived[rid] = d
    mismatch = {rid: (prot.get(rid), derived[rid]) for rid in runs
                if derived[rid] != "unknown" and prot.get(rid, "") != derived[rid]}
    rep.add("RUN-10", "运行元数据", "protection_assignment 与 institutions/laws 是否自洽",
            "配置值与数据反查结果一致",
            json.dumps({k: f"配置{v[0]} vs 数据{v[1]}" for k, v in mismatch.items()},
                       ensure_ascii=False) if mismatch else
            f"全部自洽: {json.dumps(derived, ensure_ascii=False)}",
            not mismatch,
            "从 law_no_social_security / institution_social_security 等字段反查")

    rep_ = {rid: int(config.get(rid, {}).get("replicate", -1)) for rid in runs}
    derived_rep = {rid: (i["saves"][0]["replicate"] if i["saves"] else -1)
                   for rid, i in runs.items()}
    rep.add("RUN-11", "运行元数据", "replicate 与文件名编号是否一致",
            json.dumps(derived_rep, ensure_ascii=False),
            json.dumps(rep_, ensure_ascii=False),
            rep_ == derived_rep,
            "取自存档文件名里的 _NN_ 片段")

    dupes = {rid: [p.name for p in packages
                   if any(s["run_id"] == rid for s in
                          (bi.inspect_package(p, bi.AnomalyLog()).get("saves") or []))]
             for rid in runs}
    dupes = {k: v for k, v in dupes.items() if len(v) > 1}
    rep.add("RUN-12", "运行元数据", "每个 run 对应的导出包数",
            "每个 run 恰好 1 个包",
            json.dumps(dupes, ensure_ascii=False) if dupes else "全部唯一",
            not dupes,
            "重复包不影响合并结果（已按 run_id 去重），但会浪费磁盘并让来源难以辨认")


# --------------------------------------------------------------------------- #
def check_tables(rep: Report, runs: dict, interim: dict) -> None:
    present = sorted(interim)
    missing = [t for t in bi.CANONICAL_TABLES if t not in interim]
    rep.add("TBL-01", "表级", f"{len(bi.CANONICAL_TABLES)} 张规范表是否齐备",
            "13 张全部存在",
            f"存在 {len(present)} 张" + (f"，缺 {missing}" if missing else ""),
            not missing,
            "缺失的表说明合并不完整")

    # 行数守恒：逐表比对 interim 与各 run 原始包之和
    for i, table in enumerate(bi.CANONICAL_TABLES, start=1):
        if table not in interim:
            rep.add(f"TBL-02.{i:02d}", "表级", table, "interim 行数 = Σ 各 run 行数",
                    "表不存在", False, "缺少该表，无法校验")
            continue
        _, rows = interim[table]
        per_run = Counter(r["run_id"] for r in rows)
        expected = {}
        for rid, info in runs.items():
            path = info["package"] / "raw_data" / table
            expected[rid] = len(bi.read_csv_rows(path)[1]) if path.is_file() else 0
        ok = dict(per_run) == expected
        rep.add(f"TBL-02.{i:02d}", "表级", table, "interim 行数 = Σ 各 run 行数",
                f"interim={dict(per_run)} 预期={expected}", ok,
                f"合计 {len(rows)} 行")

    # 列结构
    bad_cols = []
    for table, (cols, _) in interim.items():
        head = cols[:len(bi.PROVENANCE_COLUMNS)]
        if head != bi.PROVENANCE_COLUMNS:
            bad_cols.append(f"{table}(前{len(head)}列={head[:3]}…)")
    rep.add("TBL-03", "表级", "13 张表的前 5 列",
            f"依次为 {bi.PROVENANCE_COLUMNS}",
            "全部正确" if not bad_cols else "; ".join(bad_cols[:4]),
            not bad_cols,
            "溯源列必须固定在最前面，便于按 run 筛选")

    rep.add("TBL-04", "表级", "是否有空表",
            "每张表行数 > 0",
            json.dumps({t: len(v[1]) for t, v in sorted(interim.items())}, ensure_ascii=False),
            all(len(v[1]) > 0 for v in interim.values()),
            "空表说明该 run 未产出对应记录")


# --------------------------------------------------------------------------- #
def check_provenance(rep: Report, runs: dict, interim: dict) -> None:
    def blank(col):
        per_table = {}
        for table, (cols, rows) in interim.items():
            if col not in cols:
                continue
            n = sum(1 for r in rows if not str(r.get(col, "")).strip())
            if n:
                per_table[table] = n
        return per_table

    for i, (cid, col, expect, note) in enumerate([
        ("PRV-01", "run_id", "无空值", "每行必须能追溯到 run"),
        ("PRV-02", "definition_fingerprint", "无空值", "定义指纹用于规则版本溯源"),
        ("PRV-03", "replicate", "无空值", "重复号"),
        ("PRV-04", "protection_assignment", "无空值", "社会保护分组标签"),
        ("PRV-05", "speed_assignment", "无空值", "工业化速度分组标签"),
    ]):
        b = blank(col)
        rep.add(cid, "溯源列", f"列 {col}", expect,
                "无空值" if not b else f"空值分布: {json.dumps(b, ensure_ascii=False)}",
                not b, note)

    # fingerprint 是否等于 manifest 里的值
    fp = {rid: i["fingerprint"] for rid, i in runs.items()}
    bad = []
    for table, (cols, rows) in interim.items():
        if "definition_fingerprint" not in cols:
            continue
        for r in rows:
            if r.get("definition_fingerprint") != fp.get(r["run_id"]):
                bad.append(f"{table}/{r['run_id']}")
                break
    rep.add("PRV-06", "溯源列", "definition_fingerprint 是否等于 manifest 记录值",
            "逐行一致", "全部一致" if not bad else f"{len(bad)} 张表不一致: {bad[:3]}",
            not bad, "确保标签没有错位贴到别的 run 上")

    # replicate 与文件名编号
    bad = []
    for table, (cols, rows) in interim.items():
        if "replicate" not in cols or "source_file" not in cols:
            continue
        for r in rows:
            m = bi.RUN_ID_RE.search(r.get("source_file", ""))
            if not m:
                bad.append(f"{table}/{r.get('source_file')}")
                break
            if str(r["replicate"]) != str(int(m.group(2))):
                bad.append(f"{table}/{r['source_file']}: {r['replicate']} vs {m.group(2)}")
                break
    rep.add("PRV-07", "溯源列", "replicate 是否与 source_file 里的编号一致",
            "逐行一致", "全部一致" if not bad else f"{len(bad)} 处不符: {bad[:3]}",
            not bad, "防止 run 标签串行")


# --------------------------------------------------------------------------- #
def check_content(rep: Report, runs: dict, interim: dict) -> None:
    # source_file 集合
    bad = {}
    for table, (cols, rows) in interim.items():
        if "source_file" not in cols:
            continue
        for rid in {r["run_id"] for r in rows}:
            got = {r["source_file"] for r in rows if r["run_id"] == rid}
            want = set(manifest_saves(runs[rid]))
            if got != want:
                bad[f"{table}/{rid}"] = {"缺": sorted(want - got), "多": sorted(got - want)}
    rep.add("CNT-01", "内容一致性", "各表 source_file 集合是否等于 manifest 存档集合",
            "逐表逐 run 一致",
            "全部一致" if not bad else json.dumps(bad, ensure_ascii=False)[:200],
            not bad, "防止漏表或混入别的 run 的存档")

    # game_date 与 manifest 一致
    bad = []
    for table, (cols, rows) in interim.items():
        if "game_date" not in cols or "source_file" not in cols:
            continue
        for r in rows:
            want = manifest_saves(runs[r["run_id"]]).get(r["source_file"], {}).get("game_date")
            if want is None:
                continue
            if bi.parse_game_date(r["game_date"]) != want:
                bad.append(f"{table}/{r['source_file']}")
    rep.add("CNT-02", "内容一致性", "interim 的 game_date 与 manifest 记录",
            "逐行一致", "全部一致" if not bad else f"{len(bad)} 处不符: {sorted(set(bad))[:3]}",
            not bad, "日期是面板数据的时间轴，错位会毁掉整个分析")

    # save_metadata 唯一性
    cols, rows = interim.get("save_metadata_raw.csv", ([], []))
    keys = Counter((r["run_id"], r["source_file"]) for r in rows)
    dup = {k: v for k, v in keys.items() if v > 1}
    rep.add("CNT-03", "内容一致性", "save_metadata 的 (run_id, source_file) 唯一性",
            "无重复", "无重复" if not dup else f"{len(dup)} 组重复: {list(dup)[:3]}",
            not dup, "每份存档在每个 run 里只能有一行身份记录")

    global_tables = ["game_definition_files_raw.csv", "game_definition_keys_raw.csv"]
    bad = [t for t in global_tables
           if t in interim and "source_file" in interim[t][0]]
    rep.add("CNT-04", "内容一致性", "两张全局表不含 source_file 列",
            "不含（它们是与单份存档无关的规则快照）",
            "符合" if not bad else f"意外含 source_file: {bad}",
            not bad, "全局表按 run 复制，跨 run 内容应完全相同")


# --------------------------------------------------------------------------- #
def check_dates(rep: Report, runs: dict, interim: dict) -> None:
    unparsable = []
    mismatched = []
    for rid, info in runs.items():
        for s in info["saves"]:
            fname = s["source_file"]
            if s["game_date"] is None:
                unparsable.append(f"{rid}/{fname}")
                continue
            m = bi.FILENAME_DATE_RE.search(fname)
            if m:
                expected = tuple(int(g) for g in m.groups())
                if expected != s["game_date"]:
                    mismatched.append(
                        f"{fname}: 文件名 {bi.fmt_date(expected)} vs 存档内 "
                        f"{bi.fmt_date(s['game_date'])}")

    rep.add("DAT-01", "日期", "所有 game_date 是否可解析",
            "全部可解析为 年.月.日", f"{len(unparsable)} 份无法解析",
            not unparsable, "; ".join(unparsable[:3]) or "格式统一为 YYYY.M.D[.tick]")

    rep.add("DAT-02", "日期", "文件名日期与存档内 game_date 是否相符",
            "逐份相符", f"{len(mismatched)} 份不符",
            not mismatched,
            "; ".join(mismatched) or "全部相符；文件名是人为命名，存档内日期才是权威值")

    gap_ok, gap_detail = True, []
    for rid, info in runs.items():
        years = sorted({s["game_date"][0] for s in info["saves"] if s["game_date"]})
        missing = [y for y in range(years[0], years[-1] + 1) if y not in years] if years else []
        if missing:
            gap_ok = False
            gap_detail.append(f"{rid} 缺 {missing}")
    rep.add("DAT-03", "日期", "每个 run 内年度是否连续",
            "无缺口",
            "; ".join(gap_detail) if gap_detail else
            "; ".join(f"{rid}: {min(s['game_date'][0] for s in i['saves'])}"
                      f"-{max(s['game_date'][0] for s in i['saves'])}"
                      for rid, i in sorted(runs.items())),
            gap_ok, "年度缺口会让面板出现断点")

    inc_ok, inc_detail = True, []
    for rid, info in runs.items():
        dates = [s["game_date"] for s in sorted(info["saves"], key=lambda x: x["source_file"])
                 if s["game_date"]]
        if dates != sorted(dates):
            inc_ok = False
            inc_detail.append(rid)
    rep.add("DAT-04", "日期", "每个 run 内按文件名排序后日期是否递增",
            "严格递增", "全部递增" if inc_ok else f"异常的 run: {inc_detail}",
            inc_ok, "顺序异常通常意味着文件命名与内容错位")

    rep.add("DAT-05", "日期", "两个 run 的观察点是否覆盖同一时间轴",
            "起止年份一致",
            "; ".join(f"{rid}: {min(s['game_date'][0] for s in i['saves'])}"
                      f"-{max(s['game_date'][0] for s in i['saves'])}"
                      for rid, i in sorted(runs.items())) + "（长度不同）",
            None,
            "FH_02 有 5 个点、SL_01 有 8 个点，做组间对比时需截齐或说明")


# --------------------------------------------------------------------------- #
def check_fields(rep: Report, interim: dict) -> None:
    # 关键字段齐全 + 空值率
    problems = {}
    for table, fields in CRITICAL_FIELDS.items():
        if table not in interim:
            problems[table] = "表缺失"
            continue
        cols, rows = interim[table]
        miss = [f for f in fields if f not in cols]
        if miss:
            problems[table] = f"缺列 {miss}"
    rep.add("FLD-01", "字段", "关键原始字段是否齐全",
            "各表关键列全部存在",
            "齐全" if not problems else json.dumps(problems, ensure_ascii=False),
            not problems, "关键列缺失会让后续 join 与变量构造无法进行")

    # 空值率（合法的空来自存档本身）
    blank = {}
    for table, fields in CRITICAL_FIELDS.items():
        if table not in interim:
            continue
        _, rows = interim[table]
        for f in fields:
            n = sum(1 for r in rows if not str(r.get(f, "")).strip())
            if n == len(rows):
                blank[f"{table}.{f}"] = "100% 为空"
    rep.add("FLD-02", "字段", "关键列是否整列为空",
            "无整列为空的关键列",
            "无" if not blank else json.dumps(blank, ensure_ascii=False),
            not blank, "整列为空通常是导出或合并出错，而非存档本身缺值")

    # 哨兵值合法性：-1 表示无工作场所
    cols, rows = interim.get("pop_records_raw.csv", ([], []))
    vals = Counter(r["workplace_building_id"] for r in rows)
    neg = {v: c for v, c in vals.items() if v.strip().startswith("-")}
    rep.add("FLD-03", "字段", "pop.workplace_building_id 的负值",
            "仅出现 -1（哨兵值 = 无工作场所）",
            json.dumps(neg, ensure_ascii=False),
            set(neg) <= {"-1"},
            "-1 不是建筑 ID，做 join 前必须先剔除，否则会误连")

    # 建筑类型多样性：确认不是只导了工业篮子
    cols, rows = interim.get("building_records_raw.csv", ([], []))
    types = {r["building_key"] for r in rows}
    nonbasket = [t for t in types if any(k in t for k in
                 ("farm", "ranch", "port", "trade_center", "university",
                  "barrack", "subsistence", "manor"))]
    rep.add("FLD-04", "字段", "building_records 建筑类型多样性",
            "含非工业篮子建筑（证明未按篮子过滤）",
            f"{len(types)} 种建筑类型，其中非篮子类 {len(nonbasket)} 种",
            len(nonbasket) >= 3,
            "样例: " + ", ".join(sorted(nonbasket)[:6]))

    # 建造队列的队列类型
    cols, rows = interim.get("construction_queue_raw.csv", ([], []))
    kinds = Counter(r["queue_kind"] for r in rows)
    rep.add("FLD-05", "字段", "construction_queue 是否区分政府/私人队列",
            "queue_kind 同时含 government 与 private",
            json.dumps(dict(kinds), ensure_ascii=False),
            {"government", "private"} <= set(kinds),
            "私人队列默认不产出，出现说明记录了非政府投资")

    # laws 每份存档生效法律数是否一致
    cols, rows = interim.get("laws_raw.csv", ([], []))
    per_save = defaultdict(int)
    for r in rows:
        if r.get("active") == "yes":
            per_save[(r["run_id"], r["source_file"])] += 1
    counts = Counter(per_save.values())
    rep.add("FLD-06", "字段", "每份存档的生效法律数",
            "各存档一致（说明法律库完整导出）",
            json.dumps(dict(counts), ensure_ascii=False),
            len(counts) == 1,
            "不一致可能是存档推进程度不同，也可能是导出缺漏，需人工确认")

    # 空值是否被填 0
    suspicious = []
    for table, fields in CRITICAL_FIELDS.items():
        if table not in interim:
            continue
        _, rows = interim[table]
        for f in fields:
            if f not in interim[table][0]:
                continue
            nz = sum(1 for r in rows if str(r.get(f, "")).strip() == "0")
            if nz == len(rows):
                suspicious.append(f"{table}.{f} 全为 0")
    rep.add("FLD-07", "字段", "是否有整列被填成 0",
            "无（空值不得改写为 0）",
            "无" if not suspicious else "; ".join(suspicious),
            not suspicious, "整列 0 是人为填充的典型特征")


# --------------------------------------------------------------------------- #
def check_references(rep: Report, interim: dict) -> None:
    if "pop_records_raw.csv" not in interim or "building_records_raw.csv" not in interim:
        rep.add("REF-01", "引用完整性", "pop.workplace_building_id → building.building_id",
                "可校验", "缺少必要表", False, "pop 或 building 表缺失")
        return

    _, pops = interim["pop_records_raw.csv"]
    _, builds = interim["building_records_raw.csv"]

    known = defaultdict(set)
    for b in builds:
        known[(b["run_id"], b["game_date"])].add(b["building_id"])

    orphan = defaultdict(int)
    checked = 0
    for p in pops:
        b_id = p["workplace_building_id"].strip()
        if b_id in ("", "-1"):
            continue
        checked += 1
        if b_id not in known[(p["run_id"], p["game_date"])]:
            orphan[f"{p['run_id']}@{p['game_date']}"] += 1

    rep.add("REF-01", "引用完整性",
            "pop.workplace_building_id → building.building_id（同 run 同日期）",
            "除 -1 外全部能对上",
            f"检查 {checked} 条，悬空 {sum(orphan.values())} 条"
            + (f" {dict(list(orphan.items())[:3])}" if orphan else ""),
            not orphan,
            "悬空说明建筑表漏导或 ID 解读有误；能对上才可做就业 join")


# --------------------------------------------------------------------------- #
def check_governance(rep: Report, interim: dict) -> None:
    hits = {}
    for table, (cols, _) in interim.items():
        bad = [c for c in cols
               if c.lower().startswith(FORBIDDEN_PREFIXES) or c in FORBIDDEN_COLUMNS]
        if bad:
            hits[table] = bad
    rep.add("GOV-01", "边界", "是否出现篮子或派生研究变量列",
            "原始层不得出现 basket_* / radicals_share / growth_rate 等",
            "未出现" if not hits else json.dumps(hits, ensure_ascii=False),
            not hits, "出现即越过 raw_only 契约，会被验收判为不合格")

    cols, rows = interim.get("save_metadata_raw.csv", ([], []))
    tags = {r.get("country_tag") for r in rows}
    rep.add("GOV-02", "边界", "国家标签是否为比利时",
            "全部为 BEL", json.dumps(sorted(tags), ensure_ascii=False),
            tags == {"BEL"}, "导出默认 --tag BEL，混入别国说明调用参数有误")

    log_path = bi.REPO_ROOT / "data" / "interim" / "_anomalies.csv"
    if log_path.is_file():
        rows = list(csv.DictReader(log_path.open(encoding="utf-8-sig")))
        severe = [r for r in rows if r["severity"] == "ERROR"]
        rep.add("GOV-03", "边界", "合并阶段的 ERROR 级异常",
                "0 条", f"{len(severe)} 条",
                not severe,
                "来自 build_interim.py 的 _anomalies.csv")
    else:
        rep.add("GOV-03", "边界", "合并阶段的 ERROR 级异常",
                "存在 _anomalies.csv", "未找到", False,
                "请先运行 scripts/build_interim.py")


# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--raw-root", default=str(REPO_ROOT / "data" / "raw"))
    parser.add_argument("--interim-dir", default=str(REPO_ROOT / "data" / "interim"))
    parser.add_argument("--config", default=str(REPO_ROOT / "config" / "runs.toml"))
    parser.add_argument("--out", default=str(
        REPO_ROOT / "reports" / "validation" / "data_quality_report.csv"),
        help="校验报告主路径（会进版本库）")
    parser.add_argument("--mirror-out", default=str(
        REPO_ROOT / "data" / "interim" / "data_quality_report.csv"),
        help="同步写一份到数据目录，便于与合并表一起查看；传空字符串可关闭")
    args = parser.parse_args(argv)

    raw_root = Path(args.raw_root).resolve()
    interim_dir = Path(args.interim_dir).resolve()
    config_path = Path(args.config).resolve()
    out_paths = [Path(args.out).resolve()]
    if args.mirror_out.strip():
        mirror = Path(args.mirror_out).resolve()
        if mirror not in out_paths:
            out_paths.append(mirror)

    if not interim_dir.is_dir():
        print(f"✗ 找不到 {interim_dir}，请先运行 scripts/build_interim.py", file=sys.stderr)
        return 1

    print(f"读取 {interim_dir}")
    interim = load_interim(interim_dir)
    print(f"  载入 {len(interim)} 张表")

    print(f"扫描 {raw_root}")
    packages = bi.find_packages(raw_root)
    log = bi.AnomalyLog()
    infos = [bi.inspect_package(p, log) for p in packages]
    runs = bi.select_runs(infos, log)
    config = bi.load_run_config(config_path, runs, log)
    print(f"  {len(runs)} 个 run: {sorted(runs)}")

    rep = Report()
    check_runs(rep, packages, runs, config)
    check_tables(rep, runs, interim)
    check_provenance(rep, runs, interim)
    check_content(rep, runs, interim)
    check_dates(rep, runs, interim)
    check_fields(rep, interim)
    check_references(rep, interim)
    check_governance(rep, interim)

    for path in out_paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=REPORT_FIELDS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rep.rows)

    counts = rep.counts()
    print()
    print("=" * 92)
    print(f"{'检查ID':<12}{'类别':<12}{'对象':<46}{'结果'}")
    print("-" * 92)
    for r in rep.rows:
        mark = {"PASS": "✅", "FAIL": "❌", "SKIP": "－"}[r["结果"]]
        obj = r["对象"] if len(r["对象"]) <= 44 else r["对象"][:41] + "…"
        print(f"{r['检查ID']:<12}{r['类别']:<12}{obj:<46}{mark} {r['结果']}")
    print("=" * 92)
    print("统计: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    for path in out_paths:
        print(f"报告: {path}")

    fails = [r for r in rep.rows if r["结果"] == "FAIL"]
    if fails:
        print("\n未通过项:")
        for r in fails:
            print(f"  ❌ {r['检查ID']} {r['对象']}")
            print(f"      预期: {r['预期']}")
            print(f"      实际: {r['实际']}")
            print(f"      说明: {r['说明']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
