"""Merge Victoria 3 raw exports without changing source data (Python 3.11+)."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RUNS = tuple(f"{condition}_{rep:02}" for condition in ("SL", "SH", "FL", "FH") for rep in (1, 2))
PROVENANCE = ["run_id", "speed_assignment", "protection_assignment", "replicate",
              "definition_fingerprint", "source_package", "source_manifest_sha256",
              "source_table_sha256", "source_save_sha256", "source_row_number",
              "game_date_raw", "observation_kind", "integration_mode"]


class MergeError(ValueError):
    pass


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest().upper()


def iso_date(value):
    match = re.fullmatch(r"(\d{4})[.-](\d{1,2})[.-](\d{1,2})(?:\.(\d{1,2}))?", value)
    if not match or (match[4] is not None and int(match[4]) > 23):
        raise MergeError(f"Invalid game date: {value!r}")
    try:
        return date(*map(int, match.group(1, 2, 3))).isoformat()
    except ValueError as exc:
        raise MergeError(f"Invalid game date: {value!r}") from exc


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_rows(path, columns):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != columns:
            raise MergeError(f"Schema changed in {Path(path).name}; expected {columns}, got {reader.fieldnames}")
        for line, row in enumerate(reader, 2):
            if None in row or any(value is None for value in row.values()):
                raise MergeError(f"Malformed CSV: {Path(path).name}, row {line}")
            yield line, row


def write_csv(path, columns, rows):
    with Path(path).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def require(condition, message):
    if not condition:
        raise MergeError(message)


def check_number(value, label):
    # Keep the original lexical representation; validation never fills missing values.
    if value in ("", "NA"):
        return
    try:
        if not Decimal(value).is_finite():
            raise InvalidOperation
    except InvalidOperation as exc:
        raise MergeError(f"Invalid numeric value in {label}: {value!r}") from exc


def integrate(input_root, output, rules, mode="pilot"):
    input_root, output = Path(input_root).resolve(), Path(output).resolve()
    require(input_root.is_dir(), "Input root does not exist")
    require(not output.is_relative_to(input_root) and not input_root.is_relative_to(output),
            "Input and output directories must be separate, not ancestors of each other")
    output.mkdir(parents=True, exist_ok=False)
    warnings, inventory, packages = [], [], []
    observed_hashes = {}
    summary = {"status": "running", "mode": mode, "formal_sample_ready": False,
               "script_sha256": digest(__file__)}

    def note(code, detail):
        warnings.append({"code": code, "detail": detail})

    def track(path):
        value = digest(path)
        observed_hashes[path] = value
        return value

    try:
        manifests = sorted(input_root.rglob("manifest.json"))
        require(manifests, "No extracted export packages found; unzip packages under run folders first")
        for manifest_path in manifests:
            package = manifest_path.parent
            relative = package.relative_to(input_root)
            run = relative.parts[0]
            require(run in RUNS and len(relative.parts) >= 2, f"Unknown run folder: {relative.as_posix()}")
            package_id = relative.as_posix()
            manifest_hash = track(manifest_path)
            manifest = read_json(manifest_path)
            entries = manifest.get("files", [])
            require(isinstance(entries, list), f"Invalid file list: {package_id}")
            counts = Counter(entry.get("status") for entry in entries)
            reasons = []
            if not entries or counts.get("success", 0) != manifest.get("successful_files") or counts.get("failed", 0) != manifest.get("failed_files") or set(counts) - {"success", "failed"}:
                reasons.append("manifest file counts/statuses are inconsistent")
            if manifest.get("failed_files") != 0:
                reasons.append("package contains failed exports; entire package excluded")
            if manifest.get("tool_version") != rules["tool_version"] or manifest.get("data_contract") != "raw_only":
                reasons.append("tool version or raw_only contract mismatch")
            if manifest.get("country_tag") != "BEL":
                reasons.append("country is not BEL")
            environment_path = package / "game_environment.json"
            if not environment_path.is_file():
                reasons.append("game_environment.json is missing")
                environment = {}
            else:
                track(environment_path)
                environment = read_json(environment_path)
                if environment != manifest.get("game_environment"):
                    reasons.append("environment differs from manifest")
            fingerprint = environment.get("definition_fingerprint_sha256", "")
            if not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9A-Fa-f]{64}", fingerprint):
                reasons.append("definition fingerprint is missing or invalid")
            if environment.get("installed_game_version") != rules["game_version"]:
                reasons.append("installed game version mismatch")
            files = {}
            for entry in entries:
                name = entry.get("name", "")
                require(name and name not in files, f"Duplicate/empty source filename in {package_id}")
                record = {"source_package": package_id, "run_id": run, "source_file": name,
                          "source_sha256": entry.get("sha256", ""), "game_date_raw": entry.get("game_date", ""),
                          "game_date": "", "decision": "candidate", "reason": ""}
                inventory.append(record)
                files[name] = {"entry": entry, "inventory": record}
                if entry.get("status") != "success":
                    continue
                try:
                    record["game_date"] = iso_date(entry.get("game_date", ""))
                except MergeError as exc:
                    reasons.append(str(exc))
                if entry.get("definition_version_match") is not True or entry.get("game_version") != rules["game_version"]:
                    reasons.append(f"version mismatch: {name}")
                if entry.get("country_tag") != "BEL" or not re.fullmatch(r"[0-9A-Fa-f]{64}", entry.get("sha256", "")):
                    reasons.append(f"invalid source identity: {name}")
            if reasons:
                reason = "; ".join(dict.fromkeys(reasons))
                for item in files.values():
                    item["inventory"].update(decision="excluded_package", reason=reason)
                note("excluded_package", f"{package_id}: {reason}")
                if mode == "full":
                    raise MergeError(f"{package_id}: {reason}")
                continue
            packages.append({"path": package, "id": package_id, "run": run, "files": files,
                             "fingerprint": fingerprint.upper(), "manifest_hash": manifest_hash})

        # Identical content is counted once. Conflicting same-day saves need a decision.
        dates = defaultdict(list)
        for package in packages:
            for item in package["files"].values():
                dates[(package["run"], item["inventory"]["game_date"])].append(item)
        for key, items in dates.items():
            if len(items) > 1:
                if len({item["entry"]["sha256"].upper() for item in items}) == 1:
                    kept = items[0]["inventory"]
                    reason = f"Identical save SHA-256; retained {kept['source_package']}/{kept['source_file']}"
                    for item in items[1:]:
                        item["inventory"].update(decision="excluded_identical_copy", reason=reason)
                    note("identical_save_copy", reason)
                    continue
                reason = f"Multiple saves for {key[0]} {key[1]}; explicit selection required"
                for item in items:
                    item["inventory"].update(decision="excluded_duplicate_date", reason=reason)
                note("duplicate_date", reason)
                if mode == "full":
                    raise MergeError(reason)
        selected = []
        for package in packages:
            package["selected"] = {name: item for name, item in package["files"].items()
                                   if item["inventory"]["decision"] == "candidate"}
            for item in package["selected"].values():
                item["inventory"]["decision"] = "included"
                selected.append((package["run"], item["inventory"]["game_date"]))
        require(selected, "No unambiguous, successful saves remain")
        active = [package for package in packages if package["selected"]]
        require(len({p["fingerprint"] for p in active}) == 1, "Definition fingerprints differ; do not mix exports")
        expected_dates = set(rules["planned_dates"])
        for run in RUNS:
            actual = {day for r, day in selected if r == run}
            missing, extra = sorted(expected_dates - actual), sorted(actual - expected_dates)
            if missing or extra:
                note("schedule_difference", f"{run}: {len(actual)} saves; missing={','.join(missing)}; extra={','.join(extra)}")
                if mode == "full":
                    raise MergeError(f"{run}: observations do not match planned schedule")
        if mode == "pilot":
            note("pilot_only", "Incomplete test data; not an accepted formal sample. Actual Jan 1 dates are not shifted to Dec 31.")
        stats, source_hash_rows = [], []
        for table_name, spec in rules["tables"].items():
            columns = spec["columns"]
            merged, seen_keys = [], set()
            count_by_run = Counter()
            dates_by_run = defaultdict(set)
            for package in active:
                table_path = package["path"] / "raw_data" / table_name
                require(table_path.is_file(), f"Missing table: {package['id']}/{table_name}")
                table_hash = track(table_path)
                counts_per_save = Counter()
                definition_digest = hashlib.sha256()
                for line, row in read_rows(table_path, columns):
                    is_save_table = "source_file" in columns
                    if is_save_table:
                        name = row["source_file"]
                        require(name in package["files"], f"Orphan source_file in {package['id']}/{table_name}: {name}")
                        if name not in package["selected"]:
                            continue
                        entry = package["selected"][name]["entry"]
                        raw_date = row["game_date"]
                        day = iso_date(raw_date)
                        require(raw_date == entry["game_date"] and row["game_version"] == entry["game_version"] and row["country_id"] == str(entry["country_id"]) and row["country_tag"] == "BEL",
                                f"Row/manifest identity mismatch: {package['id']}/{table_name}:{line}")
                        if table_name == "save_metadata_raw.csv":
                            require(row["source_sha256"].upper() == entry["sha256"].upper() and row["source_bytes"] == str(entry["bytes"]), "Metadata hash/size differs from manifest")
                        save_hash = entry["sha256"].upper()
                        kind = "planned" if day in expected_dates else "baseline" if day == "1836-01-01" else "off_schedule"
                        counts_per_save[name] += 1
                    else:
                        raw_date, day, save_hash, kind = "", "", "", "package_definition"
                        if table_name == "game_definition_files_raw.csv":
                            require(row["parse_status"] == "success", f"Definition parse failure: {package['id']}")
                            require(bool(re.fullmatch(r"[0-9A-Fa-f]{64}", row["source_sha256"])), "Invalid definition file hash")
                            definition_digest.update(row["relative_path"].encode("utf-8"))
                            definition_digest.update(row["source_sha256"].encode("ascii"))
                    for column in spec.get("numeric", []):
                        check_number(row[column], f"{package['id']}/{table_name}:{line}:{column}")
                    for column in spec["key"]:
                        require(row[column] not in ("", "NA"), f"Missing primary key {column}: {table_name}:{line}")
                    key = (package["run"], day if is_save_table else package["id"], *(row[c] for c in spec["key"]))
                    require(key not in seen_keys, f"Duplicate row key: {table_name}: {key}")
                    seen_keys.add(key)
                    row.update({"run_id": package["run"], "speed_assignment": package["run"][0],
                                "protection_assignment": package["run"][1], "replicate": int(package["run"][-2:]),
                                "definition_fingerprint": package["fingerprint"], "source_package": package["id"],
                                "source_manifest_sha256": package["manifest_hash"], "source_table_sha256": table_hash,
                                "source_save_sha256": save_hash, "source_row_number": line, "game_date_raw": raw_date,
                                "observation_kind": kind, "integration_mode": mode})
                    if is_save_table:
                        row["game_date"] = day
                        dates_by_run[package["run"]].add(day)
                    merged.append(row)
                    count_by_run[package["run"]] += 1
                if table_name in rules["required_nonempty_per_save"]:
                    require(set(counts_per_save) == set(package["selected"]), f"Missing save records: {package['id']}/{table_name}")
                if table_name == "save_metadata_raw.csv":
                    require(all(n == 1 for n in counts_per_save.values()), "Metadata must contain exactly one row per save")
                if table_name == "game_definition_files_raw.csv":
                    require(definition_digest.hexdigest().upper() == package["fingerprint"], f"Definition file list/fingerprint mismatch: {package['id']}")
            merged.sort(key=lambda row: (row["run_id"], row.get("game_date", ""), row["source_package"], row["source_row_number"]))
            output_columns = columns + PROVENANCE
            write_csv(output / table_name.replace("_raw.csv", "_merged.csv"), output_columns, merged)
            for run, count in sorted(count_by_run.items()):
                day_list = sorted(dates_by_run[run])
                stats.append({"table": table_name, "run_id": run, "rows": count, "columns": len(output_columns),
                              "date_min": day_list[0] if day_list else "", "date_max": day_list[-1] if day_list else ""})
        for path, before in sorted(observed_hashes.items()):
            require(digest(path) == before, f"Source changed during merge: {path.name}")
            source_hash_rows.append({"path": path.relative_to(input_root).as_posix(), "sha256": before})
        write_csv(output / "input_hashes.csv", ["path", "sha256"], source_hash_rows)
        write_csv(output / "merge_stats.csv", ["table", "run_id", "rows", "columns", "date_min", "date_max"], stats)
        summary.update(status="success", runs=sorted({run for run, _ in selected}),
                       save_count=len(selected), saves_by_run=dict(sorted(Counter(run for run, _ in selected).items())),
                       table_count=len(rules["tables"]), input_files_unchanged=True,
                       definition_fingerprint=active[0]["fingerprint"], warning_count=len(warnings))
        write_json(output / "rules_used.json", rules)
        return summary
    except Exception as exc:
        summary.update(status="failed", error=str(exc))
        raise
    finally:
        write_csv(output / "source_inventory.csv", ["source_package", "run_id", "source_file", "source_sha256", "game_date_raw", "game_date", "decision", "reason"], inventory)
        write_csv(output / "merge_warnings.csv", ["code", "detail"], warnings)
        write_json(output / "merge_summary.json", summary)
        (output / "merge_log.txt").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n" + "\n".join(f"{x['code']}: {x['detail']}" for x in warnings) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, default=REPO / "data/raw")
    parser.add_argument("--output", type=Path, help="New folder under this repository's data/interim")
    parser.add_argument("--rules", type=Path, default=REPO / "config/raw_merge_rules.json")
    parser.add_argument("--mode", choices=["pilot", "full"], default="pilot")
    args = parser.parse_args()
    output = args.output or REPO / "data/interim" / (args.mode + "_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
    require(output.resolve().is_relative_to((REPO / "data/interim").resolve()), "Output must be under data/interim")
    try:
        result = integrate(args.input_root, output, read_json(args.rules), args.mode)
    except (ValueError, OSError, KeyError) as exc:
        print(f"MERGE FAILED: {exc}\nOutput (if created): {output}")
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"Output: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
