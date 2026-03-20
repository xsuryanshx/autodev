"""Skill handlers for subagent execution."""
import logging
from pathlib import Path
from typing import Dict, Any, Optional

from core.task_context import TaskContext


class CoderHandler:
    def __init__(self):
        self.logger = logging.getLogger("autodev.coder_handler")

    def execute(self, context: TaskContext) -> Dict[str, Any]:
        self.logger.info(f"[{context.task_id}] Starting coder task: {context.description}")

        try:
            task_context = context.context or {}
            prompt = getattr(context, 'prompt', context.description)
            result = self._execute_impl(context, prompt, task_context)
            context.set_result(result)
            return result
        except Exception as e:
            self.logger.error(f"[{context.task_id}] Coder task failed: {e}")
            context.set_error(str(e))
            return {"status": "failed", "error": str(e)}

    def _execute_impl(self, context: TaskContext, prompt: str, task_context: Dict[str, Any]) -> Dict[str, Any]:
        self.logger.warning(f"[{context.task_id}] _execute_impl called but not yet connected to Claude Code")
        return {
            "status": "completed",
            "message": f"CoderHandler stub for task {context.task_id}",
            "prompt_summary": prompt[:200],
        }


class ResearcherHandler:
    def __init__(self):
        self.logger = logging.getLogger("autodev.researcher_handler")

    def execute(self, context: TaskContext) -> Dict[str, Any]:
        self.logger.info(f"[{context.task_id}] Starting researcher task: {context.description}")

        try:
            task_context = context.context or {}
            prompt = getattr(context, 'prompt', context.description)
            result = self._research(context, prompt, task_context)
            context.set_result(result)
            return result
        except Exception as e:
            self.logger.error(f"[{context.task_id}] Researcher task failed: {e}")
            context.set_error(str(e))
            return {"status": "failed", "error": str(e)}

    def _research(self, context: TaskContext, prompt: str, task_context: Dict[str, Any]) -> Dict[str, Any]:
        self.logger.warning(f"[{context.task_id}] _research called but not yet connected to web search")
        return {
            "status": "completed",
            "message": f"ResearcherHandler stub for task {context.task_id}",
            "findings": [],
        }