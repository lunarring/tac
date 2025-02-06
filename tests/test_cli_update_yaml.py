import os
import yaml
import tempfile
import unittest
from tac.cli.main import load_config

class TestConfigUpdate(unittest.TestCase):
    def test_yaml_config_update(self):
        # Define the custom configuration settings
        test_config = {
            'custom_setting': True,
            'log_level': 'DEBUG'
        }
        # Write the test config to a temporary YAML file
        with tempfile.NamedTemporaryFile('w', delete=False) as tmp:
            yaml.dump(test_config, tmp)
            tmp_path = tmp.name

        # Load the configuration using the updated load_config function
        loaded_config = load_config(tmp_path)
        os.remove(tmp_path)
        self.assertEqual(loaded_config, test_config)

if __name__ == "__main__":
    unittest.main()
