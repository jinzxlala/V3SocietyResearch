# 1837-01-01 工业基础量独立复核

复核日期：2026-10-11。AI 从只读原始 CSV 使用标准库独立计算，未调用 Notebook 第三步代码，未修改 Notebook 或既有处理输出。本记录不替代学生交叉审核。

输入：各 run 的 save_metadata_raw.csv、state_records_raw.csv、building_records_raw.csv、pop_records_raw.csv；篮子按《工业篮子建筑键对照.md》12 个精确键。只核算 1837-01-01。

采用已确认规则：主范围每期实际全国导出范围；共同州 STATE_FLANDERS、STATE_WALLONIA。工业就业为篮子工作人口 workforce；分母为有工作 workforce 扣除 building_subsistence_farm 就业，明确为非自给农业就业。保留无工作 workforce 排除量。

四个 run × 范围的基础量及比例均与 industry_base_quantities.csv 一致；全部观察到的分州/类型等级、建筑行数、工业就业均与 industry_by_state_type.csv 一致（比例容差 1e-12）。详见同目录 industry_crosscheck_1837.csv。

## 关联核验

- FL_01：同存档 50 条建筑、205 条人口；有工作人口群体 154 条、无工作 51 条。建筑 ID、人口 ID 和州 ID 无重复；有工作记录全部匹配；居住州与工作建筑州一致；日期及国家标签与 metadata 一致。
- SL_01：同存档 45 条建筑、224 条人口；有工作人口群体 166 条、无工作 58 条。建筑 ID、人口 ID 和州 ID 无重复；有工作记录全部匹配；居住州与工作建筑州一致；日期及国家标签与 metadata 一致。

人口→建筑关联键限定 run＋source_file＋country_id＋工作建筑 ID；建筑 ID 在同快照唯一，因此每条有工作人口恰好连接一条建筑，不增行。workforce 均为合法非负整数，工作标记与 ID 一致。全国范围三州：STATE_FLANDERS、STATE_GELRE、STATE_WALLONIA。

## 最小化匹配样例

- FL_01，Belgium_1837-01-01_01_FL_Jin.v3，country_id=25：pop_id=117441951，workforce=293，工作建筑 ID=458 → building_textile_mill，STATE_FLANDERS。
- SL_01，Belgium_1837-01-01_01_SL_Jin.v3，country_id=25：pop_id=67109732，workforce=3，工作建筑 ID=436 → building_steel_mill，STATE_WALLONIA。

## 人工复算方法

1. 每张原始表筛选对应 source_file 和 country_id（不能仅按实体 ID）。确认内部日期 1837.1.1 的前三段。
2. 筛选 12 个建筑键，加总 levels；共同州只保留 Flanders、Wallonia。
3. 选上面的 pop_id，使用其 workplace_building_id 查同存档建筑 ID，确认类型及州。
4. 对 has_workplace=True 的 workforce 加总；扣除工作建筑为 building_subsistence_farm 的 workforce，核对非自给农业分母。篮子就业除以该分母得到占比。

## 缺行与限制

- FL_01／national_actual 未观察到篮子类型：无。
- FL_01／common_states 未观察到篮子类型：无。
- SL_01／national_actual 未观察到篮子类型：building_motor_industry。
- SL_01／common_states 未观察到篮子类型：building_motor_industry。

缺行类型只报告未观察到，不生成零值。等级合计是观察到的篮子行总和，不能据此证明未观察到类型实际为零或快照完整性已核验。国家 ID/tag 一致仅为关联检查，不证明革命后的国家身份连续；共同州同键也不证明州内省份控制范围一致。此复核验证计算和关联一致性，不替代游戏字段语义外部证据，不计算综合 X_actual、政治结果或组间轨迹结论。

FL 的 building_motor_industry 存在 levels=0 的原始建筑行；SL 则没有该类型原始行。前者为观察到的零等级，后者为缺行，二者不能混同。
