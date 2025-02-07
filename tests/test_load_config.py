import os
import tempfile
import yaml
import unittest
from tac.cli.main import load_config

class TestLoadConfig(unittest.TestCase):
    def test_load_config_returns_expected_keys(self):
        # Create a temporary YAML file with test config data
        test_config = {
            'general': {
                'setting1': 'value1'
            },
            'git': {
                'remote': 'origin'
            }
        }
        with tempfile.NamedTemporaryFile('w', delete=False) as tmp:
            yaml.dump(test_config, tmp)
            tmp_path = tmp.name

        try:
            loaded_config = load_config(tmp_path)
            self.assertIsInstance(loaded_config, dict, "Loaded config should be a dictionary.")
            self.assertIn('general', loaded_config, "Config must contain key 'general'.")
            self.assertIn('git', loaded_config, "Config must contain key 'git'.")
            self.assertEqual(loaded_config, test_config, "Loaded config should exactly match the test config.")
        finally:
            os.remove(tmp_path)

if __name__ == "__main__":
    unittest.main()
