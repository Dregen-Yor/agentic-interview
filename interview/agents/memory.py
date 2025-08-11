"""
记忆管理系统
提供结构化的面试记忆存储和检索功能
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
import json


class InterviewMemory:
    """面试记忆管理器"""
    
    def __init__(self, candidate_name: str):
        self.candidate_name = candidate_name
        self.qa_history = []  # 问答历史
        self.score_history = []  # 评分历史
        self.context_memory = {}  # 上下文记忆
        self.created_at = datetime.now()
        
    def add_question_answer(self, question: str, answer: str, timestamp: datetime = None):
        """添加问答对"""
        if timestamp is None:
            timestamp = datetime.now()
        
        self.qa_history.append({
            "question": question,
            "answer": answer,
            "timestamp": timestamp,
            "question_id": len(self.qa_history)
        })
    
    def add_score(self, question_id: int, score: int, reasoning: str = ""):
        """添加评分"""
        self.score_history.append({
            "question_id": question_id,
            "score": score,
            "reasoning": reasoning,
            "timestamp": datetime.now()
        })
    
    def get_recent_qa(self, count: int = 5) -> List[Dict[str, Any]]:
        """获取最近的问答记录"""
        return self.qa_history[-count:] if self.qa_history else []
    
    def get_all_qa(self) -> List[Dict[str, Any]]:
        """获取所有问答记录"""
        return self.qa_history
    
    def get_scores(self) -> List[Dict[str, Any]]:
        """获取所有评分记录"""
        return self.score_history
    
    def get_average_score(self) -> float:
        """获取平均分"""
        if not self.score_history:
            return 0.0
        return sum(s["score"] for s in self.score_history) / len(self.score_history)
    
    def set_context(self, key: str, value: Any):
        """设置上下文信息"""
        self.context_memory[key] = value
    
    def get_context(self, key: str, default: Any = None) -> Any:
        """获取上下文信息"""
        return self.context_memory.get(key, default)
    
    def get_formatted_history(self, include_scores: bool = True) -> str:
        """获取格式化的历史记录"""
        formatted = f"候选人: {self.candidate_name}\n面试开始时间: {self.created_at}\n\n"
        
        for i, qa in enumerate(self.qa_history):
            formatted += f"问题 {i+1}: {qa['question']}\n"
            formatted += f"回答: {qa['answer']}\n"
            
            if include_scores:
                # 找对应的评分
                score_record = next((s for s in self.score_history if s["question_id"] == i), None)
                if score_record:
                    formatted += f"评分: {score_record['score']}/10\n"
                    if score_record['reasoning']:
                        formatted += f"评分理由: {score_record['reasoning']}\n"
            
            formatted += "\n"
        
        if include_scores and self.score_history:
            formatted += f"当前平均分: {self.get_average_score():.2f}/10\n"
        
        return formatted
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "candidate_name": self.candidate_name,
            "qa_history": self.qa_history,
            "score_history": self.score_history,
            "context_memory": self.context_memory,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
            "average_score": self.get_average_score()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'InterviewMemory':
        """从字典创建实例"""
        memory = cls(data["candidate_name"])
        memory.qa_history = data.get("qa_history", [])
        memory.score_history = data.get("score_history", [])
        memory.context_memory = data.get("context_memory", {})
        
        created_at_str = data.get("created_at")
        if created_at_str:
            try:
                memory.created_at = datetime.fromisoformat(created_at_str)
            except:
                memory.created_at = datetime.now()
        
        return memory


class MemoryManager:
    """记忆管理器，管理多个面试会话的记忆"""
    
    def __init__(self):
        self.memories = {}  # session_id -> InterviewMemory
    
    def create_memory(self, session_id: str, candidate_name: str) -> InterviewMemory:
        """创建新的面试记忆"""
        memory = InterviewMemory(candidate_name)
        self.memories[session_id] = memory
        return memory
    
    def get_memory(self, session_id: str) -> Optional[InterviewMemory]:
        """获取面试记忆"""
        return self.memories.get(session_id)
    
    def remove_memory(self, session_id: str):
        """删除面试记忆"""
        if session_id in self.memories:
            del self.memories[session_id]
    
    def get_all_memories(self) -> Dict[str, InterviewMemory]:
        """获取所有记忆"""
        return self.memories.copy()