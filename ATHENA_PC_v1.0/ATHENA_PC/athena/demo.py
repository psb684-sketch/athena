"""Fictional records, only for an explicitly separate --demo data directory."""
from datetime import date,timedelta
from . import db,catalog,ledger

def seed(path):
    with db.transaction(path) as conn:
        if conn.execute('SELECT 1 FROM products LIMIT 1').fetchone(): return
        conn.execute("UPDATE meta SET value='아테나 체험 사업장' WHERE key='business'")
        products=[]
        for name,spec,price,stock,minimum in [('기능성 풋베드','S · 230–245',30000,140,20),('기능성 풋베드','M · 250–265',30000,190,30),
            ('기능성 풋베드','L · 270–285',30000,44,40),('데일리 쿠션 패드','공용',12000,80,15),('스포츠 양말','화이트 · 250',5000,220,30),('스포츠 양말','블랙 · 270',5000,18,20)]:
            products.append(catalog.save_product(conn,{'name':name,'spec':spec,'price':price,'opening_stock':stock,'minimum':minimum,'unit':'켤레'})['id'])
        customers=[]
        for name,contact in [('한빛스포츠','김대표'),('오름상사','이대표'),('바른걸음','박대표'),('새봄유통','최대표'),('동행스포츠','정대표')]:
            customers.append(catalog.save_partner(conn,{'name':name+' (예시)','contact':contact,'note':'체험용 가상 거래처입니다.'})['id'])
        for days,cust,prod,qty,price,paid in [(6,0,0,8,30000,240000),(5,1,1,12,30000,360000),(4,2,3,15,12000,0),
          (3,3,0,10,30000,200000),(2,4,4,30,5000,150000),(1,0,1,20,30000,300000),(0,1,2,10,30000,300000),
          (0,2,0,18,30000,200000),(0,3,1,15,30000,450000)]:
            ledger.create_sale(conn,{'partner_id':customers[cust],'day':(date.today()-timedelta(days=days)).isoformat(),
                'lines':[{'product_id':products[prod],'qty':qty,'price':price}],'paid':paid,'method':'transfer','note':'체험용 가상 거래'})
        conn.execute("UPDATE meta SET value='1' WHERE key='revision'")
