import unittest
from src.tac.core.config import ConfigManager, GeneralConfig, GitConfig, AiderConfig, LLMConfig, LoggingConfig

class TestConfigDefaults(unittest.TestCase):
    def setUp(self):
        # Reset the singleton instance to ensure a fresh configuration.
        ConfigManager._instance = None
        self.config_manager = ConfigManager()

    def test_subconfig_instances(self):
        self.assertIsInstance(self.config_manager.general, GeneralConfig)
        self.assertIsInstance(self.config_manager.git, GitConfig)
        self.assertIsInstance(self.config_manager.aider, AiderConfig)
        self.assertIsInstance(self.config_manager.get_llm_config("weak"), LLMConfig)
        self.assertIsInstance(self.config_manager.get_llm_config("strong"), LLMConfig)
        self.assertIsInstance(self.config_manager.logging, LoggingConfig)

    def test_get_method_default(self):
        self.assertEqual(self.config_manager.get("non_existent", 123), 123)

if __name__ == '__main__':
    unittest.main()
