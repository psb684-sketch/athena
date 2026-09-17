"""Online backups and validated restoration into a freshly created schema."""
import os
import sqlite3
import tempfile
from datetime import date, datetime
from pathlib import Path
from . import db
from .validation import UserError, log

def snapshot(source_path,target):
    target=Path(target)
    target.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix='athena-backup-',suffix='.tmp',dir=target.parent)
    os.close(fd)
    source=dest=None
    try:
        source=db.connect(source_path)
        dest=sqlite3.connect(temp)
        source.backup(dest)
        dest.close(); dest=None
        source.close(); source=None
        os.replace(temp,target)
        return target
    finally:
        if source: source.close()
        if dest: dest.close()
        Path(temp).unlink(missing_ok=True)

def automatic(path):
    directory=Path(path).parent/'backups'
    target=snapshot(path,directory/f'athena-auto-{date.today().isoformat()}.db')
    for old in sorted(directory.glob('athena-auto-*.db'))[:-30]:
        old.unlink()
    return target

def verify(conn):
    if conn.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or conn.execute('PRAGMA foreign_key_check').fetchone():
        raise UserError('백업 파일의 데이터 연결에 오류가 있습니다.')
    if conn.execute('SELECT product_id FROM movements GROUP BY product_id HAVING SUM(qty)<0 OR SUM(qty)>1000000').fetchone():
        raise UserError('백업의 재고 수량이 올바르지 않습니다.')
    if conn.execute("SELECT 1 FROM sales s WHERE kind='sale' AND total!=COALESCE((SELECT SUM(qty*price) FROM sale_lines WHERE sale_id=s.id),0)").fetchone():
        raise UserError('백업의 판매 합계가 일치하지 않습니다.')
    if conn.execute('SELECT 1 FROM return_lines r JOIN sale_lines s ON s.id=r.sale_line_id GROUP BY s.id HAVING SUM(r.qty)>s.qty').fetchone():
        raise UserError('백업의 반품 수량이 판매 수량을 초과합니다.')
    if conn.execute('SELECT 1 FROM return_lines l JOIN returns r ON r.id=l.return_id JOIN sale_lines s ON s.id=l.sale_line_id WHERE r.sale_id!=s.sale_id').fetchone():
        raise UserError('백업의 반품 연결이 일치하지 않습니다.')
    if conn.execute('SELECT 1 FROM returns r WHERE total!=COALESCE((SELECT SUM(l.qty*s.price) FROM return_lines l JOIN sale_lines s ON s.id=l.sale_line_id WHERE l.return_id=r.id),-1)').fetchone():
        raise UserError('백업의 반품 금액이 일치하지 않습니다.')
    if conn.execute(f'SELECT 1 FROM ({db.SALES_QUERY}) WHERE paid<0 OR balance<0 OR net<0').fetchone():
        raise UserError('백업의 입금·미수금 합계가 올바르지 않습니다.')
    # Verify ledger effects, not only the displayed totals.
    if conn.execute("""SELECT 1 FROM sale_lines l WHERE l.qty != -COALESCE((SELECT SUM(m.qty) FROM movements m
        WHERE m.kind='sale' AND m.sale_id=l.sale_id AND m.product_id=l.product_id),0)""").fetchone():
        raise UserError('백업의 판매와 출고 수량이 일치하지 않습니다.')
    if conn.execute("""SELECT 1 FROM return_lines l JOIN sale_lines s ON s.id=l.sale_line_id WHERE l.qty !=
        COALESCE((SELECT SUM(m.qty) FROM movements m WHERE m.kind='return' AND m.return_id=l.return_id AND m.product_id=s.product_id),0)""").fetchone():
        raise UserError('백업의 반품과 입고 수량이 일치하지 않습니다.')

def restore(path,payload):
    if not payload.startswith(b'SQLite format 3\x00'):
        raise UserError('아테나에서 내려받은 .db 백업 파일을 선택해 주세요.')
    with tempfile.TemporaryDirectory(prefix='athena-restore-',dir=Path(path).parent) as directory:
        uploaded=Path(directory)/'uploaded.db'
        fresh=Path(directory)/'checked.db'
        uploaded.write_bytes(payload)
        # Older ATHENA 1.0 backups are upgraded in the disposable copy only.
        db.initialize(uploaded)
        db.initialize(fresh)
        source=sqlite3.connect(uploaded.as_uri()+'?mode=ro',uri=True)
        source.execute('PRAGMA trusted_schema=OFF')
        dest=db.connect(fresh)
        try:
            def schema(conn):
                return {tuple(row) for row in conn.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")}
            if schema(source)!=schema(dest):
                raise UserError('이 버전의 아테나 백업이 아닙니다. 현재 데이터는 유지됩니다.')
            meta=dict(source.execute('SELECT key,value FROM meta'))
            if meta.get('app')!='ATHENA_PC' or meta.get('schema')!=db.SCHEMA_VERSION:
                raise UserError('지원하지 않는 백업 버전입니다.')
            dest.execute('BEGIN IMMEDIATE')
            dest.execute('DELETE FROM meta')
            for table in db.TABLES:
                if table=='requests':
                    continue
                cursor=source.execute(f'SELECT * FROM {table}')
                count=0
                while True:
                    batch=cursor.fetchmany(1000)
                    if not batch: break
                    count+=len(batch)
                    if count>1000000:
                        raise UserError('복원 가능한 기록 수를 초과했습니다.')
                    dest.executemany(f'INSERT INTO {table} VALUES ({",".join(["?"]*len(batch[0]))})',batch)
            verify(dest)
            dest.commit()
        except (sqlite3.DatabaseError,ValueError,TypeError) as exc:
            dest.rollback()
            raise UserError('백업 파일을 검증하지 못했습니다. 현재 데이터는 유지됩니다.') from exc
        finally:
            source.close()
            dest.close()
        current=db.connect(path)
        revision=int(current.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0])
        current.close()
        preserved=snapshot(path,Path(path).parent/'backups'/f'before-restore-{datetime.now().strftime("%Y%m%d-%H%M%S-%f")}.db')
        with db.transaction(fresh) as conn:
            conn.execute("UPDATE meta SET value=? WHERE key='revision'",(str(revision+1),))
            log(conn,'백업 복원','백업을 복원했습니다. 복원 전 자료를 별도 보존했습니다.')
        # SQLite's backup API commits the replacement atomically; no open DB is renamed.
        source=db.connect(fresh)
        dest=db.connect(path)
        try:
            source.backup(dest)
        finally:
            source.close(); dest.close()
        automatic(path)
        return {'restored':True,'preserved':preserved.name}
