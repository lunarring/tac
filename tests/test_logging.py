import unittest
import logging
import os
import yaml
from unittest.mock import patch, mock_open
from tdac.core.log_config import setup_logging

class TestLogging(unittest.TestCase):
    def test_setup_logging(self):
        # Mock config file content
        mock_config = {
            'logging': {
                'tdac': {
                    'level': 'DEBUG',
                    'color': 'green'
                }
            }
        }
        
        # Mock open to return our config
        with patch('builtins.open', mock_open(read_data=yaml.dump(mock_config))):
            logger = setup_logging()
            
            # Verify logger was created
            self.assertIsInstance(logger, logging.Logger)
            
            # Verify level was set
            self.assertEqual(logger.level, logging.DEBUG)
            
            # Verify handler was added
            self.assertEqual(len(logger.handlers), 1)
            
            # Verify propagation is disabled
            self.assertFalse(logger.propagate)

if __name__ == '__main__':
    unittest.main()
