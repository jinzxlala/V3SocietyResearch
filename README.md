# V3SocietyResearch

基于维多利亚3的社会研究模拟

## 目录结构

| 路径                  | 用途                                     |
| --------------------- | ---------------------------------------- |
| `config/`             | 参数配置、路径映射、版本固定文件         |
| `scripts/`            | 可执行脚本（数据抓取、清洗、建模、出图） |
| `data/manifests/`     | 数据清单：来源、版本、校验和、字段说明   |
| `data/processed/`     | 清洗 / 加工后的中间产物（多为生成物）    |
| `reports/validation/` | 数据与结果的校验报告、异常记录           |
| `docs/weekly/`        | 周报与阶段性记录                         |

空目录用 `.gitkeep` 占位，保证克隆后结构完整。

## 协作方式

**不要直接在 `main` 上修改。** 请从 `main` 切出功能分支，通过 Pull Request 合并。

完整约定见 [CONTRIBUTING.md](CONTRIBUTING.md)。
