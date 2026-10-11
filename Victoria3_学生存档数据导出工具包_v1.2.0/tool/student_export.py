r"""Raw-only Victoria 3 save exporter for the student research workflow.

The exporter flattens project-relevant source records without constructing the
students' analytical variables. It deliberately does NOT calculate basket
totals, employment shares, radical shares, weighted means, growth rates, net
balances, or building-type aggregates.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import re
import shutil
import sys
import traceback
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path

import numpy as np


TOOL_VERSION = "vic3-student-raw-export-1.2.0"
ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)

from src.extractor import ExtractorCommon, ExtractorSave  # noqa: E402
from src.helpers.columnar import load_columns, write_columns  # noqa: E402
from src.helpers.melt import extract_native, melt  # noqa: E402
from src.helpers.utility import load_save, retrieve_from_tree  # noqa: E402


DEFINITION_GROUPS = {
    "buildings": "buildings",
    "building_groups": "building_groups",
    "goods": "goods",
    "laws": "laws",
    "institutions": "institutions",
    "production_methods": "production_methods",
    "production_method_groups": "production_method_groups",
    "technologies": "technology/technologies",
    "technology_eras": "technology/eras",
    "defines": "defines",
    "static_modifiers": "static_modifiers",
}


TABLE_FIELDS = {
    "game_definition_files_raw.csv": [
        "definition_group", "relative_path", "source_bytes", "source_sha256",
        "definition_key_count", "parse_status", "parse_error",
    ],
    "game_definition_keys_raw.csv": [
        "definition_group", "definition_key", "relative_path",
    ],
    "save_metadata_raw.csv": [
        "source_file", "source_sha256", "source_bytes", "source_format",
        "game_version", "game_date", "save_game_version", "save_name",
        "rank", "achievement_eligibility", "ironman", "number_of_players",
        "country_id", "country_tag",
    ],
    "country_scalar_fields_raw.csv": [
        "source_file", "game_version", "game_date", "country_id", "country_tag",
        "source_section", "field_name", "raw_value",
    ],
    "country_trend_values_raw.csv": [
        "source_file", "game_version", "game_date", "country_id", "country_tag",
        "trend_name", "channel", "channel_date", "stored_index",
        "value_position", "raw_value",
    ],
    "budget_slots_raw.csv": [
        "source_file", "game_version", "game_date", "country_id", "country_tag",
        "direction", "slot_index", "raw_value",
    ],
    "pop_records_raw.csv": [
        "source_file", "game_version", "game_date", "country_id", "country_tag",
        "pop_id", "location_state_id", "pop_type", "workforce", "dependents",
        "workplace_building_id", "has_workplace", "culture_id", "religion",
        "num_literate", "wealth", "previous_quality_of_life",
        "loyalists_and_radicals", "political_strength", "job_satisfaction",
        "partial_growth_wa", "partial_growth_dn", "social_class",
        "food_security_value", "food_security_starvation", "food_security_state",
    ],
    "building_records_raw.csv": [
        "source_file", "game_version", "game_date", "country_id", "country_tag",
        "building_id", "state_id", "state_key", "building_key", "levels",
        "last_updated_level", "active", "staffing", "previous_staffing",
        "establishment_date", "throughput", "salary_rate", "cash_reserves",
        "goods_cost", "goods_sales", "profit_after_reserves",
        "profit_after_investments", "input_goods_shortage",
        "production_methods_json", "owners_json", "input_goods_json",
        "output_goods_json", "raw_record_json",
    ],
    "state_records_raw.csv": [
        "source_file", "game_version", "game_date", "country_id", "country_tag",
        "state_id", "state_key", "incorporation", "arable_land", "land",
        "infrastructure", "infrastructure_usage", "trade_capacity",
        "trade_capacity_usage", "base_pop_bureaucracy_cost", "raw_record_json",
    ],
    "state_pop_statistics_raw.csv": [
        "source_file", "game_version", "game_date", "country_id", "country_tag",
        "state_id", "state_key", "field_name", "raw_value",
    ],
    "institutions_raw.csv": [
        "source_file", "game_version", "game_date", "country_id", "country_tag",
        "institution_record_id", "institution_key", "investment", "raw_record_json",
    ],
    "laws_raw.csv": [
        "source_file", "game_version", "game_date", "country_id", "country_tag",
        "law_record_id", "law_key", "active", "activation_date", "replace",
        "raw_record_json",
    ],
    "construction_queue_raw.csv": [
        "source_file", "game_version", "game_date", "country_id", "country_tag",
        "queue_kind", "position", "building_key", "state_id", "state_key",
        "construction_left", "construction_speed", "base_construction_speed",
        "identity_json", "raw_record_json",
    ],
    "errors.csv": ["source_file", "error"],
}


class Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, value):
        for stream in self.streams:
            stream.write(value)
            stream.flush()
        return len(value)

    def flush(self):
        for stream in self.streams:
            stream.flush()


class CsvTableSet:
    def __init__(self, data_dir: Path):
        self.handles = {}
        self.writers = {}
        for name, fields in TABLE_FIELDS.items():
            handle = (data_dir / name).open("w", encoding="utf-8-sig", newline="")
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            self.handles[name] = handle
            self.writers[name] = writer

    def rows(self, table: str, rows):
        writer = self.writers[table]
        for row in rows:
            writer.writerow(row)

    def row(self, table: str, row: dict):
        self.writers[table].writerow(row)

    def close(self):
        for handle in self.handles.values():
            handle.close()


def normalize_game_root(path: Path) -> Path | None:
    path = path.expanduser().resolve()
    if (path / "game" / "common").is_dir():
        return path
    if path.name.lower() == "game" and (path / "common").is_dir():
        return path.parent
    if (
        path.name.lower() == "common"
        and path.parent.name.lower() == "game"
        and path.is_dir()
    ):
        return path.parent.parent
    return None


def configured_game_path() -> Path | None:
    path_file = ROOT.parent / "game_path.txt"
    if not path_file.is_file():
        return None
    for line in path_file.read_text(encoding="utf-8-sig").splitlines():
        value = line.strip().strip('"')
        if value and not value.startswith("#"):
            return Path(value)
    return None


def steam_roots() -> list[Path]:
    roots = []
    if platform.system() == "Windows":
        try:
            import winreg

            registry_locations = [
                (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
            ]
            for hive, key_path, value_name in registry_locations:
                try:
                    with winreg.OpenKey(hive, key_path) as key:
                        roots.append(Path(winreg.QueryValueEx(key, value_name)[0]))
                except (FileNotFoundError, OSError):
                    pass
        except (ImportError, FileNotFoundError, OSError):
            pass
        roots.extend(
            [
                Path(r"C:\Program Files (x86)\Steam"),
                Path(r"C:\Program Files\Steam"),
            ]
        )
    elif platform.system() == "Darwin":
        roots.append(Path.home() / "Library/Application Support/Steam")
    else:
        roots.extend([Path.home() / ".steam/steam", Path.home() / ".local/share/Steam"])
    return roots


def steam_library_paths(steam_root: Path) -> list[Path]:
    libraries = [steam_root]
    file = steam_root / "steamapps/libraryfolders.vdf"
    if file.is_file():
        text = file.read_text(encoding="utf-8", errors="ignore")
        for value in re.findall(r'"path"\s+"([^"]+)"', text):
            libraries.append(Path(value.replace(r"\\", "\\")))
    return libraries


def discover_game_root(explicit: str | None) -> tuple[Path, str]:
    candidates: list[tuple[Path, str]] = []
    if explicit:
        candidates.append((Path(explicit), "command_line"))
    configured = configured_game_path()
    if configured:
        candidates.append((configured, "game_path.txt"))
    if os.environ.get("VIC3_GAME_DIR"):
        candidates.append((Path(os.environ["VIC3_GAME_DIR"]), "VIC3_GAME_DIR"))

    settings_file = ROOT / "user_variables.json"
    if settings_file.is_file():
        try:
            settings = json.loads(settings_file.read_text(encoding="utf-8-sig"))
            value = settings.get("Steamapp Location") or settings.get("Common Directory")
            if value:
                candidates.append((Path(value), "Garibaldi user_variables.json"))
        except (OSError, json.JSONDecodeError):
            pass

    for steam_root in steam_roots():
        for library in steam_library_paths(steam_root):
            candidates.append(
                (library / "steamapps/common/Victoria 3", "Steam library auto-detection")
            )

    checked = []
    for candidate, source in candidates:
        checked.append(str(candidate))
        normalized = normalize_game_root(candidate)
        if normalized is not None:
            return normalized, source
    raise FileNotFoundError(
        "Victoria 3 game directory was not found. Put the installation root "
        "(the folder containing game/common) on the first non-comment line of "
        f"{ROOT.parent / 'game_path.txt'}, then run again. Checked: "
        + "; ".join(dict.fromkeys(checked))
    )


def parse_steam_manifest(game_root: Path) -> dict:
    manifest_path = game_root.parent.parent / "appmanifest_529340.acf"
    result = {"steam_manifest_path": "", "steam_build_id": "", "steam_beta_key": ""}
    if not manifest_path.is_file():
        return result
    text = manifest_path.read_text(encoding="utf-8", errors="ignore")
    result["steam_manifest_path"] = str(manifest_path)
    for output_key, source_key in (
        ("steam_build_id", "buildid"),
        ("steam_beta_key", "BetaKey"),
    ):
        match = re.search(rf'"{source_key}"\s+"([^"]*)"', text)
        if match:
            result[output_key] = match.group(1)
    return result


def parse_game_version_files(game_root: Path) -> dict:
    result = {
        "installed_game_version": "",
        "game_branch": "",
        "game_revision": "",
        "engine_branch": "",
        "engine_revision": "",
    }
    file_map = {
        "game_branch": "caligula_branch.txt",
        "game_revision": "caligula_rev.txt",
        "engine_branch": "clausewitz_branch.txt",
        "engine_revision": "clausewitz_rev.txt",
    }
    for key, name in file_map.items():
        path = game_root / name
        if path.is_file():
            result[key] = path.read_text(encoding="utf-8", errors="ignore").strip()
    match = re.search(r"(\d+\.\d+\.\d+)", result["game_branch"])
    if match:
        result["installed_game_version"] = match.group(1)
    return result


def collect_game_definitions(game_root: Path, discovery_source: str, tables: CsvTableSet) -> dict:
    common_dir = game_root / "game/common"
    missing = []
    parse_errors = []
    fingerprint = hashlib.sha256()
    file_count = 0
    key_count = 0

    for group, relative_folder in DEFINITION_GROUPS.items():
        folder = common_dir / relative_folder
        if not folder.is_dir():
            missing.append(relative_folder)
            continue
        for file in sorted(folder.rglob("*.txt")):
            relative_path = file.relative_to(game_root).as_posix()
            file_hash = sha256(file)
            fingerprint.update(relative_path.encode("utf-8"))
            fingerprint.update(file_hash.encode("ascii"))
            status = "success"
            error = ""
            keys = []
            try:
                parsed = ExtractorCommon(str(file))
                parsed.unquote()
                if isinstance(parsed.data, dict):
                    keys = list(parsed.data.keys())
            except Exception as exc:
                status = "failed"
                error = f"{type(exc).__name__}: {exc}"
                parse_errors.append(f"{relative_path}: {error}")
            tables.row(
                "game_definition_files_raw.csv",
                {
                    "definition_group": group,
                    "relative_path": relative_path,
                    "source_bytes": file.stat().st_size,
                    "source_sha256": file_hash,
                    "definition_key_count": len(keys),
                    "parse_status": status,
                    "parse_error": error,
                },
            )
            for key in keys:
                tables.row(
                    "game_definition_keys_raw.csv",
                    {
                        "definition_group": group,
                        "definition_key": key,
                        "relative_path": relative_path,
                    },
                )
            file_count += 1
            key_count += len(keys)

    if missing:
        raise RuntimeError("Required game/common folders are missing: " + ", ".join(missing))
    if parse_errors:
        raise RuntimeError(
            f"{len(parse_errors)} game definition file(s) could not be parsed. First error: "
            + parse_errors[0]
        )

    steam_manifest = parse_steam_manifest(game_root)
    version_files = parse_game_version_files(game_root)
    if not version_files["installed_game_version"]:
        version_files["installed_game_version"] = steam_manifest.get("steam_beta_key", "")
    environment = {
        "game_root": str(game_root),
        "discovery_source": discovery_source,
        "common_directory": str(common_dir),
        "localization_directory": str(game_root / "game/localization"),
        "definition_groups": DEFINITION_GROUPS,
        "definition_file_count": file_count,
        "definition_key_count": key_count,
        "definition_fingerprint_sha256": fingerprint.hexdigest().upper(),
        **steam_manifest,
        **version_files,
    }
    return environment


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def detect_save_format(path: Path) -> str:
    with path.open("rb") as handle:
        header = handle.readline()
        probe = handle.read(64)
    if not header.startswith(b"SAV"):
        return "unknown"
    if probe.startswith(b"PK\x03\x04"):
        return "compressed_zip_binary"
    if b"\x00" in probe:
        return "binary"
    if probe.lstrip().startswith(b"meta_data") or b"=" in probe:
        return "debug_plain_text"
    return "unknown"


def safe_name(path: Path) -> str:
    value = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in path.stem)
    return value[:80] or "save"


def extract_save(source: Path, work_root: Path) -> Path:
    folder = work_root / f"{safe_name(source)}_{sha256(source)[:12]}"
    folder.mkdir(parents=True, exist_ok=False)
    result = extract_native(str(source), str(folder))
    if result is None:
        plain = folder / "save.txt"
        melt(str(source), str(plain))
        parsed = ExtractorSave(str(plain))
        parsed.write(str(folder), separate=True)
        pops = retrieve_from_tree(parsed.data, ["pops", "database"], null={})
        if not write_columns(str(folder), "pop", pops):
            raise RuntimeError("Failed to create pop column cache")
        plain.unlink(missing_ok=True)
    if not (folder / "extracted_save").is_dir():
        raise RuntimeError("Extraction finished without extracted_save data")
    return folder


def find_country_id(countries: dict, tag: str) -> str:
    for country_id, country in countries.items():
        if isinstance(country, dict) and country.get("definition") == tag:
            return str(country_id)
    raise ValueError(f"Country {tag} is not present in this save")


def json_text(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def decode(vocabs: dict, field: str, code) -> str:
    try:
        return vocabs[field][int(code)]
    except (KeyError, IndexError, TypeError, ValueError):
        return ""


def raw_value(value):
    if isinstance(value, (str, int, float, bool)) or value is None:
        return "" if value is None else value
    return json_text(value)


def scalar_rows(base: dict, section_name: str, section: dict):
    for key, value in section.items():
        if not isinstance(value, (dict, list)):
            yield {
                **base,
                "source_section": section_name,
                "field_name": key,
                "raw_value": raw_value(value),
            }


def trend_rows(base: dict, country: dict):
    for trend_name in ("gdp", "avgsoltrend", "literacy"):
        channels = country.get(trend_name, {}).get("channels", {})
        for channel, node in channels.items():
            values = node.get("values", {}).get("value", [])
            for position, value in enumerate(values):
                yield {
                    **base,
                    "trend_name": trend_name,
                    "channel": channel,
                    "channel_date": node.get("date", ""),
                    "stored_index": node.get("index", ""),
                    "value_position": position,
                    "raw_value": value,
                }


def budget_slot_rows(base: dict, country: dict):
    budget = country.get("budget", {})
    for direction, key in (("income", "weekly_income"), ("expense", "weekly_expenses")):
        values = budget.get(key, {}).get("value", [])
        for index, value in enumerate(values):
            yield {**base, "direction": direction, "slot_index": index, "raw_value": value}


def pop_rows(base: dict, folder: Path, state_ids: set[str]):
    loaded = load_columns(str(folder), "pop")
    if loaded is None:
        raise RuntimeError("The extracted save has no usable pop columns")
    columns, vocabs, ids = loaded
    locations = np.asarray(columns["location"])
    indices = np.flatnonzero(np.isin(locations, np.asarray([int(x) for x in state_ids])))

    def col(name, index, default=""):
        values = columns.get(name)
        return default if values is None else values[index].item()

    for index in indices:
        yield {
            **base,
            "pop_id": int(ids[index]),
            "location_state_id": int(col("location", index, -1)),
            "pop_type": decode(vocabs, "type", col("type", index, -1)),
            "workforce": int(col("workforce", index, 0)),
            "dependents": int(col("dependents", index, 0)),
            "workplace_building_id": int(col("workplace", index, -1)),
            "has_workplace": bool(col("has_workplace", index, False)),
            "culture_id": int(col("culture", index, -1)),
            "religion": decode(vocabs, "religion", col("religion", index, -1)),
            "num_literate": int(col("num_literate", index, 0)),
            "wealth": int(col("wealth", index, 0)),
            "previous_quality_of_life": int(col("previous_quality_of_life", index, 0)),
            "loyalists_and_radicals": float(col("loyalists_and_radicals", index, 0)),
            "political_strength": int(col("political_strength", index, 0)),
            "job_satisfaction": float(col("job_satisfaction", index, 0)),
            "partial_growth_wa": float(col("partial_growth_wa", index, 0)),
            "partial_growth_dn": float(col("partial_growth_dn", index, 0)),
            "social_class": decode(vocabs, "social_class", col("social_class", index, -1)),
            "food_security_value": float(col("food_security_value", index, 0)),
            "food_security_starvation": float(col("food_security_starvation", index, 0)),
            "food_security_state": decode(
                vocabs, "food_security_state", col("food_security_state", index, -1)
            ),
        }


def parse_save_to_tables(
    folder: Path, source: Path, source_format: str, tag: str, tables: CsvTableSet
) -> dict:
    save = load_save(
        ["meta_data", "country_manager", "states", "building_manager", "institutions", "laws"],
        str(folder),
    )
    meta = save["meta_data"]
    countries = save["country_manager"]["database"]
    country_id = find_country_id(countries, tag)
    country = countries[country_id]
    state_ids = {str(value) for value in country["states"]["value"]}
    state_db = save["states"]["database"]
    state_names = {
        state_id: state_db.get(state_id, {}).get("region", state_id) for state_id in state_ids
    }
    base = {
        "source_file": source.name,
        "game_version": meta.get("version", ""),
        "game_date": meta.get("game_date", ""),
        "country_id": country_id,
        "country_tag": tag,
    }

    tables.row(
        "save_metadata_raw.csv",
        {
            **base,
            "source_sha256": sha256(source),
            "source_bytes": source.stat().st_size,
            "source_format": source_format,
            "save_game_version": meta.get("save_game_version", ""),
            "save_name": meta.get("name", ""),
            "rank": meta.get("rank", ""),
            "achievement_eligibility": meta.get("achievement_eligibility", ""),
            "ironman": meta.get("ironman", ""),
            "number_of_players": meta.get("number_of_players", ""),
        },
    )

    tables.rows(
        "country_scalar_fields_raw.csv",
        scalar_rows(base, "country.pop_statistics", country.get("pop_statistics", {})),
    )
    tables.rows(
        "country_scalar_fields_raw.csv",
        scalar_rows(base, "country.budget", country.get("budget", {})),
    )
    tables.rows("country_trend_values_raw.csv", trend_rows(base, country))
    tables.rows("budget_slots_raw.csv", budget_slot_rows(base, country))
    tables.rows("pop_records_raw.csv", pop_rows(base, folder, state_ids))

    for building_id, building in save["building_manager"]["database"].items():
        if not isinstance(building, dict) or str(building.get("state")) not in state_ids:
            continue
        state_id = str(building.get("state", ""))
        tables.row(
            "building_records_raw.csv",
            {
                **base,
                "building_id": building_id,
                "state_id": state_id,
                "state_key": state_names.get(state_id, state_id),
                "building_key": building.get("building", ""),
                "levels": building.get("levels", ""),
                "last_updated_level": building.get("last_updated_level", ""),
                "active": building.get("active", ""),
                "staffing": building.get("staffing", ""),
                "previous_staffing": building.get("previous_staffing", ""),
                "establishment_date": building.get("establishment_date", ""),
                "throughput": building.get("throughput", ""),
                "salary_rate": building.get("salary_rate", ""),
                "cash_reserves": building.get("cash_reserves", ""),
                "goods_cost": building.get("goods_cost", ""),
                "goods_sales": building.get("goods_sales", ""),
                "profit_after_reserves": building.get("profit_after_reserves", ""),
                "profit_after_investments": building.get("profit_after_investments", ""),
                "input_goods_shortage": building.get("input_goods_shortage", ""),
                "production_methods_json": json_text(building.get("production_methods", {})),
                "owners_json": json_text(building.get("owners", {})),
                "input_goods_json": json_text(building.get("input_goods", {})),
                "output_goods_json": json_text(building.get("output_goods", {})),
                "raw_record_json": json_text(building),
            },
        )

    for state_id in sorted(state_ids, key=int):
        state = state_db.get(state_id, {})
        state_base = {
            **base,
            "state_id": state_id,
            "state_key": state_names.get(state_id, state_id),
        }
        tables.row(
            "state_records_raw.csv",
            {
                **state_base,
                "incorporation": state.get("incorporation", ""),
                "arable_land": state.get("arable_land", ""),
                "land": state.get("land", ""),
                "infrastructure": state.get("infrastructure", ""),
                "infrastructure_usage": state.get("infrastructure_usage", ""),
                "trade_capacity": state.get("trade_capacity", ""),
                "trade_capacity_usage": state.get("trade_capacity_usage", ""),
                "base_pop_bureaucracy_cost": state.get("base_pop_bureaucracy_cost", ""),
                "raw_record_json": json_text(state),
            },
        )
        for key, value in state.get("pop_statistics", {}).items():
            if not isinstance(value, (dict, list)):
                tables.row(
                    "state_pop_statistics_raw.csv",
                    {**state_base, "field_name": key, "raw_value": raw_value(value)},
                )

    for record_id, institution in save["institutions"]["database"].items():
        if not isinstance(institution, dict) or str(institution.get("country")) != country_id:
            continue
        tables.row(
            "institutions_raw.csv",
            {
                **base,
                "institution_record_id": record_id,
                "institution_key": institution.get("institution", ""),
                "investment": institution.get("investment", ""),
                "raw_record_json": json_text(institution),
            },
        )

    for record_id, law in save["laws"]["database"].items():
        if not isinstance(law, dict) or str(law.get("country")) != country_id:
            continue
        tables.row(
            "laws_raw.csv",
            {
                **base,
                "law_record_id": record_id,
                "law_key": law.get("law", ""),
                "active": law.get("active", ""),
                "activation_date": law.get("activation_date", ""),
                "replace": law.get("replace", ""),
                "raw_record_json": json_text(law),
            },
        )

    for queue_kind, queue_key in (("government", "government_queue"), ("private", "private_queue")):
        elements = country.get(queue_key, {}).get("construction_elements", {})
        for position, element in elements.items():
            if not isinstance(element, dict):
                continue
            state_id = str(element.get("state", ""))
            tables.row(
                "construction_queue_raw.csv",
                {
                    **base,
                    "queue_kind": queue_kind,
                    "position": position,
                    "building_key": element.get("type", ""),
                    "state_id": state_id,
                    "state_key": state_names.get(state_id, state_id),
                    "construction_left": element.get("construction_left", ""),
                    "construction_speed": element.get("construction_speed", ""),
                    "base_construction_speed": element.get("base_construction_speed", ""),
                    "identity_json": json_text(element.get("identity", {})),
                    "raw_record_json": json_text(element),
                },
            )

    return {
        "game_version": meta.get("version", ""),
        "game_date": meta.get("game_date", ""),
        "country_id": country_id,
        "country_tag": tag,
    }


def export_all(input_dir: Path, output_dir: Path, tag: str, game_dir: str | None) -> Path:
    saves = sorted(input_dir.glob("*.v3"))
    if not saves:
        raise FileNotFoundError(f"No .v3 files found in {input_dir}")
    game_root, discovery_source = discover_game_root(game_dir)

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    package = output_dir / f"V3_raw_export_{run_id}"
    data_dir = package / "raw_data"
    work_dir = package / "_temporary_extracted"
    data_dir.mkdir(parents=True, exist_ok=False)
    work_dir.mkdir()
    log_path = package / "export_log.txt"
    tables = CsvTableSet(data_dir)
    file_manifest = []
    errors = []

    try:
        with log_path.open("w", encoding="utf-8") as log:
            with redirect_stdout(Tee(sys.stdout, log)), redirect_stderr(Tee(sys.stderr, log)):
                print(f"Tool: {TOOL_VERSION}")
                print(f"OS: {platform.platform()}")
                print(f"Python: {sys.version}")
                print(f"Input: {input_dir}")
                print(f"Files: {len(saves)}")
                print(f"Victoria 3 directory: {game_root}")
                print(f"Game directory source: {discovery_source}")
                print("Reading version-matched definitions from game/common ...")
                game_environment = collect_game_definitions(
                    game_root, discovery_source, tables
                )
                print(
                    "Definitions: "
                    f"{game_environment['definition_file_count']} files, "
                    f"{game_environment['definition_key_count']} top-level keys"
                )
                print(
                    "Definition fingerprint: "
                    + game_environment["definition_fingerprint_sha256"]
                )
                for index, save_path in enumerate(saves, 1):
                    print(f"\n[{index}/{len(saves)}] {save_path.name}")
                    source_format = detect_save_format(save_path)
                    record = {
                        "name": save_path.name,
                        "bytes": save_path.stat().st_size,
                        "sha256": sha256(save_path),
                        "format": source_format,
                        "status": "pending",
                    }
                    extracted = None
                    try:
                        if platform.system() == "Darwin" and source_format != "debug_plain_text":
                            raise RuntimeError(
                                "macOS can only parse Debug-mode plain-text saves in this toolkit. "
                                "Keep the original unchanged and send it to the Windows exporter."
                            )
                        extracted = extract_save(save_path, work_dir)
                        identity = parse_save_to_tables(
                            extracted, save_path, source_format, tag, tables
                        )
                        record.update(identity)
                        installed_version = game_environment.get("installed_game_version", "")
                        record["installed_game_version"] = installed_version
                        record["definition_version_match"] = (
                            identity["game_version"] == installed_version
                            if installed_version
                            else "unknown"
                        )
                        record["status"] = "success"
                        print(
                            f"SUCCESS {identity['game_date']} v{identity['game_version']} "
                            "raw tables written"
                        )
                    except Exception as exc:
                        record["status"] = "failed"
                        record["error"] = f"{type(exc).__name__}: {exc}"
                        errors.append({"source_file": save_path.name, "error": record["error"]})
                        tables.row("errors.csv", errors[-1])
                        print(f"FAILED: {record['error']}")
                        traceback.print_exc()
                    finally:
                        if extracted is not None and extracted.exists():
                            shutil.rmtree(extracted)
                    file_manifest.append(record)
    finally:
        tables.close()

    if work_dir.exists():
        shutil.rmtree(work_dir)

    manifest = {
        "tool_version": TOOL_VERSION,
        "created_at_local": datetime.now().astimezone().isoformat(),
        "operating_system": platform.platform(),
        "python_version": sys.version,
        "country_tag": tag,
        "game_environment": game_environment,
        "files": file_manifest,
        "successful_files": sum(row["status"] == "success" for row in file_manifest),
        "failed_files": len(errors),
        "data_contract": "raw_only",
        "not_calculated": [
            "industrial basket totals or shares",
            "building-type or state aggregates",
            "building employment totals",
            "population totals",
            "radical or loyalist shares",
            "strata weighted means or gaps",
            "growth rates or changes",
            "fiscal net balance",
        ],
        "notes": [
            "Input saves were read only and were not moved, renamed, or modified.",
            "Game definitions were read from the installed Victoria 3 game/common directory.",
            "Definition files and top-level keys were exported without constructing research variables.",
            "Rows are flattened source records. Students construct analytical variables later.",
            "building_records_raw.csv contains every Belgium building record without basket filtering.",
            "pop_records_raw.csv retains workplace and workforce so employment can be joined later.",
            "loyalists_and_radicals is the signed raw pop value: positive loyalist, negative radical.",
        ],
    }
    (package / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (package / "game_environment.json").write_text(
        json.dumps(game_environment, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    archive = Path(shutil.make_archive(str(package), "zip", root_dir=package))
    print(f"\nCompleted: {manifest['successful_files']} success, {manifest['failed_files']} failed")
    print(f"Folder: {package}")
    print(f"Zip: {archive}")
    if errors:
        raise RuntimeError(f"{len(errors)} save(s) failed. Outputs remain in {package}.")
    return package


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", "--input", dest="input_dir", default="../input_saves")
    parser.add_argument("--output-dir", "--output", dest="output_dir", default="../output_packages")
    parser.add_argument("--tag", default="BEL")
    parser.add_argument("--game-dir", default=None)
    args = parser.parse_args()
    input_dir = (ROOT / args.input_dir).resolve()
    output_dir = (ROOT / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        export_all(input_dir, output_dir, args.tag, args.game_dir)
        return 0
    except Exception as exc:
        print(f"EXPORT STOPPED: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


