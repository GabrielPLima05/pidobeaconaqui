import io
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from unittest.mock import patch

import beacon


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        beacon.init_db(self.db)
        for name, email in (("Aluna", "aluna@example.com"), ("Colega", "colega@example.com")):
            self.db.execute("INSERT INTO users(name,email,salt,password_hash) VALUES(?,?,?,?)", (name, email, "salt", "hash"))
        self.db.commit()
        self.month = date.today().strftime("%Y-%m")

    def tearDown(self):
        self.db.close()

    def test_senhas_derivadas_com_sal(self):
        a = beacon.hash_password("senhaforte123", b"1" * 16)
        b = beacon.hash_password("senhaforte123", b"2" * 16)
        self.assertNotEqual(a, b)
        self.assertEqual(len(a), 64)

    def test_csv_protege_formula_com_espacos(self):
        self.assertTrue(beacon.csv_safe("  =HYPERLINK(\"url\")").startswith("'"))
        self.assertEqual(beacon.csv_safe("Alimentação"), "Alimentação")

    def test_pdf_respeita_usuario(self):
        self.db.execute("INSERT INTO transactions(user_id,kind,amount_cents,category,description,discretionary,occurred_on) VALUES(?,?,?,?,?,?,?)", (1,"despesa",2500,"Lazer","Festa",1,date.today().isoformat()))
        self.db.execute("INSERT INTO transactions(user_id,kind,amount_cents,category,description,discretionary,occurred_on) VALUES(?,?,?,?,?,?,?)", (2,"receita",5000,"Bolsa","Bolsas",0,date.today().isoformat()))
        one = beacon.financial_pdf(self.db, 1, self.month)
        two = beacon.financial_pdf(self.db, 2, self.month)
        self.assertTrue(one.startswith(b"%PDF-1.4"))
        self.assertIn(b"Lazer", one)
        self.assertNotIn(b"Bolsas", one)
        self.assertIn(b"Bolsas", two)
        self.assertIn(b"%%EOF", one)

    def test_pdf_multiplas_paginas(self):
        for number in range(55):
            self.db.execute("INSERT INTO transactions(user_id,kind,amount_cents,category,description,discretionary,occurred_on) VALUES(?,?,?,?,?,?,?)", (1,"despesa",1200,"Alimentação",f"Compra {number:02d}",1,date.today().isoformat()))
        data = beacon.financial_pdf(self.db, 1, self.month)
        self.assertIn(b"/Count 2", data)
        self.assertIn(b"Compra 54", data)

    def test_exportacao_pdf_gera_arquivo_local(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(beacon, "__file__", str(Path(folder) / "beacon.py")), patch.object(beacon, "read", return_value=self.month), redirect_stdout(io.StringIO()):
                beacon.export_pdf(self.db, 1)
            reports = list((Path(folder) / "exportacoes").glob("*.pdf"))
            self.assertEqual(len(reports), 1)
            self.assertGreater(reports[0].stat().st_size, 500)

    def test_mes_invalido(self):
        with self.assertRaises(ValueError):
            beacon.valid_month("2026-13")
        with self.assertRaises(ValueError):
            beacon.parse_date("31/12/2026")

    def test_entrada_monetaria_nao_aceita_infinito(self):
        for value in ("NaN", "Infinity", "-0.01", "1e99"):
            with self.assertRaises(ValueError):
                beacon.parse_money(value)

    def test_segundo_usuario_nao_enxerga_dados_do_primeiro(self):
        self.db.execute("INSERT INTO transactions(user_id,kind,amount_cents,category,description,discretionary,occurred_on) VALUES(?,?,?,?,?,?,?)", (1,"despesa",2500,"Lazer","Cinema",1,date.today().isoformat()))
        self.assertEqual(len(beacon.month_rows(self.db, 1, self.month)), 1)
        self.assertEqual(len(beacon.month_rows(self.db, 2, self.month)), 0)


if __name__ == "__main__":
    unittest.main()
