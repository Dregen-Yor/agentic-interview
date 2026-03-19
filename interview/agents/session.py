"""
InterviewSession — 面试会话数据类
维护单次面试的运行时状态，包括 Q&A 历史和评分追踪。
"""

from typing import Dict, Any, List, Optional
from datetime import datetime


class InterviewSession:
    """面试会话类 — 保存单次面试的运行时状态"""

    def __init__(self, session_id: str, candidate_name: str, resume_data: Dict[str, Any], coordinator):
        self.session_id = session_id
        self.candidate_name = candidate_name
        self.resume_data = resume_data
        self.coordinator = coordinator
        self.start_time = datetime.now()
        self.qa_history: List[Dict[str, Any]] = []
        self.current_question: Optional[Dict[str, Any]] = None
        self.question_data: Optional[Dict[str, Any]] = None
        self.is_active = True

        # 简历结构化解析结果（由 ResumeParser 填充）
        self.parsed_profile: Optional[Dict[str, Any]] = None

        # 评分追踪（替代旧 InterviewMemory 的 score_history）
        self._score_list: List[int] = []

    def add_score(self, score: int) -> None:
        """记录一轮评分"""
        self._score_list.append(score)

    def get_average_score(self) -> float:
        """获取当前平均分"""
        if not self._score_list:
            return 0.0
        return sum(self._score_list) / len(self._score_list)

    @property
    def score_list(self) -> List[int]:
        """只读访问评分列表"""
        return list(self._score_list)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "session_id": self.session_id,
            "candidate_name": self.candidate_name,
            "start_time": self.start_time.isoformat(),
            "total_questions": len(self.qa_history),
            "is_active": self.is_active,
            "current_question": self.current_question,
            "average_score": self.get_average_score(),
            "parsed_profile": self.parsed_profile,
        }
