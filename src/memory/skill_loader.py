"""Skill loader utility for solve memory items."""

import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class SkillLoader:
    """
    Loads skill snippets from the skills/ directory.
    
    Skills are markdown files with structured format.
    """

    def __init__(self, skills_dir: Optional[Path] = None):
        if skills_dir is None:
            # Default to solvita/skills/
            self.skills_dir = Path(__file__).parent.parent.parent / "skills"
        else:
            self.skills_dir = Path(skills_dir)
        
        self._cache: Dict[str, str] = {}

    def load_skill(self, skill_path: str) -> Optional[str]:
        """
        Load a skill snippet from file.
        
        Args:
            skill_path: Relative path from skills/ directory (e.g., "quick_sort.md")
        
        Returns:
            Full content of the skill file, or None if not found.
        """
        if skill_path in self._cache:
            return self._cache[skill_path]
        
        full_path = self.skills_dir / skill_path
        
        if not full_path.exists():
            logger.warning(f"Skill file not found: {full_path}")
            return None
        
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
            self._cache[skill_path] = content
            logger.debug(f"Loaded skill: {skill_path}")
            return content
        except Exception as e:
            logger.error(f"Failed to load skill {skill_path}: {e}")
            return None

    def load_skills_for_item(self, item_payload: dict) -> str:
        """
        Load all skills referenced in a solve item's payload.
        
        Args:
            item_payload: The payload dict from a solve MemoryItem
        
        Returns:
            Formatted string with all skill snippets.
        """
        skills = item_payload.get("skills", [])
        if not skills:
            return ""
        
        lines = ["\n[Referenced Skills]"]
        
        for skill_ref in skills:
            if isinstance(skill_ref, dict):
                skill_id = skill_ref.get("skill_id", "")
                skill_path = skill_ref.get("path", "")
            else:
                # Fallback: treat as path string
                skill_id = ""
                skill_path = str(skill_ref)
            
            content = self.load_skill(skill_path)
            if content:
                lines.append(f"\n### Skill: {skill_id or skill_path}")
                lines.append(content)
        
        return "\n".join(lines)
