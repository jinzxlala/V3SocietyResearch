"""Definition-table consistency cases using temporary, synthetic export packages."""
import copy
import csv
import hashlib
import tempfile
import unittest
from pathlib import Path

from merge_raw_exports import MergeError, digest, integrate, read_json, write_csv, write_json


class DefinitionIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.raw = self.root / "raw"
        self.package = self.raw / "SL_01" / "definitions"
        (self.package / "raw_data").mkdir(parents=True)
        full = read_json(Path(__file__).resolve().parents[1] / "config/raw_merge_rules.json")
        self.rules = copy.deepcopy(full)
        names = ("game_definition_files_raw.csv", "game_definition_keys_raw.csv",
                 "save_metadata_raw.csv", "building_records_raw.csv")
        self.rules["tables"] = {name: full["tables"][name] for name in names}
        self.rules["required_nonempty_per_save"] = ["save_metadata_raw.csv", "building_records_raw.csv"]
        self.files = [
            dict(definition_group="buildings", relative_path="game/common/buildings/01_industry.txt",
                 source_bytes="100", source_sha256="A" * 64, definition_key_count="2",
                 parse_status="success", parse_error=""),
            dict(definition_group="laws", relative_path="game/common/laws/00_laws.txt",
                 source_bytes="80", source_sha256="B" * 64, definition_key_count="1",
                 parse_status="success", parse_error=""),
        ]
        self.keys = [
            dict(definition_group="buildings", definition_key="building_railway",
                 relative_path=self.files[0]["relative_path"]),
            dict(definition_group="buildings", definition_key="building_food_industry",
                 relative_path=self.files[0]["relative_path"]),
            dict(definition_group="laws", definition_key="law_no_social_security",
                 relative_path=self.files[1]["relative_path"]),
        ]
        fingerprint = hashlib.sha256()
        for row in self.files:
            fingerprint.update(row["relative_path"].encode("utf-8"))
            fingerprint.update(row["source_sha256"].encode("ascii"))
        self.environment = dict(installed_game_version="1.13.10", definition_file_count=2,
                                definition_key_count=3,
                                definition_fingerprint_sha256=fingerprint.hexdigest().upper())
        entry = dict(name="autosave.v3", sha256="C" * 64, bytes=100, status="success",
                     game_date="1837.1.1", game_version="1.13.10", country_tag="BEL",
                     country_id="25", definition_version_match=True)
        self.manifest = dict(files=[entry], successful_files=1, failed_files=0,
                             data_contract="raw_only", tool_version=self.rules["tool_version"],
                             country_tag="BEL", game_environment=self.environment)
        self.write_environment()
        self.write_table("game_definition_files_raw.csv", self.files)
        self.write_table("game_definition_keys_raw.csv", self.keys)
        write_csv(self.package / "raw_data/errors.csv", ["source_file", "error"], [])
        for name in self.rules["required_nonempty_per_save"]:
            row = dict.fromkeys(self.rules["tables"][name]["columns"], "")
            row.update(source_file=entry["name"], game_date=entry["game_date"],
                       game_version=entry["game_version"], country_id=entry["country_id"], country_tag="BEL")
            if name == "save_metadata_raw.csv":
                row.update(source_sha256=entry["sha256"], source_bytes="100")
            else:
                row.update(building_id="1", state_id="2", building_key="building_railway",
                           levels="1", staffing="NA", cash_reserves="")
            self.write_table(name, [row])

    def write_environment(self):
        self.manifest["game_environment"] = self.environment
        write_json(self.package / "manifest.json", self.manifest)
        write_json(self.package / "game_environment.json", self.environment)

    def write_table(self, name, rows):
        write_csv(self.package / "raw_data" / name, self.rules["tables"][name]["columns"], rows)

    def run_merge(self):
        return integrate(self.raw, self.root / "result", self.rules, "pilot")

    def assert_rejected(self):
        with self.assertRaises(MergeError):
            self.run_merge()
        self.assertEqual(read_json(self.root / "result/merge_summary.json")["status"], "failed")

    def test_consistent_definition_tables_pass_and_preserve_sources(self):
        before = {path: digest(path) for path in self.raw.rglob("*") if path.is_file()}
        result = self.run_merge()
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["save_count"], 1)
        self.assertEqual(result["table_count"], 4)
        self.assertEqual(before, {path: digest(path) for path in before})
        with (self.root / "result/game_definition_keys_merged.csv").open(encoding="utf-8-sig", newline="") as stream:
            self.assertEqual(len(list(csv.DictReader(stream))), 3)

    def test_missing_definition_keys_are_rejected(self):
        # Keep both manifest/environment totals unchanged: the original bug passed this.
        self.write_table("game_definition_keys_raw.csv", [])
        self.assert_rejected()

    def test_orphan_definition_key_is_rejected_even_when_total_count_matches(self):
        self.keys[0]["relative_path"] = "game/common/buildings/not_exported.txt"
        self.write_table("game_definition_keys_raw.csv", self.keys)
        self.assert_rejected()

    def test_per_file_key_count_mismatch_is_rejected_with_valid_total(self):
        # Preserve overall count and valid references; move one key into the other file.
        self.keys[0].update(definition_group="laws", relative_path=self.files[1]["relative_path"])
        self.write_table("game_definition_keys_raw.csv", self.keys)
        self.assert_rejected()

    def test_environment_definition_file_total_mismatch_is_rejected(self):
        self.environment["definition_file_count"] = 3
        self.write_environment()
        self.assert_rejected()

    def test_environment_definition_key_total_mismatch_is_rejected(self):
        self.environment["definition_key_count"] = 4
        self.write_environment()
        self.assert_rejected()


if __name__ == "__main__":
    unittest.main()
