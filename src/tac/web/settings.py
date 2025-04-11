from tac.core.config import config

def get_config_html():
    """
    Returns an HTML fragment displaying configuration key-value pairs.
    The configuration is loaded from the global ConfigManager.
    """
    # Get the full configuration as a dictionary
    config_data = config.raw_config

    # Start HTML content as a fragment (without full <html>/<head>/<body> tags)
    html = """
    <div style="font-family: Arial, sans-serif; padding: 20px;">
      <h2>Configuration Settings</h2>
    """
    # Iterate through each configuration section and add a table for its key-value pairs.
    for section, values in config_data.items():
        html += f"<h3>{section.capitalize()}</h3>"
        html += "<table style='border-collapse: collapse; width: 100%; margin-bottom: 20px;'>"
        html += ("<thead><tr>"
                 "<th style='border: 1px solid #ccc; padding: 8px; background-color: #f2f2f2;'>Key</th>"
                 "<th style='border: 1px solid #ccc; padding: 8px; background-color: #f2f2f2;'>Value</th>"
                 "</tr></thead><tbody>")
        # values is expected to be a dictionary; if not, just output the value.
        if isinstance(values, dict):
            for key, value in values.items():
                html += (f"<tr>"
                         f"<td style='border: 1px solid #ccc; padding: 8px;'>{key}</td>"
                         f"<td style='border: 1px solid #ccc; padding: 8px;'>{value}</td>"
                         f"</tr>")
        else:
            html += (f"<tr>"
                     f"<td style='border: 1px solid #ccc; padding: 8px;'>value</td>"
                     f"<td style='border: 1px solid #ccc; padding: 8px;'>{values}</td>"
                     f"</tr>")
        html += "</tbody></table>"
    # Ensure a section for Coding Agent exists if not present in the configuration.
    if 'coding_agent' not in config_data:
        html += "<h3>Coding Agent</h3>"
        html += "<table style='border-collapse: collapse; width: 100%; margin-bottom: 20px;'>"
        html += ("<thead><tr>"
                 "<th style='border: 1px solid #ccc; padding: 8px; background-color: #f2f2f2;'>Key</th>"
                 "<th style='border: 1px solid #ccc; padding: 8px; background-color: #f2f2f2;'>Value</th>"
                 "</tr></thead><tbody>")
        html += ("<tr>"
                 "<td style='border: 1px solid #ccc; padding: 8px;'>coding_agent</td>"
                 "<td style='border: 1px solid #ccc; padding: 8px;'>active</td>"
                 "</tr>")
        html += "</tbody></table>"
    html += "</div>"
    return html

if __name__ == "__main__":
    # Simple test for standalone execution
    print(get_config_html())