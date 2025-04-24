from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Union
import json
import os

@dataclass
class ResultComponent:
    """Base class for all result components"""
    component_type: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert component to dictionary representation"""
        return {"component_type": self.component_type}
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ResultComponent':
        """Create component from dictionary representation"""
        return cls(**data)

@dataclass
class GradeComponent(ResultComponent):
    """Component for representing a grade"""
    grade: str
    scale: str = "A-F"
    description: str = ""
    
    def __init__(self, grade: str, scale: str = "A-F", description: str = ""):
        super().__init__(component_type="grade")
        self.grade = grade
        self.scale = scale
        self.description = description
    
    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            "grade": self.grade,
            "scale": self.scale,
            "description": self.description
        })
        return data

@dataclass
class ReportComponent(ResultComponent):
    """Component for representing a text report"""
    content: str
    title: str = ""
    
    def __init__(self, content: str, title: str = ""):
        super().__init__(component_type="report")
        self.content = content
        self.title = title
    
    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            "content": self.content,
            "title": self.title
        })
        return data

@dataclass
class ScreenshotComponent(ResultComponent):
    """Component for representing a screenshot"""
    path: str
    description: str = ""
    width: Optional[int] = None
    height: Optional[int] = None
    
    def __init__(self, path: str, description: str = "", width: Optional[int] = None, height: Optional[int] = None):
        super().__init__(component_type="screenshot")
        self.path = path
        self.description = description
        self.width = width
        self.height = height
    
    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            "path": self.path,
            "description": self.description
        })
        if self.width is not None:
            data["width"] = self.width
        if self.height is not None:
            data["height"] = self.height
        
        # Add file existence check
        data["exists"] = os.path.exists(self.path)
        return data

@dataclass
class ComparisonComponent(ResultComponent):
    """Component for representing a comparison between images"""
    before_path: str
    after_path: str
    reference_path: Optional[str] = None
    description: str = ""
    
    def __init__(self, before_path: str, after_path: str, reference_path: Optional[str] = None, description: str = ""):
        super().__init__(component_type="comparison")
        self.before_path = before_path
        self.after_path = after_path
        self.reference_path = reference_path
        self.description = description
    
    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            "before_path": self.before_path,
            "after_path": self.after_path,
            "description": self.description,
            "before_exists": os.path.exists(self.before_path),
            "after_exists": os.path.exists(self.after_path)
        })
        if self.reference_path:
            data["reference_path"] = self.reference_path
            data["reference_exists"] = os.path.exists(self.reference_path)
        return data

@dataclass
class MetricComponent(ResultComponent):
    """Component for representing a metric value"""
    name: str
    value: Union[float, int, str]
    unit: str = ""
    threshold: Optional[Union[float, int]] = None
    is_better: str = "lower"  # "lower" or "higher"
    
    def __init__(self, name: str, value: Union[float, int, str], unit: str = "", 
                 threshold: Optional[Union[float, int]] = None, is_better: str = "lower"):
        super().__init__(component_type="metric")
        self.name = name
        self.value = value
        self.unit = unit
        self.threshold = threshold
        self.is_better = is_better
    
    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "is_better": self.is_better
        })
        if self.threshold is not None:
            data["threshold"] = self.threshold
            # Determine if the metric passes the threshold
            if self.is_better == "lower":
                data["passes_threshold"] = float(self.value) <= float(self.threshold)
            else:
                data["passes_threshold"] = float(self.value) >= float(self.threshold)
        return data

@dataclass
class ErrorComponent(ResultComponent):
    """Component for representing an error"""
    message: str
    error_type: str = ""
    stacktrace: Optional[str] = None
    
    def __init__(self, message: str, error_type: str = "", stacktrace: Optional[str] = None):
        super().__init__(component_type="error")
        self.message = message
        self.error_type = error_type
        self.stacktrace = stacktrace
    
    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            "message": self.message,
            "error_type": self.error_type
        })
        if self.stacktrace:
            data["stacktrace"] = self.stacktrace
        return data

@dataclass
class TrustyAgentResult:
    """Main result class for trusty agents"""
    success: bool
    agent_type: str
    summary: str
    components: List[ResultComponent] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)
    
    def add_component(self, component: ResultComponent) -> 'TrustyAgentResult':
        """Add a component to the result"""
        self.components.append(component)
        return self
    
    def add_grade(self, grade: str, scale: str = "A-F", description: str = "") -> 'TrustyAgentResult':
        """Add a grade component"""
        self.add_component(GradeComponent(grade, scale, description))
        return self
    
    def add_report(self, content: str, title: str = "") -> 'TrustyAgentResult':
        """Add a report component"""
        self.add_component(ReportComponent(content, title))
        return self
    
    def add_screenshot(self, path: str, description: str = "", 
                      width: Optional[int] = None, height: Optional[int] = None) -> 'TrustyAgentResult':
        """Add a screenshot component"""
        self.add_component(ScreenshotComponent(path, description, width, height))
        return self
    
    def add_comparison(self, before_path: str, after_path: str, 
                       reference_path: Optional[str] = None, 
                       description: str = "") -> 'TrustyAgentResult':
        """Add a comparison component"""
        self.add_component(ComparisonComponent(before_path, after_path, reference_path, description))
        return self
    
    def add_metric(self, name: str, value: Union[float, int, str], 
                  unit: str = "", threshold: Optional[Union[float, int]] = None, 
                  is_better: str = "lower") -> 'TrustyAgentResult':
        """Add a metric component"""
        self.add_component(MetricComponent(name, value, unit, threshold, is_better))
        return self
    
    def add_error(self, message: str, error_type: str = "", 
                 stacktrace: Optional[str] = None) -> 'TrustyAgentResult':
        """Add an error component"""
        self.add_component(ErrorComponent(message, error_type, stacktrace))
        return self
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary representation"""
        return {
            "success": self.success,
            "agent_type": self.agent_type,
            "summary": self.summary,
            "details": self.details,
            "components": [component.to_dict() for component in self.components]
        }
    
    def to_json(self, indent: int = 2) -> str:
        """Convert result to JSON string"""
        return json.dumps(self.to_dict(), indent=indent)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TrustyAgentResult':
        """Create result from dictionary representation"""
        components_data = data.pop("components", [])
        result = cls(**{k: v for k, v in data.items() if k != "components"})
        
        # Create components from data
        for component_data in components_data:
            component_type = component_data.get("component_type")
            if component_type == "grade":
                result.add_grade(
                    component_data.get("grade", ""),
                    component_data.get("scale", "A-F"),
                    component_data.get("description", "")
                )
            elif component_type == "report":
                result.add_report(
                    component_data.get("content", ""),
                    component_data.get("title", "")
                )
            elif component_type == "screenshot":
                result.add_screenshot(
                    component_data.get("path", ""),
                    component_data.get("description", ""),
                    component_data.get("width"),
                    component_data.get("height")
                )
            elif component_type == "comparison":
                result.add_comparison(
                    component_data.get("before_path", ""),
                    component_data.get("after_path", ""),
                    component_data.get("reference_path"),
                    component_data.get("description", "")
                )
            elif component_type == "metric":
                result.add_metric(
                    component_data.get("name", ""),
                    component_data.get("value", 0),
                    component_data.get("unit", ""),
                    component_data.get("threshold"),
                    component_data.get("is_better", "lower")
                )
            elif component_type == "error":
                result.add_error(
                    component_data.get("message", ""),
                    component_data.get("error_type", ""),
                    component_data.get("stacktrace")
                )
        
        return result
    
    @staticmethod
    def from_legacy_result(success: bool, agent_type: str, error_analysis: str, failure_type: str) -> 'TrustyAgentResult':
        """Create a TrustyAgentResult from legacy result tuple"""
        summary = "Check passed successfully" if success else f"Check failed: {failure_type}"
        result = TrustyAgentResult(success=success, agent_type=agent_type, summary=summary)
        
        if not success and error_analysis:
            result.add_report(error_analysis, "Error Analysis")
            
        return result 

# Renderer classes moved from ui.py

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
                html.append(f'<li><strong>{key}:</strong> {HTMLResultRenderer._escape_html(str(value))}</li>')
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
    def _escape_html(text: str) -> str:
        """Escape HTML special characters"""
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#39;")
    
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
            html.append(f'<p class="grade-description">{HTMLResultRenderer._escape_html(component.description)}</p>')
            
        return "\n".join(html)
    
    @staticmethod
    def _render_report(component) -> str:
        """Render a report component as HTML"""
        title = "Report"
        if hasattr(component, 'title') and component.title:
            title = component.title
            
        content = component.content.replace("\n", "<br>")
            
        html = [f'<h4>{title}</h4>']
        
        # Use a pre tag for code-like content or render as paragraphs
        if "```" in content:
            # Content contains code blocks, render with special handling
            in_code_block = False
            formatted_content = []
            
            for line in content.split("<br>"):
                if line.strip().startswith("```"):
                    if in_code_block:
                        formatted_content.append("</code></pre>")
                        in_code_block = False
                    else:
                        # Extract language if specified
                        lang = line.strip().replace("```", "").strip()
                        lang_class = f"language-{lang}" if lang else "code"
                        formatted_content.append(f'<pre><code class="{lang_class}">')
                        in_code_block = True
                else:
                    if in_code_block:
                        formatted_content.append(HTMLResultRenderer._escape_html(line))
                    else:
                        formatted_content.append(f"<p>{HTMLResultRenderer._escape_html(line)}</p>")
            
            # Ensure code blocks are properly closed
            if in_code_block:
                formatted_content.append("</code></pre>")
                
            html.append("\n".join(formatted_content))
        else:
            # Simple content, just escape HTML
            html.append(f'<div class="report-content">{HTMLResultRenderer._escape_html(content)}</div>')
        
        return "\n".join(html)
    
    @staticmethod
    def _render_screenshot(component) -> str:
        """Render a screenshot component as HTML"""
        html = [f'<h4>Screenshot</h4>']
        
        if component.description:
            html.append(f'<p>{HTMLResultRenderer._escape_html(component.description)}</p>')
        
        # Check if file exists
        if os.path.exists(component.path):
            # Create a relative path for display in the browser
            rel_path = os.path.basename(component.path)
            html.append(f'<div class="screenshot">')
            html.append(f'<img src="{rel_path}" alt="Screenshot" class="screenshot-img" />')
            html.append(f'</div>')
            
            if component.width and component.height:
                html.append(f'<p class="screenshot-info">Dimensions: {component.width}x{component.height}</p>')
        else:
            html.append(f'<div class="error-msg">Screenshot file not found: {component.path}</div>')
        
        return "\n".join(html)
    
    @staticmethod
    def _render_comparison(component) -> str:
        """Render a comparison component as HTML"""
        html = [f'<h4>Visual Comparison</h4>']
        
        if component.description:
            html.append(f'<p>{HTMLResultRenderer._escape_html(component.description)}</p>')
        
        html.append(f'<div class="comparison-container">')
        
        # Before image
        html.append(f'<div class="comparison-item">')
        html.append(f'<h5>Before</h5>')
        if os.path.exists(component.before_path):
            before_rel_path = os.path.basename(component.before_path)
            html.append(f'<img src="{before_rel_path}" alt="Before" class="comparison-img" />')
        else:
            html.append(f'<div class="error-msg">Image not found</div>')
        html.append(f'</div>')
        
        # After image
        html.append(f'<div class="comparison-item">')
        html.append(f'<h5>After</h5>')
        if os.path.exists(component.after_path):
            after_rel_path = os.path.basename(component.after_path)
            html.append(f'<img src="{after_rel_path}" alt="After" class="comparison-img" />')
        else:
            html.append(f'<div class="error-msg">Image not found</div>')
        html.append(f'</div>')
        
        # Reference image (if provided)
        if component.reference_path:
            html.append(f'<div class="comparison-item">')
            html.append(f'<h5>Reference</h5>')
            if os.path.exists(component.reference_path):
                ref_rel_path = os.path.basename(component.reference_path)
                html.append(f'<img src="{ref_rel_path}" alt="Reference" class="comparison-img" />')
            else:
                html.append(f'<div class="error-msg">Image not found</div>')
            html.append(f'</div>')
        
        html.append(f'</div>') # Close comparison-container
        
        return "\n".join(html)
    
    @staticmethod
    def _render_metric(component) -> str:
        """Render a metric component as HTML"""
        html = [f'<h4>Metric: {HTMLResultRenderer._escape_html(component.name)}</h4>']
        
        # Format value with unit
        value_str = f"{component.value}{' ' + component.unit if component.unit else ''}"
        
        # Determine if the metric has a threshold and passes it
        has_threshold = component.threshold is not None
        passes_threshold = False
        if has_threshold and hasattr(component, 'passes_threshold'):
            passes_threshold = component.passes_threshold
        
        # Set status class based on threshold
        status_class = ""
        if has_threshold:
            status_class = "metric-pass" if passes_threshold else "metric-fail"
        
        html.append(f'<div class="metric-value {status_class}">{HTMLResultRenderer._escape_html(value_str)}</div>')
        
        if has_threshold:
            # Format threshold with unit
            threshold_str = f"{component.threshold}{' ' + component.unit if component.unit else ''}"
            threshold_desc = f"Better is {component.is_better}" if component.is_better else ""
            
            html.append(f'<div class="metric-threshold">')
            html.append(f'Threshold: {HTMLResultRenderer._escape_html(threshold_str)} ({threshold_desc})')
            html.append(f'</div>')
            
            # Add pass/fail indicator
            result_text = "PASSES threshold" if passes_threshold else "FAILS threshold"
            html.append(f'<div class="metric-result {status_class}">{result_text}</div>')
        
        return "\n".join(html)
    
    @staticmethod
    def _render_error(component) -> str:
        """Render an error component as HTML"""
        html = [f'<div class="error-component">']
        
        if component.error_type:
            html.append(f'<h4>Error: {HTMLResultRenderer._escape_html(component.error_type)}</h4>')
        else:
            html.append(f'<h4>Error</h4>')
        
        html.append(f'<div class="error-message">{HTMLResultRenderer._escape_html(component.message)}</div>')
        
        if component.stacktrace:
            html.append(f'<details class="error-stacktrace">')
            html.append(f'<summary>Stacktrace</summary>')
            html.append(f'<pre>{HTMLResultRenderer._escape_html(component.stacktrace)}</pre>')
            html.append(f'</details>')
        
        html.append(f'</div>')
        return "\n".join(html)

def get_result_css() -> str:
    """Return CSS styles for rendering TrustyAgentResult in HTML"""
    return """
    .trusty-result {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        border: 1px solid #e1e4e8;
        border-radius: 6px;
        padding: 16px;
        margin: 10px 0;
        max-width: 100%;
        overflow: auto;
    }
    
    .trusty-result.success {
        border-left: 4px solid #2cbe4e;
    }
    
    .trusty-result.error {
        border-left: 4px solid #cb2431;
    }
    
    .trusty-result .result-header {
        margin-top: 0;
        padding-bottom: 8px;
        border-bottom: 1px solid #e1e4e8;
    }
    
    .trusty-result .component {
        padding: 12px 0;
        border-bottom: 1px solid #e1e4e8;
    }
    
    .trusty-result .component:last-child {
        border-bottom: none;
    }
    
    .trusty-result .component h4 {
        margin-top: 0;
        margin-bottom: 8px;
    }
    
    .trusty-result .grade {
        font-size: 32px;
        font-weight: bold;
        display: inline-block;
        padding: 4px 16px;
        border-radius: 4px;
        margin: 8px 0;
    }
    
    .trusty-result .grade-good {
        background-color: #2cbe4e;
        color: white;
    }
    
    .trusty-result .grade-medium {
        background-color: #f9c513;
        color: black;
    }
    
    .trusty-result .grade-bad {
        background-color: #cb2431;
        color: white;
    }
    
    .trusty-result .grade-default {
        background-color: #6f42c1;
        color: white;
    }
    
    .trusty-result .report-content {
        white-space: pre-wrap;
        font-family: monospace;
        background-color: #f6f8fa;
        padding: 12px;
        border-radius: 4px;
        overflow-x: auto;
    }
    
    .trusty-result pre {
        margin: 0;
        padding: 12px;
        background-color: #f6f8fa;
        border-radius: 4px;
        overflow-x: auto;
    }
    
    .trusty-result .screenshot-img,
    .trusty-result .comparison-img {
        max-width: 100%;
        border: 1px solid #e1e4e8;
        border-radius: 4px;
    }
    
    .trusty-result .comparison-container {
        display: flex;
        flex-wrap: wrap;
        gap: 16px;
    }
    
    .trusty-result .comparison-item {
        flex: 1;
        min-width: 200px;
    }
    
    .trusty-result .comparison-item h5 {
        margin-top: 0;
        margin-bottom: 8px;
    }
    
    .trusty-result .error-msg {
        color: #cb2431;
        padding: 8px;
        background-color: #ffeef0;
        border-radius: 4px;
    }
    
    .trusty-result .metric-value {
        font-size: 24px;
        font-weight: bold;
        margin: 8px 0;
    }
    
    .trusty-result .metric-pass {
        color: #2cbe4e;
    }
    
    .trusty-result .metric-fail {
        color: #cb2431;
    }
    
    .trusty-result .metric-threshold,
    .trusty-result .metric-result {
        margin: 4px 0;
    }
    
    .trusty-result .error-component {
        background-color: #ffeef0;
        padding: 12px;
        border-radius: 4px;
    }
    
    .trusty-result .error-component h4 {
        color: #cb2431;
        margin-top: 0;
    }
    
    .trusty-result .error-stacktrace {
        margin-top: 12px;
    }
    
    .trusty-result .error-stacktrace summary {
        cursor: pointer;
        padding: 4px 0;
    }
    
    .trusty-result .details {
        margin-top: 16px;
        padding-top: 8px;
        border-top: 1px solid #e1e4e8;
    }
    
    .trusty-result .details h4 {
        margin-top: 0;
        margin-bottom: 8px;
    }
    
    .trusty-result .details ul {
        margin: 0;
        padding-left: 20px;
    }
    """ 