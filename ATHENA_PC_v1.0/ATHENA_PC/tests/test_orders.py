"""Order inbox, accounting isolation, migrations, backups and HTTP contracts."""
import http.client
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
import uuid
from datetime import date, timedelta
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from athena import db, backup, orders, reports, trash
from athena.server import Application, Server
from athena.validation import UserError

UI = Path(__file__).resolve().parents[1] / 'ui'


class Orders(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'athena.db'
        self.app = Application(self.path, UI)
        self.today = date.today().isoformat()
        self.product = self.write('products', {'name': '주문 품목', 'price': 3000, 'opening_stock': 5})['id']
        self.partner = self.write('partners', {'name': '주문 거래처'})['id']

    def tearDown(self):
        self.temp.cleanup()

    def read(self, fn, *args):
        conn = db.connect(self.path)
        try:
            return fn(conn, *args)
        finally:
            conn.close()

    def state(self):
        return self.read(reports.state)

    def write(self, action, data, key=None, revision=None):
        return self.app.write(action, {**data, 'request_key': key or str(uuid.uuid4()),
                                      'revision': self.state()['revision'] if revision is None else revision})

    def payload(self, **changes):
        return {'partner_id': self.partner, 'day': self.today, 'note': '수동 접수',
                'lines': [{'product_id': self.product, 'qty': 10, 'price': 3000}], **changes}

    def order(self, **changes):
        return self.write('orders', self.payload(**changes))['id']

    def ledger_snapshot(self):
        return self.read(lambda c: {t: db.rows(c, f'SELECT * FROM {t} ORDER BY id') for t in
                                  ('products', 'partners', 'sales', 'sale_lines', 'payments', 'returns', 'return_lines', 'movements')})

    def legacy(self, version='3'):
        conn = db.connect(self.path)
        try:
            conn.execute('DROP TABLE order_lines')
            conn.execute('DROP TABLE orders')
            if version in ('1', '2'):
                conn.execute('DROP TABLE edit_history')
            if version == '1':
                conn.execute('DROP TABLE trash_rows')
                conn.execute('DROP TABLE trash')
            conn.execute("UPDATE meta SET value=? WHERE key='schema'", (version,))
        finally:
            conn.close()

    def test_crud_statuses_and_trash_leave_all_ledger_tables_unchanged(self):
        sale = self.write('sales', self.payload(lines=[{'product_id': self.product, 'qty': 3, 'price': 3000}]))['id']
        self.write('payments', {'partner_id': self.partner, 'day': self.today, 'amount': 3000, 'method': 'cash'})
        line = self.read(reports.sale_detail, sale)['lines'][0]['id']
        self.write('returns', {'sale_id': sale, 'day': self.today, 'note': '기존 반품',
                              'lines': [{'sale_line_id': line, 'qty': 1}], 'method': 'cash'})
        before = self.ledger_snapshot()
        summary = self.state()['summary']
        order_id = self.order()  # More than available stock is intentionally allowed.
        detail = self.read(orders.detail, order_id)
        self.assertEqual((detail['status'], detail['total']), ('pending', 30000))
        self.write('orders', self.payload(id=order_id, lines=[{'product_id': self.product, 'qty': 4, 'price': 4000}]))
        for status in ('confirmed', 'completed', 'cancelled', 'pending'):
            self.write('order-status', {'id': order_id, 'status': status})
            self.assertEqual(self.read(orders.detail, order_id)['status'], status)
        deleted = self.write('delete', {'entity': 'order', 'id': order_id})['id']
        self.assertEqual(self.read(orders.list_orders, {})['orders'], [])
        with self.assertRaises(UserError):
            self.read(orders.detail, order_id)
        with self.assertRaises(UserError):
            self.write('order-status', {'id': order_id, 'status': 'confirmed'})
        self.write('trash-restore', {'id': deleted})
        self.assertEqual(self.read(orders.detail, order_id)['total'], 16000)
        deleted = self.write('delete', {'entity': 'order', 'id': order_id})['id']
        self.write('trash-purge', {'id': deleted})
        with self.assertRaises(UserError):
            self.write('trash-restore', {'id': deleted})
        self.assertEqual(before, self.ledger_snapshot())
        self.assertEqual(summary, self.state()['summary'])
        history = self.read(lambda c: db.rows(c, "SELECT * FROM edit_history WHERE entity='order' ORDER BY id"))
        self.assertEqual(len(history), 5)
        self.assertEqual(json.loads(history[0]['before_json'])['total'], 30000)
        self.read(backup.verify)

    def test_invalid_payloads_roll_back_without_losing_previous_lines(self):
        order_id = self.order()
        original = self.read(orders.detail, order_id)
        invalid = [self.payload(lines=[]), self.payload(lines=[None]), self.payload(lines=[{}]),
                   self.payload(lines=self.payload()['lines'] * 2), self.payload(partner_id=99999),
                   self.payload(day=(date.today()+timedelta(days=1)).isoformat()), self.payload(note='a'*1001)]
        for qty in (0, -1, True, 1.5, 1000001):
            invalid.append(self.payload(lines=[{'product_id': self.product, 'qty': qty, 'price': 3000}]))
        for price in (-1, True, 1.1, 1000000001):
            invalid.append(self.payload(lines=[{'product_id': self.product, 'qty': 1, 'price': price}]))
        invalid.append(self.payload(lines=[{'product_id': self.product, 'qty': 1000000, 'price': 1000000000}]))
        for payload in invalid:
            with self.subTest(payload=payload):
                revision = self.state()['revision']
                with self.assertRaises(UserError):
                    self.write('orders', {**payload, 'id': order_id})
                self.assertEqual(self.state()['revision'], revision)
                self.assertEqual(self.read(orders.detail, order_id), original)
        for status in ('shipped', '', None, [], {}):
            with self.assertRaises(UserError):
                self.write('order-status', {'id': order_id, 'status': status})

    def test_snapshots_and_existing_hidden_references_remain_editable(self):
        order_id = self.order()
        self.write('partners', {'id': self.partner, 'name': '새 거래처명'})
        self.write('products', {'id': self.product, 'name': '새 품목명', 'price': 999})
        self.write('delete', {'entity': 'partner', 'id': self.partner})
        self.write('delete', {'entity': 'product', 'id': self.product})
        self.write('orders', self.payload(id=order_id, note='기존 주문 수정'))
        detail = self.read(orders.detail, order_id)
        self.assertEqual(detail['partner_name'], '주문 거래처')
        self.assertEqual(detail['lines'][0]['product_name'], '주문 품목')
        with self.assertRaises(UserError):
            self.order()

    def test_idempotency_stale_revision_and_missing_order(self):
        revision = self.state()['revision']
        key = str(uuid.uuid4())
        first = self.write('orders', self.payload(), key, revision)
        self.assertEqual(first, self.write('orders', self.payload(), key, revision))
        self.assertEqual(len(self.read(orders.list_orders, {})['orders']), 1)
        with self.assertRaises(UserError):
            self.write('orders', self.payload(id=first['id']), revision=revision)
        for action, data in [('orders', self.payload(id=9999)), ('order-status', {'id': 9999, 'status': 'pending'}),
                             ('delete', {'entity': 'order', 'id': 9999})]:
            with self.assertRaises(UserError):
                self.write(action, data)

    def test_search_status_filter_zero_price_multiple_lines_and_unique_numbers(self):
        product2 = self.write('products', {'name': '두 번째 상품', 'price': 0})['id']
        first = self.order(lines=[{'product_id': self.product, 'qty': 2, 'price': 0},
                                 {'product_id': product2, 'qty': 1, 'price': 0}])
        second = self.order(note='전화 접수')
        self.write('order-status', {'id': second, 'status': 'confirmed'})
        self.assertEqual(self.read(orders.detail, first)['total'], 0)
        for query in ('ORD-', '주문 거래처', '주문 품목'):
            self.assertEqual(len(self.read(orders.list_orders, {'q': query})['orders']), 2)
        self.assertEqual(len(self.read(orders.list_orders, {'q': '전화', 'status': 'confirmed'})['orders']), 1)
        self.assertEqual(self.read(orders.list_orders, {'q': '전화', 'status': 'pending'})['orders'], [])
        self.write('delete', {'entity': 'order', 'id': second})
        self.assertGreater(self.order(), second)

    def test_backup_restore_and_restart_preserve_orders_trash_and_history(self):
        first = self.order()
        second = self.order()
        self.write('order-status', {'id': first, 'status': 'completed'})
        trash_id = self.write('delete', {'entity': 'order', 'id': second})['id']
        saved = backup.snapshot(self.path, self.path.parent/'saved.db').read_bytes()
        self.order()
        backup.restore(self.path, saved)
        self.app = Application(self.path, UI)
        self.assertEqual(self.read(orders.detail, first)['status'], 'completed')
        self.assertEqual(len(self.read(orders.list_orders, {})['orders']), 1)
        self.write('trash-restore', {'id': trash_id})
        self.assertEqual(self.read(orders.detail, second)['total'], 30000)
        self.read(backup.verify)

    def test_invalid_order_backup_is_rejected_and_live_data_survives(self):
        order_id = self.order()
        saved = backup.snapshot(self.path, self.path.parent/'bad.db')
        conn = db.connect(saved)
        conn.execute('UPDATE orders SET total=1');conn.close()
        original = self.path.read_bytes()
        with self.assertRaises(UserError):
            backup.restore(self.path, saved.read_bytes())
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.read(orders.detail, order_id)['total'], 30000)

    def test_v1_v2_v3_upgrade_preserves_exact_original_and_is_repeatable(self):
        for version in ('1', '2', '3'):
            with self.subTest(version=version):
                self.legacy(version)
                original = self.read(lambda c: list(c.iterdump()))
                before = self.ledger_snapshot()
                existing_backups = set((self.path.parent/'backups').glob('before-schema-v4-*.db'))
                db.initialize(self.path)
                new_backups = set((self.path.parent/'backups').glob('before-schema-v4-*.db')) - existing_backups
                self.assertEqual(len(new_backups), 1)
                saved = new_backups.pop()
                # SQLite online backup changes header counters, not schema/records.
                with closing(db.connect(saved)) as saved_conn:
                    self.assertEqual(list(saved_conn.iterdump()), original)
                self.assertEqual(self.ledger_snapshot(), before)
                db.initialize(self.path)
                self.assertEqual(self.read(lambda c: c.execute("SELECT value FROM meta WHERE key='schema'").fetchone()[0]), '4')
                self.assertEqual(self.read(orders.list_orders, {})['orders'], [])

    def test_failed_migration_or_backup_does_not_change_legacy_database(self):
        self.legacy()
        original = self.path.read_bytes()
        with patch('athena.backup.snapshot', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                db.initialize(self.path)
        self.assertEqual(self.path.read_bytes(), original)
        with patch('athena.db.ORDER_SCHEMA', db.ORDER_SCHEMA + '\nINVALID SQL;'):
            with self.assertRaises(sqlite3.Error):
                db.initialize(self.path)
        self.assertEqual(self.read(lambda c: c.execute("SELECT value FROM meta WHERE key='schema'").fetchone()[0]), '3')
        self.assertIsNone(self.read(lambda c: c.execute("SELECT name FROM sqlite_master WHERE name='orders'").fetchone()))

    def test_legacy_backup_restores_into_v4(self):
        self.legacy()
        saved = backup.snapshot(self.path, self.path.parent/'legacy.db').read_bytes()
        db.initialize(self.path)
        self.order()
        backup.restore(self.path, saved)
        self.assertEqual(self.read(orders.list_orders, {})['orders'], [])
        self.assertEqual(self.state()['products'][0]['stock'], 5)
        self.order()

    def test_http_orders_routes_security_errors_and_assets(self):
        server = Server(self.app, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True);thread.start()
        client = http.client.HTTPConnection('127.0.0.1', server.server_port)
        headers = {'Cookie': f'{server.cookie_name}={self.app.token}', 'Origin': server.origin,
                   'Content-Type': 'application/json', 'X-Athena-CSRF': self.app.csrf}
        def get(path, authenticated=True):
            client.request('GET', path, headers=headers if authenticated else {})
            response = client.getresponse();return response.status, response.read()
        def post(action, data, authenticated=True):
            body = json.dumps({**data, 'request_key': str(uuid.uuid4()), 'revision': self.state()['revision']})
            client.request('POST', '/api/'+action, body, headers if authenticated else {})
            response = client.getresponse();return response.status, json.loads(response.read())
        try:
            self.assertEqual(get('/api/orders', False)[0], 401)
            self.assertEqual(post('orders', self.payload(), False)[0], 401)
            self.assertEqual(get('/orders.js')[0], 200)
            status, data = post('orders', self.payload());self.assertEqual(status, 200)
            order_id = data['id']
            self.assertEqual(get(f'/api/order/{order_id}')[0], 200)
            self.assertEqual(post('orders', self.payload(id=order_id, note='HTTP 수정'))[0], 200)
            self.assertEqual(post('order-status', {'id': order_id, 'status': 'confirmed'})[0], 200)
            status, body = get('/api/orders?status=confirmed');self.assertEqual(len(json.loads(body)['orders']), 1)
            self.assertEqual(get('/api/orders?status=unknown')[0], 400)
            self.assertEqual(post('order-status', {'id': order_id, 'status': []})[0], 400)
            self.assertEqual(post('orders', self.payload(lines=[]))[0], 400)
            self.assertEqual(post('delete', {'entity': 'order', 'id': order_id})[0], 200)
            self.assertEqual(get(f'/api/order/{order_id}')[0], 400)
        finally:
            client.close();server.shutdown();server.server_close();thread.join()


if __name__ == '__main__':
    unittest.main(verbosity=2)
