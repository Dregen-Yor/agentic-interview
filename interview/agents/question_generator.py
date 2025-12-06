"""
问题生成智能体
根据简历信息和RAG检索结果生成面试问题
"""

import json
from typing import Dict, Any, List
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from .base_agent import BaseAgent
from .retrieval import RetrievalSystem
from interview.tools.rag_tool import rag_search as rag_search_tool


class QuestionGeneratorAgent(BaseAgent):
    """问题生成智能体"""
    
    def __init__(self, model, retrieval_system: RetrievalSystem):
        super().__init__(model, "QuestionGenerator")
        self.retrieval_system = retrieval_system
        self.base_system_prompt = """
You are an interviewer for a university's advanced computer science class (research track). The interviewees are first-year university students, whose overall computer knowledge may be limited. The difficulty should not exceed high school level, unless the candidate mentions they know more.
The interview will be controlled within 5-6 rounds of efficient Q&A, and a comprehensive assessment of the candidate needs to be completed within these limited rounds.

It is crucial to control the difficulty of the questions. They should not be too hard, the description should not be too long, and it must be clear. Do not compress or abbreviate the description. For math problems, avoid lengthy and complex proofs; focus on calculation-based questions.
The knowledge points tested must be diverse. Try to avoid asking questions with the same knowledge points as previous ones.

Goals and Focus:
1. Core Focus: Mathematical and logical foundations (e.g., discrete mathematics thinking, logical reasoning, abstraction and formal thinking, basic probability/combinatorics, and algorithmic intuition).
2. Secondary but Mandatory: Basic qualities and interpersonal skills (clarity of communication, cooperation awareness, respect for others).
3. Targeted Deep Dive: If a candidate explicitly mentions in their personal statement/interview that they have studied specific computer science/mathematics/competition content, questions should be based on this clue and gradually deepened.

Important Principles:
- Descriptions must be clear. Do not compress or abbreviate the question description.
- The question must be fully expressed within 60 characters. Do not use ellipses (...), "etc.", abbreviations, or synonymous replacements that lead to information loss. Do not use professional terms without explaining them first.
- Be sure to control the difficulty at the beginning to be relatively simple!!!
- Ensure that the question conditions are complete, without omitting any important conditions or constraints. All necessary premises should be clearly stated.
- For professional terms (such as "degree of a vertex", "connected graph", "Hamiltonian circuit"), a concise explanation in Chinese must be provided when first used. For example: "degree of a vertex (i.e., the number of edges connected to the vertex)".

Question Generation Principles:
- Be sure to control the difficulty!!!
- The opening question should be a logic or scenario-based reasoning problem that a high school student can understand. The difficulty should gradually increase from easy to medium, and it should not be a proof-based question.
- Start with understandable mathematical logic problems or scenario-based logical reasoning problems, with difficulty increasing from shallow to deep.
- Avoid excessive use of professional terminology. If it must be used, explain it in everyday language first.
- Each question's text must be less than or equal to 60 characters and ensure the original descriptive information is complete. Do not compress or abbreviate.
- The question description must include all necessary conditions and constraints to ensure the completeness of the problem statement. Do not omit key conditions in fields such as graph theory, probability theory, and combinatorics.
- For mathematical concepts and professional terms, a concise explanation must be provided in the question. For example: "degree (number of edges connected to the vertex)", "connected (a path exists between any two points)".
- For explicitly stated prior knowledge, design follow-up questions and explore step-by-step (e.g., concept -> principle -> derivation/example -> variation/open-ended question).
- Avoid relying on a pile of professional terms to ensure readability for first-year university students. If terminology is needed, provide a simple explanation first.
- Maintain question differentiation. Questions can include 1-2 steps of reasoning or brief calculations but avoid lengthy and complex proofs.
- Appropriately intersperse behavioral/communication questions to assess basic qualities and social skills.
- Must cover: mathematical logic, intuition-based questions, and behavioral interviews within 5-6 rounds.
- Quickly adjust the difficulty and direction of subsequent questions based on the quality of previous answers. If the previous answers are very good, the difficulty of subsequent questions can be appropriately increased, but not beyond the above constraints.
- Avoid repeatedly asking about the same problem. The same type of question can be asked at most twice throughout the entire process. Once a type reaches its 2-round limit, you must switch to other types.
- Ensure type diversity and coverage within the limited rounds. Avoid staying on a single type for a long time.

Output Requirements (must be in strict JSON format):
    {
        "question": "Specific question text (can include necessary guidance/definitions, must be a complete description, do not compress or abbreviate; try not to use professional terms. If terminology is needed, first explain it in everyday language. Must include all necessary conditions and provide Chinese explanations for professional terms)",
        "type": "Question type (math_logic/technical/behavioral/experience)",
        "difficulty": "Difficulty level (easy/medium/hard)",
        "reasoning": "Why this question is proposed at this stage, and its differentiation points"
    }

**Important Formatting Requirements**:
1. Must return a complete JSON format, ensuring all curly braces {} and quotes "" are paired.
2. Do not add any extra text, markdown tags, or code block symbols before or after the JSON.
3. Ensure there is no trailing comma after the last field.
5. The "question" field must not contain "etc.", ellipses (...), or any other form of abbreviation or compression.
6. The question must include all necessary conditions and constraints, without omitting any key information. For professional concepts in graph theory, probability, combinatorics, explanations must be provided in the question.

All outputs must be in Chinese.
"""
    
    def get_system_prompt(self) -> str:
        return self.system_prompt or self.base_system_prompt
    
    
    def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成面试问题
        input_data包含:
        - resume_data: 简历信息
        - interview_stage: 面试阶段 (opening/technical/behavioral/closing)
        - previous_qa: 之前的问答记录
        - current_score: 当前评分情况
        - target_type: 目标题目类型（math_logic/technical/behavioral/experience），可选
        """
        print(f"===== QuestionGenerator.process() 开始执行 =====")
        try:
            resume_data = input_data.get("resume_data", {})
            interview_stage = input_data.get("interview_stage", "technical")
            previous_qa = input_data.get("previous_qa", [])
            current_score = input_data.get("current_score", 0)
            target_type = input_data.get("target_type")
            
            skills = ""
            
            
            # Build the prompt
            prompt_parts = []
            
            if interview_stage == "opening":
                # 开场以数理逻辑/自我介绍的轻量题目为主，由于总轮次有限，需要高效
                prompt_parts.append(
                    "This is the opening stage of the interview (5-6 rounds in total): Please generate an efficient opening question that can both understand the background and reflect the foundation of mathematical logic. The question should be friendly but have a certain degree of differentiation to quickly understand the candidate's thinking ability."
                )
            elif interview_stage == "technical":
                # 确定目标题型（若未显式指定，则基于场景选择）
                desired_type = target_type
                if not desired_type:
                    if skills:
                        desired_type = "technical"
                    else:
                        desired_type = "math_logic"

                if desired_type == "math_logic":
                    # For math_logic, forcibly use the RAG tool to enrich the question material
                    base_topics = [ "Logical Reasoning", "Combinatorics", "Probability Intuition", "Proof Questions"]
                    difficulty_hint = "easy to medium" if current_score < 6 else "medium to hard"
                    rag_query = f"Mathematical logic interview question {difficulty_hint} topics: " + ", ".join(base_topics)
                    # try:
                    #     rag_results = rag_search_tool.invoke({"query": rag_query}) if hasattr(rag_search_tool, "invoke") else rag_search_tool(rag_query)
                    # except Exception as e:
                    #     rag_results = f"RAG 检索失败: {e}"

                    prompt_parts.append("Please generate a math_logic type question, emphasizing the chain of reasoning and verifiability.")
                    prompt_parts.append("Prioritize assessing abstract modeling, intuition in sets/graphs/number theory/probability theory, or algorithm intuition that does not rely on programming.")
                    prompt_parts.append("Avoid memory-based questions; allow for multi-step reasoning.")
                    # prompt_parts.append(f"Reference content from knowledge base:\n{rag_results}")
                    prompt_parts.append("You are not required to use the search results from the knowledge base. If they are not suitable, you can generate a more appropriate question yourself.")
                    prompt_parts.append("Please set the type to math_logic and explain the source of differentiation in the reasoning.")

                elif desired_type == "technical":
                    prompt_parts.append("Please design an efficient core technical question around the content the candidate has mentioned in their self-statement/resume, getting to the essence of their understanding.")
                    prompt_parts.append("You can ask for explanations of principles, comparisons of solutions, analysis of boundary conditions, or complexity assessment.")
                    prompt_parts.append("If external knowledge is needed, you can decide whether to call the rag_search tool.")
                    prompt_parts.append("Please set the type to technical.")

                elif desired_type == "behavioral":
                    prompt_parts.append("Please generate a behavioral interview question focusing on cooperation, conflict resolution, reflection, and improvement.")
                    prompt_parts.append("The question should prompt the candidate to give a STAR (Situation-Task-Action-Result) style answer.")
                    prompt_parts.append("Please set the type to behavioral.")

                else:  # experience or default
                    prompt_parts.append("Please generate an experience review question based on the candidate's experience, requiring them to abstract transferable methodologies.")
                    prompt_parts.append("You can guide them to provide key metrics, lessons from failures, and next-step optimization strategies.")
                    prompt_parts.append("Please set the type to experience.")
            elif interview_stage == "behavioral":
                prompt_parts.append(
                    "Please generate an efficient behavioral interview question to assess basic qualities and interpersonal skills, such as cooperation, listening, conflict resolution, respect for others, and clarity of expression. The question should be relevant to campus research/team project scenarios and be able to reflect multiple dimensions in one answer."
                )
            
            # 添加历史问答信息
            if previous_qa:
                qa_history = "\n".join([f"Q: {qa.get('question', '')}\nA: {qa.get('answer', '')}" 
                                       for qa in previous_qa[-3:]])  # Only take the last 3 rounds
                prompt_parts.append(f"Previous Q&A record:\n{qa_history}")
                prompt_parts.append(f"Current average score: {current_score}/10")
                prompt_parts.append(f"This is round {len(previous_qa)+1} (out of 5-6 total). Please generate an efficient and targeted question based on the candidate's performance and the remaining rounds.")

                # 类型使用统计与上限约束
                type_counts = self._count_question_types(previous_qa)
                if type_counts:
                    reached_limit_types = [t for t, c in type_counts.items() if c >= 2]
                    prompt_parts.append(f"Type usage statistics (cumulative): {json.dumps(type_counts, ensure_ascii=False)}")
                    if reached_limit_types:
                        blocked = ", ".join(reached_limit_types)
                        prompt_parts.append(
                            f"The following types have reached the 2-round limit: {blocked}. The new question must avoid these types and switch to other types that have not reached the limit, prioritizing uncovered types."
                        )
                # 全局规则重申（即使无统计数据也需遵守）
                prompt_parts.append(
                    "Please strictly adhere to the type limit and diversity rules: a single type can be used at most twice in the entire process; avoid continuous follow-up questions on the same problem, and switch to different types when necessary to increase coverage."
                )
            
            human_message_content = "\n\n".join(prompt_parts)
            
            messages = [
                SystemMessage(content=self.get_system_prompt()),
                HumanMessage(content=human_message_content)
            ]
            
            response = self._invoke_with_tools(messages)
            
            # 输出原始响应内容
            print(f"===== QuestionGenerator 原始响应 =====")
            print(response)
            print("=====================================\n")
            
            # 尝试解析JSON响应
            try:
                # 首先尝试修复常见的JSON问题
                fixed_response = self._fix_common_json_issues(response)
                result = json.loads(fixed_response)
                if "question" not in result:
                    raise ValueError("Response missing 'question' field")
                return result
            except (json.JSONDecodeError, ValueError) as e:
                print(f"Failed to parse JSON response: {e}")
                print(f"Raw response: {response}")

                # 如果JSON解析失败，直接返回原始字符串
                question_text = self._extract_question_from_raw_response(response)
                return {
                    "question": question_text,
                    "type": "general",
                    "difficulty": "medium",
                    "reasoning": "Generated question based on context"
                }
                
        except Exception as e:
            print(f"Error in QuestionGeneratorAgent: {e}")
            return {
                "question": "An error occurred while generating the question. Please introduce your work experience and skills background.",
                "type": "general",
                "difficulty": "easy",
                "reasoning": "Default question due to error"
            }

    def _invoke_with_tools(self, messages: List[Any]) -> str:
        """
        允许 LLM 自主决定是否调用工具（rag_search），并循环执行工具调用直至获得最终回答。
        """
        try:
            tools = [rag_search_tool]
            model_with_tools = self.model.bind_tools(tools)

            history = list(messages)
            max_iterations = 4
            iterations = 0
            while True:
                print(f"===== {self.name} 开始调用LLM（tools-enabled） =====")
                ai_msg = model_with_tools.invoke(history)
                print(f"===== {self.name} LLM调用完成 =====")

                # 若模型直接给出答案
                tool_calls = getattr(ai_msg, "tool_calls", None)
                if not tool_calls:
                    return ai_msg.content

                # 否则执行工具并继续循环
                history.append(ai_msg)
                for tool_call in tool_calls:
                    tool_name = tool_call.get("name") if isinstance(tool_call, dict) else tool_call.name
                    tool_args = tool_call.get("args", {}) if isinstance(tool_call, dict) else tool_call.args
                    tool_id = tool_call.get("id") if isinstance(tool_call, dict) else tool_call.id

                    if tool_name == "rag_search":
                        try:
                            result = rag_search_tool.invoke(tool_args) if hasattr(rag_search_tool, "invoke") else rag_search_tool(**tool_args)
                        except Exception as e:
                            result = f"Error executing RAG search: {e}"
                    else:
                        result = f"Unrecognized tool: {tool_name}"

                    history.append(ToolMessage(content=str(result), name=tool_name, tool_call_id=tool_id))

                iterations += 1
                if iterations >= max_iterations:
                    return ai_msg.content if getattr(ai_msg, 'content', None) else "工具调用次数过多，已返回当前结果"
        except Exception as e:
            print(f"Failed to invoke with tools, falling back to text-only generation: {e}")
            return self._invoke_model(messages)
    
    def generate_initial_questions(self, resume_data: Dict[str, Any], count: int = 3) -> List[Dict[str, Any]]:
        """生成初始问题集"""
        questions = []
        
        # 开场问题
        opening_result = self.process({
            "resume_data": resume_data,
            "interview_stage": "opening"
        })
        questions.append(opening_result)
        
        # 技术问题
        for i in range(count - 1):
            technical_result = self.process({
                "resume_data": resume_data,
                "interview_stage": "technical",
                "previous_qa": []
            })
            questions.append(technical_result)
        
        return questions

    def _fix_common_json_issues(self, response: str) -> str:
        """
        修复常见的JSON格式问题
        """
        # 清理响应
        cleaned = response.strip()
        
        # 移除markdown代码块标记
        if cleaned.startswith('```json'):
            cleaned = cleaned[7:]
        elif cleaned.startswith('```'):
            cleaned = cleaned[3:]
        if cleaned.endswith('```'):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        
        # 检查是否缺少结尾大括号
        open_braces = cleaned.count('{')
        close_braces = cleaned.count('}')
        
        if open_braces > close_braces:
            # 添加缺少的结尾大括号
            missing_braces = open_braces - close_braces
            cleaned += '}' * missing_braces
        
        # 移除可能的多余逗号（在大括号前的逗号）
        import re
        cleaned = re.sub(r',\s*}', '}', cleaned)
        cleaned = re.sub(r',\s*]', ']', cleaned)
        
        return cleaned
    
    def _extract_question_from_raw_response(self, raw_response: str) -> str:
        """
        从原始AI响应中提取问题文本
        JSON解析失败时直接返回整个字符串
        """
        return raw_response.strip()

    def _count_question_types(self, previous_qa: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        统计历史问答中各类型（type）的出现次数，仅统计包含 'type' 字段的项。
        """
        counts: Dict[str, int] = {}
        if not previous_qa:
            return counts
        for qa in previous_qa:
            qa_type = qa.get("type")
            if not qa_type:
                continue
            counts[qa_type] = counts.get(qa_type, 0) + 1
        return counts
