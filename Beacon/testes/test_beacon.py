import io
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from unittest.mock import patch

import beacon


class BeaconTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        beacon.init_db(self.db)
        self.db.execute("INSERT INTO users(name,email,salt,password_hash) VALUES(?,?,?,?)",
                        ("Aluno", "aluno@example.com", "a", "b"))
        self.db.execute("INSERT INTO users(name,email,salt,password_hash) VALUES(?,?,?,?)",
                        ("Outra pessoa", "outro@example.com", "a", "b"))
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_dinheiro_e_validacao(self):
        self.assertEqual(beacon.parse_money("1.234,56"), 123456)
        self.assertEqual(beacon.parse_money("25.90"), 2590)
        self.assertEqual(beacon.parse_money("0", allow_zero=True), 0)
        self.assertEqual(beacon.money(123456), "R$ 1.234,56")
        with self.assertRaises(ValueError):
            beacon.parse_money("-5")
        with self.assertRaises(ValueError):
            beacon.parse_money("abc")

    def test_exemplos_e_idempotencia(self):
        with patch.object(beacon, "read", return_value="s"), redirect_stdout(io.StringIO()):
            beacon.load_demo(self.db, 1)
            beacon.load_demo(self.db, 1)
        count = self.db.execute("SELECT COUNT(*) FROM transactions WHERE user_id=1").fetchone()[0]
        self.assertEqual(count, 30)
        data = beacon.month_rows(self.db, 1, date.today().strftime("%Y-%m"))
        self.assertEqual(beacon.totals(data), (225000, 185500, 60500))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM transactions WHERE user_id=2").fetchone()[0], 0)

    def test_projecao_e_cortes_exatos(self):
        with patch.object(beacon, "read", return_value="s"), redirect_stdout(io.StringIO()):
            beacon.load_demo(self.db, 1)
        deadline = beacon.offset_month(date.today(), 7) + "-28"
        self.db.execute("INSERT INTO goals(user_id,name,target_cents,saved_cents,deadline) VALUES(?,?,?,?,?)",
                        (1, "Computador", 480000, 0, deadline))
        self.db.commit()
        output = io.StringIO()
        with redirect_stdout(output):
            beacon.suggestions(self.db, 1)
        text = output.getvalue()
        self.assertIn("R$ 600,00", text)
        self.assertIn("R$ 205,00", text)
        self.assertIn("Delivery: reduzir R$ 180,00", text)
        self.assertIn("Lazer: reduzir R$ 25,00", text)

    def test_graficos_gerados(self):
        self.assertEqual(len(beacon.bar(100, 100, 24)), 24)
        with patch.object(beacon, "read", return_value="s"), redirect_stdout(io.StringIO()):
            beacon.load_demo(self.db, 1)
        with patch.object(beacon, "read", return_value=date.today().strftime("%Y-%m")):
            output = io.StringIO()
            with redirect_stdout(output):
                beacon.expense_charts(self.db, 1)
        self.assertIn("EVOLUÇÃO DAS DESPESAS", output.getvalue())
        self.assertIn("Moradia", output.getvalue())

    def test_exportacao_isolada(self):
        with patch.object(beacon, "read", return_value="s"), redirect_stdout(io.StringIO()):
            beacon.load_demo(self.db, 1)
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(beacon, "__file__", str(Path(folder)/"beacon.py")), redirect_stdout(io.StringIO()):
                beacon.export_csv(self.db, 1)
            files = list((Path(folder)/"exportacoes").glob("*.csv"))
            self.assertEqual(len(files), 1)
            contents = files[0].read_text(encoding="utf-8-sig")
            self.assertIn("Bolsa", contents)
            self.assertIn("Gasto_opcional", contents)


if __name__ == "__main__":
    unittest.main()
