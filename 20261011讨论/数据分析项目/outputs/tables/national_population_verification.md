# 国家三阶层人口与国家统计 Y 核验

核验日期：2026-10-11。适用本批 FL_01、SL_01，游戏版本 1.13.10。原始数据只读。

## 结论与通过范围

三层社会分类互斥且覆盖人口的结构证据、国家/州字段的同存档一致性检查通过；可以按国家统计口径计算导出国家的激进派比例。不是国家人口与逐人口实体人口完全一致的验证，也不证明革命后对象身份连续。后两项限制独立保留，不因本次分母验证消失。

## 证据链

1. 本机 launcher 设置 rawVersion=1.13.10，与本批 CSV 游戏版本一致。游戏随附 game/common/social_classes/readme.md 规定每个人口群体属于唯一 social class，class 属于 lower/middle/upper 三层之一。00_default.txt 将 lower_class、middle_class、upper_class 分别映射到对应三层。相关文件的相对来源与 SHA-256 存于 config/national_population_evidence.json；执行分析不依赖游戏安装位置。
2. 本批全部人口行的 social_class 均为上述三类之一，没有缺失或其他类；同存档 pop_id 唯一。分类覆盖检查不依赖人口规模对账是否一致。
3. 本地导出程序 student_export.py 的 scalar_rows 直接保留指定 country.pop_statistics 标量；作为字段来源旁证，不将其视作全部字段语义自动通过。
4. 逐存档核对 source_file、country_id、内部日期、country_tag、版本；三个国家字段分别为单一合法非负整数；对应州字段覆盖该存档全部州且无重复。51 个存档的每一国家阶层数均与全部州的对应统计精确相等。
5. 49 个有 population_radicals 的存档，其国家值与完整州合计也精确一致。两组基线缺该字段，未按零处理。

## 计算与缺失

P_national = population_lower_strata + population_middle_strata + population_upper_strata。
Y = population_radicals / P_national，存储 0–1，显示百分比乘 100。

分母或分子字段缺失/重复/非法数值、州覆盖不完整、定义版本/分类不通过、分母为零或人数越界时保留 Y 缺失；不补零、不裁剪。共同州不能使用全国政治人数，Y 保持缺失。

全国固定年度面板共 50 行，其中 48 个 Y 有效、两个基线缺失；额外事件表 1 个 Y 有效。年度面板没有增加事件权重。本次未计算均值、峰值或首末变化。

## 示例：1850-01-01

| run | 国家三层总人口 | 国家激进派 | 国家统计 Y（%） |
| --- | ---: | ---: | ---: |
| FL_01 | 3,307,559 | 646,144 | 19.535373 |
| SL_01 | 4,549,710 | 744,681 | 16.367659 |

## 保留的限制

国家分层人口与逐人口实体按阶层汇总仍有 118 个“存档×阶层”差异（不是独立人口或 run 数）。不修改原始数值，也没有证据认定差异必然来自缓存、取整或更新时点。国家/州统计相等是同一统计体系的内部一致性证据，不是与独立游戏界面总人口的逐期一致性证明。

本次 Y 的含义限定为导出国家统计比例；革命后新政府/操控对象是否与导出对象连续仍待具体证据。不得把可计算状态写成已排除身份混淆，也不自动形成正式的连续研究对象政治结论。游戏社会分类文档适用于该版本的规则，不证明其他版本或 mod 没有改变分类。

## 可复现输出

- scripts/verify_national_population_y.py：独立从原始 CSV 重检后写入全国 Y。
- config/national_population_evidence.json：分类证据、版本与哈希，未来新版本须重新核验。
- data/processed/national_population_field_checks.csv：逐字段覆盖、一致性及与人口实体差异。
- data/processed/national_statistics_y.csv：51 个存档的来源、状态与 Y。
- data/processed/analysis_panel.csv、event_records.csv：更新国家人口、激进派与 Y；原始候选与身份限制不覆盖。

不将全部原始数据发送到外部服务。此报告为 AI 核验记录，不记作学生交叉审核或老师界面核验。
