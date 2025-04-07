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