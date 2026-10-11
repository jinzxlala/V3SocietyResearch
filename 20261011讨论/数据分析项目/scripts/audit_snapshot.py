"""从原始 CSV 独立复算一个日期，不调用特征构造代码，不修改处理面板。"""
import argparse
import csv
from decimal import Decimal
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEYS = ['run_id', 'source_file', 'country_id']
COMMON = {'STATE_FLANDERS', 'STATE_WALLONIA'}
BASKET = {key for line in (ROOT / '工业篮子建筑键对照.md').read_text().splitlines()
          if re.match(r'^\|\s*\d+\s*\|', line)
          for key in re.findall(r'`(building_[a-z_]+)`', line)}
assert len(BASKET) == 12


def read(name):
    with name.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def integer(value):
    number = Decimal(value)
    assert number.is_finite() and number == number.to_integral_value(), "非整数原值"
    return int(number)


def matching(rows, source, country):
    return [r for r in rows if r['source_file'] == source and r['country_id'] == country]


def unique_map(rows, column):
    result = {r[column]: r for r in rows}
    assert len(result) == len(rows), f'{column} 重复'
    return result


def write(path, rows, columns):
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def audit(target_date):
    panel = read(ROOT / 'data/processed/analysis_panel.csv')
    sensitivity = read(ROOT / 'data/processed/sensitivity_analysis_panel.csv')
    detail = read(ROOT / 'data/processed/industry_by_state_type.csv')
    values, checks, notes, samples = [], [], [], []

    def compare(run, scope, field, actual, expected):
        if isinstance(actual, float):
            equal = bool(expected) and math.isclose(actual, float(expected), abs_tol=1e-12, rel_tol=0)
        elif isinstance(actual, int):
            equal = bool(expected) and actual == int(float(expected))
        else:
            equal = str(actual) == str(expected)
        checks.append({'run_id': run, 'date': target_date, 'scope': scope,
                       'field': field, 'raw_recalculated': actual,
                       'panel_or_detail_value': expected, 'matches': equal})

    for run in sorted({r['run_id'] for r in panel}):
        folder = ROOT / 'data_raw' / run / 'raw_data'
        metadata = [r for r in read(folder / 'save_metadata_raw.csv')
                    if '-'.join(f'{int(part):02d}' if index else f'{int(part):04d}'
                                for index, part in enumerate(r['game_date'].split('.')[:3])) == target_date]
        assert len(metadata) == 1, f'{run}: 目标日期不是唯一存档'
        meta = metadata[0]
        source, country = meta['source_file'], meta['country_id']
        tables = {name: matching(read(folder / filename), source, country) for name, filename in [
            ('buildings', 'building_records_raw.csv'), ('pops', 'pop_records_raw.csv'),
            ('states', 'state_records_raw.csv'), ('scalars', 'country_scalar_fields_raw.csv'),
            ('laws', 'laws_raw.csv'), ('institutions', 'institutions_raw.csv')]}
        for table in tables.values():
            assert all(r['game_date'] == meta['game_date'] and r['country_tag'] == meta['country_tag'] for r in table)
        buildings = unique_map(tables['buildings'], 'building_id')
        states = unique_map(tables['states'], 'state_id')
        unique_map(tables['pops'], 'pop_id')
        for building in buildings.values():
            assert states[building['state_id']]['state_key'] == building['state_key']
            assert integer(building['levels']) >= 0
        for pop in tables['pops']:
            assert integer(pop['workforce']) >= 0 and integer(pop['dependents']) >= 0
            assert pop['location_state_id'] in states
            if pop['has_workplace'] == 'True':
                building = buildings[pop['workplace_building_id']]
                assert pop['location_state_id'] == building['state_id']
            else:
                assert pop['has_workplace'] == 'False' and pop['workplace_building_id'] == '-1'
        scalar_map = unique_map([r for r in tables['scalars'] if r['source_section'] == 'country.pop_statistics'], 'field_name')
        raw_radicals = integer(scalar_map['population_radicals']['raw_value'])
        negative_total = sum(-integer(p['loyalists_and_radicals']) for p in tables['pops'] if integer(p['loyalists_and_radicals']) < 0)
        strata_total = sum(integer(scalar_map[name]['raw_value']) for name in
                           ['population_lower_strata', 'population_middle_strata', 'population_upper_strata'])
        excessive = sum(abs(integer(p['loyalists_and_radicals'])) > integer(p['workforce']) + integer(p['dependents']) for p in tables['pops'])
        active_laws = {r['law_key'] for r in tables['laws'] if r['active'] == 'yes'}
        for scope, source_panel in [('national_actual', panel), ('common_states', sensitivity)]:
            selected = matching([r for r in source_panel if r['run_id'] == run and r['date'] == target_date], source, country)
            assert len(selected) == 1
            result = selected[0]
            allowed = set(r['state_key'] for r in states.values()) if scope == 'national_actual' else COMMON
            b = [r for r in buildings.values() if r['state_key'] in allowed and r['building_key'] in BASKET]
            pops = [r for r in tables['pops'] if states[r['location_state_id']]['state_key'] in allowed]
            working = [r for r in pops if r['has_workplace'] == 'True']
            industrial = [r for r in working if buildings[r['workplace_building_id']]['building_key'] in BASKET]
            observed_subsistence = {buildings[r['workplace_building_id']]['building_key'] for r in working
                                   if buildings[r['workplace_building_id']]['building_key'].startswith('building_subsistence_')}
            assert observed_subsistence.issubset({'building_subsistence_farm'}), '新自给类型须核验'
            subsistence = [r for r in working if buildings[r['workplace_building_id']]['building_key'] == 'building_subsistence_farm']
            workforce = sum(integer(r['workforce']) for r in working)
            excluded = sum(integer(r['workforce']) for r in subsistence)
            I = sum(integer(r['workforce']) for r in industrial)
            E = workforce - excluded
            L = sum(integer(r['levels']) for r in b)
            P = sum(integer(r['workforce']) + integer(r['dependents']) for r in pops)
            calculated = {'basket_levels_observed': L, 'industrial_employment': I,
                          'working_workforce_including_subsistence': workforce,
                          'subsistence_employment_excluded': excluded,
                          'non_subsistence_employment_denominator': E,
                          'no_workplace_workforce_excluded': sum(integer(r['workforce']) for r in pops if r['has_workplace'] == 'False'),
                          'industrial_employment_share': I / E, 'population_candidate': P}
            for field, actual in calculated.items(): compare(run, scope, field, actual, result[field])
            if scope == 'national_actual' and result.get('national_population_verification_status', '').startswith('三层分类互斥穷尽'):
                compare(run, scope, 'Y 国家统计口径', raw_radicals / strata_total, result['Y'])
                compare(run, scope, 'national_population', strata_total, result['national_population'])
                compare(run, scope, 'national_radicals', raw_radicals, result['national_radicals'])
            else:
                compare(run, scope, 'Y 留空', '', result['Y'])
            if result['X_actual']:
                # 用原始基线独立复算组成项，不调用Part 4计算代码。
                params = __import__('json').loads((ROOT / 'data/processed/x_actual_parameters.json').read_text())
                all_meta = read(folder / 'save_metadata_raw.csv')
                base_meta = next(r for r in all_meta if r['game_date'] == '1836.1.1')
                bb = unique_map(matching(read(folder / 'building_records_raw.csv'), base_meta['source_file'], base_meta['country_id']), 'building_id')
                bp = matching(read(folder / 'pop_records_raw.csv'), base_meta['source_file'], base_meta['country_id'])
                base_L = sum(integer(r['levels']) for r in bb.values() if r['building_key'] in BASKET)
                base_I = sum(integer(r['workforce']) for r in bp if r['has_workplace']=='True' and bb[r['workplace_building_id']]['building_key'] in BASKET)
                base_E = sum(integer(r['workforce']) for r in bp if r['has_workplace']=='True' and bb[r['workplace_building_id']]['building_key']!='building_subsistence_farm')
                A, B = (L-base_L)/base_L, 100*(I/E-base_I/base_E)
                x = params['weights']['building_growth']*A/params['sd_building_growth'] + params['weights']['employment_share_change']*B/params['sd_share_change_pp']
                compare(run, scope, 'X_actual 独立原始基线复算', x, result['X_actual'])
            else:
                compare(run, scope, 'X_actual 尚未计算', '', result['X_actual'])
            compare(run, scope, 'date', target_date, result['date'])
            compare(run, scope, 'game_date', meta['game_date'], result['game_date'])
            compare(run, scope, 'country_tag', meta['country_tag'], result['country_tag'])
            missing_types = '|'.join(sorted(BASKET - {r['building_key'] for r in b}))
            compare(run, scope, 'basket_types_without_records', missing_types, result['basket_types_without_records'])
            for component, law, institution in [
                ('social_security', 'law_no_social_security', 'institution_social_security'),
                ('worker_protection', 'law_no_workers_rights', 'institution_workplace_safety')]:
                assert law in active_laws
                compare(run, scope, component + '_active_law', law, result[component + '_active_law'])
                count = sum(r['institution_key'] == institution for r in tables['institutions'])
                compare(run, scope, component + '_institution_rows', count, result[component + '_institution_rows'])
                if count == 0:
                    compare(run, scope, component + '_investment 保留缺失', '', result[component + '_investment_numeric_candidate'])
                assert '用户确认未设立' in result[component + '_institution_status']
            if scope == 'national_actual':
                for field, actual in [('country_radicals_candidate', raw_radicals),
                     ('pop_negative_political_candidate', negative_total),
                     ('population_strata_sum_candidate', strata_total),
                     ('population_from_pop_candidate', P),
                     ('political_abs_exceeds_population_rows', excessive)]:
                    compare(run, scope, field, actual, result[field])
            # 原始分州/类型分别计算，与中间核查表对照。
            raw_detail = {}
            for building in b:
                group = (building['state_key'], building['building_key'])
                entry = raw_detail.setdefault(group, [0, 0, 0])
                entry[0] += integer(building['levels'])
                entry[1] += 1
            for pop in industrial:
                building = buildings[pop['workplace_building_id']]
                raw_detail[(building['state_key'], building['building_key'])][2] += integer(pop['workforce'])
            existing = {(r['state_key'], r['building_key']): r for r in detail
                        if r['run_id'] == run and r['source_file'] == source and r['country_id'] == country and r['scope'] == scope}
            assert set(existing) == set(raw_detail), '分州/类型键覆盖不一致'
            for group, amounts in raw_detail.items():
                for index, field in enumerate(['levels', 'building_rows', 'industrial_employment']):
                    compare(run, scope, '|'.join(group) + ':' + field, amounts[index], existing[group][field])
            values.append({'run_id': run, 'source_file': source, 'country_id': country,
                           'date': target_date, 'scope': scope, **calculated,
                           'basket_types_without_records': missing_types,
                           'verification_status': 'AI 独立复算；不替代学生交叉审核；Y待核验'})
        notes.append(f'- {run}：原始建筑 {len(buildings)} 行，人口 {len(tables["pops"])} 行；国家激进派原值 {raw_radicals:,}、逐人口负值合计 {negative_total:,}，均仍是候选来源；超人口政治原值记录 {excessive} 行。')
        sample = next(r for r in tables['pops'] if r['has_workplace'] == 'True' and buildings[r['workplace_building_id']]['building_key'] in BASKET)
        building = buildings[sample['workplace_building_id']]
        samples.append({'run_id': run, 'source_file': source, 'country_id': country,
                        'date': target_date, 'pop_id': sample['pop_id'],
                        'workforce': sample['workforce'],
                        'workplace_building_id': sample['workplace_building_id'],
                        'building_key': building['building_key'], 'state_key': building['state_key']})
    output = ROOT / 'outputs/tables'
    output.mkdir(parents=True, exist_ok=True)
    stem = f'snapshot_crosscheck_{target_date.replace("-", "")}'
    write(output / f'{stem}.csv', values, list(values[0]))
    write(output / f'{stem}_checks.csv', checks, list(checks[0]))
    write(ROOT / 'data/processed' / f'{stem}_workplace_examples.csv', samples, list(samples[0]))
    failures = [r for r in checks if not r['matches']]
    report = f'# {target_date} 独立复算\n\n复核日期：2026-10-11；只读原始 CSV 独立计算，未调用 Notebook 特征构造代码，未修改处理面板。AI 复核不替代两位学生交叉审核。\n\n共 {len(checks)} 项检查，差异 {len(failures)} 项。全国与共同州的基础量、人口候选、分州/类型、来源日期及保护状态逐项对照。\n\n'
    report += '| run／范围 | 等级 | 工业就业 | 非自给就业分母 | 人口候选 | 工业占比 |\n| --- | ---: | ---: | ---: | ---: | ---: |\n'
    for r in values:
        report += f'| {r["run_id"]}／{r["scope"]} | {r["basket_levels_observed"]} | {r["industrial_employment"]:,} | {r["non_subsistence_employment_denominator"]:,} | {r["population_candidate"]:,} | {r["industrial_employment_share"]:.6%} |\n'
    report += f'\n少量工作人口关联样例仅保存在本地 data/processed/{stem}_workplace_examples.csv。\n' + '\n'.join(notes) + '\n\n缺行类型仅报告未观察到，不生成零等级；对应机构原始缺行与用户确认未设立的反馈分开保存，investment 不填0。政治来源差异、人口分母语义、革命后国家身份及州内省份范围仍待核验。Y 按面板最新登记的国家统计口径复核，共同州 Y 留空；X_actual 若已计算则用原始基线与登记尺度复核。本复算不解决字段更新机制或身份限制，也不形成因果结论。\n\n人工复算：限定同存档、同国家后加总篮子 levels；工作人口按建筑 ID 匹配类型；用有工作 workforce 减自给就业得到分母，再核对分子与占比。人口候选另加 workforce＋dependents，包含无工作人口与自给人口。\n'
    (output / f'{stem}.md').write_text(report, encoding='utf-8')
    for r in values:
        print(r['run_id'], r['scope'], 'L=', r['basket_levels_observed'], 'I=', r['industrial_employment'],
              'E=', r['non_subsistence_employment_denominator'], 'P候选=', r['population_candidate'])
    print(f'{len(checks)} 项检查，差异 {len(failures)} 项；复核报告已保存。')
    if failures:
        raise AssertionError('出现差异，请查看复核检查表；原处理结果未改写。')
    return values, checks


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', required=True)
    audit(parser.parse_args().date)
