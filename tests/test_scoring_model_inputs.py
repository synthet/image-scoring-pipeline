"""Model inputs must select actual pixels, with no client paths across transport."""
import hashlib
import queue
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from modules.engines.host import MultiModelHost
from modules.engines.registry import ModelRegistry
from modules.pipeline import ImageJob, ScoringWorker


class PixelModel:
    score_range = (0, 1)
    def __init__(self, name):
        self.name = name
        self.seen = []
    def predict(self, path):
        with Image.open(path) as image:
            self.seen.append((image.size, image.getpixel((0, 0))))
        return {"status": "success", "score": 0.5}
    def normalize(self, value):
        return value


def spec(tmp_path, name, size, color):
    path = tmp_path / (name + '.jpg')
    Image.new('RGB', (size, size), color).save(path)
    return {"path": str(path), "metadata": {
        "policy": "upright-v1", "source_id": "same-source",
        "width": size, "height": size, "resolution": size, "jpeg_quality": 85,
        "source_width": 1600, "source_height": 1200,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }}


def host_for(models):
    registry = ModelRegistry()
    for model in models:
        registry.register(model)
    registry.all_active = lambda: models
    backend = SimpleNamespace(is_raw_file=lambda _: False,
                              calculate_weighted_categories=lambda _: {"general": 0.5})
    return MultiModelHost(backend, registry)


def test_registry_selects_each_model_rendition(tmp_path):
    models = [PixelModel(name) for name in ('liqe', 'spaq', 'ava')]
    host = host_for(models)
    inputs = {name: spec(tmp_path, name, size, color) for name, size, color in
              [('liqe', 1024, 'red'), ('spaq', 512, 'green'), ('ava', 224, 'blue')]}
    result = host.run_all_models(inputs['spaq']['path'], model_inputs=inputs,
                                 logger=lambda *_: None, write_metadata=False)
    for model, size, color in zip(models, [1024, 512, 224], [(254, 0, 0), (0, 128, 1), (0, 0, 254)]):
        assert model.seen == [((size, size), color)]
        assert result['models'][model.name]['input'] == inputs[model.name]['metadata']


def test_missing_selected_input_fails_before_any_inference(tmp_path):
    models = [PixelModel('spaq'), PixelModel('liqe')]
    host = host_for(models)
    one = spec(tmp_path, 'spaq', 512, 'red')
    with pytest.raises(ValueError, match='liqe'):
        host.run_all_models(one['path'], model_inputs={'spaq': one}, write_metadata=False)
    assert all(not model.seen for model in models)


def test_external_scores_do_not_require_an_input_or_replay_inference(tmp_path):
    models = [PixelModel('spaq'), PixelModel('liqe')]
    host = host_for(models)
    one = spec(tmp_path, 'spaq', 512, 'red')
    result = host.run_all_models(one['path'], model_inputs={'spaq': one},
                                 external_scores={'liqe': {'status': 'success', 'score': 0.7,
                                                         'normalized_score': 0.7}},
                                 write_metadata=False, logger=lambda *_: None)
    assert models[1].seen == []
    assert result['models']['liqe']['score'] == 0.7


@pytest.mark.parametrize('overrides', [{}, {'liqe': 1024, 'spaq': 512, 'ava': 224},
                                      {'liqe': {'resolution': 1024}, 'ava': 224}])
def test_worker_derives_variants_from_common_source(tmp_path, monkeypatch, overrides):
    from modules import pipeline
    models = [PixelModel(name) for name in ('liqe', 'spaq', 'ava')]
    host = host_for(models)
    source = tmp_path / 'source.jpg'
    Image.new('RGB', (1600, 1200), 'white').save(source)
    calls = []
    def preprocess(path, output_dir=None, resolution_override=None):
        calls.append((path, resolution_override))
        size = resolution_override or 512
        output = Path(output_dir) / f'preprocessed_{size}.jpg'
        Image.new('RGB', (size, size), 'white').save(output)
        return str(output)
    host.backend.preprocess_image = preprocess
    monkeypatch.setattr(pipeline.app_config, 'load_config', lambda: {
        'raw_conversion': {'max_resolution': 512}, 'scoring': {'model_preprocessing': overrides}})
    output = queue.Queue()
    worker = ScoringWorker(queue.Queue(), output, threading.Event(), host)
    job = ImageJob(str(source), job_id=0, process_path=str(source), source_decode_route='pillow:raster')
    worker.process(job)
    assert output.get_nowait() is job
    assert job.result is not None
    for model in models:
        configured = overrides.get(model.name, 512)
        expected = configured['resolution'] if isinstance(configured, dict) else configured
        assert model.seen[0][0] == (expected, expected)
        assert job.result['models'][model.name]['input']['source_width'] == 1600
        assert job.result['models'][model.name]['input']['decode_route'] == 'pillow:raster'
    assert all(path == str(source) for path, _ in calls)
    assert len(calls) == len({m.seen[0][0] for m in models})


def test_remote_scoring_receives_model_specific_pixels_without_host_paths(tmp_path):
    from modules.remote_gpu.proxies import RemoteScoringHost
    from modules.remote_gpu.runtime import InferenceRuntime
    from modules.remote_gpu.contract import SCORING

    models = [PixelModel(name) for name in ('liqe', 'spaq', 'ava')]
    local = host_for(models)
    received = []
    runtime = InferenceRuntime(SimpleNamespace(scoring_host=lambda: local))
    class Client:
        def call(self, endpoint, params, data, **kwargs):
            received.append(params)
            assert endpoint == SCORING
            return runtime.execute(endpoint, params, data, filename=kwargs['filename'])
    remote = RemoteScoringHost(Client(), local.backend, local.registry)
    inputs = {name: spec(tmp_path, name, size, color) for name, size, color in
              [('liqe', 1024, 'red'), ('spaq', 512, 'green'), ('ava', 224, 'blue')]}
    result = remote.run_all_models(inputs['spaq']['path'], model_inputs=inputs,
                                   logger=lambda *_: None, write_metadata=False)
    for model, size in zip(models, [1024, 512, 224]):
        assert model.seen[0][0] == (size, size)
        assert result['models'][model.name]['input'] == inputs[model.name]['metadata']
    assert str(tmp_path) not in str(received)
    assert all('path' not in str(item) for item in received)


def test_http_schema_preserves_selected_model_inputs(tmp_path):
    from fastapi.testclient import TestClient
    from modules.remote_gpu.client import GpuRunnerClient
    from modules.remote_gpu.proxies import RemoteScoringHost
    from modules.remote_gpu.server import create_app
    models = [PixelModel(name) for name in ('spaq', 'ava')]
    local = host_for(models)
    config = {'scoring': {}}
    app = create_app(token='test', provider=SimpleNamespace(scoring_host=lambda: local),
                     config_loader=lambda: config)
    inputs = {'spaq': spec(tmp_path, 'spaq', 512, 'red'), 'ava': spec(tmp_path, 'ava', 224, 'blue')}
    with TestClient(app) as http:
        client = GpuRunnerClient('http://testserver', 'test', http=http, config_loader=lambda: config)
        remote = RemoteScoringHost(client, local.backend, local.registry)
        result = remote.run_all_models(inputs['spaq']['path'], model_inputs=inputs,
                                       logger=lambda *_: None, write_metadata=False)
    assert models[0].seen[0][0] == (512, 512)
    assert models[1].seen[0][0] == (224, 224)
    assert result['models']['ava']['input'] == inputs['ava']['metadata']


@pytest.mark.parametrize('params', [
    {'model_inputs': {}},
    {'model_inputs': {}, 'scoring_inputs_version': 2},
    {'model_inputs': {}, 'scoring_inputs_version': True},
    {'scoring_inputs_version': 1},
])
def test_http_rejects_incomplete_or_unsupported_bundle_before_inference(tmp_path, params):
    import json
    from fastapi.testclient import TestClient
    from modules.remote_gpu.server import create_app
    from modules.remote_gpu.contract import SCORING, FINGERPRINT_HEADER, phase_fingerprint
    app = create_app(token='test', provider=SimpleNamespace(
        scoring_host=lambda: pytest.fail('invalid bundle reached models')), config_loader=lambda: {})
    one = spec(tmp_path, 'spaq', 512, 'red')
    with TestClient(app) as http:
        response = http.post(SCORING, headers={'Authorization': 'Bearer test',
                             FINGERPRINT_HEADER: phase_fingerprint({}, 'scoring')},
                             data={'meta': json.dumps(params)},
                             files={'file': ('input.jpg', Path(one['path']).read_bytes(), 'image/jpeg')})
    assert response.status_code == 422


def test_changed_prepared_bytes_are_rejected_before_inference(tmp_path):
    model = PixelModel('spaq')
    host = host_for([model])
    one = spec(tmp_path, 'spaq', 512, 'red')
    Path(one['path']).write_bytes(b'corrupted')
    with pytest.raises(ValueError, match='digest'):
        host.run_all_models(one['path'], model_inputs={'spaq': one}, write_metadata=False)
    assert not model.seen


def test_result_worker_persists_input_provenance_in_run_report(tmp_path, monkeypatch):
    import json
    from modules import pipeline
    from modules.db_operations import job_reports
    from modules.report_collector import ReportCollector
    one = spec(tmp_path, 'spaq', 512, 'red')
    writes = []
    connector = SimpleNamespace(execute=lambda sql, params: writes.append((sql, params)))
    monkeypatch.setattr(pipeline.db, 'upsert_image', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(pipeline.db, 'set_image_phase_status', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(pipeline.db, 'update_job_phase_counters', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(pipeline.db, 'insert_job_image_actions', lambda actions:
                        job_reports.insert_job_image_actions(actions, get_connector=lambda: connector))
    collector = ReportCollector(10, 'scoring')
    worker = pipeline.ResultWorker(queue.Queue(), queue.Queue(), threading.Event(), None)
    worker.report_collector = collector
    job = ImageJob('original.jpg', 10, image_id=42, status='success', result={
        'summary': {}, 'models': {'spaq': {'normalized_score': 0.5, 'input': one['metadata']}}})
    worker.process(job)
    assert collector.flush() == 1
    stored = json.loads(writes[0][1][-1])
    assert stored['scoring_inputs']['spaq'] == one['metadata']
    assert 'path' not in stored['scoring_inputs']['spaq']


@pytest.mark.parametrize('value', [True, 512.5, 'large', -1])
def test_invalid_resolution_rejected_without_inference(tmp_path, monkeypatch, value):
    from modules import pipeline
    model = PixelModel('liqe')
    host = host_for([model])
    source = tmp_path / 'source.jpg'
    Image.new('RGB', (1600, 1200), 'white').save(source)
    host.backend.preprocess_image = lambda *_args, **_kwargs: pytest.fail('invalid policy must fail first')
    monkeypatch.setattr(pipeline.app_config, 'load_config', lambda: {
        'scoring': {'model_preprocessing': {'liqe': value}}})
    output = queue.Queue()
    worker = ScoringWorker(queue.Queue(), output, threading.Event(), host)
    job = ImageJob(str(source), job_id=0, process_path=str(source))
    worker.process(job)
    assert output.get_nowait().status == 'failed'
    assert not model.seen


def test_bundle_failure_is_detected_before_loading_remote_models(tmp_path):
    import base64
    from modules.remote_gpu.contract import SCORING, SCORING_INPUTS_VERSION
    from modules.remote_gpu.runtime import InferenceRuntime
    one = spec(tmp_path, 'spaq', 512, 'red')
    runtime = InferenceRuntime(SimpleNamespace(scoring_host=lambda: pytest.fail('invalid input reached models')))
    params = {'scoring_inputs_version': SCORING_INPUTS_VERSION, 'model_inputs': {
        'spaq': {'data': base64.b64encode(b'corrupted').decode(), 'metadata': one['metadata']}}}
    with pytest.raises(ValueError, match='digest'):
        runtime.execute(SCORING, params, Path(one['path']).read_bytes(), filename='input.jpg')


@pytest.mark.ml
def test_real_variants_keep_upright_source_detail_and_order_independence(tmp_path, monkeypatch):
    import numpy as np
    from modules import pipeline
    import scripts.python.run_all_musiq_models as module
    source = tmp_path / 'detail.png'
    y, x = np.indices((1200, 1600))
    pixels = np.stack([(x % 13)*19, (y % 11)*23, ((x+y) % 7)*36], axis=-1).astype(np.uint8)
    image = Image.fromarray(pixels)
    image.getexif()[274] = 8
    image.save(source, exif=image.getexif())
    config = {'raw_conversion': {'max_resolution': 512, 'jpeg_quality': 85},
              'scoring': {'model_preprocessing': {'liqe': 1024, 'spaq': 224, 'ava': 512}}}
    monkeypatch.setattr(pipeline.app_config, 'load_config', lambda: config)
    monkeypatch.setattr(module, '_merged_app_config', lambda: config)
    backend = object.__new__(module.MultiModelMUSIQ)
    backend.temp_dir = None
    backend.temp_files = []
    backend.calculate_weighted_categories = lambda _: {'general': 0.5}
    models = [PixelModel(name) for name in ('spaq', 'ava', 'liqe')]
    host = host_for(models)
    host._backend = backend
    for order in (models, list(reversed(models))):
        host.registry.all_active = lambda: order
        output = queue.Queue()
        worker = ScoringWorker(queue.Queue(), output, threading.Event(), host)
        job = ImageJob(str(source), job_id=0, process_path=str(source))
        worker.process(job)
        assert output.get_nowait().status != 'failed', job.error
        for name, resolution in config['scoring']['model_preprocessing'].items():
            expected = backend.preprocess_image(str(source), output_dir=str(tmp_path / f'oracle-{name}'),
                                                resolution_override=resolution)
            metadata = job.result['models'][name]['input']
            assert metadata['sha256'] == hashlib.sha256(Path(expected).read_bytes()).hexdigest()
            assert (metadata['source_width'], metadata['source_height']) == (1200, 1600)


@pytest.mark.ml
def test_direct_registry_raster_call_normalizes_before_inference(tmp_path, monkeypatch):
    import scripts.python.run_all_musiq_models as module
    source = tmp_path / 'original.png'
    image = Image.new('RGB', (1200, 800), 'red')
    image.getexif()[274] = 6
    image.save(source, exif=image.getexif())
    monkeypatch.setattr(module, '_merged_app_config', lambda: {
        'raw_conversion': {'max_resolution': 512, 'jpeg_quality': 85}})
    backend = object.__new__(module.MultiModelMUSIQ)
    backend.temp_dir = str(tmp_path / 'converted')
    Path(backend.temp_dir).mkdir()
    backend.temp_files = []
    backend.calculate_weighted_categories = lambda _: {'general': 0.5}
    model = PixelModel('spaq')
    host = host_for([model])
    host._backend = backend
    host.run_all_models(str(source), write_metadata=False)
    assert model.seen[0][0] == (512, 512)


def test_direct_registry_preparation_failure_does_not_score_original(tmp_path):
    model = PixelModel('spaq')
    host = host_for([model])
    host.backend.preprocess_image = lambda *_args, **_kwargs: None
    original = tmp_path / 'original.jpg'
    Image.new('RGB', (600, 400), 'red').save(original)
    result = host.run_all_models(str(original), write_metadata=False)
    assert result['models'] == {}
    assert not model.seen
