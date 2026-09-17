"""Products, stock receipts/corrections, and customers."""
import sqlite3
from datetime import date
from .db import SALES_QUERY, one
from .validation import UserError, integer, string, day, now, existing, stock, log

def save_product(conn, data):
    product_id=data.get('id')
    if product_id:
        old=existing(conn,'products',product_id)
        product_id=old['id']
    name=string(data.get('name'),'품목명',True,120)
    sku=string(data.get('sku',''),'품목 코드',False,40)
    if not sku:
        if product_id:
            sku=old['sku']
        else:
            sequence=conn.execute('SELECT COALESCE(MAX(id),0)+1 FROM products').fetchone()[0]
            sku=f'P-{sequence:04d}'
            while conn.execute('SELECT 1 FROM products WHERE sku=? COLLATE NOCASE',(sku,)).fetchone():
                sequence+=1
                sku=f'P-{sequence:04d}'
    values=(sku,name,string(data.get('spec',''),'규격',maximum=100),string(data.get('unit','개'),'단위',True,12),
            integer(data.get('price',0),'기본 단가'),integer(data.get('minimum',0),'부족 알림 수량',0,1000000))
    try:
        if product_id:
            conn.execute('UPDATE products SET sku=?,name=?,spec=?,unit=?,price=?,minimum=? WHERE id=?',(*values,product_id))
        else:
            product_id=conn.execute('INSERT INTO products(sku,name,spec,unit,price,minimum,created_at) VALUES (?,?,?,?,?,?,?)',(*values,now())).lastrowid
            opening=integer(data.get('opening_stock',0),'시작 재고',0,1000000)
            if opening:
                conn.execute('INSERT INTO movements(product_id,day,kind,qty,note,created_at) VALUES (?,?,?,?,?,?)',
                             (product_id,date.today().isoformat(),'opening',opening,'품목 등록 시 시작 재고',now()))
    except sqlite3.IntegrityError as exc:
        raise UserError('이미 사용 중인 품목 코드입니다. 다른 코드를 입력해 주세요.') from exc
    log(conn,'품목 수정' if data.get('id') else '품목 등록',name)
    return {'id':product_id}

def stock_change(conn,data):
    product=existing(conn,'products',data.get('product_id'),True)
    kind=data.get('kind')
    if kind not in ('receive','adjust'):
        raise UserError('입고 또는 재고 조정을 선택해 주세요.')
    current=stock(conn,product['id'])
    note=string(data.get('note',''),'메모 / 조정 사유',kind=='adjust',300)
    if kind=='receive':
        qty=integer(data.get('qty'),'입고 수량',1,1000000)
    else:
        counted=integer(data.get('counted'),'실제 재고',0,1000000)
        qty=counted-current
        if qty==0:
            raise UserError('기존 재고와 같습니다. 변경할 수량이 없습니다.')
        note=f'실사 {current:,} → {counted:,} / {note}'
    if not 0 <= current+qty <= 1000000:
        raise UserError('품목당 재고는 0~1,000,000 범위로 관리할 수 있습니다.')
    movement_day=day(data.get('day'))
    movement_id=conn.execute('INSERT INTO movements(product_id,day,kind,qty,note,created_at) VALUES (?,?,?,?,?,?)',
                            (product['id'],movement_day,kind,qty,note or '입고',now())).lastrowid
    log(conn,'입고' if kind=='receive' else '재고 조정',f"{product['name']} {qty:+,}{product['unit']} / {note}")
    return {'id':movement_id}

def save_partner(conn,data):
    partner_id=data.get('id')
    if partner_id:
        partner_id=existing(conn,'partners',partner_id)['id']
    values=(string(data.get('name'),'거래처명',True,120),string(data.get('contact',''),'담당자',maximum=60),
            string(data.get('phone',''),'연락처',maximum=40),string(data.get('address',''),'주소',maximum=200),
            string(data.get('note',''),'메모',maximum=1000))
    if partner_id:
        conn.execute('UPDATE partners SET name=?,contact=?,phone=?,address=?,note=? WHERE id=?',(*values,partner_id))
    else:
        partner_id=conn.execute('INSERT INTO partners(name,contact,phone,address,note,created_at) VALUES (?,?,?,?,?,?)',(*values,now())).lastrowid
        opening=integer(data.get('opening_balance',0),'시작 미수금',0,1000000000000)
        if opening:
            opening_day=day(data.get('opening_day',date.today().isoformat()))
            conn.execute('INSERT INTO sales(number,partner_id,partner_name,day,kind,total,note,created_at) VALUES (?,?,?,?,?,?,?,?)',
                         (f'OPEN-{partner_id:04d}',partner_id,values[0],opening_day,'opening',opening,'아테나 도입 전 미수금',now()))
    log(conn,'거래처 수정' if data.get('id') else '거래처 등록',values[0])
    return {'id':partner_id}

def archive(conn,data):
    table=data.get('table')
    if table not in ('products','partners'):
        raise UserError('보관할 항목을 확인해 주세요.')
    item=existing(conn,table,data.get('id'))
    archived=integer(data.get('archived'),'보관 여부',0,1)
    if archived:
        if table=='products' and stock(conn,item['id']):
            raise UserError('재고가 남아 있습니다. 재고를 정리한 뒤 보관해 주세요.')
        if table=='partners':
            balance=conn.execute(f'SELECT COALESCE(SUM(balance),0) FROM ({SALES_QUERY}) WHERE partner_id=?',(item['id'],)).fetchone()[0]
            if balance:
                raise UserError('미수금이 남아 있습니다. 입금을 기록한 뒤 보관해 주세요.')
    conn.execute(f'UPDATE {table} SET archived=? WHERE id=?',(archived,item['id']))
    log(conn,'항목 보관' if archived else '보관 해제',item['name'])
    return {'id':item['id']}

def settings(conn,data):
    for key,label,limit in [('business','사업장명',120),('owner','대표 / 담당자',60),('phone','전화',40),('address','주소',200)]:
        value=string(data.get(key,''),label,key=='business',limit)
        conn.execute('UPDATE meta SET value=? WHERE key=?',(value,key))
    log(conn,'사업장 설정','사업장 정보 변경')
    return {'saved':True}
