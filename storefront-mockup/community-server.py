"""Local Avocado Shack catalog and community forms. No external email delivery."""
import argparse, datetime, email.utils, json, os, re, sqlite3, time, unicodedata
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
CONFIG = Path(os.environ.get('AVOSHACK_COMMUNITY_CONFIG', ROOT / 'community.json'))
DB = Path(os.environ.get('AVOSHACK_COMMUNITY_DB', ROOT.parent / 'community-data' / 'community.sqlite3'))

def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys=ON')
    connection.executescript('''CREATE TABLE IF NOT EXISTS subscriptions (
      email TEXT PRIMARY KEY, newsletter INTEGER NOT NULL DEFAULT 0, hikes INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL, consent_version TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS rsvps (
      id INTEGER PRIMARY KEY, event_id TEXT NOT NULL, email TEXT NOT NULL, name TEXT NOT NULL,
      party_size INTEGER NOT NULL CHECK(party_size BETWEEN 1 AND 6), created_at TEXT NOT NULL,
      UNIQUE(event_id,email));''')
    connection.commit()
    try: os.chmod(DB, 0o600)
    except OSError: pass
    return connection

def config():
    return json.loads(CONFIG.read_text())

def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

class FormError(ValueError):
    """A guest-facing form problem whose text is safe to show as-is."""

def email_address(value):
    if not isinstance(value, str): raise FormError('Please enter a valid email address.')
    value = value.strip().lower()
    # Refuse (never strip) ASCII controls; the \s below misses NUL, ESC, DEL and others.
    if any(ord(c)<0x20 or ord(c)==0x7f for c in value): raise FormError('Please enter a valid email address.')
    if len(value)>254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
        raise FormError('Please enter a valid email address.')
    # Refuse invisible/look-alike characters (format, separator, surrogate, private use) and empty domain labels.
    if any(unicodedata.category(c) in ('Cf','Zl','Zp','Zs','Cs','Co') for c in value) or '' in value.rpartition('@')[2].split('.'):
        raise FormError('Please enter a valid email address.')
    return value

def scheduled(event):
    try:
        raw = event['startsAt']
        if not isinstance(raw, str): return False
        start = datetime.datetime.fromisoformat(raw.replace('Z','+00:00'))
        return event.get('status')=='scheduled' and start.tzinfo is not None and start>datetime.datetime.now(datetime.timezone.utc)
    except (ValueError, KeyError, TypeError, AttributeError, OverflowError): return False

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(ROOT),**kwargs)
    def translate_path(self,path):
        # Serve the same page with or without a trailing slash, including HEAD.
        if urlsplit(path).path in ('/hike','/hike/'):
            return str(ROOT / 'hike' / 'index.html')
        return super().translate_path(path)
    def log_message(self,fmt,*args):
        # Avoid recording submitted personal details in access logs.
        pass
    def reply(self,code,payload):
        body=json.dumps(payload).encode()
        self.send_response(code); self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if urlsplit(self.path).path!='/api/community': return super().do_GET()
        data=config()
        with connect() as db:
            counts=dict((r['event_id'],r['seats']) for r in db.execute('SELECT event_id,SUM(party_size) seats FROM rsvps GROUP BY event_id'))
        events=[]
        for item in data.get('events',[]):
            # A record that is not an object or has no text id cannot take an RSVP; leave it out.
            if not isinstance(item,dict) or not isinstance(item.get('id'),str): continue
            e=dict(item); capacity=e.get('capacity')
            e['confirmedGuests']=int(counts.get(e['id'],0))
            e['remaining']=max(0,capacity-counts.get(e['id'],0)) if isinstance(capacity,int) and capacity>0 else None
            e['rsvpOpen']=scheduled(e) and bool(e.get('meetingPoint')) and e.get('rsvpEnabled',False)
            events.append(e)
        self.reply(200,{'clubName':data.get('clubName','North Coast Hiking Club'),'emailConnected':False,'acceptsSubmissions':True,'events':events,'routeIdeas':data.get('routeIdeas',[]),**({'showSamples':False} if data.get('showSamples') is False else {})})
    def do_POST(self):
        if self.headers.get('Host') not in [f'localhost:{self.server.server_port}',f'127.0.0.1:{self.server.server_port}']:
            return self.reply(403,{'error':'This is a local sandbox.'})
        origin=self.headers.get('Origin')
        if origin and origin not in [f'http://localhost:{self.server.server_port}',f'http://127.0.0.1:{self.server.server_port}']:
            return self.reply(403,{'error':'Please submit from the local site.'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if length<=0 or length>8192: return self.reply(413,{'error':'Please use the form on the page.'})
            if self.headers.get_content_type()!='application/json': return self.reply(415,{'error':'JSON is required.'})
            data=json.loads(self.rfile.read(length))
            if not isinstance(data,dict): raise FormError('Please use the form on the page.')
            path=urlsplit(self.path).path
            if path=='/api/community/subscriptions':
                address=email_address(data.get('email')); newsletter=data.get('newsletter') is True; hikes=data.get('hikes') is True
                if not (newsletter or hikes): raise FormError('Choose at least one kind of update.')
                stamp=now()
                with connect() as db:
                    db.execute('''INSERT INTO subscriptions VALUES(?,?,?,?,?,?) ON CONFLICT(email) DO UPDATE SET
                      newsletter=MAX(subscriptions.newsletter,excluded.newsletter),hikes=MAX(subscriptions.hikes,excluded.hikes),
                      updated_at=excluded.updated_at''',(address,int(newsletter),int(hikes),stamp,stamp,'local-setup-v1'))
                return self.reply(200,{'saved':True,'emailSent':False,'message':'Saved to the local signup list. Email delivery is not connected yet.'})
            if path=='/api/community/rsvps':
                event=next((x for x in config().get('events',[]) if x.get('id')==data.get('eventId')),None)
                if not event or not scheduled(event) or not event.get('rsvpEnabled') or not event.get('meetingPoint'):
                    return self.reply(409,{'error':'This hike is not accepting RSVPs.'})
                address=email_address(data.get('email')); name=data.get('name')
                if not isinstance(name,str): raise FormError('Please enter your name (up to 120 characters).')
                name=name.strip()
                if not name or len(name)>120: raise FormError('Please enter your name (up to 120 characters).')
                party=data.get('partySize',1)
                if type(party) is not int or not 1<=party<=6: raise FormError('Choose between one and six people.')
                db=connect()
                try:
                    db.execute('BEGIN IMMEDIATE')
                    duplicate=db.execute('SELECT party_size FROM rsvps WHERE event_id=? AND email=?',(event['id'],address)).fetchone()
                    if duplicate:
                        db.rollback(); return self.reply(200,{'saved':True,'alreadyRegistered':True,'emailSent':False,'message':'An RSVP for this email is already on the local list. No additional places were added.'})
                    seats=db.execute('SELECT COALESCE(SUM(party_size),0) FROM rsvps WHERE event_id=?',(event['id'],)).fetchone()[0]
                    cap=event.get('capacity')
                    if isinstance(cap,int) and cap>0 and seats+party>cap:
                        db.rollback();return self.reply(409,{'error':'There aren’t enough places left for that group. Please choose a smaller group.'})
                    db.execute('INSERT INTO rsvps(event_id,email,name,party_size,created_at) VALUES(?,?,?,?,?)',(event['id'],address,name,party,now()));db.commit()
                finally: db.close()
                return self.reply(200,{'saved':True,'emailSent':False,'message':'Your RSVP is saved locally. No confirmation email has been sent.'})
            return self.reply(404,{'error':'Not found.'})
        except FormError as e:
            return self.reply(400,{'error':str(e)})
        except (ValueError,json.JSONDecodeError):
            return self.reply(400,{'error':'Please check your name, email, and form selections.'})
        except sqlite3.Error:
            return self.reply(503,{'error':'We couldn’t save that just now. Please try again.'})

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=3101);args=parser.parse_args()
    connect().close()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    print(f'Local catalog and community forms: http://127.0.0.1:{server.server_port}/',flush=True)
    server.serve_forever()
