import argparse
import ast
import sys
from pathlib import Path

class SecurityScanner(ast.NodeVisitor):
    def __init__(self):
        self.issues = []

    def visit_Call(self, node):
        # Check for subprocess.run(..., shell=True)
        if isinstance(node.func, ast.Attribute) and node.func.attr == 'run':
            if isinstance(node.func.value, ast.Name) and node.func.value.id == 'subprocess':
                self.check_subprocess(node)
        
        # Check for eval() or exec()
        if isinstance(node.func, ast.Name):
            if node.func.id in {'eval', 'exec'}:
                self.issues.append({
                    "line": node.lineno,
                    "severity": "CRITICAL",
                    "msg": f"Use of dangerous built-in '{node.func.id}' detected."
                })
        
        self.generic_visit(node)

    def check_subprocess(self, node):
        shell_true = False
        for keyword in node.keywords:
            if keyword.arg == 'shell' and isinstance(keyword.value, ast.Constant) and keyword.value.value is True:
                shell_true = True
        
        if shell_true:
            # Check if the first argument (command) is an f-string or variable (Risk)
            # vs a string literal (Safe)
            cmd_arg = node.args[0] if node.args else None
            
            # If args passed via keyword 'args'
            if not cmd_arg:
                for kw in node.keywords:
                    if kw.arg == 'args':
                        cmd_arg = kw.value
            
            if cmd_arg:
                if not isinstance(cmd_arg, (ast.Constant, ast.List)):
                    self.issues.append({
                        "line": node.lineno,
                        "severity": "HIGH",
                        "msg": "subprocess.run with shell=True and dynamic arguments. Potential Command Injection."
                    })
                elif isinstance(cmd_arg, ast.JoinedStr):
                     self.issues.append({
                        "line": node.lineno,
                        "severity": "HIGH",
                        "msg": "subprocess.run with shell=True using f-string. High Command Injection Risk."
                    })

def scan_file(filepath: Path):
    try:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source)
        scanner = SecurityScanner()
        scanner.visit(tree)
        return scanner.issues
    except Exception as e:
        return [{"line": 0, "severity": "ERROR", "msg": f"Failed to parse file: {e}"}]

def main():
    parser = argparse.ArgumentParser(description="Autonomous DNA Security Scanner")
    parser.add_argument("target", help="File or directory to scan")
    args = parser.parse_args()
    
    target_path = Path(args.target)
    all_issues = []
    
    if target_path.is_file():
        issues = scan_file(target_path)
        for i in issues:
            i['file'] = str(target_path)
            all_issues.append(i)
    else:
        for f in target_path.glob("**/*.py"):
            issues = scan_file(f)
            for i in issues:
                i['file'] = str(f)
                all_issues.append(i)
                
    if all_issues:
        print(f"\n❌ SECURITY ISSUES FOUND ({len(all_issues)}):")
        for i in all_issues:
            print(f"  [{i['severity']}] {i['file']}:{i['line']} - {i['msg']}")
        sys.exit(1)
    else:
        print("\n✅ Security Scan Passed: No obvious vulnerabilities detected.")
        sys.exit(0)

if __name__ == "__main__":
    main()
