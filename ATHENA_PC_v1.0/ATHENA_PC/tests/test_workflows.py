"""Business invariants and HTTP boundary tests; temporary databases only."""
import http.client
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
import uuid
from datetime import date,timedelta

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from athena import db, reports, backup, trash
from athena.server import Application,Server
from athena.validation import UserError

class Workflows(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'athena.db'
        self.app=Application(self.path,Path(__file__).resolve().parents[1]/'ui')
        self.today=date.today().isoformat()
        self.product=self.write('products',{'name':'테스트 풋베드','price':30000,'minimum':2,'opening_stock':20})['id']
        self.partner=self.write('partners',{'name':'검증용 거래처'})['id']

    def tearDown(self):
        self.temp.cleanup()

    def read(self,fn,*args):
        conn=db.connect(self.path)
        try:return fn(conn,*args)
        finally:conn.close()

    def state(self):return self.read(reports.state)
    def write(self,action,data,key=None,revision=None):
        return self.app.write(action,{**data,'revision':self.state()['revision'] if revision is None else revision,
                                      'request_key':key or str(uuid.uuid4())})
    def sale(self,qty=4,paid=0,**kwargs):
        return self.write('sales',{'partner_id':self.partner,'day':self.today,'lines':[{'product_id':self.product,'qty':qty,'price':30000}],
                                   'paid':paid,'method':'transfer',**kwargs})['id']
    def detail(self,sale):return self.read(reports.sale_detail,sale)
    def return_data(self,sale,qty,**kwargs):
        return {'sale_id':sale,'day':self.today,'lines':[{'sale_line_id':self.detail(sale)['lines'][0]['id'],'qty':qty}],
                'note':'검증용 반품','method':'transfer',**kwargs}

    def test_sale_payment_partial_return_and_refund(self):
        sale=self.sale(4,30000)
        self.assertEqual(self.state()['products'][0]['stock'],16)
        self.assertEqual(self.detail(sale)['balance'],90000)
        self.write('payments',{'partner_id':self.partner,'day':self.today,'amount':60000,'method':'cash'})
        self.write('returns',self.return_data(sale,1))
        self.assertEqual(self.detail(sale)['balance'],0)
        with self.assertRaises(UserError):self.write('returns',self.return_data(sale,1))
        self.write('returns',self.return_data(sale,1,refund_confirmed=True))
        detail=self.detail(sale)
        self.assertEqual((detail['net'],detail['paid'],detail['balance']),(60000,60000,0))
        self.assertEqual(self.state()['products'][0]['stock'],18)
        self.assertEqual(self.state()['summary']['today_cash'],60000)
        self.read(backup.verify)

    def test_insufficient_stock_rolls_back_everything(self):
        before=self.state()
        with self.assertRaises(UserError):self.sale(21,30000)
        after=self.state()
        self.assertEqual(before['revision'],after['revision'])
        self.assertEqual(after['recent_sales'],[])
        self.assertEqual(after['products'][0]['stock'],20)
        self.assertEqual(after['summary']['today_cash'],0)

    def test_duplicate_lines_and_fractional_inputs_rejected(self):
        lines=[{'product_id':self.product,'qty':2,'price':30000}]*2
        with self.assertRaises(UserError):self.sale(lines=lines)
        for qty in [1.5,-1,True,0]:
            with self.assertRaises(UserError):self.sale(qty)
        self.assertEqual(self.state()['products'][0]['stock'],20)

    def test_idempotency_and_stale_view(self):
        key=str(uuid.uuid4());revision=self.state()['revision']
        payload={'partner_id':self.partner,'day':self.today,'lines':[{'product_id':self.product,'qty':3,'price':30000}],'paid':30000}
        a=self.write('sales',payload,key,revision)
        b=self.write('sales',payload,key,revision)
        self.assertEqual(a,b)
        self.assertEqual(self.state()['products'][0]['stock'],17)
        with self.assertRaises(UserError):self.write('sales',payload,revision=revision)

    def test_concurrent_sale_is_serialized(self):
        revision=self.state()['revision'];results=[]
        def submit():
            try:results.append(self.write('sales',{'partner_id':self.partner,'day':self.today,
                'lines':[{'product_id':self.product,'qty':15,'price':30000}]},revision=revision))
            except UserError:results.append('rejected')
        threads=[threading.Thread(target=submit) for _ in range(2)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertEqual(results.count('rejected'),1)
        self.assertEqual(self.state()['products'][0]['stock'],5)

    def test_opening_balance_and_oldest_first_allocation(self):
        self.partner=self.write('partners',{'name':'기존 거래처','opening_balance':50000})['id']
        sale=self.sale(3,0)
        self.write('payments',{'partner_id':self.partner,'day':self.today,'amount':80000,'method':'transfer'})
        self.assertEqual(self.detail(sale)['paid'],30000)
        self.assertEqual(self.state()['summary']['today_sales'],90000)
        with self.assertRaises(UserError):self.write('payments',{'partner_id':self.partner,'day':self.today,'amount':60001,'method':'transfer'})
        partner=self.read(reports.partner_detail,self.partner)
        self.assertEqual(partner['partner']['balance'],60000)
        self.assertEqual(partner['ledger'][-1]['balance'],60000)

    def test_backdated_payment_cannot_pay_future_invoice(self):
        self.sale()
        with self.assertRaises(UserError):self.write('payments',{'partner_id':self.partner,'day':(date.today()-timedelta(days=1)).isoformat(),
                                                              'amount':10000,'method':'transfer'})

    def test_return_limits_and_restore_archive_on_return(self):
        sale=self.sale(20,600000)
        self.write('archive',{'table':'products','id':self.product,'archived':1})
        self.write('returns',self.return_data(sale,5,refund_confirmed=True))
        self.assertEqual(self.state()['products'][0]['archived'],0)
        with self.assertRaises(UserError):self.write('returns',self.return_data(sale,16,refund_confirmed=True))
        self.assertEqual(self.state()['products'][0]['stock'],5)

    def test_payment_correction_preserves_history(self):
        sale=self.sale(4,60000);payment=self.detail(sale)['payments'][0]
        self.write('payment-correction',{'id':payment['id'],'day':self.today,'note':'입금액 오기입'})
        detail=self.detail(sale)
        self.assertEqual((detail['paid'],detail['balance'],len(detail['payments'])),(0,120000,2))
        with self.assertRaises(UserError):self.write('payment-correction',{'id':payment['id'],'day':self.today,'note':'중복 정정'})

    def test_catalog_changes_preserve_sale_snapshots(self):
        sale=self.sale()
        self.write('products',{'id':self.product,'name':'수정된 품목','price':99999,'unit':'상자','spec':'변경'})
        self.write('partners',{'id':self.partner,'name':'수정 거래처'})
        detail=self.detail(sale)
        self.assertEqual(detail['partner_name'],'검증용 거래처')
        self.assertEqual(detail['lines'][0]['product_name'],'테스트 풋베드')
        self.assertEqual(detail['lines'][0]['price'],30000)

    def test_backup_round_trip_and_restart_persistence(self):
        sale=self.sale(4,30000)
        self.write('returns',self.return_data(sale,1))
        target=backup.snapshot(self.path,Path(self.temp.name)/'manual.db')
        expected=self.detail(sale)
        self.sale(2,60000)
        old_revision=self.state()['revision']
        result=backup.restore(self.path,target.read_bytes())
        self.assertTrue(result['restored'])
        self.assertEqual(self.detail(sale),expected)
        self.assertEqual(len(self.state()['recent_sales']),1)
        self.assertGreater(self.state()['revision'],old_revision)
        reopened=Application(self.path,Path(__file__).resolve().parents[1]/'ui')
        self.assertTrue(reopened.path.exists())
        self.assertEqual(self.state()['products'][0]['stock'],17)
        self.read(backup.verify)

    def test_bad_backup_never_overwrites_live_data(self):
        self.sale()
        target=backup.snapshot(self.path,Path(self.temp.name)/'bad.db')
        conn=sqlite3.connect(target)
        try:conn.execute('UPDATE sales SET total=3');conn.commit()
        finally:conn.close()
        before=self.state()
        with self.assertRaises(UserError):backup.restore(self.path,target.read_bytes())
        self.assertEqual(self.state(),before)
        with self.assertRaises(UserError):backup.restore(self.path,b'not sqlite')
        conn=sqlite3.connect(target)
        try:conn.execute('CREATE VIEW malicious AS SELECT * FROM sales');conn.commit()
        finally:conn.close()
        with self.assertRaises(UserError):backup.restore(self.path,target.read_bytes())

    def test_csv_formula_injection_and_utf8(self):
        self.write('partners',{'name':'=HYPERLINK("x")','phone':'+820000'})
        text=self.read(reports.csv_bytes,'partners',{}).decode('utf-8-sig')
        self.assertIn("'=HYPERLINK",text)
        self.assertIn("'+820000",text)
        self.assertIn('검증용 거래처',text)

    def test_stock_adjustment_requires_reason_and_preserves_log(self):
        with self.assertRaises(UserError):self.write('stock',{'product_id':self.product,'kind':'adjust','counted':3,'day':self.today,'note':''})
        self.write('stock',{'product_id':self.product,'kind':'adjust','counted':3,'day':self.today,'note':'실사 수량 반영'})
        self.assertEqual(self.state()['products'][0]['stock'],3)
        self.assertEqual(self.read(reports.movements,{'product_id':self.product})['movements'][0]['qty'],-17)

    def test_sale_delete_and_trash_restore_reverse_every_effect(self):
        sale=self.sale(4,60000)
        self.write('returns',self.return_data(sale,1))
        before=self.detail(sale)
        self.assertEqual(self.state()['products'][0]['stock'],17)
        deleted=self.write('delete',{'entity':'sale','id':sale})
        state=self.state()
        self.assertEqual(state['products'][0]['stock'],20)
        self.assertEqual(state['recent_sales'],[])
        self.assertEqual(state['summary']['today_cash'],0)
        self.assertEqual(len(self.read(trash.list_trash)),1)
        with self.assertRaises(UserError):self.detail(sale)
        self.write('trash-restore',{'id':deleted['id']})
        self.assertEqual(self.state()['products'][0]['stock'],17)
        self.assertEqual(self.detail(sale),before)

    def test_return_delete_and_restore_include_its_refund(self):
        sale=self.sale(4,120000)
        returned=self.write('returns',self.return_data(sale,1,refund_confirmed=True))
        self.assertEqual((self.detail(sale)['net'],self.detail(sale)['paid']),(90000,90000))
        deleted=self.write('delete',{'entity':'return','id':returned['id']})
        self.assertEqual((self.detail(sale)['net'],self.detail(sale)['paid']),(120000,120000))
        self.assertEqual(self.state()['products'][0]['stock'],16)
        self.write('trash-restore',{'id':deleted['id']})
        self.assertEqual((self.detail(sale)['net'],self.detail(sale)['paid']),(90000,90000))
        self.assertEqual(self.state()['products'][0]['stock'],17)

    def test_unsafe_stock_delete_rolls_back_and_purge_cannot_restore(self):
        self.sale(4)
        opening=next(m for m in self.read(reports.movements,{'product_id':self.product})['movements'] if m['kind']=='opening')
        with self.assertRaises(UserError):self.write('delete',{'entity':'movement','id':opening['id']})
        self.assertEqual(self.state()['products'][0]['stock'],16)
        payment_sale=self.sale(1,30000)
        payment=self.detail(payment_sale)['payments'][0]
        deleted=self.write('delete',{'entity':'payment','id':payment['id']})
        self.write('trash-purge',{'id':deleted['id']})
        self.assertEqual(self.read(trash.list_trash),[])
        with self.assertRaises(UserError):self.write('trash-restore',{'id':deleted['id']})

    def test_v1_schema_migration_preserves_data_and_pre_migration_backup(self):
        conn=db.connect(self.path)
        try:
            conn.execute('DROP TABLE edit_history')
            conn.execute('DROP TABLE trash_rows')
            conn.execute('DROP TABLE trash')
            conn.execute("UPDATE meta SET value='1' WHERE key='schema'")
        finally:conn.close()
        Application(self.path,Path(__file__).resolve().parents[1]/'ui')
        conn=db.connect(self.path)
        try:self.assertEqual(dict(conn.execute('SELECT key,value FROM meta'))['schema'],'3')
        finally:conn.close()
        self.assertTrue((self.path.parent/'backups'/'before-schema-v3.db').exists())
        self.assertEqual(self.state()['products'][0]['stock'],20)

    def test_sale_edit_recalculates_stock_and_preserves_history(self):
        sale=self.sale(4,30000)
        self.write('sale-edit',{'id':sale,'partner_id':self.partner,'day':self.today,'note':'수량 정정',
            'lines':[{'product_id':self.product,'qty':3,'price':40000}]})
        detail=self.detail(sale)
        self.assertEqual((detail['total'],detail['paid'],detail['balance']),(120000,30000,90000))
        self.assertEqual(detail['lines'][0]['qty'],3)
        self.assertEqual(self.state()['products'][0]['stock'],17)
        conn=db.connect(self.path)
        try:self.assertEqual(conn.execute("SELECT COUNT(*) FROM edit_history WHERE entity='sale' AND entity_id=?",(sale,)).fetchone()[0],1)
        finally:conn.close()
        with self.assertRaises(UserError):self.write('sale-edit',{'id':sale,'partner_id':self.partner,'day':self.today,
            'lines':[{'product_id':self.product,'qty':1,'price':10000}]})
        self.assertEqual(self.state()['products'][0]['stock'],17)

    def test_payment_return_and_movement_edits_recalculate_ledger(self):
        sale=self.sale(4,120000)
        payment=self.detail(sale)['payments'][0]
        self.write('payment-edit',{'id':payment['id'],'day':self.today,'amount':90000,'method':'card','note':'입금액 수정'})
        self.assertEqual((self.detail(sale)['paid'],self.detail(sale)['balance']),(90000,30000))
        returned=self.write('returns',self.return_data(sale,1,refund_confirmed=True))
        self.assertEqual((self.detail(sale)['net'],self.detail(sale)['paid']),(90000,90000))
        line=self.detail(sale)['lines'][0]
        self.write('return-edit',{'id':returned['id'],'day':self.today,'note':'수량 수정','method':'cash',
            'lines':[{'sale_line_id':line['id'],'qty':2}],'refund_confirmed':True})
        detail=self.detail(sale)
        self.assertEqual((detail['net'],detail['paid'],detail['balance']),(60000,60000,0))
        self.assertEqual(self.state()['products'][0]['stock'],18)
        received=self.write('stock',{'product_id':self.product,'kind':'receive','qty':5,'day':self.today,'note':'입고'})['id']
        self.write('movement-edit',{'id':received,'day':self.today,'qty':3,'note':'수량 수정'})
        self.assertEqual(self.state()['products'][0]['stock'],21)

    def test_local_session_host_and_csrf(self):
        server=Server(self.app,0)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        client=http.client.HTTPConnection('127.0.0.1',server.server_port)
        cookie=f'{server.cookie_name}={self.app.token}'
        def get(path,headers):
            client.request('GET',path,headers=headers);response=client.getresponse();body=response.read();return response.status,body
        try:
            self.assertEqual(get('/api/state',{})[0],401)
            self.assertEqual(get('/api/state',{'Cookie':cookie,'Host':'evil.example'})[0],403)
            self.assertEqual(get('/api/state',{'Cookie':cookie,'Sec-Fetch-Site':'cross-site'})[0],403)
            self.assertEqual(get('/api/state',{'Cookie':cookie})[0],200)
            client.request('POST','/api/partners',body=b'{}',headers={'Cookie':cookie,'Content-Type':'application/json','Origin':server.origin})
            r=client.getresponse();r.read();self.assertEqual(r.status,403)
            self.assertEqual(get('/../run.py',{'Cookie':cookie})[0],404)
            self.assertEqual(get('/api/export/products',{'Cookie':cookie})[0],200)
        finally:
            client.close();server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main(verbosity=2)
