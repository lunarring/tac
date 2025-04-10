from tac.core.config import config

def get_config_html():
    """
    Returns a simple HTML page displaying configuration key-value pairs.
    The configuration is loaded from the global ConfigManager.
    """
    # Get the full configuration as a dictionary
    config_data = config.raw_config
    
    # Start HTML output
    html = """
    <html>
      <head>
        <meta charset="UTF-8">
        <title>Settings</title>
        <style>
          body { font-family: Arial, sans-serif; padding: 20px; }
          h2 { border-bottom: 2px solid #ccc; padding-bottom: 5px; }
          h3 { margin-top: 20px; }
          table { border-collapse: collapse; width: 100%; margin-bottom: 20px; }
          th, td { border: 1px solid #ccc; padding: 8px; text-align: left; }
          th { background-color: #f2f2f2; }
        </style>
      </head>
      <body>
        <h2>Configuration Settings</h2>
    """
    # Iterate through each configuration section and add a table for its key-value pairs.
    for section, values in config_data.items():
        html += f"<h3>{section.capitalize()}</h3>"
        html += "<table><thead><tr><th>Key</th><th>Value</th></tr></thead><tbody>"
        # values is a dictionary; if not, convert it into one.
        if isinstance(values, dict):
            for key, value in values.items():
                html += f"<tr><td>{key}</td><td>{value}</td></tr>"
        else:
            html += f"<tr><td>value</td><td>{values}</td></tr>"
        html += "</tbody></table>"
    
    html += """
      </body>
    </html>
    """
    return html

if __name__ == "__main__":
    # Simple test for standalone execution
    print(get_config_html())