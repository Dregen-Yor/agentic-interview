"""
Rubric 维度定义 — 5 维度 LOW/MEDIUM/HIGH 描述
适配大学 CS 拔尖班选拔场景（面向大一新生）
"""

RUBRIC_DIMENSIONS = {
    "math_logic": {
        "name": "数学/逻辑基础",
        "weight": "1-4",
        "levels": {
            "LOW": "Only reproduces memorized formulas; cannot reason beyond single-step deduction; no evidence of abstraction.",
            "MEDIUM": "Demonstrates multi-step reasoning on familiar problems; some abstraction ability; occasional logical gaps.",
            "HIGH": "Fluent abstract/formal reasoning; constructs proofs or counter-examples independently; strong algorithmic intuition.",
        },
    },
    "reasoning_rigor": {
        "name": "推理严谨性",
        "weight": "1-2",
        "levels": {
            "LOW": "Jumps to conclusions without justification; ignores edge cases and boundary conditions.",
            "MEDIUM": "Generally sound reasoning; acknowledges some boundary conditions but misses subtle cases.",
            "HIGH": "Systematic verification; considers edge cases proactively; self-corrects when finding inconsistencies.",
        },
    },
    "communication": {
        "name": "表达与沟通",
        "weight": "1-2",
        "levels": {
            "LOW": "Disorganized expression; cannot articulate thought process; poor listening.",
            "MEDIUM": "Reasonably clear explanations; structured when prompted; adequate listening.",
            "HIGH": "Concise, well-structured communication; adapts explanation to audience; active listening.",
        },
    },
    "collaboration": {
        "name": "合作与社交基线",
        "weight": "0-1",
        "levels": {
            "LOW": "Dismissive of others' input; no teamwork awareness.",
            "MEDIUM": "Respectful; acknowledges collaboration value but limited evidence.",
            "HIGH": "Concrete examples of effective teamwork; emotional maturity under disagreement.",
        },
    },
    "growth_potential": {
        "name": "成长潜力",
        "weight": "0-1",
        "levels": {
            "LOW": "No self-reflection; avoids unfamiliar problems; passive learning attitude.",
            "MEDIUM": "Some curiosity; reflects on mistakes when prompted; willing to try new approaches.",
            "HIGH": "Self-driven learner; seeks challenges; demonstrates meta-cognitive awareness.",
        },
    },
}


def format_rubric_for_prompt() -> str:
    """格式化为可嵌入 LLM prompt 的文本"""
    lines = []
    for dim_key, dim in RUBRIC_DIMENSIONS.items():
        lines.append(f"### {dim['name']} ({dim_key}, weight {dim['weight']})")
        for level, desc in dim["levels"].items():
            lines.append(f"  - {level}: {desc}")
    return "\n".join(lines)
