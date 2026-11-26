import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import beacon


class NavigationTests(unittest.TestCase):
    def test_pausa_sem_terminal_interativo(self):
        with patch.object(beacon.sys.stdin, "isatty", return_value=False), patch("builtins.input", return_value="") as typed:
            beacon.wait_for_menu()
        typed.assert_called_once_with("\nPressione Enter para voltar ao menu...")

    def test_pausa_encerramento_de_entrada(self):
        with patch.object(beacon.sys.stdin, "isatty", return_value=False), patch("builtins.input", side_effect=EOFError), redirect_stdout(io.StringIO()):
            beacon.wait_for_menu()

    def test_menu_aguarda_apos_abertura_e_comando(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(beacon, "DB_PATH", Path(folder) / "test.db"), patch.object(beacon, "authenticate", return_value={"id": 1, "name": "Teste"}), patch.object(beacon, "read", side_effect=["1", "0"]), patch.object(beacon, "wait_for_menu") as waiting, redirect_stdout(io.StringIO()):
                beacon.main()
            self.assertEqual(waiting.call_count, 2)

    def test_faq_aguarda_resposta(self):
        with patch.object(beacon, "read", side_effect=["1", "0"]), patch.object(beacon, "wait_for_menu") as waiting, redirect_stdout(io.StringIO()):
            beacon.frequently_asked()
        waiting.assert_called_once_with()

    def test_quiz_aguarda_leitura_de_cada_resposta(self):
        with patch.object(beacon, "read", side_effect=["b", "a", "c", "a", "b"]), patch.object(beacon, "wait_for_menu") as waiting, redirect_stdout(io.StringIO()):
            beacon.quiz()
        self.assertEqual(waiting.call_count, 5)

    def test_material_didatico_aguarda_leitura(self):
        with patch.object(beacon, "read", side_effect=["1", "0"]), patch.object(beacon, "wait_for_menu") as waiting, redirect_stdout(io.StringIO()):
            beacon.learn()
        waiting.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
