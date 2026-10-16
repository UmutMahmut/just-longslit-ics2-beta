import time
import pytest
from fastapi.testclient import TestClient
from justls.ics.app.main import app
from justls.ics.kernel.runtime import get_runtime, reset_runtime, shutdown_runtime


@pytest.fixture(autouse=True)
def manual_profile(monkeypatch, tmp_path):
    from justls.ics.infra.camera_config import CameraSystemConfig
    profile = CameraSystemConfig(calibration_control='manual')
    path = tmp_path / 'manual-sim.json'
    path.write_text(profile.model_dump_json(), encoding='utf-8')
    monkeypatch.setenv('ICS_BETA_CAMERA_CONFIG', str(path))
    monkeypatch.setenv('JUSTLS_AUTO_READOUT_ENABLED', '1')
    reset_runtime()
    yield
    shutdown_runtime()


def completed(client):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        status = client.get('/api/v1/observation/status').json()
        if status['state'] == 'completed':
            return status
        time.sleep(.01)
    pytest.fail(str(status))


def test_zero_bias_completes_and_preserves_requested_zero():
    client = TestClient(app)
    assert client.post('/api/v1/observation/arm', json={'frame_type': 'bias', 'exp_time_s': 0}).json()['ok']
    assert client.post('/api/v1/observation/start').json()['ok']
    record = completed(client)['latest_exposure_record']
    assert record['requested_exp_time_s'] == 0
    assert record['frame_type'] == 'bias'


@pytest.mark.parametrize('frame', ['science', 'dark', 'flat', 'arc', 'test'])
def test_zero_is_only_valid_for_bias(frame):
    assert TestClient(app).post('/api/v1/observation/arm', json={'frame_type': frame, 'exp_time_s': 0}).status_code == 422


@pytest.mark.parametrize('frame', ['flat', 'arc'])
def test_manual_calibration_does_not_require_electric_lamp_state(frame):
    client = TestClient(app)
    assert not get_runtime().lamps.get_snapshot().lamp_enabled
    response = client.post('/api/v1/observation/arm', json={'frame_type': frame, 'exp_time_s': .01})
    assert response.json()['ok'], response.text
    assert client.post('/api/v1/observation/start').json()['ok']
    status = completed(client)
    assert status['observation_meta']['calibration_snapshot']['control_mode'] == 'manual'
    assert status['observation_meta']['calibration_snapshot']['physical_state_verified'] is False


def test_manual_sequence_includes_bias_dark_flat_arc():
    client = TestClient(app)
    plan = {'exposures': [{'frame_type': frame, 'exp_time_s': 0 if frame == 'bias' else .01}
                          for frame in ['bias', 'dark', 'flat', 'arc']]}
    response = client.post('/api/v1/observation/sequence/load', json=plan)
    assert response.json()['ok'], response.text
    for index in range(4):
        assert client.post('/api/v1/observation/sequence/start').json()['ok']
        completed(client)
        seq = client.get('/api/v1/observation/sequence/status').json()
        assert len(seq['step_results']) == index + 1
        assert not seq['active_exposure']
    assert seq['state'] == 'completed'


def test_settings_apply_to_next_frame_metadata_and_pixels():
    client = TestClient(app)
    response = client.put('/api/v1/cameras/science/settings', json={'gain': 125, 'offset': 20, 'binning': 2, 'width': 320, 'height': 240})
    assert response.status_code == 200, response.text
    assert client.post('/api/v1/observation/arm', json={'exp_time_s': .01, 'frame_type': 'test'}).json()['ok']
    assert client.post('/api/v1/observation/start').json()['ok']
    metadata = completed(client)['latest_exposure_record']['detector_metadata']
    assert (metadata['gain'], metadata['offset'], metadata['bin_x'], metadata['width'], metadata['height']) == (125, 20, 2, 320, 240)
    assert get_runtime().detector.adapter.driver.get_latest_image().shape == (240, 320)


def test_invalid_settings_and_ownership_do_not_mutate():
    client = TestClient(app)
    before = client.get('/api/v1/cameras/science/settings').json()
    assert client.put('/api/v1/cameras/science/settings', json={'width': 10000, 'gain': 22}).status_code == 400
    assert client.get('/api/v1/cameras/science/settings').json() == before
    assert client.put('/api/v1/cameras/slit/settings', json={'cooler_enabled': True}).status_code == 400
    assert client.post('/api/v1/observation/arm', json={'exp_time_s': 1}).json()['ok']
    assert client.put('/api/v1/cameras/science/settings', json={'gain': 22}).status_code == 409
    assert client.post('/api/v1/observation/abort_discard').json()['ok']
    assert client.post('/api/v1/observation/sequence/load', json={'exposures': [{'exp_time_s': 1}]}).json()['ok']
    assert client.put('/api/v1/cameras/slit/settings', json={'gain': 22}).status_code == 409
