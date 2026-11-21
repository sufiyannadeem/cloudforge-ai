"""Real local TLS handshakes: no cloud calls and no verification bypasses."""
import importlib.util
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest

ROOT=Path(__file__).resolve().parents[1]


class MetricsHandler(BaseHTTPRequestHandler):
    redirect_to = None

    def do_GET(self):
        if self.redirect_to:
            self.send_response(302);self.send_header("Location",self.redirect_to);self.end_headers();return
        body=json.dumps({'status':'success','data':{'resultType':'vector','result':[{'metric':{},'value':[1,'1']}]}}).encode()
        self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(body)

    def log_message(self,*args):
        pass


@pytest.fixture
def endpoint(tmp_path,monkeypatch):
    monkeypatch.setenv('NO_PROXY','localhost,127.0.0.1')
    cert=tmp_path/'cert.pem';key=tmp_path/'key.pem'
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1',
                    '-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost',
                    '-keyout',str(key),'-out',str(cert)],check=True,capture_output=True)
    server=ThreadingHTTPServer(('127.0.0.1',0),MetricsHandler)
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version=ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(cert,key)
    server.socket=context.wrap_socket(server.socket,server_side=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    yield f'https://localhost:{server.server_port}',cert
    server.shutdown();server.server_close();thread.join(timeout=3)


def client(service,url):
    name='tls_'+service.replace('-','_')
    spec=importlib.util.spec_from_file_location(name,ROOT/'services'/service/'app/prometheus_client.py')
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    return module.PrometheusClient(base_url=url,timeout_seconds=2)


@pytest.mark.parametrize('service',['aiops-service','finops-service'])
def test_python_clients_verify_ca_and_hostname(endpoint,service):
    url,cert=endpoint
    env=dict(os.environ);env.pop('SSL_CERT_FILE',None);env['APP_ENV']='production'
    # CA variables are configured before process startup in rendered workloads.
    probe = "import importlib.util,json,sys; spec=importlib.util.spec_from_file_location('probe',sys.argv[1]); m=importlib.util.module_from_spec(spec);sys.modules['probe']=m;spec.loader.exec_module(m);r=m.PrometheusClient(base_url=sys.argv[2],timeout_seconds=2).query('up');print(json.dumps({'error':r.error,'value':r.value}))"
    command=[sys.executable,'-c',probe,str(ROOT/'services'/service/'app/prometheus_client.py')]
    def query(target):
        return json.loads(subprocess.check_output(command+[target],env=env,text=True,timeout=10))
    assert query(url)['error'] is not None
    env['SSL_CERT_FILE']=str(cert)
    trusted=query(url)
    assert trusted['error'] is None and len(trusted['value'])==1
    assert query(url.replace('localhost','127.0.0.1'))['error'] is not None


def test_node_fetch_verifies_ca_and_hostname(endpoint):
    url,cert=endpoint
    env=dict(os.environ)
    env.pop('NODE_EXTRA_CA_CERTS',None);env.pop('NODE_TLS_REJECT_UNAUTHORIZED',None)
    command=['node','-e',"fetch(process.argv[1],{redirect:'error'}).then(r=>r.json()).then(d=>{if(d.status!=='success')process.exit(3)}).catch(()=>process.exit(2))"]
    assert subprocess.run(command+[url],env=env,capture_output=True,timeout=10).returncode==2
    env['NODE_EXTRA_CA_CERTS']=str(cert)
    assert subprocess.run(command+[url],env=env,capture_output=True,timeout=10).returncode==0
    assert subprocess.run(command+[url.replace('localhost','127.0.0.1')],env=env,capture_output=True,timeout=10).returncode==2


def test_local_development_http_remains_available(monkeypatch):
    monkeypatch.setenv('NO_PROXY','localhost,127.0.0.1')
    server=ThreadingHTTPServer(('127.0.0.1',0),MetricsHandler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        for service in ['aiops-service','finops-service']:
            assert client(service,f'http://localhost:{server.server_port}').query('up').error is None
    finally:
        server.shutdown();server.server_close();thread.join(timeout=3)


@pytest.mark.parametrize('service',['aiops-service','finops-service'])
def test_production_monitoring_rejects_plaintext_and_redirects(endpoint,monkeypatch,service):
    url,cert=endpoint
    monkeypatch.setenv('APP_ENV','production');monkeypatch.setenv('SSL_CERT_FILE',str(cert))
    assert 'HTTPS' in client(service,url.replace('https:','http:')).query('up').error
    monkeypatch.setattr(MetricsHandler,'redirect_to','http://localhost:9')
    assert '302' in client(service,url).query('up').error
