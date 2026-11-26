import http.cookiejar
import json
import sqlite3
import tempfile
import threading
import unittest
from datetime import date
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

import beacon
import web_app


class InterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.original_db = beacon.DB_PATH
        beacon.DB_PATH = Path(cls.folder.name) / "beacon.db"
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), web_app.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"
        with web_app.db_session():
            pass

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        beacon.DB_PATH = cls.original_db
        cls.folder.cleanup()

    def setUp(self):
        self.client = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.email = f"test{self.id().split('.')[-1].lower()}@example.com"
        self.session = None
        self.request("POST", "/api/auth/register", {"name": "Aluno Teste", "email": self.email, "password": "testesenha123", "confirm": "testesenha123"}, 201)
        self.session = self.request("POST", "/api/auth/login", {"email": self.email, "password": "testesenha123"})

    def request(self, method, path, body=None, expected=200):
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Accept":"application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if self.session and method != "GET":
            headers["X-Beacon-CSRF"] = self.session["csrf"]
        req = Request(self.url+path, data=data, headers=headers, method=method)
        try:
            with self.client.open(req) as response:
                self.assertEqual(response.status, expected)
                if path.startswith('/api/export/'):
                    return response.read()
                return json.loads(response.read())
        except HTTPError as exc:
            self.assertEqual(exc.code, expected)
            return json.loads(exc.read())

    def test_app_serves_real_interface(self):
        request = Request(self.url+'/')
        with self.client.open(request) as response:
            html = response.read().decode('utf-8')
        self.assertIn('Simulador de compras', html)
        self.assertIn('Visão geral', html)
        self.assertIn('app.js', html)

    def test_purchase_demo_button_is_available(self):
        with self.client.open(self.url + '/') as response:
            html = response.read().decode('utf-8')
        with self.client.open(self.url + '/app.js') as response:
            script = response.read().decode('utf-8')
        self.assertIn('id="purchase-demo-button"', html)
        self.assertIn('id="purchase-demo-status"', html)
        self.assertIn("loadDemoData('purchase')", script)

    def test_demo_data_can_be_loaded_without_duplicates(self):
        first = self.request('POST', '/api/demo', {})
        second = self.request('POST', '/api/demo', {})
        self.assertEqual(first['created'], 30)
        self.assertEqual(second['created'], 0)
        transactions = self.request('GET', '/api/transactions')['transactions']
        self.assertEqual(len(transactions), 30)
        self.assertTrue(all(row['description'].startswith('DEMO | ') for row in transactions))
        current = self.request('GET', '/api/dashboard')
        self.assertGreater(current['income'], 0)
        self.assertGreater(current['expense'], 0)
        result = self.request('POST', '/api/purchase', {
            'amount': '600,00', 'installments': 6, 'monthlyRate': '0',
            'month': date.today().strftime('%Y-%m')
        })
        self.assertEqual(result['payment'], 100)
        self.assertEqual(len(self.request('GET', '/api/transactions')['transactions']), 30)

    def test_session_user_and_dashboard(self):
        self.assertEqual(self.request('GET','/api/session')['user']['email'], self.email)
        d = self.request('GET','/api/dashboard')
        self.assertEqual(d['income'],0)
        self.assertEqual(d['expense'],0)

    def test_transactions_projections_and_deletion(self):
        self.request('POST','/api/transactions',{'kind':'receita','amount':'1000,00','category':'Bolsa','description':'Estágio','date':date.today().isoformat()},201)
        self.request('POST','/api/transactions',{'kind':'despesa','amount':'100,00','category':'Lazer','description':'Cinema','date':date.today().isoformat(),'optional':True},201)
        d=self.request('GET','/api/dashboard')
        self.assertEqual((d['income'],d['expense'],d['optional']), (1000,100,100))
        rows=self.request('GET','/api/transactions')['transactions']
        self.assertEqual(len(rows),2)
        self.request('DELETE','/api/transactions/'+str(rows[0]['id']))
        self.assertEqual(len(self.request('GET','/api/transactions')['transactions']),1)

    def test_goal_and_purchase_simulator_is_readonly(self):
        deadline=beacon.offset_month(date.today(),6)+'-28'
        self.request('POST','/api/goals',{'name':'Notebook','target':'1200,00','saved':'0','deadline':deadline},201)
        goals=self.request('GET','/api/goals')['goals']
        self.assertEqual(len(goals),1)
        self.assertGreater(goals[0]['monthly'],0)
        result=self.request('POST','/api/purchase',{'amount':'600,00','installments':6,'monthlyRate':'0','month':date.today().strftime('%Y-%m')})
        self.assertEqual((result['payment'],result['total']), (100,600))
        self.assertEqual(len(self.request('GET','/api/transactions')['transactions']),0)
        self.request('PATCH','/api/goals/'+str(goals[0]['id']),{'saved':'250,00'})
        self.assertEqual(self.request('GET','/api/goals')['goals'][0]['saved'],250)

    def test_profile_education_and_faq(self):
        self.request('POST','/api/profile',{'role':'estagiario','incomePattern':'mista','conservativeIncome':'800,00','protectedCategories':'Transporte,Alimentação'})
        profile=self.request('GET','/api/profile')
        self.assertEqual(profile['conservativeIncome'],800)
        recommended=self.request('GET','/api/education')['recommended']
        self.assertTrue(any('acadêmico' in x['title'].lower() or 'renda variável' in x['title'].lower() for x in recommended))
        self.assertGreater(len(self.request('GET','/api/faq')['items']),5)
        text=self.request('GET','/api/material/01_orcamento.md')['content']
        self.assertIn('orçamento',text)

    def test_export_pdf_and_csv(self):
        pdf=self.request('GET','/api/export/pdf')
        csv_data=self.request('GET','/api/export/csv')
        self.assertTrue(pdf.startswith(b'%PDF-'))
        self.assertTrue(csv_data.startswith(b'\xef\xbb\xbf'))

    def test_csrf_rejects_requests_without_token(self):
        old=self.session
        self.session=None
        try:
            result=self.request('POST','/api/transactions',{'kind':'receita','amount':'100','category':'Bolsa','date':date.today().isoformat()},403)
            self.assertIn('inválida',result['error'])
        finally:
            self.session=old

    def test_user_isolation(self):
        with web_app.db_session() as db:
            other=db.execute('SELECT id FROM users WHERE email=?',(self.email,)).fetchone()['id']
            db.execute("INSERT INTO transactions(user_id,kind,amount_cents,category,description,discretionary,occurred_on) VALUES(?,?,?,?,?,?,?)",(other,'receita',1000,'Bolsa','Privado',0,date.today().isoformat()))
            db.commit()
        new_client=build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        with self.assertRaises(HTTPError) as context:
            new_client.open(self.url+'/api/transactions')
        self.assertEqual(context.exception.code,401)


if __name__ == '__main__':
    unittest.main()
