"""Atomic sale, payment, and return operations. All KRW amounts are integers."""
from .db import SALES_QUERY, one, rows, active
from .validation import UserError, integer, string, day, now, method, existing, stock, log

def sale_summary(conn,sale_id):
    result=one(conn,SALES_QUERY+' WHERE s.id=?',(integer(sale_id,'판매 번호',1),))
    if not result:
        raise UserError('거래를 찾을 수 없습니다.')
    return result

def create_sale(conn,data):
    partner=existing(conn,'partners',data.get('partner_id'),True)
    sold_day=day(data.get('day'))
    note=string(data.get('note',''),'메모',maximum=1000)
    lines=data.get('lines')
    if not isinstance(lines,list) or not 1<=len(lines)<=100:
        raise UserError('판매 품목을 1~100개 선택해 주세요.')
    selected=set()
    items=[]
    total=0
    for line in lines:
        if not isinstance(line,dict):
            raise UserError('판매 품목 형식을 확인해 주세요.')
        product=existing(conn,'products',line.get('product_id'),True)
        if product['id'] in selected:
            raise UserError('같은 품목은 한 줄에 수량을 합쳐 주세요.')
        selected.add(product['id'])
        qty=integer(line.get('qty'),'수량',1,1000000)
        price=integer(line.get('price'),'판매 단가')
        current=stock(conn,product['id'])
        if qty>current:
            raise UserError(f"{product['name']}: 재고가 {current:,}{product['unit']} 있습니다. 입고 수량을 확인해 주세요.")
        total+=qty*price
        items.append((product,qty,price))
    integer(total,'판매 합계',1,1000000000000)
    paid=integer(data.get('paid',0),'받은 금액',0,total)
    payment_method=method(data.get('method','transfer'))
    sequence=conn.execute('SELECT COALESCE(MAX(id),0)+1 FROM sales').fetchone()[0]
    number=f"AT-{sold_day.replace('-','')}-{sequence:05d}"
    sale_id=conn.execute('INSERT INTO sales(number,partner_id,partner_name,day,kind,total,note,created_at) VALUES (?,?,?,?,?,?,?,?)',
                         (number,partner['id'],partner['name'],sold_day,'sale',total,note,now())).lastrowid
    for product,qty,price in items:
        conn.execute('INSERT INTO sale_lines(sale_id,product_id,product_name,spec,unit,qty,price) VALUES (?,?,?,?,?,?,?)',
                     (sale_id,product['id'],product['name'],product['spec'],product['unit'],qty,price))
        conn.execute('INSERT INTO movements(product_id,day,kind,qty,sale_id,note,created_at) VALUES (?,?,?,?,?,?,?)',
                     (product['id'],sold_day,'sale',-qty,sale_id,number,now()))
    if paid:
        _payment(conn,sale_id,sold_day,paid,payment_method,'판매 시 입금')
    log(conn,'판매 등록',f"{number} / {partner['name']} / {total:,}원")
    return {'id':sale_id,'number':number}

def _payment(conn,sale_id,payment_day,amount,payment_method,note):
    conn.execute('INSERT INTO payments(sale_id,day,amount,method,note,created_at) VALUES (?,?,?,?,?,?)',
                 (sale_id,payment_day,amount,payment_method,note,now()))

def receive_payment(conn,data):
    partner=existing(conn,'partners',data.get('partner_id'),True)
    payment_day=day(data.get('day'))
    amount=integer(data.get('amount'),'입금액',1,1000000000000)
    payment_method=method(data.get('method'))
    note=string(data.get('note',''),'입금 메모',maximum=300)
    eligible=rows(conn,f'SELECT * FROM ({SALES_QUERY}) WHERE partner_id=? AND balance>0 AND day<=? ORDER BY day,id',
                  (partner['id'],payment_day))
    if data.get('sale_id'):
        target=integer(data['sale_id'],'거래 번호',1)
        eligible=[s for s in eligible if s['id']==target]
    balance=sum(s['balance'] for s in eligible)
    if amount>balance:
        raise UserError(f'선택한 입금일 기준 받을 금액은 {balance:,}원입니다. 초과 입금은 기록할 수 없습니다.')
    remaining=amount
    for sale in eligible:
        allocation=min(remaining,sale['balance'])
        if allocation:
            _payment(conn,sale['id'],payment_day,allocation,payment_method,note)
            remaining-=allocation
    log(conn,'입금 기록',f"{partner['name']} / {amount:,}원 / {note}")
    return {'partner_id':partner['id'],'amount':amount}

def create_return(conn,data):
    sale=sale_summary(conn,data.get('sale_id'))
    if sale['kind']!='sale':
        raise UserError('시작 미수금에는 상품 반품을 기록할 수 없습니다.')
    return_day=day(data.get('day'))
    if return_day<sale['day']:
        raise UserError('반품일은 판매일 이후로 선택해 주세요.')
    # Do not rewrite the chronology of already-recorded receipts/refunds.
    latest=conn.execute(f"SELECT MAX(day) FROM (SELECT day FROM payments p WHERE sale_id=? AND {active('payments','p')} UNION ALL SELECT day FROM returns r WHERE sale_id=? AND {active('returns','r')})",
                        (sale['id'],sale['id'])).fetchone()[0]
    if latest and return_day<latest:
        raise UserError(f'이 거래의 최근 입금·반품일({latest}) 이후 날짜를 선택해 주세요.')
    note=string(data.get('note',''),'반품 사유',True,300)
    lines=data.get('lines')
    if not isinstance(lines,list) or not 1<=len(lines)<=100:
        raise UserError('반품 수량을 입력해 주세요.')
    items=[]
    selected=set()
    total=0
    for line in lines:
        if not isinstance(line,dict):
            raise UserError('반품 품목을 확인해 주세요.')
        item=existing(conn,'sale_lines',line.get('sale_line_id'))
        if item['sale_id']!=sale['id'] or item['id'] in selected:
            raise UserError('반품 품목이 중복되었거나 다른 거래의 품목입니다.')
        selected.add(item['id'])
        returned=conn.execute(f"SELECT COALESCE(SUM(qty),0) FROM return_lines r WHERE sale_line_id=? AND {active('return_lines','r')}",(item['id'],)).fetchone()[0]
        qty=integer(line.get('qty'),'반품 수량',1,item['qty']-returned)
        if stock(conn,item['product_id'])+qty>1000000:
            raise UserError('반품 후 재고가 관리 가능한 최대 수량을 초과합니다.')
        total+=qty*item['price']
        items.append((item,qty))
    refund=max(0,sale['paid']-(sale['net']-total))
    if refund and data.get('refund_confirmed') is not True:
        raise UserError(f'{refund:,}원을 실제로 환불한 뒤 환불 완료에 체크해 주세요.')
    refund_method=method(data.get('method','transfer'))
    return_id=conn.execute('INSERT INTO returns(sale_id,day,total,note,created_at) VALUES (?,?,?,?,?)',
                           (sale['id'],return_day,total,note,now())).lastrowid
    for item,qty in items:
        conn.execute('INSERT INTO return_lines(return_id,sale_line_id,qty) VALUES (?,?,?)',(return_id,item['id'],qty))
        conn.execute('INSERT INTO movements(product_id,day,kind,qty,sale_id,return_id,note,created_at) VALUES (?,?,?,?,?,?,?,?)',
                     (item['product_id'],return_day,'return',qty,sale['id'],return_id,note,now()))
        conn.execute('UPDATE products SET archived=0 WHERE id=?',(item['product_id'],))
    if refund:
        _payment(conn,sale['id'],return_day,-refund,refund_method,f'반품 환불: {note}')
    log(conn,'반품 기록',f"{sale['number']} / 반품 {total:,}원 / 환불 {refund:,}원")
    return {'id':return_id,'refund':refund}

def reverse_payment(conn,data):
    """Correct an erroneous receipt without deleting its history."""
    payment=existing(conn,'payments',data.get('id'))
    if payment['amount']<=0:
        raise UserError('입금 기록만 정정할 수 있습니다.')
    marker=f"[입금정정 #{payment['id']}]"
    if conn.execute(f"SELECT 1 FROM payments p WHERE note LIKE ? AND {active('payments','p')}",(marker+'%',)).fetchone():
        raise UserError('이미 정정한 입금입니다.')
    sale=sale_summary(conn,payment['sale_id'])
    if sale['paid']<payment['amount']:
        raise UserError('반품·환불이 연결된 입금입니다. 남은 입금액보다 큰 정정은 할 수 없습니다.')
    corrected_day=day(data.get('day'))
    latest=conn.execute(f"SELECT MAX(day) FROM (SELECT day FROM payments p WHERE sale_id=? AND {active('payments','p')} UNION ALL SELECT day FROM returns r WHERE sale_id=? AND {active('returns','r')})",
                        (sale['id'],sale['id'])).fetchone()[0]
    if corrected_day<(latest or payment['day']):
        raise UserError('최근 입금·반품 이후 날짜로 정정해 주세요.')
    note=string(data.get('note',''),'정정 사유',True,200)
    _payment(conn,sale['id'],corrected_day,-payment['amount'],payment['method'],f'{marker} {note}')
    log(conn,'입금 정정',f"{sale['number']} / {payment['amount']:,}원 / {note}")
    return {'id':payment['id']}
