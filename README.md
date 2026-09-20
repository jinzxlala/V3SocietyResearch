# V3SocietyReseaarch
基于维多利亚3的社会研究模拟

## 第04部分：原始表整合（两组测试）

将解压后的导出包放在 `data/raw/SL_01/`、`data/raw/FL_01/` 等组别目录。
使用 Python 3.11 或更新版本，在仓库根目录运行：

```console
python scripts/merge_raw_exports.py --mode pilot
```

结果写入新的 `data/interim/pilot_运行时间/` 文件夹，原始数据保持不变。
当前试运行只使用两组不完整数据，不代表200个正式观察点已经齐全。

- [运行说明与处理规则](docs/weekly/step04_raw_merge.md)
- [最新自查报告（24项测试）](reports/validation/step04_selfcheck_20260920/README.md)
- [初次试运行报告](reports/validation/step04_pilot_20260920/README.md)
- [来源及排除记录](data/manifests/step04_source_inventory.csv)
- [固定列结构与主键配置](config/raw_merge_rules.json)
