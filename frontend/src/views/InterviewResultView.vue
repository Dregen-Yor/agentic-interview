<template>
    <div class="result-container">
        <h1>面试评估报告</h1>
        <div v-if="isLoading" class="loading">正在加载您的面试结果...</div>
        <div v-if="error" class="error-message">{{ error }}</div>
        <div v-if="interviewResult" class="result-content">
            <!-- 基本信息卡片 -->
            <div class="result-card basic-info">
                <div class="result-header">
                    <h2>{{ interviewResult.candidate_name || interviewResult.name }} 的面试评估</h2>
                    <div class="header-right">
                        <span :class="['status', getDecisionClass(interviewResult.final_decision)]">
                            {{ getDecisionText(interviewResult.final_decision) }}
                        </span>
                        <div class="final-grade" v-if="interviewResult.final_grade">
                            <span class="grade-label">最终等级</span>
                            <span class="grade-value">{{ interviewResult.final_grade }}</span>
                        </div>
                        <div class="overall-score" v-if="interviewResult.overall_score">
                            <span class="score-label">综合评分</span>
                            <span class="score-value">{{ getScoreValue(interviewResult.overall_score) }}/10</span>
                        </div>
                    </div>
                </div>
            </div>

            <!-- 面试总结 -->
            <div class="result-card summary-card">
                <h3>面试总结</h3>
                <p class="summary-text">{{ interviewResult.summary }}</p>
                <div class="confidence-level" v-if="interviewResult.confidence_level">
                    <span class="confidence-label">评估置信度:</span>
                    <span :class="['confidence-value', `confidence-${interviewResult.confidence_level}`]">
                        {{ getConfidenceText(interviewResult.confidence_level) }}
                    </span>
                </div>
            </div>

            <!-- 优势和不足 -->
            <div class="result-grid">
                <div class="result-card strengths-card">
                    <h3>✨ 候选人优势</h3>
                    <ul v-if="interviewResult.strengths && interviewResult.strengths.length > 0">
                        <li v-for="(strength, index) in interviewResult.strengths" :key="index">
                            {{ strength }}
                        </li>
                    </ul>
                    <p v-else class="no-data">暂无数据</p>
                </div>

                <div class="result-card weaknesses-card">
                    <h3>⚠️ 需要改进的地方</h3>
                    <ul v-if="interviewResult.weaknesses && interviewResult.weaknesses.length > 0">
                        <li v-for="(weakness, index) in interviewResult.weaknesses" :key="index">
                            {{ weakness }}
                        </li>
                    </ul>
                    <p v-else class="no-data">暂无数据</p>
                </div>
            </div>

            <!-- 详细分析 -->
            <div class="result-card analysis-card" v-if="interviewResult.detailed_analysis">
                <h3>📊 详细能力分析</h3>
                <div class="analysis-grid">
                    <div class="analysis-item" v-for="(value, key) in interviewResult.detailed_analysis" :key="key">
                        <div class="analysis-header">
                            <span class="analysis-title">{{ getAnalysisTitle(key) }}</span>
                        </div>
                        <div class="analysis-content">
                            {{ value }}
                        </div>
                    </div>
                </div>
            </div>

            <!-- 建议和推荐 -->
            <div class="result-card recommendations-card" v-if="interviewResult.recommendations">
                <h3>💡 建议与推荐</h3>
                <div class="recommendations-content">
                    <div class="recommendation-section" v-if="interviewResult.recommendations.for_candidate">
                        <h4>对候选人的建议</h4>
                        <p>{{ interviewResult.recommendations.for_candidate }}</p>
                    </div>
                    <div class="recommendation-section" v-if="interviewResult.recommendations.for_program || interviewResult.recommendations.for_company">
                        <h4>对项目/学院的建议</h4>
                        <p>{{ interviewResult.recommendations.for_program || interviewResult.recommendations.for_company }}</p>
                    </div>
                </div>
            </div>

            <!-- 数据库保存状态 -->
            <div class="result-card db-status-card" v-if="interviewResult.database_save_status">
                <div class="db-status">
                    <span class="db-icon">💾</span>
                    <span class="db-message">{{ interviewResult.database_save_status }}</span>
                </div>
            </div>

            <!-- 结果时间戳 -->
            <div class="result-footer">
                <div class="timestamp-info">
                    <span class="timestamp-label">生成时间:</span>
                    <span class="timestamp-value">
                        {{ formatTimestamp(interviewResult.generated_at || interviewResult.created_at || interviewResult.timestamp) }}
                    </span>
                </div>
                <div class="processed-by" v-if="interviewResult.processed_by">
                    <span class="processed-label">处理者:</span>
                    <span class="processed-value">{{ interviewResult.processed_by }}</span>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useAuth } from '@/stores/auth';

const authStore = useAuth();
const interviewResult = ref<any>(null);
const isLoading = ref(true);
const error = ref<string | null>(null);

// 决策状态映射
const getDecisionClass = (decision: string) => {
    switch (decision) {
        case 'accept':
            return 'status-pass';
        case 'reject':
            return 'status-fail';
        case 'conditional':
            return 'status-conditional';
        default:
            return 'status-default';
    }
};

const getDecisionText = (decision: string) => {
    switch (decision) {
        case 'accept':
            return '建议录用';
        case 'reject':
            return '不建议录用';
        case 'conditional':
            return '条件录用';
        default:
            return decision || '待评估';
    }
};

// 置信度映射
const getConfidenceText = (confidence: string) => {
    switch (confidence) {
        case 'high':
            return '高';
        case 'medium':
            return '中等';
        case 'low':
            return '低';
        default:
            return confidence || '未知';
    }
};

// 分析标题映射
const getAnalysisTitle = (key: string) => {
    const titles: { [key: string]: string } = {
        technical_skills: '技术能力', // 旧字段
        experience_match: '经验匹配度', // 旧字段
        communication: '沟通能力',
        problem_solving: '问题解决能力', // 旧字段
        growth_potential: '发展潜力',
        // 新字段兼容
        math_logic: '数理与逻辑',
        reasoning_rigor: '推理严谨性',
        collaboration: '合作与社交'
    };
    return titles[key] || key;
};

// 处理MongoDB数值格式
const getScoreValue = (score: any) => {
    if (typeof score === 'object' && score.$numberDouble) {
        return parseFloat(score.$numberDouble).toFixed(1);
    }
    if (typeof score === 'object' && score.$numberInt) {
        return parseInt(score.$numberInt);
    }
    if (typeof score === 'number') {
        return score.toFixed(1);
    }
    return score || '0.0';
};

// 时间戳格式化
const formatTimestamp = (timestamp: any) => {
    if (!timestamp) return '未知时间';

    try {
        let dateValue;

        // 处理MongoDB $date格式
        if (typeof timestamp === 'object' && timestamp.$date && timestamp.$date.$numberLong) {
            dateValue = new Date(parseInt(timestamp.$date.$numberLong));
        }
        // 处理字符串格式
        else if (typeof timestamp === 'string') {
            dateValue = new Date(timestamp);
        }
        // 处理数字格式
        else if (typeof timestamp === 'number') {
            dateValue = new Date(timestamp);
        }
        else {
            return '未知时间';
        }

        if (isNaN(dateValue.getTime())) {
            return '无效时间';
        }

        return dateValue.toLocaleString('zh-CN', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
    } catch (e) {
        return '时间格式错误';
    }
};

onMounted(async () => {
    try {
        const data = await authStore.getInterviewResult();
        if (data.result) {
            // 根据新的result.json格式，面试结果在detailed_summary中
            if (data.result.detailed_summary) {
                const detailedSummary = data.result.detailed_summary;
                interviewResult.value = {
                    ...detailedSummary,
                    session_id: data.result.session_id,
                    created_at: data.result.timestamp || data.result.created_at,
                    saved_at: data.result.saved_at,
                    // 确保candidate_name字段存在
                    candidate_name: detailedSummary.candidate_name || data.result.candidate_name || data.result.name
                };
            } else {
                // 如果没有detailed_summary，尝试使用其他字段
                interviewResult.value = {
                    ...data.result,
                    // 如果没有summary字段，使用comment作为summary
                    summary: data.result.summary || data.result.comment || '暂无面试总结'
                };
            }
        } else {
            error.value = '未能获取到面试结果。';
        }
    } catch (e: any) {
        error.value = e.message || '获取面试结果失败。';
    } finally {
        isLoading.value = false;
    }
});
</script>

<style scoped>
.result-container {
    max-width: 1000px;
    margin: 2rem auto;
    padding: 2rem;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
    background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
    min-height: 100vh;
}

h1 {
    text-align: center;
    color: #2c3e50;
    margin-bottom: 2rem;
    font-size: 2.5rem;
    font-weight: 300;
    text-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.loading, .error-message {
    text-align: center;
    padding: 2rem;
    font-size: 1.2rem;
    border-radius: 12px;
    margin: 2rem 0;
}

.loading {
    background: rgba(255,255,255,0.9);
    color: #666;
}

.error-message {
    color: #e74c3c;
    background: rgba(231, 76, 60, 0.1);
    border: 1px solid rgba(231, 76, 60, 0.3);
}

.result-content {
    display: flex;
    flex-direction: column;
    gap: 2rem;
}

.result-card {
    background: rgba(255, 255, 255, 0.95);
    backdrop-filter: blur(10px);
    border: 1px solid rgba(255, 255, 255, 0.2);
    border-radius: 16px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
    overflow: hidden;
    transition: all 0.3s ease;
    padding: 2rem;
}

.result-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.15);
}

.basic-info {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    margin-bottom: 1rem;
}

.basic-info .result-header {
    background: transparent;
    border-bottom: 1px solid rgba(255, 255, 255, 0.2);
}

.basic-info h2 {
    color: white;
}

.result-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1.5rem;
    padding-bottom: 1rem;
    border-bottom: 1px solid rgba(0,0,0,0.1);
}

.header-right {
    display: flex;
    align-items: center;
    gap: 1rem;
}

.status {
    padding: 0.75rem 1.5rem;
    border-radius: 25px;
    font-weight: 600;
    color: #fff;
    font-size: 1rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    box-shadow: 0 4px 15px rgba(0,0,0,0.2);
}

.status-pass {
    background: linear-gradient(45deg, #27ae60, #2ecc71);
}

.status-fail {
    background: linear-gradient(45deg, #e74c3c, #c0392b);
}

.status-conditional {
    background: linear-gradient(45deg, #f39c12, #e67e22);
}

.overall-score {
    display: flex;
    flex-direction: column;
    align-items: center;
    background: rgba(255,255,255,0.2);
    padding: 1rem;
    border-radius: 12px;
    backdrop-filter: blur(10px);
}

.final-grade {
    display: flex;
    flex-direction: column;
    align-items: center;
    background: rgba(255,255,255,0.2);
    padding: 1rem;
    border-radius: 12px;
    backdrop-filter: blur(10px);
}

.grade-label {
    font-size: 0.9rem;
    opacity: 0.9;
    margin-bottom: 0.25rem;
}

.grade-value {
    font-size: 1.8rem;
    font-weight: bold;
}

.score-label {
    font-size: 0.9rem;
    opacity: 0.9;
    margin-bottom: 0.25rem;
}

.score-value {
    font-size: 1.8rem;
    font-weight: bold;
}

.result-card h3 {
    color: #2c3e50;
    margin-bottom: 1rem;
    font-size: 1.4rem;
    font-weight: 600;
}

.summary-card .summary-text {
    font-size: 1.1rem;
    line-height: 1.7;
    color: #34495e;
    margin-bottom: 1rem;
}

.confidence-level {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-top: 1rem;
    padding: 0.75rem 1rem;
    background: rgba(52, 152, 219, 0.1);
    border-radius: 8px;
}

.confidence-label {
    font-weight: 600;
    color: #2980b9;
}

.confidence-value {
    padding: 0.25rem 0.75rem;
    border-radius: 15px;
    font-size: 0.9rem;
    font-weight: 600;
}

.confidence-high {
    background: #27ae60;
    color: white;
}

.confidence-medium {
    background: #f39c12;
    color: white;
}

.confidence-low {
    background: #e74c3c;
    color: white;
}

.result-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 2rem;
}

.strengths-card {
    border-left: 4px solid #27ae60;
}

.weaknesses-card {
    border-left: 4px solid #e74c3c;
}

.strengths-card h3 {
    color: #27ae60;
}

.weaknesses-card h3 {
    color: #e74c3c;
}

.strengths-card ul, .weaknesses-card ul {
    list-style: none;
    padding: 0;
}

.strengths-card li, .weaknesses-card li {
    padding: 0.75rem 0;
    border-bottom: 1px solid rgba(0,0,0,0.05);
    position: relative;
    padding-left: 2rem;
}

.strengths-card li:before {
    content: "✓";
    position: absolute;
    left: 0;
    color: #27ae60;
    font-weight: bold;
}

.weaknesses-card li:before {
    content: "⚠";
    position: absolute;
    left: 0;
    color: #e74c3c;
    font-weight: bold;
}

.no-data {
    color: #95a5a6;
    font-style: italic;
    text-align: center;
    padding: 2rem;
}

.analysis-card {
    border-left: 4px solid #3498db;
}

.analysis-card h3 {
    color: #3498db;
}

.analysis-grid {
    display: grid;
    gap: 1.5rem;
}

.analysis-item {
    background: rgba(52, 152, 219, 0.05);
    border: 1px solid rgba(52, 152, 219, 0.1);
    border-radius: 8px;
    padding: 1.5rem;
    transition: all 0.3s ease;
}

.analysis-item:hover {
    background: rgba(52, 152, 219, 0.1);
    transform: translateY(-1px);
}

.analysis-header {
    margin-bottom: 1rem;
}

.analysis-title {
    font-weight: 600;
    color: #2980b9;
    font-size: 1.1rem;
    display: block;
    padding-bottom: 0.5rem;
    border-bottom: 2px solid rgba(52, 152, 219, 0.3);
}

.analysis-content {
    color: #34495e;
    line-height: 1.6;
}

.recommendations-card {
    border-left: 4px solid #9b59b6;
}

.recommendations-card h3 {
    color: #9b59b6;
}

.recommendations-content {
    display: grid;
    gap: 1.5rem;
}

.recommendation-section {
    background: rgba(155, 89, 182, 0.05);
    border: 1px solid rgba(155, 89, 182, 0.1);
    border-radius: 8px;
    padding: 1.5rem;
}

.recommendation-section h4 {
    color: #8e44ad;
    margin-bottom: 0.75rem;
    font-size: 1.1rem;
}

.recommendation-section p {
    color: #34495e;
    line-height: 1.6;
    margin: 0;
}

.db-status-card {
    background: linear-gradient(135deg, rgba(46, 204, 113, 0.1), rgba(39, 174, 96, 0.05));
    border: 1px solid rgba(46, 204, 113, 0.3);
}

.db-status {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    color: #27ae60;
    font-weight: 600;
}

.db-icon {
    font-size: 1.5rem;
}

.db-message {
    font-size: 1rem;
}

.result-footer {
    background: rgba(255, 255, 255, 0.9);
    backdrop-filter: blur(10px);
    border: 1px solid rgba(255, 255, 255, 0.2);
    border-radius: 16px;
    padding: 2rem;
    margin-top: 1rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
}

.timestamp-info, .processed-by {
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

.timestamp-label, .processed-label {
    font-weight: 600;
    color: #7f8c8d;
}

.timestamp-value, .processed-value {
    color: #34495e;
    font-weight: 500;
}

/* 响应式设计 */
@media (max-width: 768px) {
    .result-container {
        padding: 1rem;
        margin: 1rem auto;
    }

    .result-grid {
        grid-template-columns: 1fr;
        gap: 1rem;
    }

    .result-footer {
        flex-direction: column;
        gap: 1rem;
        text-align: center;
    }

    h1 {
        font-size: 2rem;
    }

    .result-card {
        padding: 1.5rem;
    }

    .header-right {
        flex-direction: column;
        gap: 0.5rem;
    }
}
</style>