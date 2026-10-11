# 近几届奥运会反兴奋剂数据（按运动项目）

数据抓取日期：2026 年。全部数据由脚本从官方 PDF 提取，并做算术校验。

## 一、重要前提：「兴奋剂使用数据」的正确读法

官方并不公布「各项目有多少人使用兴奋剂」。可获得的官方量度只有两类：

1. **检测量（tests / samples / analyses）**——按项目统计的检查次数。
   这是**风险评估与资源分配**的结果，**不能**直接当作各项目兴奋剂流行率：
   队员人数多、历史违规多、生理风险高的项目天然被查得多。
2. **阳性结果（AAF，Adverse Analytical Finding）**——每个赛事只有个位数到十几例，
   其中相当一部分最终判定为「无违规」（持证用药 TUE、允许途径、无过失等）。

本数据集提供的是「**检测量 + 阳性案件**」组合，而非流行率。

## 二、数据来源（全部为官方一手文件）

| 赛事 | 来源文件 | 链接 |
|---|---|---|
| Paris 2024 | WADA《Independent Observer Report — 2024 Summer Olympic Games, Paris》 | https://www.wada-ama.org/sites/default/files/2025-10/io_report_paris_2024_olympic_games_final1.pdf |
| Tokyo 2020 | WADA《Report of the Independent Observers — Olympic Games Tokyo 2020》 | https://www.wada-ama.org/sites/default/files/2022-01/IO%20Report_2020%20Tokyo%20Olympic%20Games_Final.pdf |
| Beijing 2022 | WADA《IO Report — Olympic Winter Games Beijing 2022》 | https://www.wada-ama.org/sites/default/files/2022-07/2022_beijing_io_report_olympic_winter_games_final_en.pdf |
| Rio 2016 | WADA《IO Team Report — Rio 2016》（**无分项目表，仅总数与阳性清单**） | https://www.wada-ama.org/sites/default/files/resources/files/rio2016_io_team_report_26102016.pdf |
| Rio 2016（分项目数据） | WADA《2016 Anti-Doping Testing Figures》Testing Authority Report | https://www.wada-ama.org/sites/default/files/resources/files/2016_anti-doping_testing_figures.pdf |
| Paris 2024（赛前） | ITA《Paris 2024 Pre-Games Report》 | https://ita.sport/uploads/2024/11/ITA_Paris-2024-pre-Games-Report.pdf |

各赛事数据所在页：
- Paris 2024：IO 报告 p.75–77（检测量）、p.78–79（样本类型）、p.80（阳性清单）
- Tokyo 2020：IO 报告 p.43–44（检测量表）、p.45（阳性清单）
- Beijing 2022：IO 报告 p.51（样本表）、p.45（阳性清单）
- Rio 2016：IO 报告 p.34（总数）、p.54–55（阳性清单）；WADA 2016 Figures p.205–246（Table 26–53，各项目 IOC 行）

## 三、口径差异（务必注意，四个赛事互不可比）

| 赛事 | 计量单位 | 总量 | 统计区间 | 数据基础 |
|---|---|---|---|---|
| Tokyo 2020 | analyses（尿/血/ABP 各类分析次数） | **6,349** | 2021-07-13 ~ 08-08 | 赛事期，IOC/ITA |
| Paris 2024 | doping controls（1 次检查含同一运动员同次采样的全部样本） | **4,783** | 2024-07-18 ~ 08-11 | 赛事期，IOC/ITA |
| Paris 2024 | samples（实际采集样本数） | **6,217** | 同上 | 同上 |
| Beijing 2022 | samples | **3,166** | 冬奥会期 | 赛事期，IOC/ITA |
| **Rio 2016** | samples | **4,952** | **2016 整个日历年** | **IOC 作为检测机构（含少量非 Rio 检测）** |

Rio 2016 需要特别注意（也是它与其他三届不可比的原因）：

1. Rio 的 WADA IO 报告**没有分项目表**——只有总数（计划 5,380、实际 IOC 采集 4,660、其他检测机构 222、合计 4,882）
   和 28 条阳性清单。分项目数据只能取自 WADA《2016 Testing Figures》中 **IOC 作为检测机构（Testing Authority）** 的行。
2. 该口径为**整个 2016 日历年**且**以 IOC 为检测机构**，故 4,952 比 Rio 赛事期的 4,660 多约 292 个样本（约 6%，
   为 IOC 在 2016 年的其他检测）。**引用时请标注这一口径。**
3. 该口径的 AAF 数（33）与 Rio 赛事期阳性清单（28 条）**不是同一概念**：前者为 2016 年度 IOC 报告的全部 AAF，
   可能含对往届样本的复检结果；后者为 Rio 赛事期内样本的发现（其中 14 条最终为 TUE）。

## 四、与各机构官方通稿的口径差异（已核对）

| 赛事 | 本数据集（IO/Figures 报告） | 官方通稿 | 说明 |
|---|---|---|---|
| Paris 2024 | 4,783 次检查 / 6,217 样本 / 4,154 名受检 | 4,770+ 次检查 / 6,130 样本 / 4,150 名运动员 | 通稿为赛后即时数，IO 为最终核定数 |
| Beijing 2022 | 3,166 样本 / 1,620 名受检 | 「3,100+ 样本 / 1,600+ 名受检」 | 一致 |
| Tokyo 2020 | 6,349 分析 / 4,125 名受检 | 6,200 样本 / 4,255 名受检 | 统计口径与截止时间不同 |
| Rio 2016 | IOC 口径 4,952 样本 | Rio IO 报告：IOC 赛事期采集 4,660 | 口径不同（日历年 vs 赛事期） |

## 五、原始文件内部不自洽之处（已保留原值，未擅自修正）

1. **Tokyo 2020 · Weightlifting**：尿样 IC(170) + OOC(77) = 247，但印刷的 Urine Total 为 **246**。
   （血样 44+43=87 ✓，ABP 3 ✓，Grand Total 246+87+3=336 ✓ → 系原文件印刷笔误）
2. **Paris 2024 · Aquatics / Swimming Sprint 100m or less**：
   IC 合计 172 + OOC 合计 131 = 303，但印刷的 Grand Total 为 **302**；
   导致 Aquatics 项目小计（872）比其分项之和（871）多 1。

除上述两处外，**Paris / Tokyo / Beijing 共 192 行数据的加总关系全部通过校验**：
- 各组 IC + OOC = Total
- 各项目 Grand Total = 各分项 Total 之和
- （Paris / Beijing）各项目合计 = 印刷的 Grand Total 行（完全一致）

Rio 数据取自汇总表（无分项目明细可校验），已核对 28 个项目全部为夏季奥运项目，且 Winter 表（Lillehammer 2016 YOG，
131 样本）已剔除。

## 六、文件说明

| 文件 | 内容 |
|---|---|
| `combined_by_sport.csv` | **推荐入口**。全部赛事统一长表：赛事 / 单位 / 项目 / 分项 / 层级 / 赛内 / 赛外 / 合计 |
| `paris_tests.csv` | Paris 2024 检查次数（按项目 + 分项）：ic, ooc, grand |
| `paris_samples.csv` | Paris 2024 样本数（尿/血/ABP/DBS 细分） |
| `tokyo.csv` | Tokyo 2020 分析次数（尿/血/ABP × IC/OOC） |
| `beijing.csv` | Beijing 2022 样本数（尿/血/ABP/DBS × IC/OOC） |
| `rio2016_by_sport.csv` | Rio 2016，IOC 口径样本数（尿/血 × IC/OOC，含 ATF/AAF 列） |
| `adverse_findings_all_games.csv` | Paris / Tokyo / Beijing 阳性清单（29 条） |
| `rio2016_games_findings.csv` | Rio 2016 赛事期阳性清单（28 条，含 TUE 与待决） |

`level` 列取值：`sport`（项目合计行）/ `discipline`（分项行）/ `TOTAL`（总合计行）。
**汇总时请只取 `level == 'sport'`，否则分项会被重复计算。**

## 七、阳性案件概况

| 赛事 | 记录在案 | 其中构成 ADRV（违规） | 备注 |
|---|---|---|---|
| Rio 2016 | 28 | 10（14 条 TUE、4 条待决） | 自行车 4、举重 4、体操 4、水上 6（多为 TUE） |
| Tokyo 2020 | 10 | 6 | 田径 5、水上 1 等 |
| Paris 2024 | 12（含 1 例 ATF） | 5 | ITA 通稿亦称「5 例违规」，与该报告一致 |
| Beijing 2022 | 7 | — | **报告未公布对应项目**，仅列禁用物质与类别 |

Beijing 2022 的 IO 报告在阳性表中只列出物质（如 dehydrochloromethyltestosterone、brinzolamide、clostebol）
与 WADA 分类，**未标注运动项目**，故该项目留空为 "Not published"。
另注：该实验室共报告 13 例 AAF，其中 6 例来自 WADA 双盲质控样本，不计入赛事期间样本。

## 八、复现方式

脚本：`scripts/`（`build.py` 坐标解析、`pipeline.py` 表结构切分、`emit.py` 导出）。
解析方法：按 PDF 文字坐标聚类列位置（右对齐数字列），用**加总恒等式**自动校验列映射是否正确，
再用字体加粗（Arial-BoldMT）区分「项目合计行」与「分项行」。
