"""Integration check using the actual launcher and HTTP routes, in disposable data."""
import http.client
import json
import locale
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit
import uuid

ROOT=Path(__file__).resolve().parents[1]

def main():
    checkpoints=[]
    with tempfile.TemporaryDirectory(prefix='athena-http-check-') as directory:
        directory=Path(directory)
        process=None
        connection=None

        def start():
            nonlocal process,connection
            process=subprocess.Popen([sys.executable,str(ROOT/'run.py'),'--no-browser','--data-dir',str(directory)],
                                     stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            for _ in range(200):
                if (directory/'instance.json').exists():break
                if process.poll() is not None:raise AssertionError(process.communicate())
                time.sleep(0.025)
            info=json.loads((directory/'instance.json').read_text())
            parsed=urlsplit(info['url'])
            connection=http.client.HTTPConnection('127.0.0.1',parsed.port,timeout=15)
            connection.request('GET',parsed.path+'?'+parsed.query)
            response=connection.getresponse();response.read()
            assert response.status==303
            return info['origin'],response.getheader('Set-Cookie').split(';')[0]

        def stop():
            nonlocal process,connection
            if connection:connection.close();connection=None
            if process and process.poll() is None:
                if os.name=='nt':process.terminate()
                else:process.send_signal(signal.SIGINT)
                process.communicate(timeout=10)
                if os.name=='nt':(directory/'instance.json').unlink(missing_ok=True)
            process=None

        try:
            origin,cookie=start()
            def get(path,raw=False):
                connection.request('GET',path,headers={'Cookie':cookie})
                r=connection.getresponse();body=r.read();assert r.status==200,(path,r.status,body)
                return body if raw else json.loads(body)
            def post(action,payload,expected=200,key=None):
                state=get('/api/state')
                body=json.dumps({**payload,'request_key':key or str(uuid.uuid4()),'revision':state['revision']}).encode()
                connection.request('POST','/api/'+action,body,{'Cookie':cookie,'Origin':origin,'Content-Type':'application/json','X-Athena-CSRF':state['csrf']})
                r=connection.getresponse();body=r.read();assert r.status==expected,(action,r.status,body)
                return json.loads(body)

            state=get('/api/state');assert state['products']==[] and state['partners']==[]
            today=state['today'];checkpoints.append('Empty first launch with no sample business data')
            for asset in ['/','/app.js','/forms.js','/orders.js','/shared.js','/style.css','/statement.html','/statement.js','/favicon.svg']:
                assert get(asset,True)
            checkpoints.append('All HTML/CSS/JS and statement assets served through authenticated HTTP')
            product=post('products',{'name':'HTTP 검증 품목','price':10000,'opening_stock':10})['id']
            partner=post('partners',{'name':'HTTP 검증 거래처'})['id']
            order_data={'partner_id':partner,'day':today,'lines':[{'product_id':product,'qty':100,'price':10000}]}
            order=post('orders',order_data)['id']
            post('orders',{**order_data,'id':order,'note':'HTTP 주문 수정'})
            post('order-status',{'id':order,'status':'confirmed'})
            assert get('/api/orders?status=confirmed')['orders'][0]['id']==order
            deleted_order=post('delete',{'entity':'order','id':order})['id']
            assert get('/api/orders')['orders']==[]
            post('trash-restore',{'id':deleted_order})
            assert get('/api/state')['products'][0]['stock']==10
            assert get('/api/state')['summary']['receivable']==0
            checkpoints.append('Order create/edit/status/delete/restore leaves inventory and receivables unchanged')
            sale=post('sales',{'partner_id':partner,'day':today,'lines':[{'product_id':product,'qty':4,'price':10000}],
                               'paid':10000,'method':'cash'})['id']
            state=get('/api/state');assert state['products'][0]['stock']==6 and state['summary']['receivable']==30000
            post('sales',{'partner_id':partner,'day':today,'lines':[{'product_id':product,'qty':7,'price':10000}]},400)
            post('payments',{'partner_id':partner,'day':today,'amount':20000,'method':'transfer'})
            detail=get(f'/api/sale/{sale}');line=detail['lines'][0]['id']
            post('returns',{'sale_id':sale,'day':today,'note':'반품 검증','lines':[{'sale_line_id':line,'qty':2}],'method':'cash'},400)
            post('returns',{'sale_id':sale,'day':today,'note':'반품 검증','lines':[{'sale_line_id':line,'qty':2}],'method':'cash','refund_confirmed':True})
            detail=get(f'/api/sale/{sale}');assert (detail['net'],detail['paid'],detail['balance'])==(20000,20000,0)
            assert get('/api/state')['products'][0]['stock']==8
            checkpoints.append('Sale → partial payment → excess-refund gate → partial return with confirmed refund')
            deleted=post('delete',{'entity':'sale','id':sale})['id']
            state=get('/api/state');assert state['products'][0]['stock']==10 and len(state['trash'])==1
            post('trash-restore',{'id':deleted})
            assert get('/api/state')['products'][0]['stock']==8
            checkpoints.append('Whole-sale delete reverses linked stock and cash, then trash restore reapplies them')
            for kind in ['products','partners','sales','movements']:
                assert get('/api/export/'+kind,True).startswith(b'\xef\xbb\xbf')
            assert get(f'/api/export/ledger?partner_id={partner}',True)
            checkpoints.append('UTF-8 CSV exports for all five export types')
            archived=get('/api/backup',True)
            movement=post('stock',{'product_id':product,'kind':'receive','qty':5,'day':today,'note':'복원 검증용'})['id']
            post('movement-edit',{'id':movement,'day':today,'qty':3,'note':'HTTP 수정 검증'})
            state=get('/api/state');assert state['products'][0]['stock']==11
            connection.request('POST','/api/restore',archived,{'Cookie':cookie,'Origin':origin,'Content-Type':'application/octet-stream',
                'X-Athena-CSRF':state['csrf'],'X-Athena-Restore':'RESTORE','X-Athena-Revision':str(state['revision'])})
            r=connection.getresponse();body=r.read();assert r.status==200,body
            assert get('/api/state')['products'][0]['stock']==8
            checkpoints.append('HTTP backup download and validated restore, preserving pre-restore data')
            second=subprocess.run([sys.executable,str(ROOT/'run.py'),'--no-browser','--data-dir',str(directory)],capture_output=True,
                                  text=True,encoding=locale.getpreferredencoding(False),errors='replace',timeout=10)
            assert second.returncode==0 and '이미 실행 중' in second.stdout
            checkpoints.append('Duplicate launcher reuses the running data instance')
            stop()
            origin,cookie=start()
            state=get('/api/state');assert state['products'][0]['stock']==8 and state['summary']['receivable']==0
            assert len(get(f'/api/sale/{sale}')['payments'])==3
            assert get(f'/api/order/{order}')['status']=='confirmed'
            assert get(f'/api/order/{order}')['note']=='HTTP 주문 수정'
            checkpoints.append('Order contents and status survive backup restore and full process restart')
            checkpoints.append('Full process shutdown and restart preserve stock, sales, payments and return')
        finally:
            stop()
    print(json.dumps({'status':'passed','checkpoints':checkpoints},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
