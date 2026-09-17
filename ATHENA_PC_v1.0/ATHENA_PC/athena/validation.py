"""User input validation, shared by catalog and accounting operations."""
import re
from datetime import date, datetime

class UserError(Exception):
    pass

def integer(value, label, minimum=0, maximum=1000000000):
    if isinstance(value,str) and re.fullmatch(r'-?\d{1,16}', value):
        value = int(value)
    if type(value) is not int or not minimum <= value <= maximum:
        raise UserError(f'{label}: {minimum:,}~{maximum:,} 사이의 정수를 입력해 주세요.')
    return value

def string(value, label, required=False, maximum=300):
    if not isinstance(value,str):
        raise UserError(f'{label}를 확인해 주세요.')
    value = value.strip()
    if (required and not value) or len(value)>maximum or '\x00' in value:
        raise UserError(f'{label}: '+(f'1~{maximum}자' if required else f'{maximum}자 이내')+'로 입력해 주세요.')
    return value

def day(value):
    try:
        if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):
            raise ValueError()
        result = date.fromisoformat(value)
        if result > date.today() or result.year < 2000:
            raise ValueError()
        return value
    except (ValueError,TypeError):
        raise UserError('날짜는 2000년 이후부터 오늘까지 선택해 주세요.')

def now():
    return datetime.now().astimezone().isoformat(timespec='microseconds')

def method(value):
    if value not in ('transfer','cash','card','other'):
        raise UserError('결제 수단을 선택해 주세요.')
    return value

def existing(conn, table, row_id, active=False):
    # Table names are internal constants, never request values.
    row_id=integer(row_id,'항목 번호',1)
    row=conn.execute(f"""SELECT * FROM {table} x WHERE id=? AND NOT EXISTS (
        SELECT 1 FROM trash_rows d JOIN trash t ON t.id=d.trash_id
        WHERE d.table_name=? AND d.row_id=x.id AND t.restored_at IS NULL)""",(row_id,table)).fetchone()
    if not row or (active and row['archived']):
        raise UserError('항목이 없거나 보관된 항목입니다. 화면을 새로고침해 주세요.')
    return dict(row)

def stock(conn, product_id):
    return conn.execute("""SELECT COALESCE(SUM(qty),0) FROM movements m WHERE product_id=? AND NOT EXISTS (
        SELECT 1 FROM trash_rows d JOIN trash t ON t.id=d.trash_id
        WHERE d.table_name='movements' AND d.row_id=m.id AND t.restored_at IS NULL)""",(product_id,)).fetchone()[0]

def log(conn, action, note):
    conn.execute('INSERT INTO audit(action,note,created_at) VALUES (?,?,?)',(action,note,now()))
