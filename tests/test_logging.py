import pytest
import logging
from unittest.mock import patch, mock_open
import yaml
from tdac.core.logging import setup_logging

@pytest.fixture
def mock_config():
    return {
        'logging': {
            'tdac': {
                'level': 'DEBUG',
                'color': 'green'
            }
        }
    }

def test_setup_logging(mock_config):
    # Mock the config file reading
    mock_yaml = yaml.dump(mock_config)
    
    with patch('builtins.open', mock_open(read_data=mock_yaml)):
        logger = setup_logging()
        
        # Verify logger level
        assert logger.level == logging.DEBUG
        
        # Verify handler and formatter setup
        assert len(logger.handlers) == 1
        handler = logger.handlers[0]
        assert isinstance(handler, logging.StreamHandler)
        
        # Verify formatter colors
        formatter = handler.formatter
        assert formatter.log_colors['INFO'] == 'green'
        assert formatter.log_colors['DEBUG'] == 'cyan'
        assert formatter.log_colors['WARNING'] == 'yellow'
        assert formatter.log_colors['ERROR'] == 'red'
        assert formatter.log_colors['CRITICAL'] == 'red,bg_white'
        
        # Verify propagation is disabled
        assert logger.propagate is False
