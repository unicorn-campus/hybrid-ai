"""주제만 주면 교재(마크다운)와 슬라이드(Marp·HTML·PPTX)를 스스로 계획·제작·검토하는 에이전트."""
from .config import Settings
from .orchestrator import CoursewareAgent

__all__ = ["CoursewareAgent", "Settings"]
