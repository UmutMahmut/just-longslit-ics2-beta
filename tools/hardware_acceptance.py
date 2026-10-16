"""Repeatable bench acceptance for the supplied ASI294/ASI678 deployment.

Uses FastAPI lifespan and HTTP endpoints via TestClient, never vendor capture
software. Validates both serials and full-frame science FITS. Does not change
cooler settings or simulate USB unplugging. Install .[dev] first. Example:

    python tools/hardware_acceptance.py --hardware --dll C:/vendor/ASICamera2.dll
"""
import os, sys, json, time, hashlib, traceback
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse, unquote
from urllib.request import url2pathname

import argparse
parser = argparse.ArgumentParser(description='Explicit dual-ZWO API bench acceptance. Requires attached cameras; writes engineering FITS.')
parser.add_argument('--hardware', action='store_true', help='Explicitly enable real hardware acquisition')
parser.add_argument('--dll', required=True, type=Path)
parser.add_argument('--config', type=Path, default=Path('config/cameras.lhires-dual-zwo.example.json'))
parser.add_argument('--output', type=Path, default=Path('var/hardware-acceptance'))
parser.add_argument('--long-exposure-s', type=float, default=10)
parser.add_argument('--sequence-cycles', type=int, default=1, help='Saved automatic 1/2/3-second sequences with concurrent guide previews')
args = parser.parse_args()
if not args.hardware:
    parser.error('Pass --hardware to explicitly enable real camera operations')
if sys.flags.optimize:
    parser.error('Do not use Python -O: acceptance assertions must be enabled')
if args.long_exposure_s < 2:
    parser.error('--long-exposure-s must be at least 2')
if not 1 <= args.sequence_cycles <= 1000:
    parser.error('--sequence-cycles must be between 1 and 1000')
root=Path(__file__).resolve().parents[1]; os.chdir(root); stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'); out=args.output.resolve()/stamp; out.mkdir(parents=True)
os.environ.update(ICS_ZWO_SDK_LIBRARY=str(args.dll.resolve()),ICS_BETA_CAMERA_CONFIG=str(args.config.resolve()),ICS_BETA_DATA_ROOT=str(out/'data'),JUSTLS_SETUP_CONTEXT_PATH=str(out/'setup.json'),JUSTLS_SEQUENCE_STATE_PATH=str(out/'sequence.json'),JUSTLS_INSTRUMENT_CONTEXT_PATH=str(out/'instrument.json'),JUSTLS_AUTO_READOUT_ENABLED='1',ICS_BETA_HOTPLUG_INTERVAL_S='2')
os.environ.pop('ICS_BETA_FORCE_SIM',None)
sys.path.insert(0,str(root/'src'))
from fastapi.testclient import TestClient
from justls.ics.app.main import app
from justls.ics.kernel.runtime import get_runtime
from astropy.io import fits
import numpy as np
report={'output':str(out),'checks':[],'frames':[]}
def check(name, detail=None):
    report['checks'].append({'name':name,'detail':detail}); print(name,flush=True)
def save_report():
    (out/'report.json').write_text(json.dumps(report,indent=2,default=str))
def cmd(client,path,payload=None,ok=True):
    r=client.post('/api/v1/'+path,json=payload) if payload is not None else client.post('/api/v1/'+path)
    if ok: assert r.status_code==200 and r.json().get('ok',r.json().get('reloaded',False)),(path,r.status_code,r.text)
    return r

def await_complete(client,deadline_s=20):
    deadline=time.monotonic()+deadline_s; previews=0
    while time.monotonic()<deadline:
        r=client.get('/camera/slit/latest.jpg'); assert r.status_code==200,r.text; previews+=1
        status=client.get('/api/v1/observation/status').json()
        if status['state']=='completed':
            check('automatic readout with concurrent guide preview',{'guide_frames':previews})
            return status
        assert status['state'] in ('exposing','reading_out'),status
        time.sleep(.3)
    raise AssertionError('completion timeout')

def validate(status):
    rec=status['latest_exposure_record']; result=status['last_exposure']; path=Path(url2pathname(unquote(urlparse(result['file_uri']).path)))
    with fits.open(path,uint=True,checksum=True) as hdus:
        hdus.verify('exception'); data=hdus[0].data; h=hdus[0].header
        assert data.shape==(2822,4144) and data.dtype==np.dtype('uint16')
        assert h['SIMULATE'] is False and h['DETSER']=='28344F041D010900'
        assert h['BAYERPAT']=='RGGB'; assert h['EXPTIME']>0
        assert datetime.fromisoformat(h['DATE-END'])>=datetime.fromisoformat(h['DATE-OBS'])
        assert hashlib.sha256(path.read_bytes()).hexdigest()==result['checksum']
        report['frames'].append({'path':str(path),'shape':data.shape,'dtype':str(data.dtype),'min':int(data.min()),'max':int(data.max()),'mean':float(data.mean()),'requested':h.get('EXPREQ'),'actual':h['EXPTIME'],'serial':h['DETSER'],'simulated':h['SIMULATE'],'checksum':result['checksum']})
    check('independent FITS validation',str(path));save_report()

def expose(client,duration,save=True):
    cmd(client,'observation/arm',{'exp_time_s':duration,'frame_type':'test','save_requested':save})
    cmd(client,'observation/start')
    return await_complete(client,duration+20)
try:
    with TestClient(app) as client:
        cameras=client.get('/api/v1/cameras/status').json(); (out/'cameras.json').write_text(json.dumps(cameras,indent=2))
        assert cameras['science_camera'] and cameras['science_camera']['driver']=='zwo' and cameras['science_camera']['connected'],cameras
        assert cameras['slit_camera']['driver']=='zwo' and cameras['slit_camera']['connected'],cameras
        check('both hardware cameras bound by serial')
        for duration in (.1,.2,args.long_exposure_s): validate(expose(client,duration))
        check('short repeated and longer integration', args.long_exposure_s)
        cmd(client,'observation/arm',{'exp_time_s':.6,'frame_type':'test','save_requested':False});cmd(client,'observation/start')
        assert client.post('/api/v1/cameras/reload').status_code==409
        cmd(client,'observation/abort_discard')
        cmd(client,'observation/arm',{'exp_time_s':2,'frame_type':'test','save_requested':True});cmd(client,'observation/start')
        time.sleep(.8)
        assert client.get('/api/v1/observation/status').json()['state']=='exposing'
        validate(await_complete(client));check('abort A then B survives A deadline; active reload rejected')
        # Probe the SDK's retained early-readout behavior without requesting persistence.
        cmd(client,'observation/arm',{'exp_time_s':3,'frame_type':'test','save_requested':False});cmd(client,'observation/start')
        time.sleep(.2); early=cmd(client,'observation/stop_readout',ok=False)
        report['early_readout']={'status':early.status_code,'response':early.json()};save_report()
        check('early readout exercised',{'status':early.status_code,'ok':early.json().get('ok')})
        if early.json().get('ok'):
            assert early.json()['observation_state']=='completed'
        else:
            assert client.get('/api/v1/observation/status').json()['state']=='exposing'
            await_complete(client);check('unsupported early readout preserves automatic completion')
        assert cmd(client,'cameras/reload').json()['science_camera']
        check('controlled real handle close and rebind')
        plan={'plan_id':'hardware-bench','save_requested':True,'exposures':[{'exp_time_s':.1,'frame_type':'test'},{'exp_time_s':.2,'frame_type':'test'}]}
        cmd(client,'observation/sequence/load',plan)
        assert client.post('/api/v1/cameras/reload').status_code==409
        for i in range(2):
            cmd(client,'observation/sequence/start');validate(await_complete(client))
            seq=client.get('/api/v1/observation/sequence/status').json();assert len(seq['step_results'])==i+1,seq
        assert seq['state']=='completed';check('two saved operator-stepped sequence exposures with automatic readout')
        for cycle in range(args.sequence_cycles):
            auto_plan = {'save_requested': True, 'auto_advance': True, 'exposures': [
                {'exp_time_s': seconds, 'frame_type': 'test'} for seconds in (1, 2, 3)
            ]}
            cmd(client, 'observation/sequence/load', auto_plan)
            cmd(client, 'observation/sequence/start')
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                preview = client.get('/camera/slit/latest.jpg')
                assert preview.status_code == 200, preview.text
                assert client.get('/api/v1/status/full').status_code == 200
                seq = client.get('/api/v1/observation/sequence/status').json()
                if seq['state'] == 'completed':
                    break
                assert seq['state'] == 'running', seq
                time.sleep(.3)
            assert seq['state'] == 'completed' and len(seq['step_results']) == 3, seq
            validate(client.get('/api/v1/observation/status').json())
            check('automatic sequence cycle completed', cycle + 1)
        guide = client.get('/api/v1/cameras/status').json()['slit_camera']
        assert guide.get('failed_frames', 0) == 0, guide
        report['guide_after_sequences'] = guide
        validate(expose(client,.1))
        old=get_runtime();cmd(client,'observation/arm',{'exp_time_s':3,'frame_type':'test','save_requested':False});cmd(client,'observation/start')
    assert old.closed and not old.readout_scheduler.active
    check('lifespan shutdown cancels pending readout and releases hardware')
    with TestClient(app) as client:
        validate(expose(client,.1));check('service lifecycle restart and capture')
    report['passed']=True
except BaseException as exc:
    report['passed']=False;report['error']=repr(exc);report['traceback']=traceback.format_exc();print(report['traceback'],flush=True)
finally:
    save_report();print('REPORT',out/'report.json',flush=True)
if not report['passed']:sys.exit(1)
