import pytest

from scripts.python.summarize_scoring_input_benchmark import summarize


def report(scores):
    samples = []
    for image_id, values in enumerate(scores, 1):
        samples.append({'image_id': image_id, 'source': f'{image_id}.jpg',
                        'upright_dimensions': [400, 600], 'models': {'spaq': {
                            name: {'score': value, 'seconds': [0.1]}
                            for name, value in zip(('square512', 'inside512', 'cache_square512'), values)}}})
    return {'samples': samples, 'models': ['spaq'], 'manifest': {'units': [{
        'image_ids': [1, 2], 'block': 10, 'split': 'test',
        'frames': [{'image_id': 1, 'best': True, 'grade': 2},
                   {'image_id': 2, 'best': False, 'grade': 0}]}]}}


def test_human_pick_agreement_and_ties_are_not_legacy_rank_agreement():
    result = summarize(report([[10, 30, 20], [20, 20, 20]]))['models']['spaq']
    assert result['square512']['human_best_agreement'] == 0
    assert result['inside512']['human_best_agreement'] == 1
    assert result['inside512']['mean_within_unit_kendall_tau'] == -1
    assert result['cache_square512']['human_best_agreement'] == 0.5
    assert result['cache_square512']['human_rejected_winner_rate'] == 0.5
    assert result['inside512']['p95_absolute_normalized_delta'] == pytest.approx(0.19)
    assert result['inside512']['human_best_by_orientation']['portrait']['n'] == 1


def test_failed_input_is_excluded_from_quality_denominator_and_reported():
    result = summarize(report([[10, None, 10], [20, 20, 20]]))['models']['spaq']['inside512']
    assert result['failures'] == 1
    assert result['eligible_units'] == 0
    assert result['human_best_agreement'] is None
