from tac.core.config import config

def get_config_html():
    """
    Returns an HTML fragment displaying component_llm_mappings from the configuration.
    """
    # Get only the component_llm_mappings from the configuration
    component_llm_mappings = config.raw_config.get('component_llm_mappings', {})

    # Start HTML content as a fragment
    html = """
    <div style="font-family: Arial, sans-serif; padding: 20px;">
      <h2>Component LLM Mappings</h2>
    """
    
    # Create a table for the component-to-LLM mappings
    html += "<table style='border-collapse: collapse; width: 100%; margin-bottom: 20px;'>"
    html += ("<thead><tr>"
             "<th style='border: 1px solid #ccc; padding: 8px; background-color: #f2f2f2;'>Component</th>"
             "<th style='border: 1px solid #ccc; padding: 8px; background-color: #f2f2f2;'>LLM</th>"
             "</tr></thead><tbody>")
    
    # Add each component mapping to the table
    for component, llm in component_llm_mappings.items():
        html += (f"<tr>"
                 f"<td style='border: 1px solid #ccc; padding: 8px;'>{component}</td>"
                 f"<td style='border: 1px solid #ccc; padding: 8px;'>{llm}</td>"
                 f"</tr>")
    
    html += "</tbody></table>"
    html += "</div>"
    return html

if __name__ == "__main__":
    # Simple test for standalone execution
    print(get_config_html())