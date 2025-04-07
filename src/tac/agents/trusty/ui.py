#!/usr/bin/env python3
import os
import json
from typing import Dict, Any, Optional, List

from tac.agents.trusty.results import TrustyAgentResult, ResultComponent

class ConsoleResultRenderer:
    """Renders TrustyAgentResult components in a console-friendly format"""
    
    @staticmethod
    def render_result(result: TrustyAgentResult) -> str:
        """
        Render a TrustyAgentResult as text for console output.
        
        Args:
            result: The TrustyAgentResult to render
            
        Returns:
            str: Formatted text representation of the result
        """
        output = []
        
        # Add header
        status = "✅ PASSED" if result.success else "❌ FAILED"
        output.append(f"{status} - {result.summary}")
        output.append("=" * 80)
        
        # Render each component
        for component in result.components:
            rendered = ConsoleResultRenderer._render_component(component)
            if rendered:
                output.append(rendered)
                output.append("-" * 80)
        
        # Add any additional details
        if result.details:
            output.append("Additional Details:")
            for key, value in result.details.items():
                if isinstance(value, str) and len(value) > 100:
                    value = value[:97] + "..."
                output.append(f"  {key}: {value}")
        
        return "\n".join(output)
    
    @staticmethod
    def _render_component(component: ResultComponent) -> str:
        """Render a specific component based on its type"""
        if component.component_type == "grade":
            return ConsoleResultRenderer._render_grade(component)
        elif component.component_type == "report":
            return ConsoleResultRenderer._render_report(component)
        elif component.component_type == "screenshot":
            return ConsoleResultRenderer._render_screenshot(component)
        elif component.component_type == "comparison":
            return ConsoleResultRenderer._render_comparison(component)
        elif component.component_type == "metric":
            return ConsoleResultRenderer._render_metric(component)
        elif component.component_type == "error":
            return ConsoleResultRenderer._render_error(component)
        else:
            return f"Unknown component type: {component.component_type}"
    
    @staticmethod
    def _render_grade(component) -> str:
        """Render a grade component"""
        title = "Grade"
        if hasattr(component, 'title') and component.title:
            title = component.title
            
        output = [f"{title}: {component.grade} ({component.scale})"]
        if component.description:
            output.append(component.description)
        return "\n".join(output)
    
    @staticmethod
    def _render_report(component) -> str:
        """Render a report component"""
        title = "Report"
        if hasattr(component, 'title') and component.title:
            title = component.title
            
        output = [f"{title}:"]
        output.append(component.content)
        return "\n".join(output)
    
    @staticmethod
    def _render_screenshot(component) -> str:
        """Render a screenshot component"""
        output = ["Screenshot:"]
        if component.description:
            output.append(component.description)
        
        file_status = "✅ File exists" if os.path.exists(component.path) else "❌ File missing"
        output.append(f"Path: {component.path} ({file_status})")
        
        if component.width and component.height:
            output.append(f"Dimensions: {component.width}x{component.height}")
            
        return "\n".join(output)
    
    @staticmethod
    def _render_comparison(component) -> str:
        """Render a comparison component"""
        output = ["Comparison:"]
        if component.description:
            output.append(component.description)
            
        before_status = "✅ File exists" if os.path.exists(component.before_path) else "❌ File missing"
        after_status = "✅ File exists" if os.path.exists(component.after_path) else "❌ File missing"
        
        output.append(f"Before: {component.before_path} ({before_status})")
        output.append(f"After: {component.after_path} ({after_status})")
        
        if component.reference_path:
            ref_status = "✅ File exists" if os.path.exists(component.reference_path) else "❌ File missing"
            output.append(f"Reference: {component.reference_path} ({ref_status})")
            
        return "\n".join(output)
    
    @staticmethod
    def _render_metric(component) -> str:
        """Render a metric component"""
        output = [f"Metric - {component.name}:"]
        value_str = f"{component.value}{' ' + component.unit if component.unit else ''}"
        output.append(f"Value: {value_str}")
        
        if component.threshold is not None:
            threshold_str = f"{component.threshold}{' ' + component.unit if component.unit else ''}"
            output.append(f"Threshold: {threshold_str} (Better is {component.is_better})")
            
            if hasattr(component, 'passes_threshold'):
                passes = "✅ PASSES" if component.passes_threshold else "❌ FAILS"
                output.append(f"Result: {passes} threshold")
                
        return "\n".join(output)
    
    @staticmethod
    def _render_error(component) -> str:
        """Render an error component"""
        output = ["Error:"]
        if component.error_type:
            output.append(f"Type: {component.error_type}")
            
        output.append(component.message)
        
        if component.stacktrace:
            output.append("\nStacktrace:")
            # Limit stacktrace to 10 lines for readability
            stacktrace_lines = component.stacktrace.split("\n")
            if len(stacktrace_lines) > 10:
                stacktrace_lines = stacktrace_lines[:10] + ["... (truncated)"]
            output.append("\n".join(stacktrace_lines))
            
        return "\n".join(output)

class HTMLResultRenderer:
    """Renders TrustyAgentResult components in HTML format for web display"""
    
    @staticmethod
    def render_result(result: TrustyAgentResult) -> str:
        """
        Render a TrustyAgentResult as HTML for web display.
        
        Args:
            result: The TrustyAgentResult to render
            
        Returns:
            str: HTML representation of the result
        """
        html = []
        
        # Add header with appropriate status styling
        status_class = "success" if result.success else "error"
        status_icon = "✅" if result.success else "❌"
        
        html.append(f'<div class="trusty-result {status_class}">')
        html.append(f'<h3 class="result-header">{status_icon} {result.summary}</h3>')
        
        # Render each component
        for component in result.components:
            rendered = HTMLResultRenderer._render_component(component)
            if rendered:
                html.append(f'<div class="component {component.component_type}">')
                html.append(rendered)
                html.append('</div>')
        
        # Add any additional details
        if result.details:
            html.append('<div class="details">')
            html.append('<h4>Additional Details</h4>')
            html.append('<ul>')
            for key, value in result.details.items():
                if isinstance(value, str) and len(value) > 100:
                    value = value[:97] + "..."
                html.append(f'<li><strong>{key}:</strong> {value}</li>')
            html.append('</ul>')
            html.append('</div>')
        
        html.append('</div>')
        return "\n".join(html)
    
    @staticmethod
    def _render_component(component: ResultComponent) -> str:
        """Render a specific component based on its type"""
        if component.component_type == "grade":
            return HTMLResultRenderer._render_grade(component)
        elif component.component_type == "report":
            return HTMLResultRenderer._render_report(component)
        elif component.component_type == "screenshot":
            return HTMLResultRenderer._render_screenshot(component)
        elif component.component_type == "comparison":
            return HTMLResultRenderer._render_comparison(component)
        elif component.component_type == "metric":
            return HTMLResultRenderer._render_metric(component)
        elif component.component_type == "error":
            return HTMLResultRenderer._render_error(component)
        else:
            return f"<p>Unknown component type: {component.component_type}</p>"
    
    @staticmethod
    def _render_grade(component) -> str:
        """Render a grade component as HTML"""
        title = "Grade"
        if hasattr(component, 'title') and component.title:
            title = component.title
            
        # Determine grade color class
        grade_class = "grade-default"
        if component.grade in ["A", "B"]:
            grade_class = "grade-good"
        elif component.grade in ["C"]:
            grade_class = "grade-medium"
        elif component.grade in ["D", "F"]:
            grade_class = "grade-bad"
            
        html = [f'<h4>{title}</h4>']
        html.append(f'<div class="grade {grade_class}">{component.grade}</div>')
        html.append(f'<p class="grade-scale">Scale: {component.scale}</p>')
        
        if component.description:
            html.append(f'<p class="grade-description">{component.description}</p>')
            
        return "\n".join(html)
    
    @staticmethod
    def _render_report(component) -> str:
        """Render a report component as HTML"""
        title = "Report"
        if hasattr(component, 'title') and component.title:
            title = component.title
            
        html = [f'<h4>{title}</h4>']
        
        # Format content with proper line breaks
        formatted_content = component.content.replace("\n", "<br>")
        html.append(f'<div class="report-content">{formatted_content}</div>')
            
        return "\n".join(html)
    
    @staticmethod
    def _render_screenshot(component) -> str:
        """Render a screenshot component as HTML"""
        html = ['<h4>Screenshot</h4>']
        
        if component.description:
            html.append(f'<p class="screenshot-description">{component.description}</p>')
        
        # Only show the image if the file exists
        if os.path.exists(component.path):
            # Create image tag with width/height if provided
            style = ""
            if component.width and component.height:
                style = f' style="max-width:{component.width}px; max-height:{component.height}px"'
            
            html.append(f'<img src="file://{component.path}" alt="Screenshot"{style} class="screenshot-image">')
            html.append(f'<p class="screenshot-path">Path: {component.path}</p>')
        else:
            html.append(f'<p class="screenshot-missing">Screenshot file not found: {component.path}</p>')
            
        return "\n".join(html)
    
    @staticmethod
    def _render_comparison(component) -> str:
        """Render a comparison component as HTML"""
        html = ['<h4>Comparison</h4>']
        
        if component.description:
            html.append(f'<p class="comparison-description">{component.description}</p>')
        
        html.append('<div class="comparison-container">')
        
        # Before image
        html.append('<div class="comparison-before">')
        html.append('<h5>Before</h5>')
        if os.path.exists(component.before_path):
            html.append(f'<img src="file://{component.before_path}" alt="Before" class="comparison-image">')
        else:
            html.append('<p class="image-missing">Image not found</p>')
        html.append('</div>')
        
        # After image
        html.append('<div class="comparison-after">')
        html.append('<h5>After</h5>')
        if os.path.exists(component.after_path):
            html.append(f'<img src="file://{component.after_path}" alt="After" class="comparison-image">')
        else:
            html.append('<p class="image-missing">Image not found</p>')
        html.append('</div>')
        
        # Reference image (if provided)
        if component.reference_path:
            html.append('<div class="comparison-reference">')
            html.append('<h5>Reference</h5>')
            if os.path.exists(component.reference_path):
                html.append(f'<img src="file://{component.reference_path}" alt="Reference" class="comparison-image">')
            else:
                html.append('<p class="image-missing">Image not found</p>')
            html.append('</div>')
        
        html.append('</div>') # Close comparison-container
            
        return "\n".join(html)
    
    @staticmethod
    def _render_metric(component) -> str:
        """Render a metric component as HTML"""
        html = [f'<h4>Metric: {component.name}</h4>']
        
        value_str = f"{component.value}{' ' + component.unit if component.unit else ''}"
        
        # Add status class if threshold is defined
        value_class = ""
        if hasattr(component, 'passes_threshold'):
            value_class = " metric-pass" if component.passes_threshold else " metric-fail"
            
        html.append(f'<div class="metric-value{value_class}">{value_str}</div>')
        
        if component.threshold is not None:
            threshold_str = f"{component.threshold}{' ' + component.unit if component.unit else ''}"
            html.append(f'<p class="metric-threshold">Threshold: {threshold_str}</p>')
            html.append(f'<p class="metric-direction">Better is {component.is_better}</p>')
            
            if hasattr(component, 'passes_threshold'):
                status = "PASSES" if component.passes_threshold else "FAILS"
                status_class = "metric-status-pass" if component.passes_threshold else "metric-status-fail"
                html.append(f'<p class="metric-status {status_class}">{status} threshold</p>')
                
        return "\n".join(html)
    
    @staticmethod
    def _render_error(component) -> str:
        """Render an error component as HTML"""
        html = ['<h4>Error</h4>']
        
        if component.error_type:
            html.append(f'<p class="error-type">Type: {component.error_type}</p>')
            
        html.append(f'<p class="error-message">{component.message}</p>')
        
        if component.stacktrace:
            html.append('<div class="error-stacktrace">')
            html.append('<h5>Stacktrace</h5>')
            html.append('<pre>')
            # Limit stacktrace to first 20 lines for readability
            stacktrace_lines = component.stacktrace.split("\n")
            if len(stacktrace_lines) > 20:
                display_lines = stacktrace_lines[:20]
                display_lines.append("... (truncated)")
                html.append(HTMLResultRenderer._escape_html("\n".join(display_lines)))
            else:
                html.append(HTMLResultRenderer._escape_html(component.stacktrace))
            html.append('</pre>')
            html.append('</div>')
            
        return "\n".join(html)
    
    @staticmethod
    def _escape_html(text: str) -> str:
        """Escape HTML special characters in text"""
        return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;")
        )

def get_result_css() -> str:
    """
    Returns CSS styles for HTML rendering of trusty agent results
    """
    return """
    .trusty-result {
        font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
        border: 1px solid #ddd;
        border-radius: 8px;
        padding: 15px;
        margin: 15px 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    .trusty-result.success {
        border-left: 5px solid #4CAF50;
    }
    
    .trusty-result.error {
        border-left: 5px solid #F44336;
    }
    
    .result-header {
        margin-top: 0;
        color: #333;
    }
    
    .component {
        border-top: 1px solid #eee;
        padding: 10px 0;
    }
    
    .grade {
        font-size: 3em;
        font-weight: bold;
        text-align: center;
        width: 80px;
        height: 80px;
        line-height: 80px;
        border-radius: 50%;
        margin: 10px 0;
    }
    
    .grade-good {
        background-color: #4CAF50;
        color: white;
    }
    
    .grade-medium {
        background-color: #FF9800;
        color: white;
    }
    
    .grade-bad {
        background-color: #F44336;
        color: white;
    }
    
    .grade-default {
        background-color: #2196F3;
        color: white;
    }
    
    .report-content {
        background-color: #f5f5f5;
        padding: 10px;
        border-radius: 4px;
        white-space: pre-wrap;
    }
    
    .screenshot-image, .comparison-image {
        max-width: 100%;
        height: auto;
        border: 1px solid #ddd;
        margin: 10px 0;
    }
    
    .comparison-container {
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
    }
    
    .comparison-before, .comparison-after, .comparison-reference {
        flex: 1;
        min-width: 200px;
        border: 1px solid #eee;
        padding: 10px;
        border-radius: 4px;
    }
    
    .metric-value {
        font-size: 2em;
        font-weight: bold;
        margin: 10px 0;
    }
    
    .metric-pass {
        color: #4CAF50;
    }
    
    .metric-fail {
        color: #F44336;
    }
    
    .error-message {
        color: #F44336;
        font-weight: bold;
    }
    
    .error-stacktrace pre {
        background-color: #f5f5f5;
        padding: 10px;
        border-radius: 4px;
        overflow-x: auto;
        font-size: 0.9em;
    }
    
    .image-missing {
        color: #F44336;
        font-style: italic;
    }
    """

def main():
    """Demo function to show the renderers in action"""
    from tac.agents.trusty.results import TrustyAgentResult
    
    # Create a simple result
    result = TrustyAgentResult(
        success=True,
        agent_type="threejs_vision",
        summary="Visual test completed successfully"
    )
    
    # Add a grade
    result.add_grade("A", "A-F", "Excellent visual implementation")
    
    # Add a report
    result.add_report(
        "The scene contains a red cube rotating above a blue plane as expected.\n"
        "The lighting is properly configured with ambient and directional lights.\n"
        "Shadows are correctly rendered on the plane.",
        "Visual Analysis"
    )
    
    # Add a screenshot
    result.add_screenshot(
        "/tmp/screenshot.png",
        "Screenshot of the rendered Three.js scene"
    )
    
    # Add a metric
    result.add_metric(
        "Render Time", 
        16.5, 
        "ms", 
        20.0, 
        "lower"
    )
    
    # Print console rendering
    print("Console Rendering:")
    print(ConsoleResultRenderer.render_result(result))
    
    # Save HTML rendering to file
    html_output = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Trusty Agent Result Demo</title>
        <style>{get_result_css()}</style>
    </head>
    <body>
        <h1>Trusty Agent Result Demo</h1>
        {HTMLResultRenderer.render_result(result)}
    </body>
    </html>
    """
    
    with open("/tmp/trusty_result_demo.html", "w") as f:
        f.write(html_output)
    
    print("\nHTML rendering saved to /tmp/trusty_result_demo.html")

if __name__ == "__main__":
    main() 