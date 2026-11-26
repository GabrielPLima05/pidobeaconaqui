import io
import sqlite3
import unittest
from contextlib import redirect_stdout
from datetime import date
from decimal import Decimal
from unittest.mock import patch

import beacon


class NewFeaturesTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        beacon.init_db(self.db)
        self.db.execute("INSERT INTO users(name,email,salt,password_hash) VALUES(?,?,?,?)", ("Estudante", "estudante@example.com", "salt", "hash"))
        self.db.execute("INSERT INTO users(name,email,salt,password_hash) VALUES(?,?,?,?)", ("Colega", "colega@example.com", "salt", "hash"))
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def load_demo(self):
        with patch.object(beacon, "read", return_value="s"), redirect_stdout(io.StringIO()):
            beacon.load_demo(self.db, 1)

    def test_perfil_salvo_e_isolado(self):
        answers = iter(["s", "3", "2", "1.600,00", "Moradia,Transporte,Delivery"])
        with patch.object(beacon, "read", side_effect=lambda *args: next(answers)), redirect_stdout(io.StringIO()):
            beacon.student_mode(self.db, 1)
        profile = beacon.get_student_profile(self.db, 1)
        self.assertEqual(profile["role"], "ambos")
        self.assertEqual(profile["conservative_income_cents"], 160000)
        self.assertIsNone(beacon.get_student_profile(self.db, 2))
        self.assertIn("delivery", beacon.protected_names(profile))

    def test_corte_protege_categoria_e_renda(self):
        self.load_demo()
        deadline = beacon.offset_month(date.today(), 7) + "-28"
        self.db.execute("INSERT INTO goals(user_id,name,target_cents,saved_cents,deadline) VALUES(?,?,?,?,?)", (1, "Computador", 480000, 0, deadline))
        self.db.execute("INSERT INTO student_profiles(user_id,role,income_pattern,conservative_income_cents,protected_categories) VALUES(?,?,?,?,?)", (1, "estagiario", "variavel", 180000, "Moradia,Delivery"))
        self.db.commit()
        result = io.StringIO()
        with redirect_stdout(result):
            beacon.suggestions(self.db, 1)
        text = result.getvalue()
        self.assertIn("Renda conservadora utilizada: R$ 1.800,00", text)
        self.assertNotIn("Delivery: reduzir", text)
        self.assertIn("Lazer: reduzir", text)
        self.assertIn("Streaming: reduzir", text)

    def test_recomendacoes_adaptativas(self):
        self.load_demo()
        self.db.execute("INSERT INTO student_profiles(user_id,role,income_pattern,conservative_income_cents,protected_categories) VALUES(?,?,?,?,?)", (1, "ambos", "mista", 160000, "Transporte,Estudos"))
        self.db.commit()
        choices = beacon.education_recommendations(self.db, 1)
        files = [item[0] for item in choices]
        self.assertIn("05_atividade_pratica.md", files)
        self.assertIn("06_renda_variavel.md", files)
        self.assertIn("08_vida_academica.md", files)
        self.assertEqual(beacon.education_recommendations(self.db, 2)[0][0], "01_orcamento.md")

    def test_compra_sem_juros_sem_perda_de_centavos(self):
        payments = beacon.create_payment_schedule(10000, 3)
        self.assertEqual(len(payments), 3)
        self.assertEqual(sum(payments), 10000)
        self.assertEqual(payments, [3334, 3333, 3333])

    def test_compra_com_juros_e_validacao(self):
        payments = beacon.create_payment_schedule(60000, 6, Decimal("2"))
        self.assertEqual(len(payments), 6)
        self.assertGreater(sum(payments), 60000)
        self.assertTrue(all(payment == payments[0] for payment in payments))
        for count, interest in ((0, Decimal("0")), (61, Decimal("0")), (6, Decimal("31")), (6, Decimal("NaN"))):
            with self.assertRaises(ValueError):
                beacon.create_payment_schedule(60000, count, interest)

    def test_simulacao_nao_altera_dados(self):
        self.load_demo()
        initial = self.db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        analysis = beacon.purchase_analysis(self.db, 1, 50000, beacon.create_payment_schedule(50000, 5), date.today().strftime("%Y-%m"))
        self.assertEqual(len(analysis), 6)
        self.assertEqual(analysis[0]["income"], 225000)
        self.assertEqual(analysis[0]["expense"], 185500)
        self.assertEqual(analysis[0]["after"], 29500)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], initial)

    def test_simulacao_identifica_comprometimento_de_metas(self):
        self.load_demo()
        deadline = beacon.offset_month(date.today(), 5) + "-28"
        self.db.execute("INSERT INTO goals(user_id,name,target_cents,saved_cents,deadline) VALUES(?,?,?,?,?)", (1, "Reserva", 180000, 0, deadline))
        self.db.commit()
        analysis = beacon.purchase_analysis(self.db, 1, 60000, beacon.create_payment_schedule(60000, 6), date.today().strftime("%Y-%m"))
        self.assertEqual(analysis[0]["goal"], 30000)
        self.assertEqual(analysis[1]["goal"], 30000)
        self.assertEqual(analysis[0]["before"], 9500)
        self.assertTrue(analysis[0]["new_shortfall"])

    def test_faq_predefinido_sem_ia(self):
        output = io.StringIO()
        answers = iter(["simulador", "0"])
        with patch.object(beacon, "read", side_effect=lambda *args: next(answers)), patch.object(beacon, "wait_for_menu"), redirect_stdout(output):
            beacon.frequently_asked()
        self.assertIn("Como funciona o simulador de compras?", output.getvalue())
        self.assertIn("não altera suas transações", output.getvalue().lower())

    def test_migracao_db_existente(self):
        old_db = sqlite3.connect(":memory:")
        old_db.row_factory = sqlite3.Row
        old_db.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT, salt TEXT, password_hash TEXT)")
        old_db.execute("INSERT INTO users VALUES(1,'Antes','antes@exemplo.com','a','b')")
        beacon.init_db(old_db)
        self.assertEqual(old_db.execute("SELECT COUNT(*) FROM users").fetchone()[0], 1)
        self.assertIn("student_profiles", {r[0] for r in old_db.execute("SELECT name FROM sqlite_master WHERE type='table'")})
        old_db.close()


if __name__ == "__main__":
    unittest.main()
