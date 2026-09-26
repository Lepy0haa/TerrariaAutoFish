"""Все строки tr("...") во всех модулях программы переведены на английский."""
import ast
import glob
import os
import unittest

import i18n

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def tr_strings(path):
    """Строки-литералы, переданные в tr(...) в файле path: [(строка, номер строки)]."""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    found = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
                and (getattr(node.func, "id", None) == "tr" or getattr(node.func, "attr", None) == "tr")):
            found.append((node.args[0].value, node.lineno))
    return found


class Translations(unittest.TestCase):
    def test_all_translated(self):
        missing = []
        files = [p for p in glob.glob(os.path.join(ROOT, "*.py")) if os.path.basename(p) != "i18n.py"]
        for path in sorted(files):
            for text, line in tr_strings(path):
                if text not in i18n.EN:
                    missing.append("%s:%d %r" % (os.path.basename(path), line, text))
        self.assertEqual(missing, [], "нет перевода:\n" + "\n".join(missing))

    def test_same_placeholders(self):
        bad = [k for k, v in i18n.EN.items() if k.count("%") != v.count("%")]
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
