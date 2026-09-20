"""Small synthetic regression cases; never modifies research input packages."""
import copy
import csv
import json
import tempfile
import unittest
from pathlib import Path

from merge_raw_exports import MergeError, digest, integrate, iso_date, read_json, write_csv, write_json


class MergeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.raw = self.root / "raw"
        self.raw.mkdir()
        full = read_json(Path(__file__).resolve().parents[1] / "config/raw_merge_rules.json")
        self.rules = copy.deepcopy(full)
        self.rules["tables"] = {name: full["tables"][name] for name in ("save_metadata_raw.csv", "building_records_raw.csv")}
        self.rules["required_nonempty_per_save"] = list(self.rules["tables"])

    def package(self, run="SL_01", folder="one", day="1837.1.1", version_match=True, fingerprint="A" * 64, failed=0, save_hash="B" * 64):
        package = self.raw / run / folder
        (package / "raw_data").mkdir(parents=True)
        entry = dict(name="autosave.v3", sha256=save_hash, bytes=100, status="success",
                     game_date=day, game_version="1.13.10", country_tag="BEL", country_id="25",
                     definition_version_match=version_match)
        environment = dict(installed_game_version="1.13.10", definition_fingerprint_sha256=fingerprint)
        entries = [entry]
        if failed:
            entries.append(dict(name="broken.v3", sha256="C" * 64, status="failed"))
        write_json(package / "manifest.json", dict(files=entries, successful_files=1, failed_files=failed,
                   data_contract="raw_only", tool_version=self.rules["tool_version"], country_tag="BEL", game_environment=environment))
        write_json(package / "game_environment.json", environment)
        for name, spec in self.rules["tables"].items():
            row = dict.fromkeys(spec["columns"], "")
            row.update(source_file=entry["name"], game_date=day, game_version="1.13.10", country_id="25", country_tag="BEL")
            if name.startswith("save_metadata"):
                row.update(source_sha256=entry["sha256"], source_bytes="100")
            else:
                row.update(building_id="1", state_id="2", building_key="building_railway", levels="0", staffing="NA", cash_reserves="")
            write_csv(package / "raw_data" / name, spec["columns"], [row])
        return package

    def run_merge(self, mode="pilot"):
        return integrate(self.raw, self.root / "result", self.rules, mode)

    def test_two_runs_and_exact_missing_values_and_read_only(self):
        self.package()
        self.package(run="FL_01")
        before = {p: digest(p) for p in self.raw.rglob("*") if p.is_file()}
        result = self.run_merge()
        self.assertEqual(result["save_count"], 2)
        self.assertFalse(result["formal_sample_ready"])
        self.assertEqual(before, {p: digest(p) for p in before})
        with (self.root / "result/building_records_merged.csv").open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual({r["run_id"] for r in rows}, {"SL_01", "FL_01"})
        self.assertEqual(rows[0]["levels"], "0")
        self.assertEqual(rows[0]["staffing"], "NA")
        self.assertEqual(rows[0]["cash_reserves"], "")
        self.assertEqual(rows[0]["game_date"], "1837-01-01")
        self.assertEqual(rows[0]["game_date_raw"], "1837.1.1")
        self.assertEqual(rows[0]["building_key"], "building_railway")

    def test_same_filename_different_package_dates_is_not_duplicate(self):
        self.package()
        self.package(folder="two", day="1838.1.1")
        self.assertEqual(self.run_merge()["save_count"], 2)

    def test_duplicate_dates_are_quarantined_not_arbitrarily_deduplicated(self):
        self.package()
        self.package(folder="two", save_hash="E" * 64)
        self.package(run="FL_01")
        self.assertEqual(self.run_merge()["saves_by_run"], {"FL_01": 1})

    def test_identical_save_copy_counted_once(self):
        self.package()
        self.package(folder="two")
        self.package(run="FL_01")
        self.assertEqual(self.run_merge()["saves_by_run"], {"SL_01": 1, "FL_01": 1})

    def test_failed_package_and_version_mismatch_are_excluded(self):
        self.package(failed=1)
        self.package(folder="two", day="1838.1.1", version_match=False)
        self.package(run="FL_01")
        self.assertEqual(self.run_merge()["saves_by_run"], {"FL_01": 1})

    def test_fingerprint_mismatch_stops(self):
        self.package()
        self.package(run="FL_01", fingerprint="D" * 64)
        with self.assertRaisesRegex(MergeError, "fingerprints differ"):
            self.run_merge()
        self.assertEqual(read_json(self.root / "result/merge_summary.json")["status"], "failed")

    def test_schema_change_stops(self):
        p = self.package() / "raw_data/building_records_raw.csv"
        p.write_text(p.read_text(encoding="utf-8-sig").replace("levels,", "unexpected_levels,", 1), encoding="utf-8-sig")
        with self.assertRaisesRegex(MergeError, "Schema changed"):
            self.run_merge()

    def test_invalid_number_stops(self):
        p = self.package() / "raw_data/building_records_raw.csv"
        with p.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            columns, rows = reader.fieldnames, list(reader)
        rows[0]["levels"] = "not a number"
        write_csv(p, columns, rows)
        with self.assertRaisesRegex(MergeError, "Invalid numeric"):
            self.run_merge()

    def test_duplicate_entity_key_stops(self):
        p = self.package() / "raw_data/building_records_raw.csv"
        text = p.read_text(encoding="utf-8-sig")
        p.write_text(text + text.splitlines()[1] + "\n", encoding="utf-8-sig")
        with self.assertRaisesRegex(MergeError, "Duplicate row key"):
            self.run_merge()

    def test_full_mode_rejects_incomplete_pilot(self):
        self.package()
        with self.assertRaisesRegex(MergeError, "planned schedule"):
            self.run_merge(mode="full")

    def test_invalid_dates_and_hour(self):
        self.assertEqual(iso_date("1846.4.19.12"), "1846-04-19")
        for day in ("1846.2.30", "1846.4.19.99", "unknown"):
            with self.assertRaises(MergeError):
                iso_date(day)


if __name__ == "__main__":
    unittest.main()
