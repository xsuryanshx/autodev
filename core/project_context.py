"""Project context loader for AutoDev - manages project-specific CLAUDE.md."""
import os
from pathlib import Path
from typing import Optional, Dict, Any


# Default project context template
DEFAULT_PROJECT_CONTEXT = """# Project Context

This file provides context for AI agents working on this project.

## Project Overview
- **Name**: {project_name}
- **Language**: {language}
- **Framework**: {framework}

## Key Files
{main_files}

## Architecture
{architecture}

## Notes
- Add project-specific notes here
- Include important conventions
- Document API endpoints, key configs, etc.
"""


class ProjectContextLoader:
    """
    Manages project-specific context for AI agents.
    
    Checks for CLAUDE.md in project root, creates from template if missing.
    """
    
    CLAUDE_MD = "CLAUDE.md"
    
    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)
        self.claude_md_path = self.repo_path / self.CLAUDE_MD
    
    def load_context(self) -> Optional[str]:
        """Load existing CLAUDE.md if it exists."""
        if self.claude_md_path.exists():
            return self.claude_md_path.read_text()
        return None
    
    def has_context(self) -> bool:
        """Check if CLAUDE.md exists."""
        return self.claude_md_path.exists()
    
    def create_default_context(self, project_info: Dict[str, Any]) -> str:
        """Create default CLAUDE.md from project info."""
        # Format main files list
        main_files = ""
        if project_info.get("main_files"):
            files = project_info["main_files"][:10]  # Limit to 10
            main_files = "\n".join(f"- {f}" for f in files)
        else:
            main_files = "- (No main files detected)"
        
        # Build context
        context = DEFAULT_PROJECT_CONTEXT.format(
            project_name=project_info.get("name", "Project"),
            language=project_info.get("language", "Unknown"),
            framework=project_info.get("framework", "N/A"),
            main_files=main_files,
            architecture=project_info.get("architecture", "See README")
        )
        
        # Write to file
        self.claude_md_path.write_text(context)
        
        return context
    
    def get_or_create_context(self, project_info: Dict[str, Any]) -> str:
        """Get existing context or create new one."""
        existing = self.load_context()
        if existing:
            return existing
        
        return self.create_default_context(project_info)
    
    def detect_project_info(self) -> Dict[str, Any]:
        """Detect project information from codebase."""
        info = {
            "name": self.repo_path.name,
            "language": "Unknown",
            "framework": "N/A",
            "main_files": [],
            "architecture": "See README.md"
        }
        
        # Detect language from files
        py_files = list(self.repo_path.rglob("*.py"))
        ts_files = list(self.repo_path.rglob("*.ts")) + list(self.repo_path.rglob("*.tsx"))
        js_files = list(self.repo_path.rglob("*.js"))
        
        if py_files:
            info["language"] = "Python"
            # Find main entry points
            for f in ["main.py", "app.py", "server.py", "api.py", "__main__.py"]:
                matches = list(self.repo_path.rglob(f))
                if matches:
                    info["main_files"].extend([str(m.relative_to(self.repo_path)) for m in matches[:2]])
            
            # Check for common frameworks
            if (self.repo_path / "pyproject.toml").exists() or (self.repo_path / "setup.py").exists():
                info["main_files"].append("pyproject.toml")
            
            # Check for FastAPI
            if any("fastapi" in f.read_text()[:500] for f in py_files if f.stat().st_size < 100000):
                info["framework"] = "FastAPI"
            elif any("flask" in f.read_text()[:500] for f in py_files if f.stat().st_size < 100000):
                info["framework"] = "Flask"
            elif any("django" in f.read_text()[:500] for f in py_files if f.stat().st_size < 100000):
                info["framework"] = "Django"
        
        if ts_files or js_files:
            info["language"] = "TypeScript/JavaScript"
            for f in ["index.ts", "main.ts", "app.ts", "server.ts"]:
                matches = list(self.repo_path.rglob(f))
                if matches:
                    info["main_files"].extend([str(m.relative_to(self.repo_path)) for m in matches[:2]])
            
            if (self.repo_path / "package.json").exists():
                info["main_files"].append("package.json")
                
            if any("next" in f.read_text()[:500] for f in ts_files + js_files if f.stat().st_size < 100000):
                info["framework"] = "Next.js"
            elif any("express" in f.read_text()[:500] for f in ts_files + js_files if f.stat().st_size < 100000):
                info["framework"] = "Express"
        
        return info
