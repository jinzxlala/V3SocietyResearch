"""已确认的综合X与Part 4描述性图表；run、窗口、权重使用项目配置。"""
import argparse
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/processed'
TABLES = ROOT / 'outputs/tables'
FIGURES = ROOT / 'outputs/figures'
SETTINGS = json.loads((ROOT / 'config/part4_settings.json').read_text())
NUMERIC = ['basket_levels_observed', 'industrial_employment', 'non_subsistence_employment_denominator',
           'industrial_employment_share', 'national_population', 'national_radicals', 'Y']


def load(filename):
    frame = pd.read_csv(DATA / filename, dtype={'run_id': 'string', 'country_id': 'string', 'source_file': 'string'})
    for col in NUMERIC:
        if col in frame:
            frame[col] = pd.to_numeric(frame[col], errors='coerce')
    if frame.duplicated(['run_id', 'source_file', 'country_id']).any():
        raise ValueError(f'{filename}: 同存档身份键重复')
    if not frame['scope'].eq(SETTINGS['scope']).all():
        raise ValueError('输入范围不是已确认的全国主分析范围')
    return frame


def calculate_x():
    panel, events = load('analysis_panel.csv'), load('event_records.csv')
    if panel.duplicated(['run_id', 'date']).any():
        raise ValueError('年度run-date不唯一')
    missing_runs = set(SETTINGS['standardization_reference_runs']) - set(panel['run_id'])
    if missing_runs:
        raise ValueError(f'标准化参考run缺失：{sorted(missing_runs)}')
    for frame in [panel, events]:
        frame['building_growth_from_baseline'] = np.nan
        frame['industrial_share_change_pp'] = np.nan
        frame['industrial_employment_growth'] = np.nan
    for run, group in panel.groupby('run_id'):
        baseline = group.loc[group['date'].eq(SETTINGS['baseline_date'])]
        if len(baseline) != 1:
            raise ValueError(f'{run}: 基线不是唯一记录')
        base = baseline.iloc[0]
        L0, I0, E0 = [base[c] for c in ['basket_levels_observed', 'industrial_employment', 'non_subsistence_employment_denominator']]
        p0 = I0 / E0 if pd.notna(I0) and pd.notna(E0) and E0 > 0 else np.nan
        for frame in [panel, events]:
            mask = frame['run_id'].eq(run)
            L, I, E = [frame.loc[mask, c] for c in ['basket_levels_observed', 'industrial_employment', 'non_subsistence_employment_denominator']]
            if pd.notna(L0) and L0 > 0:
                frame.loc[mask, 'building_growth_from_baseline'] = ((L - L0) / L0).where(L.ge(0))
            if pd.notna(p0):
                p = (I / E).where(E.gt(0) & I.ge(0) & I.le(E))
                frame.loc[mask, 'industrial_share_change_pp'] = 100 * (p - p0)
            if pd.notna(I0) and I0 > 0:
                frame.loc[mask, 'industrial_employment_growth'] = ((I - I0) / I0).where(I.ge(0))
    start, end = SETTINGS['industrial_window']
    refs = panel.loc[panel['run_id'].isin(SETTINGS['standardization_reference_runs'])
                     & panel['date'].between(start, end)].copy()
    components = ['building_growth_from_baseline', 'industrial_share_change_pp']
    complete_dates = set.intersection(*(set(refs.loc[refs['run_id'].eq(run)
        & refs[components].notna().all(axis=1), 'date']) for run in SETTINGS['standardization_reference_runs']))
    reference = refs.loc[refs['date'].isin(complete_dates)]
    sd = reference[components].std(ddof=SETTINGS['standard_deviation_ddof'])
    if len(reference) < 2 or not np.isfinite(sd).all() or not sd.gt(0).all():
        raise ValueError('共同标准差不可用；不以小常数或单项权重替代')
    w = SETTINGS['weights']
    if not np.isclose(sum(w.values()), 1):
        raise ValueError('权重之和不为1')
    for frame in [panel, events]:
        frame['building_growth_standardized'] = frame[components[0]] / sd[components[0]]
        frame['share_change_standardized'] = frame[components[1]] / sd[components[1]]
        frame['X_actual'] = w['building_growth'] * frame['building_growth_standardized'] + w['employment_share_change'] * frame['share_change_standardized']
        frame['X_actual_status'] = np.where(frame['X_actual'].notna(),
            '已计算：观察到建筑等级和非自给就业口径；缺行类型与身份限制保留', '组成项缺失，综合X留空')
        frame['X_actual_unit'] = '无量纲，共同标准差单位；不减均值'
        frame['X_actual_method_version'] = SETTINGS['method_version']
        frame['X_actual_reference_sd_building_growth'] = sd[components[0]]
        frame['X_actual_reference_sd_share_change_pp'] = sd[components[1]]
        frame['industrial_employment_growth_unit'] = '0-1增长比例'
        frame['building_growth_unit'] = '0-1增长比例'
        frame['industrial_share_change_unit'] = '百分点'
    for frame, filename in [(panel, 'analysis_panel.csv'), (events, 'event_records.csv')]:
        frame.to_csv(DATA / filename, index=False, encoding='utf-8-sig')
    params = {**SETTINGS, 'reference_record_count': len(reference),
              'reference_dates': sorted(complete_dates),
              'reference_dates_per_run': len(complete_dates),
              'sd_building_growth': float(sd[components[0]]),
              'sd_share_change_pp': float(sd[components[1]]),
              'limits': '缩放只基于固定日期；观察到的等级合计不证明缺行类型为零；身份未核验'}
    (DATA / 'x_actual_parameters.json').write_text(json.dumps(params, ensure_ascii=False, indent=2) + '\n')
    print(f'X_actual 已计算：标准化参考 {len(reference)} 条，含基线，不含额外存档。')
    return panel, events


def prepare_summary(panel):
    runs = SETTINGS['analysis_runs']
    selected = panel.loc[panel['run_id'].isin(runs)].copy()
    if set(selected['run_id']) != set(runs):
        raise ValueError('比较配置run未全部出现')
    ystart, yend = SETTINGS['y_window']
    ycandidates = selected.loc[selected['date'].between(ystart, yend)]
    shared = set.intersection(*(set(ycandidates.loc[ycandidates['run_id'].eq(run)
        & ycandidates['Y'].notna(), 'date']) for run in runs))
    if not {ystart, yend}.issubset(shared):
        raise ValueError('已确认Y首末日期不同时有效；不自动改用其他起点')
    ydata = ycandidates.loc[ycandidates['date'].isin(shared)].copy()
    rows = []
    for run, group in selected.groupby('run_id'):
        group = group.loc[group['date'].between(*SETTINGS['industrial_window'])].sort_values('date')
        first, last = group.iloc[0], group.iloc[-1]
        yy = ydata.loc[ydata['run_id'].eq(run)].sort_values('date')
        peak = yy['Y'].max()
        peak_dates = '|'.join(yy.loc[yy['Y'].eq(peak), 'date'])
        rows.append({'run_id': run, 'condition': first['condition'], 'scope': SETTINGS['scope'],
            'industrial_window_start': first['date'], 'industrial_window_end': last['date'],
            'industrial_fixed_dates_including_baseline': len(group), 'X_actual_valid_dates': int(group['X_actual'].notna().sum()),
            'basket_levels_baseline': first['basket_levels_observed'], 'basket_levels_end': last['basket_levels_observed'],
            'basket_levels_net_change': last['basket_levels_observed'] - first['basket_levels_observed'],
            'building_growth_end': last['building_growth_from_baseline'],
            'industrial_employment_baseline': first['industrial_employment'], 'industrial_employment_end': last['industrial_employment'],
            'industrial_employment_growth_end': last['industrial_employment_growth'],
            'non_subsistence_employment_baseline': first['non_subsistence_employment_denominator'],
            'non_subsistence_employment_end': last['non_subsistence_employment_denominator'],
            'industrial_share_baseline': first['industrial_employment_share'], 'industrial_share_end': last['industrial_employment_share'],
            'industrial_share_change_pp': last['industrial_share_change_pp'],
            'X_actual_baseline': first['X_actual'], 'X_actual_end': last['X_actual'],
            'X_actual_change_from_baseline': last['X_actual'] - first['X_actual'],
            'Y_window_start': ystart, 'Y_window_end': yend, 'Y_valid_shared_fixed_dates': len(yy),
            'Y_baseline_in_mean': False, 'extra_snapshots_in_mean': False,
            'Y_mean': yy['Y'].mean(), 'Y_peak': peak, 'Y_peak_date': peak_dates.split('|')[0],
            'Y_peak_all_dates': peak_dates, 'Y_first': yy.iloc[0]['Y'], 'Y_last': yy.iloc[-1]['Y'],
            'Y_change_1860_minus_1837_pp': 100 * (yy.iloc[-1]['Y'] - yy.iloc[0]['Y']),
            'Y_unit': '0-1；变化单位百分点',
            'basket_missing_type_dates': int(group['basket_types_without_records'].fillna('').ne('').sum()),
            'method_version': SETTINGS['method_version'],
            'limitation': '导出国家描述性比较；身份连续性及实体统计差异未解决；缺行建筑类型非零值证据'})
    return selected, ydata, pd.DataFrame(rows)


def generate_figures():
    os.environ.setdefault('MPLCONFIGDIR', str(DATA / '.matplotlib_cache'))
    os.environ.setdefault('XDG_CACHE_HOME', str(DATA / '.runtime_cache'))
    (DATA / '.runtime_cache').mkdir(parents=True, exist_ok=True)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib import font_manager
    fonts = {f.name for f in font_manager.fontManager.ttflist}
    chosen = next((name for name in ['Arial Unicode MS', 'PingFang SC', 'Heiti SC', 'Noto Sans CJK SC', 'Microsoft YaHei', 'SimHei'] if name in fonts), None)
    if chosen:
        plt.rcParams['font.family'] = chosen
    plt.rcParams.update({'axes.unicode_minus': False, 'font.size': 10, 'axes.spines.top': False,
                         'axes.spines.right': False, 'axes.titlesize': 12, 'figure.facecolor': '#ffffff'})
    def T(cn, en): return cn if chosen else en
    panel, events = load('analysis_panel.csv'), load('event_records.csv')
    for frame in [panel, events]:
        for column in ['X_actual','building_growth_from_baseline','industrial_share_change_pp','industrial_employment_growth']:
            frame[column] = pd.to_numeric(frame[column], errors='coerce')
    selected, ydata, summary = prepare_summary(panel)
    selected['plot_date'] = pd.to_datetime(selected['date'])
    ydata['plot_date'] = pd.to_datetime(ydata['date'])
    events['plot_date'] = pd.to_datetime(events['date'])
    FIGURES.mkdir(parents=True, exist_ok=True)
    TABLES.mkdir(parents=True, exist_ok=True)
    summary.to_csv(TABLES / 'run_summary.csv', index=False, encoding='utf-8-sig')
    colors = {run: color for run, color in zip(SETTINGS['analysis_runs'], plt.get_cmap('tab10').colors)}
    if 'FL_01' in colors: colors['FL_01'] = '#167D8D'
    if 'SL_01' in colors: colors['SL_01'] = '#D57935'
    changes = pd.read_csv(DATA / 'state_scope_changes.csv')
    def style(ax, marks=True):
        ax.grid(axis='y', alpha=.20)
        ax.xaxis.set_major_locator(mdates.YearLocator(4))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
        ax.set_xlim(datetime.fromisoformat(SETTINGS['industrial_window'][0]) - timedelta(days=180),
                    datetime.fromisoformat(SETTINGS['industrial_window'][1]) + timedelta(days=250))
        if marks:
            for row in changes.itertuples(index=False):
                if row.run_id in colors:
                    ax.axvline(pd.Timestamp(row.first_observed_change_date), color=colors[row.run_id], linestyle=':', alpha=.35, linewidth=1)
    def finish(fig, title, subtitle, footer, name):
        fig.suptitle(title, x=.085, ha='left', y=.985, fontsize=16, fontweight='normal')
        fig.text(.085, .945, subtitle, ha='left', fontsize=9, color='#525a65')
        fig.text(.085, .035, footer, ha='left', va='bottom', fontsize=8.5, color='#525a65')
        fig.subplots_adjust(left=.10, right=.97, top=.88, bottom=.17, hspace=.34)
        fig.savefig(FIGURES / f'{name}.png', dpi=180)
        plt.close(fig)
    ref_count = len(selected)
    counts = ', '.join(f'{run}: {len(selected.loc[selected["run_id"].eq(run)])}' for run in SETTINGS['analysis_runs'])
    scope_footer = T('点线：首次观察到州范围变化（FL 1840；SL 1860），不是确切事件发生日。\n等级为观察到的篮子记录合计；未出现类型、革命后身份及州内省份范围仍有核验限制。',
                     'Dotted lines: first observed state-scope changes (FL 1840; SL 1860), not exact event dates.\nLevels sum observed basket records; absent types, identity continuity and province scope remain limited.')
    fig, axes = plt.subplots(3, 1, figsize=(10.5, 8.5), sharex=True)
    for ax, column, label, factor in zip(axes,
        ['basket_levels_observed','industrial_employment','non_subsistence_employment_denominator'],
        [T('工业篮子等级（级）','Basket levels'),T('工业就业（万人）','Industrial employment (10,000 persons)'),
         T('非自给农业就业分母（万人）','Non-subsistence employment (10,000 persons)')], [1,10000,10000]):
        for run, group in selected.groupby('run_id'):
            group=group.sort_values('plot_date')
            ax.plot(group['plot_date'], group[column]/factor, color=colors[run], linewidth=2, label=run)
        ax.set_ylabel(label)
        style(ax)
    axes[0].legend(frameon=False, ncol=len(colors), loc='upper left')
    axes[-1].set_xlabel(T('观察日期（年初固定点）','Observation year (fixed Jan 1 snapshots)'))
    finish(fig,T('图 1｜工业基础量轨迹','Figure 1 | Industrial base quantities'),
           T(f'全国实际范围 · 1836—1860 · 含基线 · 固定日期数 {counts}',f'Actual national scope | 1836–1860 | Includes baseline | Fixed dates {counts}'),scope_footer,'01_industrial_base_trends')
    fig, axes=plt.subplots(2,1,figsize=(10.5,6.9),sharex=True)
    for run, group in selected.groupby('run_id'):
        group=group.sort_values('plot_date')
        axes[0].plot(group['plot_date'],group['X_actual'],color=colors[run],linewidth=2,label=run)
        axes[1].plot(group['plot_date'],100*group['industrial_employment_growth'],color=colors[run],linewidth=2,label=run)
    axes[0].set_ylabel(T('综合 X_actual（无量纲）','Composite X_actual (dimensionless)'))
    axes[1].set_ylabel(T('工业就业增长率（%）','Industrial employment growth (%)'))
    for ax in axes:
        style(ax)
        ax.axhline(0,color='#9ca3af',linewidth=.6)
    axes[0].legend(frameon=False,ncol=len(colors),loc='upper left')
    axes[-1].set_xlabel(T('观察日期','Observation year'))
    params=json.loads((DATA/'x_actual_parameters.json').read_text())
    finish(fig,T('图 2｜实际工业扩张：综合指标与替代指标','Figure 2 | Composite and alternative industrial expansion'),
           T(f'全国范围 · 1836 基线=0 · 固定日期数 {counts} · 50/50 权重 · 共同缩放参考 n={params["reference_record_count"]}',
             f'National scope | 1836 baseline=0 | Fixed dates {counts} | Weights 50/50 | Reference n={params["reference_record_count"]}'),
           T('上图：等级增长率、就业占比百分点变化分别除以共同标准差，不减均值。\n下图：就业相对基线增长率；不同单位不直接相减。缺行类型、身份和领土变化限制保留。',
             'Top: building growth and share change divided by shared SD, without mean subtraction.\nBottom: employment growth from baseline. Units differ; absent types, identity and territory remain limitations.'),
           '02_actual_industrialization_trends')
    fig,ax=plt.subplots(figsize=(10.5,5.4))
    for run, group in ydata.groupby('run_id'):
        group=group.sort_values('plot_date')
        ax.plot(group['plot_date'],100*group['Y'],color=colors[run],linewidth=2,label=run)
    extra=events.loc[events['run_id'].isin(SETTINGS['analysis_runs']) & events['Y'].notna()]
    for run,group in extra.groupby('run_id'):
        ax.scatter(group['plot_date'],100*group['Y'],marker='D',s=48,facecolors='white',edgecolors=colors[run],linewidths=1.8,
                   label=T(f'{run} 额外存档（不计均值）',f'{run} extra snapshot (excluded from mean)'),zorder=4)
    style(ax)
    ax.set_ylabel(T('国家统计激进派占比（%）','National-statistics radical share (%)'))
    ax.set_xlabel(T('观察日期','Observation year'))
    ax.legend(frameon=False,ncol=2,loc='upper left')
    ycounts=', '.join(f'{run}: {len(ydata.loc[ydata["run_id"].eq(run)])}' for run in SETTINGS['analysis_runs'])
    finish(fig,T('图 3｜低保护条件下的政治轨迹','Figure 3 | Political trajectories under low protection'),
           T(f'全国国家统计 · 1837—1860 共同有效固定日期 · {ycounts} · 基线缺失',f'National statistics | Shared fixed dates 1837–1860 | {ycounts} | Baseline missing'),
           T('分母：国家下／中／上层人口之和。额外存档单独标记，不参与均值或峰值汇总。\n点线为州范围首次变化观察日；革命后身份及国家／逐人口统计差异仍待解释。',
             'Denominator: lower + middle + upper strata. Extra snapshot excluded from mean and peak summaries.\nDotted lines mark first observed scope changes; identity and entity/statistics differences remain unresolved.'),
           '03_national_radical_share_trends')
    plot_columns=['run_id','condition','date','record_type','basket_levels_observed','industrial_employment',
        'non_subsistence_employment_denominator','building_growth_from_baseline','industrial_share_change_pp',
        'industrial_employment_growth','X_actual','national_population','national_radicals','Y']
    plotted=pd.concat([selected[plot_columns],extra[plot_columns]],ignore_index=True)
    plotted['Y_in_summary']=plotted['record_type'].ne('extra_event') & plotted['date'].isin(set(ydata['date']))
    plotted.to_csv(TABLES/'part4_plot_data.csv',index=False,encoding='utf-8-sig')
    report=['# Part 4 描述性图表与汇总\n',
            '全国主分析；工业窗口1836-01-01至1860-01-01（含基线）；Y窗口1837-01-01至1860-01-01共同有效固定日期。额外存档不计均值、峰值或首末变化。\n',
            '三图分别为工业基础量、综合与替代工业指标、国家统计激进派比例。run_summary.csv 各比例存储0–1；百分点变化列以 _pp 明确标记。\n']
    for r in summary.itertuples(index=False):
        report.append(f'- {r.run_id}：观察到篮子等级 {r.basket_levels_baseline:g} → {r.basket_levels_end:g}；'
            f'就业占比增加 {r.industrial_share_change_pp:.3f} 个百分点；末期综合X={r.X_actual_end:.3f}。'
            f'Y共同有效点 {r.Y_valid_shared_fixed_dates} 个，均值 {100*r.Y_mean:.3f}%，峰值 {100*r.Y_peak:.3f}%（{r.Y_peak_all_dates}），'
            f'1860减1837变化 {r.Y_change_1860_minus_1837_pp:.3f} 个百分点。\n')
    report.append('\n等级净变化可能受领土变化影响；各类等级非等容量。非自给农业就业分母不包括自给就业和无工作人口。国家统计与逐人口差异、革命后身份连续性与州内省份范围仍有限制；图中曲线仅是导出国家轨迹。每条件一次，年度行不独立，不进行显著性检验或因果解释。缺行类型不补为零。\n')
    report.append('\n标准化参数见 data/processed/x_actual_parameters.json；新增run可配置使用已说明口径，但变更参考样本必须更新方法版本并保留原结果。权重与共同州敏感性分析在Part 5另行执行。\n')
    (TABLES/'part4_figure_notes.md').write_text('\n'.join(report))
    print('已生成三张 PNG、run_summary.csv、作图汇总数据及图注；额外存档未进入Y汇总。')
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--stage',choices=['features','figures','all'],default='all')
    stage=parser.parse_args().stage
    if stage in ['features','all']: calculate_x()
    if stage in ['figures','all']: generate_figures()
