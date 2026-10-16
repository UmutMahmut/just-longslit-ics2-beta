from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from justls.ics.app.main import app
from justls.ics.kernel.runtime import get_runtime, reset_runtime, shutdown_runtime
from justls.ics.kernel.errors import InvalidStateError


@pytest.fixture(autouse=True)
def fresh_runtime():
    reset_runtime()
    yield
    shutdown_runtime()


def start(client, duration=10):
    assert client.post('/api/v1/observation/arm', json={'exp_time_s': duration}).json()['ok']
    assert client.post('/api/v1/observation/start').json()['ok']


def test_abort_from_another_request_cancels_runtime_timer(monkeypatch):
    monkeypatch.setenv('JUSTLS_AUTO_READOUT_ENABLED', '1')
    client = TestClient(app)
    start(client)
    runtime = get_runtime()
    assert runtime.readout_scheduler.active
    assert client.post('/api/v1/observation/abort_discard').json()['ok']
    assert not runtime.readout_scheduler.active
    start(client)
    assert client.post('/api/v1/observation/finish').json()['ok']
    assert not runtime.readout_scheduler.active


def test_late_callback_cannot_complete_replacement_exposure(monkeypatch):
    client = TestClient(app)
    runtime = get_runtime()
    callbacks = []
    monkeypatch.setattr(runtime.readout_scheduler, 'schedule', lambda **kw: callbacks.append(kw['callback']))
    start(client)
    old = callbacks[-1]
    assert client.post('/api/v1/observation/abort_discard').json()['ok']
    start(client)
    old()
    assert client.get('/api/v1/observation/status').json()['state'] == 'exposing'
    callbacks[-1]()
    assert client.get('/api/v1/observation/status').json()['state'] == 'completed'


@pytest.mark.parametrize('phase', ['armed', 'exposing'])
def test_reload_rejects_detector_ownership(phase):
    client = TestClient(app)
    runtime = get_runtime()
    assert client.post('/api/v1/observation/arm', json={'exp_time_s': 10}).json()['ok']
    if phase == 'exposing':
        assert client.post('/api/v1/observation/start').json()['ok']
    assert client.post('/api/v1/cameras/reload').status_code == 409
    assert get_runtime() is runtime
    assert not runtime.closed
    assert client.post('/api/v1/observation/abort_discard').json()['ok']
    assert client.post('/api/v1/cameras/reload').status_code == 200
    assert runtime.closed


def test_released_runtime_rejects_stale_reload_and_commands():
    client = TestClient(app)
    old = get_runtime()
    assert client.post('/api/v1/cameras/reload').status_code == 200
    with pytest.raises(InvalidStateError):
        reset_runtime(expected=old)
    with pytest.raises(InvalidStateError):
        old.require_open()


def test_shutdown_invalidates_pending_callback(monkeypatch):
    client = TestClient(app)
    old = get_runtime()
    callbacks = []
    monkeypatch.setattr(old.readout_scheduler, 'schedule', lambda **kw: callbacks.append(kw['callback']))
    start(client)
    shutdown_runtime()
    callbacks[-1]()
    assert old.closed
    assert old.detector._latest_exposure_record is None


def test_concurrent_finish_keeps_exactly_one_completed_record():
    client = TestClient(app)
    start(client)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: client.post('/api/v1/observation/finish').json(), range(2)))
    assert sum(result['ok'] for result in results) == 1
    assert client.get('/api/v1/observation/status').json()['state'] == 'completed'


def test_failed_rebuild_drops_released_singleton(monkeypatch):
    import justls.ics.kernel.runtime as module
    old = get_runtime()
    original = module.RuntimeAssembler.build

    def fail(self):
        raise RuntimeError('invalid deployment')

    monkeypatch.setattr(module.RuntimeAssembler, 'build', fail)
    assert TestClient(app).post('/api/v1/cameras/reload').status_code == 503
    assert old.closed
    assert module._default_runtime is None
    monkeypatch.setattr(module.RuntimeAssembler, 'build', original)
    assert get_runtime() is not old


def test_readout_io_failure_is_audited_and_not_stuck_reading(monkeypatch):
    client = TestClient(app)
    start(client)
    runtime = get_runtime()

    def disk_full(*args, **kwargs):
        raise OSError('disk full')

    monkeypatch.setattr(runtime.detector.adapter, 'finish_exposure', disk_full)
    response = client.post('/api/v1/observation/finish')
    assert not response.json()['ok']
    assert runtime.detector._state.value == 'failed'
    assert 'disk full' in response.text
    assert client.post('/api/v1/cameras/reload').status_code == 200


def load_sequence(client):
    result = client.post('/api/v1/observation/sequence/load', json={
        'plan_id': 'regression-sequence', 'save_requested': False,
        'exposures': [{'exp_time_s': 10, 'frame_type': 'test'}] * 2,
    })
    assert result.json()['ok'], result.text


def test_sequence_reload_guard_and_abort_timer_across_requests(monkeypatch):
    monkeypatch.setenv('JUSTLS_AUTO_READOUT_ENABLED', '1')
    client = TestClient(app)
    runtime = get_runtime()
    load_sequence(client)
    assert client.post('/api/v1/cameras/reload').status_code == 409
    assert client.post('/api/v1/observation/sequence/start').json()['ok']
    assert runtime.readout_scheduler.active
    assert client.post('/api/v1/observation/sequence/abort').json()['ok']
    assert not runtime.readout_scheduler.active
    assert client.post('/api/v1/cameras/reload').status_code == 200


def test_sequence_late_callback_cannot_complete_new_step(monkeypatch):
    client = TestClient(app)
    runtime = get_runtime()
    callbacks = []
    monkeypatch.setattr(runtime.readout_scheduler, 'schedule', lambda **kw: callbacks.append(kw['callback']))
    load_sequence(client)
    assert client.post('/api/v1/observation/sequence/start').json()['ok']
    old = callbacks[-1]
    assert client.post('/api/v1/observation/sequence/finish_step').json()['ok']
    assert client.post('/api/v1/observation/sequence/start').json()['ok']
    old()
    status = client.get('/api/v1/observation/sequence/status').json()
    assert status['current_index'] == 1
    assert status['active_exposure']
    callbacks[-1]()
    assert client.get('/api/v1/observation/sequence/status').json()['state'] == 'completed'


def test_sequence_acquisition_failure_requires_durable_review(monkeypatch):
    client = TestClient(app)
    load_sequence(client)
    assert client.post('/api/v1/observation/sequence/start').json()['ok']

    def disconnect():
        raise RuntimeError('camera removed')

    monkeypatch.setattr(get_runtime().detector.adapter, 'finish_exposure', disconnect)
    result = client.post('/api/v1/observation/sequence/finish_step')
    assert not result.json()['ok']
    status = client.get('/api/v1/observation/sequence/status').json()
    assert status['state'] == 'recovery_required'
    assert status['recovery']['reason'] == 'acquisition_failure'
    assert not status['recovery']['retry_allowed']
    assert client.post('/api/v1/cameras/reload').status_code == 409
    assert client.post('/api/v1/observation/sequence/mark_failed').json()['ok']
    assert client.post('/api/v1/cameras/reload').status_code == 200


@pytest.mark.parametrize('endpoint', ['finish', 'stop_readout'])
def test_rejected_readout_does_not_cancel_exposure_timer(monkeypatch, endpoint):
    from justls.ics.kernel.errors import UnsupportedError
    monkeypatch.setenv('JUSTLS_AUTO_READOUT_ENABLED', '1')
    client = TestClient(app)
    start(client)
    runtime = get_runtime()

    def unavailable():
        raise UnsupportedError('readout not ready or unsupported')

    name = 'ensure_readout_ready' if endpoint == 'finish' else 'ensure_early_readout_supported'
    monkeypatch.setattr(runtime.detector.adapter.driver, name, unavailable, raising=False)
    response = client.post('/api/v1/observation/' + endpoint)
    assert not response.json()['ok']
    assert client.get('/api/v1/observation/status').json()['state'] == 'exposing'
    assert runtime.readout_scheduler.active


def test_missing_detector_readout_is_a_command_rejection():
    runtime = get_runtime()
    runtime.detector = None
    client = TestClient(app)
    assert client.post('/api/v1/observation/finish').status_code == 400
    assert client.post('/api/v1/observation/stop_readout').status_code == 400


def test_sequence_start_device_fault_requires_review(monkeypatch):
    client = TestClient(app)
    load_sequence(client)

    def removed(**kwargs):
        raise RuntimeError('camera removed during start')

    monkeypatch.setattr(get_runtime().detector.adapter, 'start_exposure', removed)
    assert not client.post('/api/v1/observation/sequence/start').json()['ok']
    status = client.get('/api/v1/observation/sequence/status').json()
    assert status['state'] == 'recovery_required'
    assert not status['recovery']['retry_allowed']
