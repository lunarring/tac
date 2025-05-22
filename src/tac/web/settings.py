from tac.core.config import config

def get_config_html():
    """
    Returns an HTML fragment displaying component_llm_mappings from the configuration,
    with dropdown menus to change each component's LLM.
    """
    # Get the component_llm_mappings and available LLM templates
    component_llm_mappings = config.raw_config.get('component_llm_mappings', {})
    llm_templates = config.raw_config.get('llm_templates', {}).keys()

    # Start HTML content as a fragment
    html = """
    <div style="font-family: Arial, sans-serif; padding: 20px;">
      <h2>Component LLM Mappings</h2>
      <p>Select which LLM to use for each component:</p>
      <div style="background-color: #FFF3CD; color: #856404; padding: 10px; margin-bottom: 15px; border-radius: 4px;">
        <strong>Note:</strong> After saving changes, you will need to restart the application for them to take effect.
      </div>
      <form id="component-mapping-form" style="margin-bottom: 20px;">
    """
    
    # Create a table for the component-to-LLM mappings with dropdowns
    html += "<table style='border-collapse: collapse; width: 100%; margin-bottom: 20px;'>"
    html += ("<thead><tr>"
             "<th style='border: 1px solid #ccc; padding: 8px; background-color: #f2f2f2;'>Component</th>"
             "<th style='border: 1px solid #ccc; padding: 8px; background-color: #f2f2f2;'>LLM</th>"
             "</tr></thead><tbody>")
    
    # Add each component mapping to the table with a dropdown
    for component, current_llm in component_llm_mappings.items():
        html += (f"<tr>"
                 f"<td style='border: 1px solid #ccc; padding: 8px;'>{component}</td>"
                 f"<td style='border: 1px solid #ccc; padding: 8px;'>"
                 f"<select name='component-{component}' data-component='{component}' class='llm-selector'>"
        )
        
        # Add options for each available LLM template
        for llm in llm_templates:
            selected = "selected" if llm == current_llm else ""
            html += f"<option value='{llm}' {selected}>{llm}</option>"
            
        html += "</select></td></tr>"
    
    html += "</tbody></table>"
    
    # Add save button and script to handle updates
    html += """
        <button type="button" id="save-mappings" style="padding: 8px 16px; background-color: #4CAF50; color: white; 
                 border: none; border-radius: 4px; cursor: pointer;">Save Changes</button>
      </form>
      
      <div id="status-message" style="margin-top: 10px; padding: 8px; display: none;"></div>
      
      <script>
        document.getElementById('save-mappings').addEventListener('click', function() {
          // Collect all the selected values
          const selectors = document.querySelectorAll('.llm-selector');
          const mappings = {};
          
          selectors.forEach(selector => {
            const component = selector.getAttribute('data-component');
            mappings[component] = selector.value;
          });
          
          // Send the updated mappings to the server
          const data = {
            type: 'update_component_llm_mappings',
            mappings: mappings
          };
          
          // Send message to parent window
          const statusEl = document.getElementById('status-message');
          statusEl.textContent = 'Updating component mappings...';
          statusEl.style.backgroundColor = '#FFF3CD';
          statusEl.style.color = '#856404';
          statusEl.style.padding = '8px';
          statusEl.style.borderRadius = '4px';
          statusEl.style.display = 'block';
          
          // Send to parent window which has the websocket
          window.parent.postMessage({
            type: 'settings_websocket_message',
            data: data
          }, '*');
        });
        
        // Listen for messages from parent window
        window.addEventListener('message', function(event) {
          // Check if the message is a response to our settings update
          if (event.data && event.data.type === 'component_mapping_update_result') {
            const statusEl = document.getElementById('status-message');
            if (event.data.success) {
              statusEl.textContent = 'Component mappings updated successfully! Please restart the application for changes to take effect.';
              statusEl.style.backgroundColor = '#D4EDDA';
              statusEl.style.color = '#155724';
            } else {
              statusEl.textContent = 'Error updating component mappings: ' + (event.data.error || 'Unknown error');
              statusEl.style.backgroundColor = '#F8D7DA';
              statusEl.style.color = '#721C24';
            }
            statusEl.style.display = 'block';
          }
        });
      </script>
    </div>
    """
    
    return html

if __name__ == "__main__":
    # Simple test for standalone execution
    print(get_config_html())