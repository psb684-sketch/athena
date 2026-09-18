"""Read models for screens, statements, and CSV exports."""
import csv
import io
from datetime import date, timedelta
from .db import connect, one, rows, SALES_QUERY, active
from .validation import integer, UserError
from .ledger import sale_summary

def products(conn):
    return rows(conn,f"""SELECT p.*,COALESCE(m.stock,0) stock FROM products p
      LEFT JOIN (SELECT product_id,SUM(qty) stock FROM movements mx WHERE {active('movements','mx')} GROUP BY product_id) m ON m.product_id=p.id
      WHERE {active('products','p')} ORDER BY p.archived,p.name,p.id""")

def partners(conn):
    return rows(conn,f"""SELECT p.*,COALESCE(t.balance,0) balance,COALESCE(t.volume,0) volume,t.last_day
      FROM partners p LEFT JOIN (SELECT partner_id,SUM(balance) balance,
      SUM(CASE WHEN kind='sale' THEN net ELSE 0 END) volume,
      MAX(CASE WHEN kind='sale' THEN day END) last_day FROM ({SALES_QUERY}) GROUP BY partner_id) t ON t.partner_id=p.id
      WHERE {active('partners','p')} ORDER BY p.archived,p.name,p.id""")

def activity(conn,start,end):
    return rows(conn,f"""SELECT day,SUM(sales) sales,SUM(cash) cash FROM (
      SELECT day,total sales,0 cash FROM sales s WHERE kind='sale' AND {active('sales','s')}
      UNION ALL SELECT day,-total sales,0 cash FROM returns r WHERE {active('returns','r')}
      UNION ALL SELECT day,0 sales,amount cash FROM payments p WHERE {active('payments','p')}
    ) WHERE day BETWEEN ? AND ? GROUP BY day ORDER BY day""",(start,end))

def state(conn):
    today=date.today()
    month=today.replace(day=1).isoformat()
    all_products=products(conn)
    all_partners=partners(conn)
    summary=activity(conn,month,today.isoformat())
    today_row=next((x for x in summary if x['day']==today.isoformat()),{'sales':0,'cash':0})
    week=activity(conn,(today-timedelta(days=6)).isoformat(),today.isoformat())
    by_day={x['day']:x for x in week}
    week=[by_day.get((today-timedelta(days=i)).isoformat(),{'day':(today-timedelta(days=i)).isoformat(),'sales':0,'cash':0}) for i in range(6,-1,-1)]
    return {'today':today.isoformat(),'settings':dict(conn.execute('SELECT key,value FROM meta')),
       'revision':int(conn.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0]),
       'products':all_products,'partners':all_partners,
       'summary':{'today_sales':today_row['sales'],'today_cash':today_row['cash'],
                  'month_sales':sum(x['sales'] for x in summary),'month_cash':sum(x['cash'] for x in summary),
                  'receivable':conn.execute(f'SELECT COALESCE(SUM(balance),0) FROM ({SALES_QUERY})').fetchone()[0],
                  'today_count':conn.execute(f"SELECT COUNT(*) FROM sales s WHERE day=? AND kind='sale' AND {active('sales','s')}",(today.isoformat(),)).fetchone()[0],
                  'stock_count':sum(x['stock'] for x in all_products if not x['archived']),
                  'low_count':sum(x['stock']<=x['minimum'] for x in all_products if not x['archived'])},
       'week':week,'recent_sales':rows(conn,SALES_QUERY+" WHERE s.kind='sale' ORDER BY s.day DESC,s.id DESC LIMIT 6"),
       'audit':rows(conn,'SELECT * FROM audit ORDER BY id DESC LIMIT 100')}

def sales_list(conn,params):
    clauses=['1=1']
    args=[]
    for name,op in [('from','>='),('to','<=')]:
        if params.get(name):
            try:
                date.fromisoformat(params[name])
            except (ValueError,TypeError):
                raise UserError('조회 날짜를 확인해 주세요.')
            clauses.append(f's.day{op}?')
            args.append(params[name])
    if params.get('q'):
        clauses.append("(s.number LIKE ? ESCAPE '\\' OR c.name LIKE ? ESCAPE '\\' OR s.partner_name LIKE ? ESCAPE '\\')")
        query=params['q'][:120].replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
        args.extend([f'%{query}%']*3)
    if params.get('partner_id'):
        clauses.append('s.partner_id=?')
        args.append(integer(params['partner_id'],'거래처',1))
    if params.get('status')=='unpaid':
        clauses.append('(s.total-COALESCE(r.returned,0)-COALESCE(p.paid,0))>0')
    result=rows(conn,SALES_QUERY+' WHERE '+' AND '.join(clauses)+' ORDER BY s.day DESC,s.id DESC',args)
    return {'sales':result}

def sale_detail(conn,sale_id):
    sale=sale_summary(conn,sale_id)
    sale['lines']=rows(conn,f"""SELECT l.*,COALESCE(r.qty,0) returned_qty FROM sale_lines l LEFT JOIN
       (SELECT sale_line_id,SUM(qty) qty FROM return_lines rx WHERE {active('return_lines','rx')} GROUP BY sale_line_id) r ON r.sale_line_id=l.id
       WHERE l.sale_id=? AND {active('sale_lines','l')} ORDER BY l.id""",(sale['id'],))
    sale['payments']=rows(conn,f"SELECT * FROM payments p WHERE sale_id=? AND {active('payments','p')} ORDER BY day,id",(sale['id'],))
    sale['returns']=rows(conn,f"SELECT * FROM returns r WHERE sale_id=? AND {active('returns','r')} ORDER BY day,id",(sale['id'],))
    sale['partner']=one(conn,'SELECT * FROM partners WHERE id=?',(sale['partner_id'],))
    return sale

def return_detail(conn,return_id):
    return_id=integer(return_id,'반품 번호',1)
    returned=one(conn,f"SELECT * FROM returns r WHERE id=? AND {active('returns','r')}",(return_id,))
    if not returned:raise UserError('반품 기록을 찾을 수 없습니다.')
    returned['sale']=sale_summary(conn,returned['sale_id'])
    returned['lines']=rows(conn,f"""SELECT s.*,COALESCE(current.qty,0) current_qty,COALESCE(other.qty,0) other_returned
        FROM sale_lines s
        LEFT JOIN (SELECT sale_line_id,SUM(qty) qty FROM return_lines x WHERE return_id=? AND {active('return_lines','x')} GROUP BY sale_line_id) current ON current.sale_line_id=s.id
        LEFT JOIN (SELECT l.sale_line_id,SUM(l.qty) qty FROM return_lines l JOIN returns r ON r.id=l.return_id
                   WHERE l.return_id!=? AND {active('return_lines','l')} AND {active('returns','r')} GROUP BY l.sale_line_id) other ON other.sale_line_id=s.id
        WHERE s.sale_id=? AND {active('sale_lines','s')} ORDER BY s.id""",(return_id,return_id,returned['sale_id']))
    returned['refund']=one(conn,f"""SELECT * FROM payments p WHERE sale_id=? AND day=? AND amount<0 AND created_at>=?
        AND note LIKE '반품 환불:%' AND {active('payments','p')} ORDER BY created_at,id LIMIT 1""",
        (returned['sale_id'],returned['day'],returned['created_at']))
    return returned

def movement_detail(conn,movement_id):
    movement_id=integer(movement_id,'입출고 번호',1)
    movement=one(conn,f"""SELECT m.*,p.name,p.spec,p.unit FROM movements m JOIN products p ON p.id=m.product_id
        WHERE m.id=? AND {active('movements','m')}""",(movement_id,))
    if not movement:raise UserError('입출고 기록을 찾을 수 없습니다.')
    return movement

def partner_detail(conn,partner_id):
    partner_id=integer(partner_id,'거래처 번호',1)
    partner=next((p for p in partners(conn) if p['id']==partner_id),None)
    if not partner:
        raise UserError('거래처를 찾을 수 없습니다.')
    sales=sales_list(conn,{'partner_id':partner_id})['sales']
    ledger=[]
    for sale in sales:
        ledger.append({'day':sale['day'],'created_at':sale['created_at'],'kind':'시작 미수금' if sale['kind']=='opening' else '판매',
                       'sale_id':sale['id'],'number':sale['number'],'debit':sale['total'],'credit':0,'note':sale['note']})
    for payment in rows(conn,f"SELECT p.*,s.number FROM payments p JOIN sales s ON s.id=p.sale_id WHERE s.partner_id=? AND {active('payments','p')} AND {active('sales','s')}",(partner_id,)):
        ledger.append({'day':payment['day'],'created_at':payment['created_at'],'kind':'입금' if payment['amount']>0 else ('입금 정정' if payment['note'].startswith('[입금정정 #') else '환불'),
                       'sale_id':payment['sale_id'],'number':payment['number'],'debit':0,'credit':payment['amount'],'note':payment['note']})
    for returned in rows(conn,f"SELECT r.*,s.number FROM returns r JOIN sales s ON s.id=r.sale_id WHERE s.partner_id=? AND {active('returns','r')} AND {active('sales','s')}",(partner_id,)):
        ledger.append({'day':returned['day'],'created_at':returned['created_at'],'kind':'반품','sale_id':returned['sale_id'],
                       'number':returned['number'],'debit':-returned['total'],'credit':0,'note':returned['note']})
    ledger.sort(key=lambda x:(x['day'],x['created_at'],x['sale_id']))
    balance=0
    for item in ledger:
        balance+=item['debit']-item['credit']
        item['balance']=balance
    return {'partner':partner,'sales':sales,'ledger':ledger}

def movements(conn,params):
    product_id=params.get('product_id')
    where=' AND m.product_id=?' if product_id else ''
    args=(integer(product_id,'품목 번호',1),) if product_id else ()
    return {'movements':rows(conn,f"""SELECT m.*,p.name,p.spec,p.unit FROM movements m JOIN products p ON p.id=m.product_id
                            WHERE {active('movements','m')} AND {active('products','p')}"""+where+
                            ' ORDER BY m.day DESC,m.id DESC',args)}

def csv_bytes(conn,kind,params):
    # Neutralize spreadsheet formula interpretation of user-provided text.
    def safe(value):
        if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@','\t','\r','\n')):
            return "'"+value
        return value
    if kind=='products':
        fields=[('sku','품목코드'),('name','품목명'),('spec','규격'),('unit','단위'),('stock','현재고'),('price','기본단가'),('minimum','부족알림수량'),('archived','보관여부')]
        data=products(conn)
    elif kind=='partners':
        fields=[('name','거래처'),('contact','담당자'),('phone','연락처'),('address','주소'),('balance','미수금'),('note','메모')]
        data=partners(conn)
    elif kind=='sales':
        fields=[('day','거래일'),('number','거래번호'),('partner_name','거래당시거래처'),('kind','종류'),('total','최초금액'),('returned','반품금액'),('net','현재거래금액'),('paid','순입금액'),('balance','미수금'),('note','메모')]
        data=sales_list(conn,params)['sales']
    elif kind=='ledger':
        fields=[('day','날짜'),('kind','내용'),('number','거래번호'),('debit','판매증감'),('credit','입금증감'),('balance','미수잔액'),('note','메모')]
        data=partner_detail(conn,params.get('partner_id'))['ledger']
    elif kind=='movements':
        fields=[('day','날짜'),('name','품목명'),('spec','규격'),('kind','유형'),('qty','수량증감'),('unit','단위'),('note','메모')]
        data=movements(conn,params)['movements']
    else:
        raise UserError('내보낼 자료를 선택해 주세요.')
    out=io.StringIO(newline='')
    writer=csv.writer(out)
    writer.writerow([f[1] for f in fields])
    for item in data:
        writer.writerow([safe(item.get(key,'')) for key,label in fields])
    return out.getvalue().encode('utf-8-sig')
