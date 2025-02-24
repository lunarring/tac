import ast

def extract_code_definitions(code: str):
    """
    Extracts top-level function and class definitions from Python code along with their starting and ending line numbers.
    
    Args:
        code (str): Python source code.
        
    Returns:
        list of dict: A list of dictionaries each containing:
            - 'type': 'function' or 'class'
            - 'name': Name of the function or class
            - 'start_line': The starting line number of the definition
            - 'end_line': The ending line number of the definition
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    
    definitions = []
    
    # Iterate over all top-level nodes
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Use end_lineno which should be available in Python 3.8+
            definitions.append({
                'type': 'function',
                'name': node.name,
                'start_line': node.lineno,
                'end_line': getattr(node, "end_lineno", node.lineno)
            })
        elif isinstance(node, ast.ClassDef):
            definitions.append({
                'type': 'class',
                'name': node.name,
                'start_line': node.lineno,
                'end_line': getattr(node, "end_lineno", node.lineno)
            })
    
    return definitions