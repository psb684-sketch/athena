"""Manual order inbox. Orders never mutate inventory or accounting records."""
import json
from .db import active, rows
from .validation import UserError, integer, string, day, now, existing, log

STATUSES = {'pending': '대기', 'confirmed': '확인', 'completed': '완료', 'cancelled': '취소'}


def status_value(value):
    if not isinstance(value, str) or value not in STATUSES:
        raise UserError('주문 상태를 선택해 주세요.')
    return value


def detail(conn, order_id):
    order = existing(conn, 'orders', order_id)
    order['lines'] = rows(conn, 'SELECT * FROM order_lines WHERE order_id=? ORDER BY id', (order['id'],))
    return order


def list_orders(conn, params):
    query = string(params.get('q', ''), '검색어', maximum=120).lower()
    status = params.get('status', '')
    if status:
        status_value(status)
    orders = rows(conn, f"""SELECT o.*,
        (SELECT COUNT(*) FROM order_lines l WHERE l.order_id=o.id) line_count,
        (SELECT group_concat(product_name || ' ' || spec, ', ') FROM order_lines l WHERE l.order_id=o.id) items
        FROM orders o WHERE {active('orders', 'o')} ORDER BY o.day DESC, o.id DESC""")
    return {'orders': [o for o in orders if (not status or o['status'] == status) and
                       query in f"{o['number']} {o['partner_name']} {o['items']} {o['note']}".lower()]}


def _history(conn, before, after):
    conn.execute('INSERT INTO edit_history(entity,entity_id,label,before_json,after_json,edited_at) VALUES (?,?,?,?,?,?)',
                 ('order', before['id'], before['number'], json.dumps(before, ensure_ascii=False),
                  json.dumps(after, ensure_ascii=False), now()))


def save_order(conn, data):
    before = detail(conn, data['id']) if data.get('id') is not None else None
    partner_id = integer(data.get('partner_id'), '거래처', 1)
    # Retain historical references even if the original catalog entry was hidden.
    if before and partner_id == before['partner_id']:
        partner_name = before['partner_name']
    else:
        partner_name = existing(conn, 'partners', partner_id, True)['name']
    ordered_day = day(data.get('day'))
    note = string(data.get('note', ''), '주문 메모', maximum=1000)
    lines = data.get('lines')
    if not isinstance(lines, list) or not 1 <= len(lines) <= 100:
        raise UserError('주문 품목을 1~100개 선택해 주세요.')
    old_lines = {line['product_id']: line for line in before['lines']} if before else {}
    selected = set()
    items = []
    total = 0
    for line in lines:
        if not isinstance(line, dict):
            raise UserError('주문 품목 형식을 확인해 주세요.')
        product_id = integer(line.get('product_id'), '품목', 1)
        if product_id in selected:
            raise UserError('같은 품목은 한 줄에 수량을 합쳐 주세요.')
        selected.add(product_id)
        if product_id in old_lines:
            original = old_lines[product_id]
            name, spec, unit = original['product_name'], original['spec'], original['unit']
        else:
            product = existing(conn, 'products', product_id, True)
            name, spec, unit = product['name'], product['spec'], product['unit']
        qty = integer(line.get('qty'), '주문 수량', 1, 1000000)
        price = integer(line.get('price'), '주문 단가', 0, 1000000000)
        total += qty * price
        items.append((product_id, name, spec, unit, qty, price))
    integer(total, '주문 합계', 0, 1000000000000)
    stamp = now()
    if before:
        order_id = before['id']
        conn.execute('UPDATE orders SET partner_id=?,partner_name=?,day=?,total=?,note=?,updated_at=? WHERE id=?',
                     (partner_id, partner_name, ordered_day, total, note, stamp, order_id))
        conn.execute('DELETE FROM order_lines WHERE order_id=?', (order_id,))
    else:
        # BEGIN IMMEDIATE serializes allocation; soft-deleted IDs are never reused.
        order_id = conn.execute('SELECT COALESCE(MAX(id),0)+1 FROM orders').fetchone()[0]
        conn.execute('INSERT INTO orders(id,number,partner_id,partner_name,day,status,total,note,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
                     (order_id, f'ORD-{order_id:06d}', partner_id, partner_name, ordered_day, 'pending', total, note, stamp, stamp))
    conn.executemany('INSERT INTO order_lines(order_id,product_id,product_name,spec,unit,qty,price) VALUES (?,?,?,?,?,?,?)',
                     [(order_id, *item) for item in items])
    if before:
        _history(conn, before, detail(conn, order_id))
    log(conn, '주문 수정' if before else '주문 등록', f'ORD-{order_id:06d} / {partner_name}')
    return {'id': order_id}


def change_status(conn, data):
    before = detail(conn, data.get('id'))
    status = status_value(data.get('status'))
    if status != before['status']:
        conn.execute('UPDATE orders SET status=?,updated_at=? WHERE id=?', (status, now(), before['id']))
        _history(conn, before, detail(conn, before['id']))
        log(conn, '주문 상태 변경', f"{before['number']} / {STATUSES[before['status']]} → {STATUSES[status]}")
    return {'id': before['id'], 'status': status}
