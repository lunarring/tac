import os
import yaml
import tempfile
import unittest
from tac.core.config import ConfigManager

class TestConfigUpdate(unittest.TestCase):
    def test_yaml_config_update(self):
        # Define the custom configuration settings
        test_config = {
            'general': {
                'type': 'aider',
                'plausibility_test': True
            },
            'git': {
                'enabled': True
            }
        }
        
        # Write the test config to a temporary YAML file
        with tempfile.NamedTemporaryFile('w', delete=False) as tmp:
            yaml.dump(test_config, tmp)
            tmp_path = tmp.name

        # Create a new ConfigManager instance and reload with our test config
        config = ConfigManager()
        config.reload(tmp_path)
        
        # Verify the config was loaded correctly
        self.assertEqual(config.general.type, 'aider')
        self.assertEqual(config.general.plausibility_test, True)
        self.assertEqual(config.git.enabled, True)
        
        os.remove(tmp_path)

if __name__ == "__main__":
    unittest.main()
