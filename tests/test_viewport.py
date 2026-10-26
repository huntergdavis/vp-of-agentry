"""Viewport samples contain dimensions only and expire with existing owner sessions."""
import importlib,json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient

server=importlib.import_module('server.app')
SAMPLE=dict(innerWidth=1440,innerHeight=900,devicePixelRatio=1,screenWidth=1920,screenHeight=1080)

class ViewportTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        for name,value in [('DB',Path(temp.name)/'db.sqlite3'),('AUTH',Path(temp.name)/'auth.json'),
                           ('CREDENTIALS',Path(temp.name)/'credentials'),('_panes',lambda:[])]:
            p=patch.object(server,name,value);p.start();self.addCleanup(p.stop)
        server.LOGIN_ATTEMPTS.clear();server._initialize()
        self.password=server.CREDENTIALS.read_text().splitlines()[0].removeprefix('Password: ')
        self.client=TestClient(server.app);self.addCleanup(self.client.close)
    def login(self,client=None):
        client=client or self.client
        self.assertEqual(200,client.post('/api/login',json={'password':self.password}).status_code)
        return client
    def test_auth_origin_and_schema(self):
        self.assertEqual(401,self.client.post('/api/viewport',json=SAMPLE).status_code)
        self.login()
        self.assertEqual(403,self.client.post('/api/viewport',json=SAMPLE,headers={'origin':'https://elsewhere.invalid'}).status_code)
        for bad in (dict(SAMPLE,innerWidth=0),dict(SAMPLE,innerHeight='900'),dict(SAMPLE,devicePixelRatio=0),
                    dict(SAMPLE,url='must-not-store'),dict(SAMPLE,viewport_at=1),dict(SAMPLE,innerWidth=32769)):
            self.assertEqual(422,self.client.post('/api/viewport',json=bad).status_code)
        self.assertEqual(422,self.client.post('/api/viewport',content='{"innerWidth":390,"innerHeight":844,"devicePixelRatio":NaN}',headers={'content-type':'application/json'}).status_code)
        self.assertEqual([],self.client.get('/api/channels').json()['viewports'])
    def test_latest_only_session_isolation_expiry_and_migration(self):
        self.login()
        first_at=time.time()
        with patch.object(server.time,'time',return_value=first_at):
            self.assertEqual(200,self.client.post('/api/viewport',json=SAMPLE).status_code)
        self.assertEqual(first_at,self.client.get('/api/channels').json()['viewports'][0]['viewport_at'])
        other=TestClient(server.app);self.addCleanup(other.close);self.login(other)
        mobile=dict(innerWidth=390,innerHeight=844,devicePixelRatio=3,screenWidth=390,screenHeight=844)
        self.assertEqual(200,other.post('/api/viewport',json=mobile).status_code)
        changed=dict(SAMPLE,innerWidth=1280)
        replacement_at=time.time()+1
        with patch.object(server.time,'time',return_value=replacement_at):
            self.client.post('/api/viewport',json=changed)
        server._initialize()  # Idempotent schema migration preserves latest values.
        stored=self.client.get('/api/channels').json()['viewports']
        self.assertEqual([changed,mobile],[{k:v for k,v in item.items() if k!='viewport_at'} for item in stored])
        self.assertEqual(replacement_at,stored[0]['viewport_at'])
        self.assertGreater(stored[0]['viewport_at'],first_at)
        self.assertGreaterEqual(stored[1]['viewport_at'],first_at)
        with server._db() as db:
            self.assertEqual(2,db.execute('SELECT count(*) FROM sessions').fetchone()[0])
            self.assertEqual(0,db.execute('SELECT count(*) FROM messages').fetchone()[0])
            db.execute('UPDATE sessions SET expires_at=? WHERE token_hash=?',
                       (time.time()-1,server._session_key(other.cookies['vp_session'])))
        self.assertEqual([dict(changed,viewport_at=replacement_at)],self.client.get('/api/channels').json()['viewports'])
        self.assertEqual(401,other.post('/api/viewport',json=mobile).status_code)
        self.client.post('/api/logout')
        self.assertEqual([],server._viewports())
    def test_api_can_read_dimensions_but_cannot_create_session_sample(self):
        token=json.loads(server.AUTH.read_text())['token']
        headers={'authorization':'Bearer '+token}
        self.assertEqual(200,self.client.get('/api/channels',headers=headers).status_code)
        self.assertEqual(401,self.client.post('/api/viewport',headers=headers,json=SAMPLE).status_code)
        self.assertEqual([],server._viewports())
