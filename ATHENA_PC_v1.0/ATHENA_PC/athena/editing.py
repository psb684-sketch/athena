"""Audited corrections for saved sales, payments, returns and stock movements."""
import json
from .db import SALES_QUERY, active, one, rows
from .validation import UserError, integer, string, day, now, method, existing, stock, log
from .trash import validate_state

def _snapshot(conn,table,row_id):
    return dict(conn.execute(f'SELECT * FROM {table} WHERE id=?',(row_id,)).fetchone())

def _history(conn,entity,row_id,label,before,after):
    conn.execute('INSERT INTO edit_history(entity,entity_id,label,before_json,after_json,edited_at) VALUES (?,?,?,?,?,?)',
        (entity,row_id,label,json.dumps(before,ensure_ascii=False),json.dumps(after,ensure_ascii=False),now()))
    log(conn,f'{label} 수정',f'#{row_id} / 수정 전후 이력 보존')

def _active_rows(conn,table,where,args=()):
    return rows(conn,f"SELECT * FROM {table} x WHERE {where} AND {active(table,'x')}",args)

def edit_sale(conn,data):
    sale=existing(conn,'sales',data.get('id'))
    before={'sale':sale,'lines':_active_rows(conn,'sale_lines','sale_id=?',(sale['id'],)),
            'movements':_active_rows(conn,'movements','sale_id=?',(sale['id'],))}
    sold_day=day(data.get('day'))
    partner=existing(conn,'partners',data.get('partner_id',sale['partner_id']),True)
    note=string(data.get('note',''),'메모',maximum=1000)
    earliest=conn.execute(f"""SELECT MIN(day) FROM (
        SELECT day FROM payments p WHERE sale_id=? AND {active('payments','p')}
        UNION ALL SELECT day FROM returns r WHERE sale_id=? AND {active('returns','r')})""",(sale['id'],sale['id'])).fetchone()[0]
    if earliest and sold_day>earliest:
        raise UserError(f'판매일은 연결된 입금·반품일({earliest})보다 늦게 바꿀 수 없습니다.')
    summary=one(conn,SALES_QUERY+' WHERE s.id=?',(sale['id'],))
    if sale['kind']=='opening':
        total=integer(data.get('total'),'시작 미수금',1,1000000000000)
        if total<summary['paid']:
            raise UserError(f'이미 입금된 {summary["paid"]:,}원보다 시작 미수금을 작게 바꿀 수 없습니다.')
        conn.execute('UPDATE sales SET partner_id=?,partner_name=?,day=?,total=?,note=? WHERE id=?',
                     (partner['id'],partner['name'],sold_day,total,note,sale['id']))
    else:
        if conn.execute(f"SELECT 1 FROM returns r WHERE sale_id=? AND {active('returns','r')} LIMIT 1",(sale['id'],)).fetchone():
            raise UserError('반품이 연결된 판매입니다. 반품을 먼저 휴지통으로 옮긴 뒤 판매를 수정해 주세요.')
        lines=data.get('lines')
        if not isinstance(lines,list) or not 1<=len(lines)<=100:
            raise UserError('판매 품목을 1~100개 선택해 주세요.')
        selected=set();items=[];total=0
        old_out={r['product_id']:-r['qty'] for r in before['movements'] if r['kind']=='sale'}
        for line in lines:
            if not isinstance(line,dict):raise UserError('판매 품목 형식을 확인해 주세요.')
            product=existing(conn,'products',line.get('product_id'),True)
            if product['id'] in selected:raise UserError('같은 품목은 한 줄에 수량을 합쳐 주세요.')
            selected.add(product['id'])
            qty=integer(line.get('qty'),'수량',1,1000000);price=integer(line.get('price'),'판매 단가')
            available=stock(conn,product['id'])+old_out.get(product['id'],0)
            if qty>available:raise UserError(f"{product['name']}: 기존 판매를 되돌리면 재고가 {available:,}{product['unit']} 있습니다.")
            total+=qty*price;items.append((product,qty,price))
        integer(total,'판매 합계',1,1000000000000)
        if total<summary['paid']:
            raise UserError(f'이미 입금된 {summary["paid"]:,}원보다 판매 합계를 작게 바꿀 수 없습니다. 입금을 먼저 수정해 주세요.')
        conn.execute('DELETE FROM movements WHERE sale_id=? AND kind="sale"',(sale['id'],))
        conn.execute('DELETE FROM sale_lines WHERE sale_id=?',(sale['id'],))
        conn.execute('UPDATE sales SET partner_id=?,partner_name=?,day=?,total=?,note=? WHERE id=?',
                     (partner['id'],partner['name'],sold_day,total,note,sale['id']))
        for product,qty,price in items:
            conn.execute('INSERT INTO sale_lines(sale_id,product_id,product_name,spec,unit,qty,price) VALUES (?,?,?,?,?,?,?)',
                         (sale['id'],product['id'],product['name'],product['spec'],product['unit'],qty,price))
            conn.execute('INSERT INTO movements(product_id,day,kind,qty,sale_id,note,created_at) VALUES (?,?,?,?,?,?,?)',
                         (product['id'],sold_day,'sale',-qty,sale['id'],sale['number'],now()))
    validate_state(conn)
    after={'sale':_snapshot(conn,'sales',sale['id']),'lines':_active_rows(conn,'sale_lines','sale_id=?',(sale['id'],)),
           'movements':_active_rows(conn,'movements','sale_id=?',(sale['id'],))}
    _history(conn,'sale',sale['id'],'판매',before,after)
    return {'id':sale['id']}

def edit_payment(conn,data):
    payment=existing(conn,'payments',data.get('id'))
    if payment['amount']<=0:raise UserError('양수 입금 기록만 직접 수정할 수 있습니다.')
    marker=f"[입금정정 #{payment['id']}]"
    if conn.execute(f"SELECT 1 FROM payments p WHERE note LIKE ? AND {active('payments','p')}",(marker+'%',)).fetchone():
        raise UserError('이미 정정된 입금입니다. 정정 기록을 삭제한 뒤 수정해 주세요.')
    sale=one(conn,SALES_QUERY+' WHERE s.id=?',(payment['sale_id'],))
    payment_day=day(data.get('day'))
    if payment_day<sale['day']:raise UserError('입금일은 판매일보다 빠를 수 없습니다.')
    amount=integer(data.get('amount'),'입금액',1,1000000000000)
    before=payment
    conn.execute('UPDATE payments SET day=?,amount=?,method=?,note=? WHERE id=?',
                 (payment_day,amount,method(data.get('method')),string(data.get('note',''),'입금 메모',maximum=300),payment['id']))
    validate_state(conn)
    after=_snapshot(conn,'payments',payment['id'])
    _history(conn,'payment',payment['id'],'입금',before,after)
    return {'id':payment['id']}

def _refund_for_return(conn,returned):
    return one(conn,f"""SELECT * FROM payments p WHERE sale_id=? AND day=? AND amount<0
        AND created_at>=? AND note LIKE '반품 환불:%' AND {active('payments','p')}
        ORDER BY created_at,id LIMIT 1""",(returned['sale_id'],returned['day'],returned['created_at']))

def edit_return(conn,data):
    returned=existing(conn,'returns',data.get('id'))
    sale=one(conn,SALES_QUERY+' WHERE s.id=?',(returned['sale_id'],))
    return_day=day(data.get('day'))
    if return_day<sale['day']:raise UserError('반품일은 판매일 이후로 선택해 주세요.')
    note=string(data.get('note',''),'반품 사유',True,300)
    supplied=data.get('lines')
    if not isinstance(supplied,list) or not 1<=len(supplied)<=100:raise UserError('반품 수량을 입력해 주세요.')
    before_lines=_active_rows(conn,'return_lines','return_id=?',(returned['id'],))
    before_moves=_active_rows(conn,'movements','return_id=?',(returned['id'],))
    old_refund=_refund_for_return(conn,returned)
    before={'return':returned,'lines':before_lines,'movements':before_moves,'refund':old_refund}
    items=[];selected=set();total=0
    for line in supplied:
        item=existing(conn,'sale_lines',line.get('sale_line_id'))
        if item['sale_id']!=sale['id'] or item['id'] in selected:raise UserError('반품 품목이 중복되었거나 다른 거래의 품목입니다.')
        selected.add(item['id'])
        other=conn.execute(f"""SELECT COALESCE(SUM(l.qty),0) FROM return_lines l JOIN returns r ON r.id=l.return_id
            WHERE l.sale_line_id=? AND l.return_id!=? AND {active('return_lines','l')} AND {active('returns','r')}""",
            (item['id'],returned['id'])).fetchone()[0]
        qty=integer(line.get('qty'),'반품 수량',1,item['qty']-other)
        total+=qty*item['price'];items.append((item,qty))
    paid_without_old_refund=sale['paid']-(old_refund['amount'] if old_refund else 0)
    new_net=sale['net']+returned['total']-total
    refund=max(0,paid_without_old_refund-new_net)
    if refund and data.get('refund_confirmed') is not True:
        raise UserError(f'수정 후 환불액은 {refund:,}원입니다. 실제 환불 금액을 확인해 주세요.')
    conn.execute('DELETE FROM movements WHERE return_id=?',(returned['id'],))
    conn.execute('DELETE FROM return_lines WHERE return_id=?',(returned['id'],))
    conn.execute('UPDATE returns SET day=?,total=?,note=? WHERE id=?',(return_day,total,note,returned['id']))
    for item,qty in items:
        conn.execute('INSERT INTO return_lines(return_id,sale_line_id,qty) VALUES (?,?,?)',(returned['id'],item['id'],qty))
        conn.execute('INSERT INTO movements(product_id,day,kind,qty,sale_id,return_id,note,created_at) VALUES (?,?,?,?,?,?,?,?)',
                     (item['product_id'],return_day,'return',qty,sale['id'],returned['id'],note,now()))
    refund_method=method(data.get('method','transfer'))
    if old_refund and refund:
        conn.execute('UPDATE payments SET day=?,amount=?,method=?,note=? WHERE id=?',
                     (return_day,-refund,refund_method,f'반품 환불: {note}',old_refund['id']))
    elif old_refund:
        conn.execute('DELETE FROM payments WHERE id=?',(old_refund['id'],))
    elif refund:
        conn.execute('INSERT INTO payments(sale_id,day,amount,method,note,created_at) VALUES (?,?,?,?,?,?)',
                     (sale['id'],return_day,-refund,refund_method,f'반품 환불: {note}',now()))
    validate_state(conn)
    after={'return':_snapshot(conn,'returns',returned['id']),'lines':_active_rows(conn,'return_lines','return_id=?',(returned['id'],)),
           'movements':_active_rows(conn,'movements','return_id=?',(returned['id'],)),'refund':_refund_for_return(conn,_snapshot(conn,'returns',returned['id']))}
    _history(conn,'return',returned['id'],'반품',before,after)
    return {'id':returned['id'],'refund':refund}

def edit_movement(conn,data):
    movement=existing(conn,'movements',data.get('id'))
    if movement['kind'] not in ('opening','receive','adjust'):
        raise UserError('판매·반품 입출고는 해당 거래에서 수정해 주세요.')
    qty=integer(data.get('qty'),'수량 증감',-1000000,1000000)
    if qty==0:raise UserError('수량 증감은 0으로 수정할 수 없습니다.')
    if movement['kind'] in ('opening','receive') and qty<1:raise UserError('시작 재고와 입고 수량은 1개 이상이어야 합니다.')
    note=string(data.get('note',''),'메모 / 조정 사유',movement['kind']=='adjust',300)
    before=movement
    conn.execute('UPDATE movements SET day=?,qty=?,note=? WHERE id=?',(day(data.get('day')),qty,note,movement['id']))
    validate_state(conn)
    after=_snapshot(conn,'movements',movement['id'])
    _history(conn,'movement',movement['id'],'입출고',before,after)
    return {'id':movement['id']}
