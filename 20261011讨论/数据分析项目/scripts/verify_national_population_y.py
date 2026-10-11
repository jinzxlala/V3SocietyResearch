"""核验本批国家三阶层统计并计算导出国家统计口径的Y，保留独立身份限制。"""
import csv
import json
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / 'data/processed'
STRATA = ['population_lower_strata', 'population_middle_strata', 'population_upper_strata']


def read(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def save(path, rows, columns):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def integer(raw):
    try:
        value = Decimal(raw)
    except Exception:
        return None
    if not value.is_finite() or value < 0 or value != value.to_integral_value():
        return None
    return int(value)


def main():
    evidence = json.loads((ROOT / 'config/national_population_evidence.json').read_text())
    class_fields = {key: 'population_' + value + '_strata'
                    for key, value in evidence['social_class_to_strata'].items()}
    inventory = read(PROCESSED / 'save_inventory.csv')
    field_checks, national_results = [], []
    for run in sorted({r['run_id'] for r in inventory}):
        folder = ROOT / 'data_raw' / run / 'raw_data'
        countries = read(folder / 'country_scalar_fields_raw.csv')
        state_statistics = read(folder / 'state_pop_statistics_raw.csv')
        states = read(folder / 'state_records_raw.csv')
        pops = read(folder / 'pop_records_raw.csv')
        for meta in [r for r in inventory if r['run_id'] == run]:
            source, country = meta['source_file'], meta['country_id']
            def same(rows):
                selected = [r for r in rows if r['source_file'] == source and r['country_id'] == country]
                if any(r['game_date'] != meta['game_date'] or r['country_tag'] != meta['country_tag'] for r in selected):
                    raise ValueError('同存档日期/国家标签不一致')
                return selected
            c = [r for r in same(countries) if r['source_section'] == 'country.pop_statistics']
            st, ss, pop = same(states), same(state_statistics), same(pops)
            state_ids = {r['state_id'] for r in st}
            state_structure_ok = bool(st) and len(state_ids) == len(st)
            pop_ids = {r['pop_id'] for r in pop}
            classification_ok = (bool(pop) and len(pop_ids) == len(pop)
                and all(r['social_class'] in class_fields and r['location_state_id'] in state_ids for r in pop))
            version_ok = meta['game_version'] == evidence['game_version']
            country_values, field_valid = {}, {}
            class_population = {field: 0 for field in STRATA}
            pop_population_valid = True
            for r in pop:
                w, d = integer(r['workforce']), integer(r['dependents'])
                if w is None or d is None or r['social_class'] not in class_fields:
                    pop_population_valid = False
                else:
                    class_population[class_fields[r['social_class']]] += w + d
            for field in STRATA + ['population_radicals']:
                rows = [r for r in c if r['field_name'] == field]
                cvalue = integer(rows[0]['raw_value']) if len(rows) == 1 else None
                srows = [r for r in ss if r['field_name'] == field]
                svalues = [integer(r['raw_value']) for r in srows]
                complete = (state_structure_ok and len(srows) == len(state_ids)
                            and {r['state_id'] for r in srows} == state_ids
                            and all(value is not None for value in svalues))
                state_sum = sum(svalues) if complete else None
                valid = version_ok and cvalue is not None and complete and cvalue == state_sum
                country_values[field], field_valid[field] = cvalue, valid
                field_checks.append({'run_id': run, 'source_file': source, 'country_id': country,
                    'date': meta['date'], 'field': field, 'country_field_rows': len(rows),
                    'country_value': '' if cvalue is None else cvalue,
                    'expected_state_rows': len(state_ids), 'observed_state_field_rows': len(srows),
                    'state_sum': '' if state_sum is None else state_sum,
                    'country_equals_state_sum': valid,
                    'pop_classification_complete': classification_ok,
                    'population_entities_candidate': class_population[field] if field in STRATA and pop_population_valid else '',
                    'country_minus_population_entities': cvalue - class_population[field] if field in STRATA and pop_population_valid and cvalue is not None else '',
                    'status': '国家/州统计一致' if valid else ('国家字段缺行，不能填零' if not rows else '覆盖或数值一致性检查未通过')})
            denominator_verified = version_ok and classification_ok and all(field_valid[field] for field in STRATA)
            P = sum(country_values[field] for field in STRATA) if denominator_verified else None
            R = country_values['population_radicals']
            ratio_valid = denominator_verified and field_valid['population_radicals'] and P > 0 and 0 <= R <= P
            status = ('已计算：国家统计口径；实体差异及身份限制保留' if ratio_valid else
                      '国家激进派字段缺行，Y留空' if R is None else '核验未通过或分母/人数异常，Y留空')
            national_results.append({'run_id': run, 'source_file': source, 'country_id': country,
                'date': meta['date'], 'record_type': meta['record_type'],
                'national_population': '' if P is None else P,
                'national_radicals': '' if R is None else R,
                'Y': R / P if ratio_valid else '', 'Y_unit': '0-1', 'Y_status': status,
                'Y_numerator_source': 'country.pop_statistics.population_radicals',
                'Y_denominator_source': 'country.pop_statistics 三阶层人口之和',
                'national_population_verification_status': '三层分类互斥穷尽，国家/州一致性通过' if denominator_verified else '未通过，留空',
                'national_population_verification_reference': 'config/national_population_evidence.json; national_population_field_checks.csv',
                'population_entity_difference_status': '国家统计与逐人口快照差异保留，更新时点/差异机制未证实',
                'Y_identity_limitation': '仅解释为导出国家统计；革命后研究对象连续性待核验',
                'political_scope_status': '国家统计口径可计算；实体差异和身份限制保留' if ratio_valid else '国家统计口径缺失或未通过核验',
                'population_scope_status': '国家三阶层分母结构及国家/州一致性通过；原逐人口候选另存' if denominator_verified else '国家分母未通过核验'})
    save(PROCESSED / 'national_population_field_checks.csv', field_checks, list(field_checks[0]))
    save(PROCESSED / 'national_statistics_y.csv', national_results, list(national_results[0]))
    result_map = {(r['run_id'], r['source_file'], r['country_id']): r for r in national_results}
    for filename in ['analysis_panel.csv', 'event_records.csv']:
        rows = read(PROCESSED / filename)
        columns = list(rows[0]) if rows else []
        extra_columns = [k for k in national_results[0] if k not in ['run_id','source_file','country_id','date','record_type']]
        columns += [k for k in extra_columns if k not in columns]
        for row in rows:
            result = result_map[(row['run_id'], row['source_file'], row['country_id'])]
            if row['date'] != result['date'] or row['record_type'] != result['record_type']:
                raise ValueError('国家Y与面板日期/记录类型不一致')
            row.update({k: result[k] for k in extra_columns})
        save(PROCESSED / filename, rows, columns)
    print(f'三阶层分母通过 {sum(r["national_population"] != "" for r in national_results)}/{len(national_results)} 个存档。')
    print(f'国家统计Y计算 {sum(r["Y"] != "" for r in national_results)} 个存档；基线缺字段继续留空。')
    print('共同州Y未计算，政治实体差异与革命后身份限制仍保留。')
    return national_results, field_checks


if __name__ == '__main__':
    main()
