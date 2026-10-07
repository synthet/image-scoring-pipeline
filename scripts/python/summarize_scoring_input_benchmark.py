"""Summarize frozen input-policy measurements against recorded human best picks."""
from __future__ import annotations

import argparse
import collections
import json
import math
from pathlib import Path


def summarize(report: dict) -> dict:
    import numpy as np
    from scipy.stats import kendalltau

    records = report['samples']
    manifest = report.get('manifest') or {}
    units = manifest.get('units') or []
    by_id = {record['image_id']: record for record in records}
    policies = ('square512', 'inside512', 'cache_square512')
    ranges = {'spaq': 100, 'ava': 9, 'liqe': 4, 'topiq': 1, 'arniqa': 1}
    output = {'decision': 'HOLD', 'sources': len(records), 'units': len(units),
              'blocks': len({unit['block'] for unit in units}),
              'splits': dict(collections.Counter(unit['split'] for unit in units)),
              'orientation': dict(collections.Counter('portrait' if s['upright_dimensions'][1] > s['upright_dimensions'][0]
                  else 'landscape' if s['upright_dimensions'][0] > s['upright_dimensions'][1] else 'square' for s in records)),
              'formats': dict(collections.Counter(Path(s['source']).suffix.lower() for s in records)),
              'models': {}}
    for model in report['models']:
        stats = {}
        for policy in policies:
            deltas, times, agreements, rejected, taus, winners_changed = [], [], [], [], [], []
            splits = collections.defaultdict(list)
            orientations = collections.defaultdict(list)
            failures = 0
            for record in records:
                result = record['models'][model][policy]
                base = record['models'][model]['square512']['score']
                value = result['score']
                if value is None or not math.isfinite(value):
                    failures += 1
                    continue
                if base is not None:
                    deltas.append((value - base) / ranges[model])
                times.extend(result['seconds'])
            for unit in units:
                values, base_values = [], []
                for image_id in unit['image_ids']:
                    record = by_id[image_id]
                    values.append(record['models'][model][policy]['score'])
                    base_values.append(record['models'][model]['square512']['score'])
                if any(value is None or not math.isfinite(value) for value in values + base_values):
                    continue
                maxima = {image_id for image_id, value in zip(unit['image_ids'], values)
                          if math.isclose(value, max(values), rel_tol=0, abs_tol=1e-9)}
                base_maxima = {image_id for image_id, value in zip(unit['image_ids'], base_values)
                               if math.isclose(value, max(base_values), rel_tol=0, abs_tol=1e-9)}
                preferred = {frame['image_id'] for frame in unit['frames'] if frame.get('best')}
                rejected_frames = {frame['image_id'] for frame in unit['frames'] if frame.get('grade') == 0}
                agreement = len(maxima & preferred) / len(maxima)
                agreements.append(agreement)
                rejected.append(len(maxima & rejected_frames) / len(maxima))
                splits[unit['split']].append(agreement)
                shapes = {('portrait' if by_id[i]['upright_dimensions'][1] > by_id[i]['upright_dimensions'][0]
                           else 'landscape' if by_id[i]['upright_dimensions'][0] > by_id[i]['upright_dimensions'][1]
                           else 'square') for i in unit['image_ids']}
                orientations[next(iter(shapes)) if len(shapes) == 1 else 'mixed'].append(agreement)
                winners_changed.append(maxima != base_maxima)
                tau = kendalltau(base_values, values).statistic
                if math.isfinite(tau):
                    taus.append(tau)
            stats[policy] = {'failures': failures,
                'mean_normalized_delta': float(np.mean(deltas)) if deltas else None,
                'p95_absolute_normalized_delta': float(np.percentile(np.abs(deltas), 95)) if deltas else None,
                'p95_seconds': float(np.percentile(times, 95)) if times else None,
                'human_best_agreement': float(np.mean(agreements)) if agreements else None,
                'human_rejected_winner_rate': float(np.mean(rejected)) if rejected else None,
                'eligible_units': len(agreements),
                'human_best_by_split': {split: {'n': len(values), 'agreement': float(np.mean(values))}
                                         for split, values in splits.items()},
                'human_best_by_orientation': {aspect: {'n': len(values), 'agreement': float(np.mean(values))}
                                               for aspect, values in orientations.items()},
                'mean_within_unit_kendall_tau': float(np.mean(taus)) if taus else None,
                'changed_winner_sets': sum(winners_changed)}
        output['models'][model] = stats
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = summarize(json.loads(args.report.read_text()))
    args.output.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
