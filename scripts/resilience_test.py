#!/usr/bin/env python3
"""Bounded chaos against this twin only; finally restores every stopped service."""
import json, subprocess, time, uuid
from pathlib import Path
import httpx
BASE='http://localhost:28080';client=httpx.Client(base_url=BASE,timeout=5)
out=Path('artifacts/resilience');out.mkdir(parents=True,exist_ok=True);result={}
def compose(*args):subprocess.run(['bash','scripts/compose.sh',*args],check=True,stdout=subprocess.DEVNULL)
def get(path):r=client.get(path);r.raise_for_status();return r.json()
def wait(predicate,timeout=40):
    deadline=time.monotonic()+timeout;last=None
    while time.monotonic()<deadline:
        try:
            last=predicate()
            if last:return last
        except (httpx.HTTPError,KeyError):pass
        time.sleep(.2)
    raise AssertionError(f'Recovery timed out, last={last}')
def fresh():
    s=get('/api/business/snapshot');return s if s['quality']['status']=='FRESH' else None
try:
    before=wait(fresh);result['before']=before
    compose('stop','redpanda')
    fixture='broker-outage-'+str(uuid.uuid4())
    r=client.post('/api/fulfillment/orders',json={'total':'25.50','fixtureRunId':fixture},headers={'X-Correlation-ID':fixture});r.raise_for_status();created=r.json();result['committedWhileBrokerDown']=created
    stale=wait(lambda:(s if (s:=get('/api/business/snapshot'))['quality']['status']!='FRESH' else None),10)
    assert all(v['value'] is None for v in stale['kpis'].values());result['invalidDuringOutage']=stale
    compose('start','redpanda')
    restored=wait(lambda:(o if (o:=get('/api/fulfillment/orders/'+created['orderId']))['status']=='READY' else None),60)
    result['recoveredOrder']=restored;wait(fresh,60)
    # Stopping analytics leaves its durable history; adapter must explicitly publish stale.
    old=get('/api/business/snapshot');compose('stop','business-analytics');time.sleep(3.5)
    result['adapterDuringAnalyticsOutage']=get('/health/live')
    assert result['adapterDuringAnalyticsOutage']['ready'] is False
    compose('start','business-analytics');new=wait(fresh,60)
    assert new['revision']>old['revision'] and new['coverage']['aggregateCount']>=old['coverage']['aggregateCount']
    assert get('/api/fulfillment/orders/'+created['orderId'])['readyAt']==restored['readyAt']
    result['afterAnalyticsRestart']=new
    compose('restart','grafana-live-adapter');wait(lambda:get('/health/live')['ready'],40)
    compose('restart','grafana');wait(lambda:get('/health/live')['ready'],60)
    result['afterGrafanaRestart']=get('/health/live');result['passed']=True
finally:
    compose('start','redpanda','business-analytics','grafana','grafana-live-adapter')
    (out/'evidence.json').write_text(json.dumps(result,indent=2))
