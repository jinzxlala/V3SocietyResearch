# 第04部分试运行报告（2026-09-20）

状态：整合测试通过；正式样本验收尚未完成。

输入：仓库本地 `data/raw/SL_01`、`data/raw/FL_01` 中解压后的导出包。James 已确认组别归属。本次不要求每组25份，不补缺失观察点，不生成第06部分的研究派生变量。

## 纳入结果

- FL_01：5份，1836-01-01 至 1840-01-01。
- SL_01：13份，1836-01-01 至 1853-08-27；日期不连续。
- 共18个测试观察点、13张整合表。起点和非计划日期保留标记，不自动计入正式年度样本。
- 工具版本：1.2.0；游戏版本：1.13.10；所有纳入文件的版本匹配标记为 true。
- 共同定义指纹：`724D5AAE11087DCB5A241454C3524AF79B2D4E2284DA6B37CE65C5EA82271312`。

| 整合表 | 行数 |
|---|---:|
| `budget_slots_merged.csv` | 684 |
| `building_records_merged.csv` | 922 |
| `construction_queue_merged.csv` | 154 |
| `country_scalar_fields_merged.csv` | 658 |
| `country_trend_values_merged.csv` | 12,870 |
| `game_definition_files_merged.csv` | 1,377 |
| `game_definition_keys_merged.csv` | 66,591 |
| `institutions_merged.csv` | 25 |
| `laws_merged.csv` | 2,358 |
| `pop_records_merged.csv` | 4,644 |
| `save_metadata_merged.csv` | 18 |
| `state_pop_statistics_merged.csv` | 729 |
| `state_records_merged.csv` | 42 |

两张游戏定义表保留每个导出包的定义记录，行数不能解释为独立观察点。

## 排除和未解决事项

1. `SL_01/V3_raw_export_20260920_151919` 的 manifest 有1份失败。整包隔离，其中1846-04-19革命现场的成功记录也未进入本次合并。应另行排查或重新导出该包，不能手工修改 manifest 使其通过。
2. SL_01 的 `autosave_exit.v3` 与 `比利时_1836_01_01 START.v3` 日期和 SHA-256 完全相同，只计一次。两个名称及排除原因保留在来源清单。
3. 数据主要是1月1日，另有1853-08-27记录，与既有12月31日年度计划不同。保留实际日期，未移到上一年，也未填充缺失年份。
4. 其余六组尚未纳入。本次不得写成八组、200个观察点或正式研究验收通过。
5. 原始数据已存在的默认0，本脚本无法自动判断是否代表真实0。机构实际等级、人口合理性及实验偏离需要第05部分另行验证。

## 已执行的验证

- 11项自动测试全部通过，覆盖重复、错误版本、异常数值、列变化和缺失值保留等情况。
- 以相同输入再运行一次，13张整合表的 SHA-256 全部一致。
- 逐行核对共 91,072 行：原始字段与源 CSV 对应行一致；标准化日期能通过 `game_date_raw` 查回原值。
- 运行前后复核读取的输入文件哈希，保持一致。没有覆盖源 CSV、改名或更改存档。

## 输出与复现

本机最终数据位于 `data/interim/step04_pilot_verified_20260920/`；第一次预运行与复跑结果单独保留，不是额外样本。

在取得相同输入包后，运行：

```console
python scripts/merge_raw_exports.py --mode pilot
python -B -m unittest discover -s scripts -p "test_merge*.py" -v
```

请先检查新输出的 `merge_summary.json` 中 `status=success`，再读取整合表。`formal_sample_ready=false` 是预期状态，第04部分不代替后续研究验收。

本目录保存小型验证记录；来源决定和输入哈希见 `data/manifests/step04_source_inventory.csv`、`step04_input_hashes.csv`。无个人电脑绝对路径。共享原始数据的外部位置仍需由两人登记。
