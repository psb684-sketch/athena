"""Loopback-only HTTP interface with per-launch sessions, CSRF checks and serialized writes."""
import hmac
import json
import logging
import secrets
import sqlite3
import threading
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from . import VERSION, db, catalog, ledger, reports, backup, trash, editing
from .validation import UserError, integer, string

MAX_BODY=50*1024*1024
ACTIONS={'products':catalog.save_product,'partners':catalog.save_partner,'stock':catalog.stock_change,
         'sales':ledger.create_sale,'payments':ledger.receive_payment,'returns':ledger.create_return,
         'payment-correction':ledger.reverse_payment,'archive':catalog.archive,'settings':catalog.settings,
         'delete':trash.delete_record,'trash-restore':trash.restore_record,'trash-purge':trash.purge_record,
         'sale-edit':editing.edit_sale,'payment-edit':editing.edit_payment,
         'return-edit':editing.edit_return,'movement-edit':editing.edit_movement}
STATIC={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),
        '/forms.js':('forms.js','text/javascript; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8'),
        '/shared.js':('shared.js','text/javascript; charset=utf-8'),'/statement.html':('statement.html','text/html; charset=utf-8'),
        '/statement.js':('statement.js','text/javascript; charset=utf-8'),'/favicon.svg':('favicon.svg','image/svg+xml')}

class Application:
    def __init__(self,path,ui_dir,demo=False):
        self.path=Path(path)
        self.ui_dir=Path(ui_dir)
        self.demo=demo
        self.token=secrets.token_urlsafe(32)
        self.csrf=secrets.token_urlsafe(32)
        self.lock=threading.RLock()
        self.backup_warning=''
        # Preserve the exact v1 file before adding the reversible-trash schema.
        if self.path.exists() and self.path.stat().st_size:
            check=None;needs_migration_backup=False
            try:
                check=sqlite3.connect(str(self.path))
                meta=dict(check.execute('SELECT key,value FROM meta'))
                needs_migration_backup=meta.get('app')=='ATHENA_PC' and meta.get('schema') in ('1','2')
            except sqlite3.Error:
                pass
            finally:
                if check:check.close()
            if needs_migration_backup:
                backup.snapshot(self.path,self.path.parent/'backups'/'before-schema-v3.db')
        db.initialize(path)
        self.auto_backup()

    def auto_backup(self):
        try:
            backup.automatic(self.path)
            self.backup_warning=''
        except (OSError,sqlite3.Error):
            self.backup_warning='자동 백업을 저장하지 못했습니다. 저장 공간을 확인하고 백업을 내려받아 주세요.'
            logging.exception('Automatic backup failed')

    def write(self,action,data):
        if not isinstance(data,dict):
            raise UserError('입력 형식을 확인해 주세요.')
        key=string(data.get('request_key',''),'저장 요청',True,100)
        with self.lock:
            with db.transaction(self.path) as conn:
                old=conn.execute('SELECT result FROM requests WHERE key=?',(key,)).fetchone()
                if old:
                    return json.loads(old[0])
                revision=int(conn.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0])
                if integer(data.get('revision'),'화면 버전',0,1000000000000)!=revision:
                    raise UserError('다른 화면에서 자료가 변경되었습니다. 이 창을 닫고 새로고침한 뒤 다시 입력해 주세요.')
                result=ACTIONS[action](conn,data)
                conn.execute("UPDATE meta SET value=? WHERE key='revision'",(str(revision+1),))
                conn.execute('INSERT INTO requests VALUES (?,?)',(key,json.dumps(result,ensure_ascii=False)))
            self.auto_backup()
            return result

class Server(ThreadingHTTPServer):
    daemon_threads=True
    allow_reuse_address=False
    def __init__(self,app,port):
        self.app=app
        super().__init__(('127.0.0.1',port),Handler)
        self.origin=f'http://127.0.0.1:{self.server_port}'
        self.cookie_name=f'athena_{self.server_port}'

class Handler(BaseHTTPRequestHandler):
    server_version='ATHENA-PC'
    sys_version=''
    def setup(self):
        super().setup()
        self.connection.settimeout(30)

    def log_message(self,*args):
        # Never log launch URLs or their session tokens.
        pass

    def send(self,status,content=b'',mime='application/json; charset=utf-8',headers=None):
        if not isinstance(content,bytes):
            content=json.dumps(content,ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type',mime)
        self.send_header('Content-Length',str(len(content)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        for key,value in (headers or {}).items():
            self.send_header(key,value)
        self.end_headers()
        try:
            self.wfile.write(content)
        except (BrokenPipeError,ConnectionResetError):
            pass

    def guard(self,write=False):
        if self.headers.get('Host')!=f'127.0.0.1:{self.server.server_port}':
            self.send(403,{'error':'이 PC의 실행 주소에서만 접근할 수 있습니다.'})
            return False
        if self.headers.get('Sec-Fetch-Site')=='cross-site':
            self.send(403,{'error':'외부 사이트의 접근을 차단했습니다.'})
            return False
        cookies=SimpleCookie()
        try:
            cookies.load(self.headers.get('Cookie',''))
            value=cookies[self.server.cookie_name].value if self.server.cookie_name in cookies else ''
        except Exception:
            value=''
        if not hmac.compare_digest(value,self.server.app.token):
            self.send(401,{'error':'아테나 실행 파일을 다시 눌러 화면을 열어 주세요.'})
            return False
        if write and (self.headers.get('Origin')!=self.server.origin or not hmac.compare_digest(self.headers.get('X-Athena-CSRF',''),self.server.app.csrf)):
            self.send(403,{'error':'실행 창을 다시 열어 주세요. 저장 요청의 확인 정보가 만료되었습니다.'})
            return False
        return True

    def do_GET(self):
        parsed=urlsplit(self.path)
        path=parsed.path
        params={k:v[-1] for k,v in parse_qs(parsed.query).items()}
        if path=='/launch':
            if self.headers.get('Host')==f'127.0.0.1:{self.server.server_port}' and hmac.compare_digest(params.get('token',''),self.server.app.token):
                self.send(303,b'',headers={'Location':'/','Set-Cookie':f'{self.server.cookie_name}={self.server.app.token}; HttpOnly; SameSite=Strict; Path=/'})
            else:
                self.send(403,{'error':'아테나 실행 파일을 눌러 주세요.'})
            return
        if not self.guard(): return
        app=self.server.app
        try:
            if path in STATIC:
                file,mime=STATIC[path]
                self.send(200,(app.ui_dir/file).read_bytes(),mime)
                return
            with app.lock:
                conn=db.connect(app.path)
                try:
                    if path=='/api/state':
                        data=reports.state(conn)
                        snapshots=sorted((app.path.parent/'backups').glob('*.db'),key=lambda f:f.stat().st_mtime,reverse=True)
                        data.update({'csrf':app.csrf,'demo':app.demo,'version':VERSION,'backup_warning':app.backup_warning,
                            'data_directory':str(app.path.parent),'backup_latest':snapshots[0].name if snapshots else '',
                            'backups':[p.name for p in snapshots],'trash':trash.list_trash(conn)})
                    elif path=='/api/sales': data=reports.sales_list(conn,params)
                    elif path.startswith('/api/sale/'): data=reports.sale_detail(conn,path.rsplit('/',1)[-1])
                    elif path.startswith('/api/return/'): data=reports.return_detail(conn,path.rsplit('/',1)[-1])
                    elif path.startswith('/api/movement/'): data=reports.movement_detail(conn,path.rsplit('/',1)[-1])
                    elif path.startswith('/api/partner/'): data=reports.partner_detail(conn,path.rsplit('/',1)[-1])
                    elif path=='/api/movements': data=reports.movements(conn,params)
                    elif path.startswith('/api/export/'):
                        kind=path.rsplit('/',1)[-1]
                        content=reports.csv_bytes(conn,kind,params)
                        self.send(200,content,'text/csv; charset=utf-8',{'Content-Disposition':f'attachment; filename="athena-{kind}.csv"'})
                        return
                    elif path=='/api/backup':
                        target=backup.snapshot(app.path,app.path.parent/'backups'/'athena-manual.db')
                        self.send(200,target.read_bytes(),'application/vnd.sqlite3',{'Content-Disposition':'attachment; filename="ATHENA-backup.db"'})
                        return
                    elif path=='/api/backup-file':
                        name=params.get('name','')
                        choices={p.name:p for p in (app.path.parent/'backups').glob('*.db')}
                        if name not in choices: raise UserError('백업 파일을 찾을 수 없습니다.')
                        self.send(200,choices[name].read_bytes(),'application/vnd.sqlite3',{'Content-Disposition':f'attachment; filename="{name}"'})
                        return
                    else:
                        self.send(404,{'error':'요청한 화면을 찾을 수 없습니다.'}); return
                finally:
                    conn.close()
            self.send(200,data)
        except UserError as exc:
            self.send(400,{'error':str(exc)})
        except Exception:
            logging.exception('Read failed')
            self.send(500,{'error':'자료를 읽지 못했습니다. 실행 창의 오류 기록을 확인해 주세요.'})

    def do_POST(self):
        if not self.guard(True): return
        app=self.server.app
        try:
            length=int(self.headers.get('Content-Length','0'))
            if length<=0 or length>MAX_BODY:
                raise UserError('파일은 50MB 이하로 선택해 주세요.')
            path=urlsplit(self.path).path
            if path!='/api/restore' and length>1024*1024:
                raise UserError('입력 내용이 너무 큽니다.')
            body=self.rfile.read(length)
            if len(body)!=length: raise UserError('자료 전송이 완료되지 않았습니다.')
            if path=='/api/restore':
                if self.headers.get('X-Athena-Restore')!='RESTORE': raise UserError('복원 확인이 필요합니다.')
                with app.lock:
                    conn=db.connect(app.path)
                    revision=conn.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0]
                    conn.close()
                    if self.headers.get('X-Athena-Revision')!=revision:
                        raise UserError('자료가 변경되었습니다. 새로고침 후 다시 복원해 주세요.')
                    result=backup.restore(app.path,body)
                    app.auto_backup()
            else:
                action=path.removeprefix('/api/')
                if action not in ACTIONS or not path.startswith('/api/'):
                    self.send(404,{'error':'없는 저장 요청입니다.'}); return
                if self.headers.get('Content-Type','').split(';')[0]!='application/json':
                    raise UserError('지원하지 않는 입력 형식입니다.')
                result=app.write(action,json.loads(body))
            self.send(200,result)
        except (UserError,ValueError,UnicodeError) as exc:
            self.send(400,{'error':str(exc) if isinstance(exc,UserError) else '입력 형식을 확인해 주세요.'})
        except sqlite3.IntegrityError:
            logging.exception('Data integrity error')
            self.send(400,{'error':'연결된 기록을 확인해 주세요. 이번 저장은 취소되었습니다.'})
        except Exception:
            logging.exception('Write failed')
            self.send(500,{'error':'처리 결과를 확인하지 못했습니다. 새로고침해 기록을 확인한 뒤 다시 시도해 주세요.'})
