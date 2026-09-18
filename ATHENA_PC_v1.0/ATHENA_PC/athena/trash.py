"""Reversible deletion and trash management for ledger records."""
import json
from .db import SALES_QUERY, active, one, rows
from .validation import UserError, integer, now, log

ENTITY_LABELS={
    'product':'품목','partner':'거래처','sale':'판매','payment':'입금',
    'return':'반품','movement':'입출고 기록','order':'주문'
}

def _add(rows_to_delete, table, identifiers):
    rows_to_delete.extend((table,int(row_id)) for row_id in identifiers)

def _ids(conn,query,args=()):
    return [r[0] for r in conn.execute(query,args)]

def _row(conn,table,row_id):
    row=conn.execute(f'SELECT * FROM {table} WHERE id=?',(integer(row_id,'항목 번호',1),)).fetchone()
    if not row or conn.execute("""SELECT 1 FROM trash_rows d JOIN trash t ON t.id=d.trash_id
        WHERE d.table_name=? AND d.row_id=? AND t.restored_at IS NULL""",(table,row_id)).fetchone():
        raise UserError('삭제할 기록을 찾을 수 없습니다. 화면을 새로고침해 주세요.')
    return dict(row)

def _sale_rows(conn,sale_id):
    result=[('sales',sale_id)]
    line_ids=_ids(conn,f"SELECT id FROM sale_lines l WHERE sale_id=? AND {active('sale_lines','l')}",(sale_id,))
    return_ids=_ids(conn,f"SELECT id FROM returns r WHERE sale_id=? AND {active('returns','r')}",(sale_id,))
    payment_ids=_ids(conn,f"SELECT id FROM payments p WHERE sale_id=? AND {active('payments','p')}",(sale_id,))
    movement_ids=_ids(conn,f"SELECT id FROM movements m WHERE sale_id=? AND {active('movements','m')}",(sale_id,))
    _add(result,'sale_lines',line_ids);_add(result,'returns',return_ids);_add(result,'payments',payment_ids);_add(result,'movements',movement_ids)
    if return_ids:
        marks=','.join('?'*len(return_ids))
        _add(result,'return_lines',_ids(conn,f"SELECT id FROM return_lines l WHERE return_id IN ({marks}) AND {active('return_lines','l')}",return_ids))
    return result

def _return_rows(conn,returned):
    result=[('returns',returned['id'])]
    _add(result,'return_lines',_ids(conn,f"SELECT id FROM return_lines l WHERE return_id=? AND {active('return_lines','l')}",(returned['id'],)))
    _add(result,'movements',_ids(conn,f"SELECT id FROM movements m WHERE return_id=? AND {active('movements','m')}",(returned['id'],)))
    # Version 1 refunds had no explicit return_id. The unique refund written with the
    # return is identified by sale, date, creation time and the dedicated note prefix.
    refund=conn.execute(f"""SELECT id FROM payments p WHERE sale_id=? AND day=? AND amount<0
        AND created_at>=? AND note LIKE '반품 환불:%' AND {active('payments','p')}
        ORDER BY created_at,id LIMIT 1""",(returned['sale_id'],returned['day'],returned['created_at'])).fetchone()
    if refund: result.append(('payments',refund[0]))
    return result

def validate_state(conn):
    bad=conn.execute(f"""SELECT product_id,SUM(qty) stock FROM movements m
        WHERE {active('movements','m')} GROUP BY product_id HAVING stock<0 OR stock>1000000""").fetchone()
    if bad:
        raise UserError('이 작업을 하면 재고가 음수가 되거나 허용 범위를 벗어납니다. 관련 판매·반품 기록을 먼저 확인해 주세요.')
    if conn.execute(f'SELECT 1 FROM ({SALES_QUERY}) WHERE paid<0 OR balance<0 OR net<0').fetchone():
        raise UserError('이 작업을 하면 입금 또는 미수금 계산이 맞지 않습니다. 연결된 기록을 먼저 확인해 주세요.')

def delete_record(conn,data):
    entity=data.get('entity')
    if entity not in ENTITY_LABELS:
        raise UserError('삭제할 기록 종류를 확인해 주세요.')
    table={'product':'products','partner':'partners','sale':'sales','payment':'payments','return':'returns','movement':'movements','order':'orders'}[entity]
    item=_row(conn,table,data.get('id'))
    affected=[]; impact={}
    if entity=='order':
        affected=[(table,item['id'])]
        _add(affected,'order_lines',_ids(conn,'SELECT id FROM order_lines WHERE order_id=?',(item['id'],)))
        label=f"{item['number']} · {item['partner_name']}"
        impact={'안내':'주문만 숨겨집니다. 재고·매출·미수금은 변하지 않습니다.'}
    elif entity=='product':
        affected=[(table,item['id'])];label=f"{item['sku']} · {item['name']}";impact={'안내':'품목이 목록에서 숨겨집니다.'}
    elif entity=='partner':
        affected=[(table,item['id'])];label=item['name'];impact={'안내':'거래처가 목록에서 숨겨지며 과거 장부는 유지됩니다.'}
    elif entity=='sale':
        summary=one(conn,SALES_QUERY+' WHERE s.id=?',(item['id'],))
        affected=_sale_rows(conn,item['id']);label=f"{item['number']} · {item['partner_name']}"
        impact={'재고':'판매 전 상태로 복원','판매금액':-summary['net'],'순입금액':-summary['paid'],'연결기록':len(affected)-1}
    elif entity=='payment':
        if item['amount']<0:
            raise UserError('환불·정정 기록은 연결된 판매 또는 반품에서 삭제해 주세요.')
        affected=[(table,item['id'])]
        correction=_ids(conn,f"SELECT id FROM payments p WHERE note LIKE ? AND {active('payments','p')}",(f"[입금정정 #{item['id']}]%",))
        _add(affected,'payments',correction);label=f"{item['day']} · {item['amount']:,}원 입금";impact={'미수금':item['amount'],'연결기록':len(correction)}
    elif entity=='return':
        affected=_return_rows(conn,item);label=f"{item['day']} · {item['total']:,}원 반품"
        impact={'재고':'반품 전 상태로 복원','반품금액':-item['total'],'연결기록':len(affected)-1}
    else:
        if item['kind'] not in ('opening','receive','adjust'):
            raise UserError('판매·반품으로 생긴 입출고는 해당 판매 또는 반품 기록에서 삭제해 주세요.')
        affected=[(table,item['id'])];label=f"{item['day']} · {item['qty']:+,} 재고"
        impact={'재고변화':-item['qty']}
    trash_id=conn.execute('INSERT INTO trash(entity,entity_id,label,impact,deleted_at) VALUES (?,?,?,?,?)',
        (entity,item['id'],label,json.dumps(impact,ensure_ascii=False),now())).lastrowid
    conn.executemany('INSERT INTO trash_rows(trash_id,table_name,row_id) VALUES (?,?,?)',
                     ((trash_id,table,row_id) for table,row_id in affected))
    validate_state(conn)
    log(conn,'휴지통으로 이동',f"{ENTITY_LABELS[entity]} / {label}")
    return {'id':trash_id,'label':label,'impact':impact}

def restore_record(conn,data):
    trash_id=integer(data.get('id'),'휴지통 번호',1)
    item=conn.execute('SELECT * FROM trash WHERE id=? AND restored_at IS NULL AND purged_at IS NULL',(trash_id,)).fetchone()
    if not item: raise UserError('복구할 기록을 찾을 수 없습니다.')
    conn.execute('UPDATE trash SET restored_at=? WHERE id=?',(now(),trash_id))
    validate_state(conn)
    log(conn,'휴지통 복구',f"{ENTITY_LABELS.get(item['entity'],item['entity'])} / {item['label']}")
    return {'restored':True}

def purge_record(conn,data):
    trash_id=integer(data.get('id'),'휴지통 번호',1)
    item=conn.execute('SELECT * FROM trash WHERE id=? AND restored_at IS NULL AND purged_at IS NULL',(trash_id,)).fetchone()
    if not item: raise UserError('영구 삭제할 기록을 찾을 수 없습니다.')
    conn.execute('UPDATE trash SET purged_at=? WHERE id=?',(now(),trash_id))
    log(conn,'영구 삭제',f"{ENTITY_LABELS.get(item['entity'],item['entity'])} / {item['label']} / 복구 불가")
    return {'purged':True}

def list_trash(conn):
    result=rows(conn,'SELECT id,entity,entity_id,label,impact,deleted_at FROM trash WHERE restored_at IS NULL AND purged_at IS NULL ORDER BY id DESC')
    for item in result:item['impact']=json.loads(item['impact'])
    return result
