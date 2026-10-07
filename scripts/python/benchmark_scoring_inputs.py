"""Read-only MUSIQ input-policy pilot with cached weights and explicit source manifest.

This produces evidence, never changes scoring configuration or persists scores.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--models', nargs='+', choices=['spaq', 'ava', 'liqe', 'topiq', 'arniqa'],
                        default=['spaq', 'ava'])
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error('--repeats must be positive')
    manifest = json.loads(args.manifest.read_text())
    sources = manifest['sources']
    if not sources:
        parser.error('manifest must include sources')
    args.output.mkdir(parents=True, exist_ok=True)

    # CPU measurement keeps device selection consistent across both frameworks.
    os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
    import numpy as np
    import tensorflow_hub as hub
    from PIL import Image
    from modules.rendition_cache import get_inference_rendition
    from scripts.python.run_all_musiq_models import MultiModelMUSIQ

    scorer = MultiModelMUSIQ(skip_gpu=True)
    raw_config = scorer._get_raw_conversion_config()
    if raw_config['jpeg_quality'] != 85:
        raise RuntimeError('Pilot requires JPEG quality 85 for controlled comparisons')
    scorer.temp_dir = str(args.output / 'converted')
    Path(scorer.temp_dir).mkdir(exist_ok=True)
    records = []
    for index, entry in enumerate(sources):
        source = Path(entry['path'])
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        started = time.perf_counter()
        upright = scorer.convert_raw_to_jpeg(str(source)) if scorer.is_raw_file(str(source)) else str(source)
        decode_seconds = time.perf_counter() - started
        if not upright:
            raise RuntimeError(f'Cannot decode {source}')
        directory = args.output / str(index)
        directory.mkdir(exist_ok=True)
        baseline = scorer.preprocess_image(upright, output_dir=str(directory), resolution_override=512)
        with Image.open(upright) as image:
            image = scorer._orient_raster(image).convert('RGB')
            upright_size = image.size
            image.thumbnail((512, 512), Image.Resampling.BICUBIC)
            native = directory / 'inside512.jpg'
            image.save(native, 'JPEG', quality=85)
        miss, miss_desc, miss_info = get_inference_rendition(str(source), cache_dir=str(args.output / 'cache'))
        hit, hit_desc, hit_info = get_inference_rendition(str(source), cache_dir=str(args.output / 'cache'))
        assert np.array_equal(np.asarray(miss), np.asarray(hit)), 'Cache hit/miss pixels differ'
        assert miss_desc.decode_route == hit_desc.decode_route
        cached = directory / 'cached-source.png'
        miss.save(cached)
        cache_input = scorer.preprocess_image(str(cached), output_dir=str(directory / 'cached'),
                                             resolution_override=512)
        variants = {'square512': baseline, 'inside512': str(native), 'cache_square512': cache_input}
        assert all(variants.values())
        records.append({'source': str(source), 'image_id': entry.get('image_id'), 'stratum': entry.get('stratum'),
                        'source_sha256': before, 'upright_dimensions': upright_size,
                        'decode_seconds': decode_seconds, 'cache_miss': miss_info, 'cache_hit': hit_info,
                        'cache_dimensions': miss.size, 'cache_notes': miss_desc.notes,
                        'variants': {name: {'path': path, 'sha256': hashlib.sha256(Path(path).read_bytes()).hexdigest()}
                                     for name, path in variants.items()}, 'models': {}})
        assert hashlib.sha256(source.read_bytes()).hexdigest() == before, 'Source changed'
        print(json.dumps({'prepared': index + 1, 'total': len(sources)}), flush=True)

    for name in args.models:
        metric = None
        if name in ('spaq', 'ava'):
            url = f'https://tfhub.dev/google/musiq/{name}/1'
            weights = ROOT / 'models/tfhub_cache' / hashlib.sha1(url.encode()).hexdigest()
            if not (weights / 'saved_model.pb').exists():
                raise RuntimeError(f'Cached weights required: {name}; no download is performed')
            scorer.models[name] = hub.load(str(weights))
            def predict(path):
                return scorer.predict_quality(path, name)
        else:
            import torch
            import pyiqa.utils.download_util as downloads
            from modules.liqe import LiqeScorer
            from modules.topiq import TopiqScorer
            from modules.arniqa import ArniqaScorer
            torch.set_num_threads(4)

            def no_download(*_args, **_kwargs):
                raise RuntimeError('Benchmark requires cached weights; download refused')

            downloads.download_url_to_file = no_download
            torch.hub.download_url_to_file = no_download
            metric = {'liqe': LiqeScorer, 'topiq': TopiqScorer, 'arniqa': ArniqaScorer}[name](device='cpu')
            if not metric.available:
                raise RuntimeError(f'Cached model unavailable: {name}')

            def predict(path):
                payload = metric.predict(path)
                if payload.get('status') != 'success':
                    return None
                return payload['score']

        warmed_shapes = set()
        for record in records:
            scores = {}
            for policy, variant in record['variants'].items():
                # Warm up each shape; compilation is reported separately.
                with Image.open(variant['path']) as image:
                    shape = image.size
                warmup_seconds = None
                if shape not in warmed_shapes:
                    started = time.perf_counter()
                    predict(variant['path'])
                    warmup_seconds = time.perf_counter() - started
                    warmed_shapes.add(shape)
                timings = []
                for _ in range(args.repeats):
                    started = time.perf_counter()
                    score = predict(variant['path'])
                    timings.append(time.perf_counter() - started)
                scores[policy] = {'score': score, 'warmup_seconds': warmup_seconds,
                                  'median_seconds': statistics.median(timings), 'seconds': timings}
            record['models'][name] = scores
            print(json.dumps({'source': Path(record['source']).name, 'model': name, 'results': scores}), flush=True)
            (args.output / 'progress.json').write_text(json.dumps(records, indent=2))
        if name in scorer.models:
            del scorer.models[name]
        metric = None

    import resource
    report = {'benchmark': 'scoring-input-pilot-v1', 'executor': scorer.VERSION,
              'baseline_policy': scorer.PREPROCESSING_POLICY, 'resolution': 512, 'jpeg_quality': 85,
              'device': 'CPU', 'repeats': args.repeats, 'decision': 'HOLD',
              'manifest': manifest, 'models': args.models,
              'limitations': ['Sampling and holdout coverage must be reviewed before promotion',
                              'Cache comparison combines decode route, cap and encoding changes',
                              'Peak RSS is cumulative process usage, not per-model memory'],
              'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, 'samples': records}
    (args.output / 'results.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({'report': str(args.output / 'results.json'), 'decision': 'HOLD'}), flush=True)


if __name__ == '__main__':
    main()
