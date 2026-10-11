#!/usr/bin/env python3
"""整合 data/raw/ 下的多个导出 run，输出纵向合并表到 data/interim/。

职责边界
--------
本脚本只做四件事：

1. 扫描每个导出包，读取 manifest 核对状态、日期、版本与定义指纹；
2. 给每一行补上 run 级溯源列（run_id / speed_assignment /
   protection_assignment / replicate / definition_fingerprint），
   同时完整保留 source_file、game_date 及其他原始字段；
3. 把同名的原始表纵向合并；
4. 输出行数、列数、日期范围与异常日志。

**不计算任何研究变量**（不做加总、比例、差距、增长率、净余额），
输出目录是 data/interim/，绝不写回导出包。

用法
----
    python3 scripts/build_interim.py
    python3 scripts/build_interim.py --raw-root data/raw --out-dir data/interim

需要 Python 3.11+（使用 tomllib）。
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import tomllib
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# 追加在每一行最前面的 run 级溯源列
PROVENANCE_COLUMNS = [
    "run_id",
    "speed_assignment",
    "protection_assignment",
    "replicate",
    "definition_fingerprint",
]

# 工具包应输出的 13 张原始表
CANONICAL_TABLES = [
    "country_scalar_fields_raw.csv",
    "country_trend_values_raw.csv",
    "budget_slots_raw.csv",
    "pop_records_raw.csv",
    "building_records_raw.csv",
    "state_records_raw.csv",
    "state_pop_statistics_raw.csv",
    "institutions_raw.csv",
    "laws_raw.csv",
    "construction_queue_raw.csv",
    "save_metadata_raw.csv",
    "game_definition_files_raw.csv",
    "game_definition_keys_raw.csv",
]

EXPECTED_TOOL_VERSION = "vic3-student-raw-export-1.2.0"

# 文件名里的 run 身份：比利时_1836_12_31_SL_01_Serena.v3
RUN_ID_RE = re.compile(r"_(?!\d)([A-Za-z]{2,6})_(\d{2})_")
# 文件名里的观察点：比利时_1836_12_31_...
FILENAME_DATE_RE = re.compile(r"_(\d{4})_(\d{2})_(\d{2})_")

SEVERITY_ORDER = {"ERROR": 0, "WARN": 1, "INFO": 2}


# --------------------------------------------------------------------------- #
# 基础设施
# --------------------------------------------------------------------------- #
class AnomalyLog:
    """收集异常，最后写成 CSV。"""

    def __init__(self) -> None:
        self.rows: list[dict] = []
        self._seen: set = set()

    def add(self, severity: str, code: str, detail: str,
            run_id: str = "", package: str = "", table: str = "") -> None:
        # 同一次导出可能被放了多份副本，扫描时难免重复命中；
        # 按内容去重，避免日志出现成对噪声。
        key = (severity, code, run_id, table, detail)
        if key in self._seen:
            return
        self._seen.add(key)
        self.rows.append({
            "severity": severity,
            "code": code,
            "run_id": run_id,
            "package": package,
            "table": table,
            "detail": detail,
        })

    def counts(self) -> dict:
        return dict(Counter(r["severity"] for r in self.rows))

    def sorted_rows(self) -> list[dict]:
        return sorted(
            self.rows,
            key=lambda r: (SEVERITY_ORDER.get(r["severity"], 9), r["code"], r["run_id"]),
        )


def parse_game_date(text):
    """'1837.1.1.6' -> (1837, 1, 1)；无法解析返回 None。"""
    parts = str(text or "").split(".")
    if len(parts) < 3:
        return None
    try:
        return (int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError:
        return None


def fmt_date(t) -> str:
    return f"{t[0]:04d}-{t[1]:02d}-{t[2]:02d}" if t else ""


def read_csv_rows(path: Path) -> tuple[list[str], list[dict]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        return list(reader.fieldnames or []), list(reader)


# --------------------------------------------------------------------------- #
# 扫描与校验
# --------------------------------------------------------------------------- #
def find_packages(raw_root: Path) -> list[Path]:
    """找出所有含 manifest.json 的导出包目录。"""
    if not raw_root.is_dir():
        return []
    return [
        child for child in sorted(raw_root.iterdir())
        if child.is_dir() and (child / "manifest.json").is_file()
    ]


def inspect_package(pkg: Path, log: AnomalyLog) -> dict:
    """读取 manifest，做包级校验，推导 run 身份。"""
    name = pkg.name
    try:
        manifest = json.loads((pkg / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.add("ERROR", "MANIFEST_UNREADABLE", f"无法读取 manifest: {exc}", package=name)
        return {}

    info = {
        "package": pkg,
        "package_name": name,
        "manifest": manifest,
        "tool_version": manifest.get("tool_version", ""),
        "data_contract": manifest.get("data_contract", ""),
        "created_at": manifest.get("created_at_local", ""),
        "failed_files": manifest.get("failed_files", None),
        "successful_files": manifest.get("successful_files", None),
        "fingerprint": manifest.get("game_environment", {}).get(
            "definition_fingerprint_sha256", ""
        ),
        "saves": [],
        "run_ids": set(),
        "errors": [],
    }

    # 包级校验
    if info["tool_version"] != EXPECTED_TOOL_VERSION:
        log.add("WARN", "TOOL_VERSION_MISMATCH",
                f"tool_version={info['tool_version']!r}，预期 {EXPECTED_TOOL_VERSION!r}",
                package=name)
    if info["data_contract"] != "raw_only":
        log.add("ERROR", "DATA_CONTRACT_NOT_RAW_ONLY",
                f"data_contract={info['data_contract']!r}，预期 'raw_only'", package=name)
    if info["failed_files"]:
        log.add("ERROR", "FAILED_FILES",
                f"manifest 记录 failed_files={info['failed_files']}", package=name)
    if not info["fingerprint"]:
        log.add("WARN", "FINGERPRINT_MISSING", "manifest 未记录定义指纹", package=name)

    for entry in manifest.get("files", []):
        fname = entry.get("name", "")
        sub_id = f"{name}/{fname}"

        # run 身份先从文件名解出来，后面的异常都带上它
        rid = RUN_ID_RE.search(fname)
        run_id = f"{rid.group(1)}_{rid.group(2)}" if rid else ""

        if entry.get("status") != "success":
            info["errors"].append(sub_id)
            log.add("ERROR", "SAVE_STATUS_NOT_SUCCESS",
                    f"{fname}: status={entry.get('status')!r} "
                    f"error={entry.get('error', '')!r}",
                    run_id=run_id, package=name)

        match = entry.get("definition_version_match")
        if match is not True:
            log.add("ERROR", "DEFINITION_VERSION_MISMATCH",
                    f"{fname}: definition_version_match={match!r} "
                    f"(存档 {entry.get('game_version')} vs 本机 "
                    f"{entry.get('installed_game_version')})",
                    run_id=run_id, package=name)

        game_date = parse_game_date(entry.get("game_date"))
        if game_date is None:
            log.add("ERROR", "GAME_DATE_UNPARSABLE",
                    f"{fname}: game_date={entry.get('game_date')!r}",
                    run_id=run_id, package=name)

        # 文件名日期 vs 存档内日期
        fdate = FILENAME_DATE_RE.search(fname)
        if fdate and game_date:
            expected = tuple(int(g) for g in fdate.groups())
            if expected != game_date:
                log.add("WARN", "GAME_DATE_FILENAME_MISMATCH",
                        f"{fname}: 文件名 {fmt_date(expected)} 与存档内 "
                        f"{fmt_date(game_date)} 不一致",
                        run_id=run_id, package=name)

        if rid:
            info["run_ids"].add(run_id)
            info["saves"].append({
                "source_file": fname,
                "run_id": run_id,
                "arm": rid.group(1),
                "replicate": int(rid.group(2)),
                "game_date": game_date,
                "game_version": entry.get("game_version", ""),
                "sha256": entry.get("sha256", ""),
                "bytes": entry.get("bytes", ""),
            })
        else:
            log.add("ERROR", "RUN_ID_UNRESOLVED",
                    f"{fname}: 文件名中找不到 _<臂>_<重复号>_ 片段",
                    package=name)

    if len(info["run_ids"]) > 1:
        log.add("ERROR", "MULTIPLE_ARMS_IN_PACKAGE",
                f"同一导出包内出现多个 run: {sorted(info['run_ids'])}", package=name)
    elif info["run_ids"]:
        derived = next(iter(info["run_ids"]))
        if pkg.name != derived:
            log.add("INFO", "FOLDER_NAME_MISMATCH",
                    f"文件夹名 {pkg.name!r} 与存档推导出的 run_id {derived!r} 不一致，"
                    f"以存档文件名 {derived!r} 为准", run_id=derived, package=name)

    return info


def select_runs(packages: list[dict], log: AnomalyLog) -> dict:
    """按 run_id 去重：同一次导出可能被放了两份。"""
    by_run: dict[str, list[dict]] = defaultdict(list)
    for info in packages:
        if not info or len(info["run_ids"]) != 1:
            continue
        by_run[next(iter(info["run_ids"]))].append(info)

    chosen: dict[str, dict] = {}
    for run_id, candidates in sorted(by_run.items()):
        # 优先取文件夹名与 run_id 一致的；其次取路径字典序最小的
        candidates.sort(key=lambda c: (c["package_name"] != run_id, str(c["package"])))
        chosen[run_id] = candidates[0]
        for dup in candidates[1:]:
            log.add("WARN", "DUPLICATE_RUN",
                    f"run {run_id} 有 {len(candidates)} 个候选包，已采用 "
                    f"{candidates[0]['package_name']!r}，忽略 {dup['package_name']!r}",
                    run_id=run_id, package=dup["package_name"])
    return chosen


def load_run_config(config_path: Path, runs: dict, log: AnomalyLog) -> dict:
    if not config_path.is_file():
        log.add("ERROR", "CONFIG_MISSING", f"找不到配置文件 {config_path}")
        return {}
    try:
        with config_path.open("rb") as fh:
            config = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        log.add("ERROR", "CONFIG_UNREADABLE", f"无法解析 {config_path}: {exc}")
        return {}

    configured = config.get("runs", {})
    for run_id in runs:
        if run_id not in configured:
            log.add("ERROR", "RUN_NOT_IN_CONFIG",
                    f"run {run_id} 未登记在 {config_path.name}，"
                    f"speed_assignment / protection_assignment 将为空",
                    run_id=run_id)

    for run_id, spec in configured.items():
        if run_id not in runs:
            log.add("INFO", "CONFIG_RUN_NOT_PRESENT",
                    f"配置里的 run {run_id} 在 data/raw 下没有对应导出包", run_id=run_id)
        for field in ("speed_assignment", "protection_assignment"):
            if not str(spec.get(field, "")).strip():
                log.add("WARN", "ASSIGNMENT_MISSING",
                        f"run {run_id} 的 {field} 为空（待人工确认）", run_id=run_id)
    return configured


# --------------------------------------------------------------------------- #
# 保护分组的一致性校验（用数据反过来验配置）
# --------------------------------------------------------------------------- #
def verify_protection(pkg: Path, log: AnomalyLog, run_id: str,
                      configured: str) -> tuple[str, str]:
    """从 institutions / laws 反推社会保护水平，与配置比对。

    返回 ``(derived, evidence)``。``derived`` 为 high / none / unknown。
    """
    inst_path = pkg / "raw_data" / "institutions_raw.csv"
    laws_path = pkg / "raw_data" / "laws_raw.csv"
    if not inst_path.is_file() or not laws_path.is_file():
        return "unknown", ""

    _, inst_rows = read_csv_rows(inst_path)
    _, law_rows = read_csv_rows(laws_path)

    institutions = {r.get("institution_key", "") for r in inst_rows}
    active_laws = {r.get("law_key", "") for r in law_rows if r.get("active") == "yes"}

    has_ss_inst = "institution_social_security" in institutions
    has_wp_inst = "institution_workplace_safety" in institutions
    has_pension = "law_old_age_pension" in active_laws
    has_no_ss = "law_no_social_security" in active_laws
    has_workers_rights = "law_worker_protections" in active_laws
    has_no_workers_rights = "law_no_workers_rights" in active_laws

    if has_ss_inst and has_pension:
        derived = "high"
    elif has_no_ss and has_no_workers_rights and not has_ss_inst:
        derived = "none"
    else:
        derived = "unknown"

    if configured and derived != "unknown" and configured != derived:
        log.add("WARN", "PROTECTION_MISMATCH",
                f"配置 protection_assignment={configured!r}，但数据里读出来是 {derived!r}"
                f"（social_security机构={has_ss_inst}, 养老金法={has_pension}, "
                f"no_social_security={has_no_ss}）", run_id=run_id)
    elif derived == "unknown":
        log.add("WARN", "PROTECTION_UNVERIFIED",
                f"无法从 institutions/laws 判定社会保护水平，配置值 {configured!r} 未经校验",
                run_id=run_id)

    evidence = (
        f"schools={'institution_schools' in institutions}, "
        f"social_security={has_ss_inst}, workplace_safety={has_wp_inst}, "
        f"pension={has_pension}, worker_protections={has_workers_rights}, "
        f"no_social_security={has_no_ss}, no_workers_rights={has_no_workers_rights}"
    )
    return derived, evidence


# --------------------------------------------------------------------------- #
# 合并
# --------------------------------------------------------------------------- #
def merge_tables(runs: dict, config: dict, log: AnomalyLog):
    """把每个表在所有 run 之间纵向合并，并补上 run 级溯源列。"""
    merged: dict[str, list[dict]] = {}
    meta: dict[str, dict] = {}

    table_names = list(CANONICAL_TABLES)
    # 记录实际出现的其它表，避免漏掉
    for info in runs.values():
        data_dir = info["package"] / "raw_data"
        if data_dir.is_dir():
            for p in sorted(data_dir.glob("*.csv")):
                if p.name not in table_names and p.name != "errors.csv":
                    table_names.append(p.name)

    for table in table_names:
        rows: list[dict] = []
        columns: list[str] = []
        seen_cols: set[str] = set()
        rows_by_run: dict[str, int] = {}
        schema_by_run: dict[str, list[str]] = {}
        dates_by_run: dict[str, list[tuple]] = {}

        for run_id in sorted(runs):
            info = runs[run_id]
            spec = config.get(run_id, {})
            path = info["package"] / "raw_data" / table

            if not path.is_file():
                log.add("WARN", "TABLE_MISSING",
                        f"run {run_id} 的导出包里没有 {table}", run_id=run_id,
                        package=info["package_name"], table=table)
                continue

            header, table_rows = read_csv_rows(path)
            schema_by_run[run_id] = header
            for col in header:
                if col not in seen_cols:
                    seen_cols.add(col)
                    columns.append(col)

            for row in table_rows:
                out = {
                    "run_id": run_id,
                    "speed_assignment": str(spec.get("speed_assignment", "") or ""),
                    "protection_assignment": str(spec.get("protection_assignment", "") or ""),
                    "replicate": spec.get("replicate", ""),
                    "definition_fingerprint": info["fingerprint"],
                }
                out.update(row)
                rows.append(out)

                gd = parse_game_date(row.get("game_date"))
                if gd:
                    dates_by_run.setdefault(run_id, []).append(gd)

            rows_by_run[run_id] = len(table_rows)

        # 列结构是否一致
        distinct = {tuple(sorted(v)) for v in schema_by_run.values()}
        if len(distinct) > 1:
            log.add("WARN", "SCHEMA_MISMATCH",
                    f"各 run 的列结构不同: " +
                    "; ".join(f"{k}={len(v)}列" for k, v in sorted(schema_by_run.items())),
                    table=table)

        all_dates = [d for lst in dates_by_run.values() for d in lst]
        meta[table] = {
            "rows": len(rows),
            "columns": len(PROVENANCE_COLUMNS) + len(columns),
            "columns_by_run": {k: len(v) + len(PROVENANCE_COLUMNS)
                               for k, v in sorted(schema_by_run.items())},
            "rows_by_run": dict(sorted(rows_by_run.items())),
            "date_range": [fmt_date(min(all_dates)), fmt_date(max(all_dates))] if all_dates else None,
            "date_range_by_run": {
                k: [fmt_date(min(v)), fmt_date(max(v))]
                for k, v in sorted(dates_by_run.items())
            },
            "fieldnames": PROVENANCE_COLUMNS + columns,
        }
        merged[table] = rows

    return merged, meta


# --------------------------------------------------------------------------- #
# 输出
# --------------------------------------------------------------------------- #
def write_tables(merged: dict, meta: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for table, rows in merged.items():
        path = out_dir / table
        with path.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=meta[table]["fieldnames"],
                                    extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)


def write_runs_csv(runs: dict, config: dict, out_dir: Path, protection_check: dict) -> None:
    fields = ["run_id", "arm", "replicate", "speed_assignment", "protection_assignment",
              "protection_verified", "protection_evidence", "n_saves", "year_min", "year_max",
              "definition_fingerprint", "package_name", "source_package", "note"]
    path = out_dir / "_runs.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for run_id in sorted(runs):
            info = runs[run_id]
            spec = config.get(run_id, {})
            saves = info["saves"]
            years = [s["game_date"][0] for s in saves if s["game_date"]]
            writer.writerow({
                "run_id": run_id,
                "arm": saves[0]["arm"] if saves else "",
                "replicate": spec.get("replicate", saves[0]["replicate"] if saves else ""),
                "speed_assignment": spec.get("speed_assignment", ""),
                "protection_assignment": spec.get("protection_assignment", ""),
                "protection_verified": protection_check.get(run_id, ("", ""))[0],
                "protection_evidence": protection_check.get(run_id, ("", ""))[1],
                "n_saves": len(saves),
                "year_min": min(years) if years else "",
                "year_max": max(years) if years else "",
                "definition_fingerprint": info["fingerprint"],
                "package_name": info["package_name"],
                "source_package": str(info["package"]),
                "note": spec.get("note", ""),
            })


def write_anomalies(log: AnomalyLog, out_dir: Path) -> Counter:
    fields = ["severity", "code", "run_id", "package", "table", "detail"]
    path = out_dir / "_anomalies.csv"
    rows = log.sorted_rows()
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return Counter(r["severity"] for r in rows)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--raw-root", default=str(REPO_ROOT / "data" / "raw"))
    parser.add_argument("--out-dir", default=str(REPO_ROOT / "data" / "interim"))
    parser.add_argument("--config", default=str(REPO_ROOT / "config" / "runs.toml"))
    args = parser.parse_args(argv)

    raw_root = Path(args.raw_root).resolve()
    out_dir = Path(args.out_dir).resolve()
    config_path = Path(args.config).resolve()

    log = AnomalyLog()
    print(f"[1/5] 扫描 {raw_root}")
    packages = find_packages(raw_root)
    if not packages:
        print(f"  ✗ 没有找到任何含 manifest.json 的导出包", file=sys.stderr)
        return 1
    print(f"  找到 {len(packages)} 个导出包")

    print("[2/5] 读取 manifest 并校验")
    infos = [inspect_package(p, log) for p in packages]
    runs = select_runs(infos, log)
    if not runs:
        print("  ✗ 没有任何可用的 run", file=sys.stderr)
        return 1
    for run_id, info in sorted(runs.items()):
        print(f"  run {run_id:<8} {len(info['saves'])} 份存档  "
              f"指纹 {info['fingerprint'][:12]}…  来源 {info['package_name']}")

    print("[3/5] 载入 run 登记表")
    config = load_run_config(config_path, runs, log)
    protection_check = {}
    for run_id, info in sorted(runs.items()):
        spec = config.get(run_id, {})
        result = verify_protection(info["package"], log, run_id,
                                   str(spec.get("protection_assignment", "") or ""))
        protection_check[run_id] = result if isinstance(result, tuple) else (result, "")
        if protection_check[run_id][0] != "unknown":
            print(f"  run {run_id:<8} protection 数据自检 = {protection_check[run_id][0]}"
                  f"（配置 {spec.get('protection_assignment', '')!r}）")

    # 定义指纹一致性
    fps = {rid: i["fingerprint"] for rid, i in runs.items()}
    if len(set(fps.values())) > 1:
        log.add("ERROR", "FINGERPRINT_MISMATCH",
                "各 run 的定义指纹不一致，不可直接合并: " +
                "; ".join(f"{k}={v[:12]}…" for k, v in sorted(fps.items())))

    print("[4/5] 纵向合并")
    merged, meta = merge_tables(runs, config, log)

    print("[5/5] 写出 data/interim/")
    write_tables(merged, meta, out_dir)
    write_runs_csv(runs, config, out_dir, protection_check)
    counts = write_anomalies(log, out_dir)

    report = {
        "built_at_local": datetime.now().astimezone().isoformat(),
        "raw_root": str(raw_root),
        "out_dir": str(out_dir),
        "config_path": str(config_path),
        "packages_scanned": [p.name for p in packages],
        "runs_used": {rid: {"package": i["package_name"], "n_saves": len(i["saves"]),
                            "fingerprint": i["fingerprint"]}
                      for rid, i in sorted(runs.items())},
        "tables": meta,
        "anomaly_counts": dict(counts),
    }
    (out_dir / "_build_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print("=" * 74)
    print(f"{'表':<38}{'行数':>8}{'列数':>6}  日期范围")
    print("-" * 74)
    for table, m in meta.items():
        dr = m["date_range"]
        dr = f"{dr[0]} → {dr[1]}" if dr else "—"
        print(f"{table:<38}{m['rows']:>8}{m['columns']:>6}  {dr}")
    print("=" * 74)
    summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "无"
    print(f"异常统计: {summary}")
    print(f"输出目录: {out_dir}")
    print(f"  - _runs.csv            run 台账")
    print(f"  - _anomalies.csv       异常日志")
    print(f"  - _build_report.json   行数/列数/日期范围")

    if counts.get("ERROR"):
        print("\n⚠️  存在 ERROR 级异常，请先查看 _anomalies.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
