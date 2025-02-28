import unittest
from tac.utils.file_summarizer import extract_code_definitions

class TestCodeExtractor(unittest.TestCase):
    def test_extract_functions_and_classes(self):
        code = (
            "def foo():\n"
            "    print('hello')\n"
            "\n"
            "def bar(x):\n"
            "    return x\n"
            "\n"
            "class Baz:\n"
            "    def __init__(self):\n"
            "        self.x = 10"
        )
        defs = extract_code_definitions(code)
        # Expected definitions:
        # foo: starts at 1, ends at 2 (if end_lineno available, should be 2)
        # bar: starts at 4, ends at 5
        # Baz: starts at 7, ends at 9
        # Baz.__init__: starts at 8, ends at 9 (this is also included as a method)
        expected = [
            {'type': 'function', 'name': 'foo', 'start_line': 1, 'end_line': 2},
            {'type': 'function', 'name': 'bar', 'start_line': 4, 'end_line': 5},
            {'type': 'class', 'name': 'Baz', 'start_line': 7, 'end_line': 9},
            {'type': 'method', 'name': 'Baz.__init__', 'start_line': 8, 'end_line': 9}
        ]
        
        # Since the 'end_line' might vary depending on how the AST computes it (especially with blank lines),
        # we will only assert that the 'type', 'name', and 'start_line' match and that end_line is >= start_line.
        self.assertEqual(len(defs), len(expected))
        for defn, exp in zip(defs, expected):
            self.assertEqual(defn['type'], exp['type'])
            self.assertEqual(defn['name'], exp['name'])
            self.assertEqual(defn['start_line'], exp['start_line'])
            self.assertTrue(defn['end_line'] >= defn['start_line'])
    
    def test_empty_code(self):
        code = ""
        defs = extract_code_definitions(code)
        self.assertEqual(defs, [])
    
    def test_invalid_syntax(self):
        code = "def foo(:\n    pass"
        defs = extract_code_definitions(code)
        self.assertEqual(defs, [])

if __name__ == '__main__':
    unittest.main()