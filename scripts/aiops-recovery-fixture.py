#!/usr/bin/env python3
"""Called only by the isolated recovery drill with its private fixture DSN."""
import os
from pathlib import Path
import sys
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'services/aiops-service'))
from fastapi.testclient import TestClient
from app.database import initialize_database, get_connection
from app.main import app


def main():
    url = urlparse(os.environ['DATABASE_URL'])
    socket = os.environ['CF_RECOVERY_SOCKET']
    if url.hostname or parse_qs(url.query).get('host') != [socket] or not Path(socket).is_dir():
        raise RuntimeError('Recovery database must use the private fixture socket')
    with get_connection(connect_timeout=2) as connection:
        row = connection.execute('SELECT proof FROM recovery_drill_identity WHERE run_id=%s',
                                 (os.environ['CF_RECOVERY_DRILL_ID'],)).fetchone()
        if not row or row['proof'] != os.environ['CF_RECOVERY_DRILL_PROOF']:
            raise RuntimeError('Recovery fixture ownership proof required')
    initialize_database()
    initialize_database()  # Restart/idempotence against the actual startup schema.
    key = os.environ['CLOUDFORGE_ALERTMANAGER_KEY']
    with TestClient(app) as client:
        payload = {'alerts': [{'status': 'firing', 'labels': {
            'alertname': 'RecoveryDrillServiceDown', 'service': 'recovery-drill', 'severity': 'critical'},
            'annotations': {'summary': 'Disposable recovery drill evidence'}}]}
        assert client.post('/api/v1/alerts', json=payload).status_code == 401
        assert client.get('/api/v1/incidents').status_code == 401
        headers = {'Authorization': 'Bearer ' + key}
        firing = client.post('/api/v1/alerts', json=payload, headers=headers)
        assert firing.status_code == 200 and firing.json()[0]['status'] == 'open'
        payload['alerts'][0]['status'] = 'resolved'
        resolved = client.post('/api/v1/alerts', json=payload, headers=headers)
        assert resolved.status_code == 200 and resolved.json()[0]['status'] == 'resolved'
        assert resolved.json()[0]['id'] == firing.json()[0]['id']
    with get_connection(connect_timeout=2) as connection:
        row = connection.execute("SELECT status, alert_count FROM aiops_incidents WHERE service='recovery-drill'").fetchone()
        assert row['status'] == 'resolved' and row['alert_count'] == 2
        events = connection.execute("SELECT event_type FROM aiops_incident_events ORDER BY id").fetchall()
        assert [event['event_type'] for event in events] == ['created', 'resolved']
    print('AIOps real schema and authenticated firing/resolved webhook persisted')


if __name__ == '__main__':
    main()
