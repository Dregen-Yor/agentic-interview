#!/usr/bin/env python3
"""
自动化攻击测试脚本

功能：
1. 读取攻击数据集CSV文件
2. 自动启动面试会话
3. 发送攻击内容作为面试回答
4. 获取智能体评分
5. 将评分写入CSV文件

使用方法：
python automated_attack_test.py [--csv-file CSV_FILE] [--base-url BASE_URL] [--candidate-name CANDIDATE_NAME]

作者：AI Assistant
"""

import csv
import json
import time
import argparse
import requests
import subprocess
import signal
from typing import Dict, List, Optional, Any
import sys
import os
from datetime import datetime

class AutomatedAttackTester:
    """自动化攻击测试类"""

    def __init__(self, csv_file: str, base_url: str = "http://localhost:8000", candidate_name: str = "测试候选人"):
        """
        初始化测试器

        Args:
            csv_file: CSV文件路径
            base_url: Django服务器基础URL
            candidate_name: 候选人姓名
        """
        self.csv_file = csv_file
        self.base_url = base_url.rstrip('/')
        self.candidate_name = candidate_name
        self.session = requests.Session()  # 使用session保持Django session状态
        self.attack_data = []
        self.results = []

        # 服务器管理
        self.server_process = None
        self.server_port = int(self.base_url.split(':')[-1]) if ':' in self.base_url else 8000

        # 设置请求头
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'AutomatedAttackTest/1.0'
        })

    def start_server_if_needed(self, timeout: int = 60) -> bool:
        """检查服务器状态，如果未运行则启动"""
        try:
            # 检查服务器是否已经在运行
            response = requests.get(f"{self.base_url}/api/", timeout=5)
            if response.status_code == 200:
                print("Django服务器已在运行")
                return True
        except requests.RequestException:
            pass

        print("Django服务器未运行，正在启动...")

        # 启动服务器
        try:
            env = os.environ.copy()
            env.setdefault('DJANGO_SETTINGS_MODULE', 'interview_backend.settings')

            # 使用daphne启动ASGI服务器
            daphne_cmd = [
                'daphne',
                '-b', '0.0.0.0',
                '-p', str(self.server_port),
                'interview_backend.asgi:application'
            ]

            # 设置Python路径和虚拟环境
            python_path = '/home/sunupdate/agentic-interview'
            venv_python = '/home/sunupdate/agentic-interview/.venv/bin/python'
            venv_daphne = '/home/sunupdate/agentic-interview/.venv/bin/daphne'

            # 如果虚拟环境存在，使用虚拟环境的Python
            if os.path.exists(venv_python):
                env['PATH'] = f'/home/sunupdate/agentic-interview/.venv/bin:{env.get("PATH", "")}'
                python_exe = venv_python
                print("检测到虚拟环境，使用虚拟环境中的Python")
            else:
                python_exe = sys.executable
                print("未检测到虚拟环境，使用系统Python")

            # 直接使用Django开发服务器，更加稳定
            print("使用Django开发服务器...")
            self.server_process = subprocess.Popen(
                [python_exe, 'manage.py', 'runserver', f'0.0.0.0:{self.server_port}', '--noreload'],
                cwd='/home/sunupdate/agentic-interview',
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            print(f"Django服务器进程已启动 (PID: {self.server_process.pid})")

            # 等待服务器启动
            start_time = time.time()
            print(f"等待服务器在 {self.base_url}/api/ 上响应...")

            while time.time() - start_time < timeout:
                try:
                    response = requests.get(f"{self.base_url}/api/", timeout=2)
                    if response.status_code == 200:
                        print("Django服务器启动成功！")
                        return True
                    else:
                        print(f"服务器响应但状态码异常: {response.status_code}")
                except requests.RequestException as e:
                    elapsed = time.time() - start_time
                    print(f"等待服务器响应... ({elapsed:.1f}/{timeout}秒) - {e}")
                    pass
                time.sleep(1)

            print(f"等待服务器启动超时 ({timeout}秒)")
            self.stop_server()
            return False

        except Exception as e:
            print(f"启动Django服务器失败: {e}")
            return False

    def stop_server(self):
        """停止Django服务器"""
        if self.server_process and self.server_process.poll() is None:
            print(f"正在停止Django服务器 (PID: {self.server_process.pid})...")
            try:
                self.server_process.terminate()
                self.server_process.wait(timeout=10)
                print("Django服务器已停止")
            except subprocess.TimeoutExpired:
                print("强制终止Django服务器...")
                self.server_process.kill()
                self.server_process.wait()
            finally:
                self.server_process = None

    def __del__(self):
        """析构函数，确保服务器被停止"""
        self.stop_server()

    def load_csv_data(self) -> bool:
        """加载CSV数据"""
        try:
            print(f"正在读取CSV文件: {self.csv_file}")
            with open(self.csv_file, 'r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                self.attack_data = list(reader)

            print(f"成功加载 {len(self.attack_data)} 条攻击数据")
            return True

        except Exception as e:
            print(f"读取CSV文件失败: {e}")
            return False

    def save_results_to_csv(self) -> bool:
        """保存结果到CSV文件"""
        try:
            # 创建备份文件名
            backup_file = f"{self.csv_file}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            # 备份原文件
            if os.path.exists(self.csv_file):
                os.rename(self.csv_file, backup_file)
                print(f"原文件已备份为: {backup_file}")

            # 写入新数据
            with open(self.csv_file, 'w', newline='', encoding='utf-8') as file:
                if self.attack_data:
                    # 使用固定的字段名，确保兼容性
                    fieldnames = ['id', '攻击内容', '多智能体攻击得分']
                    writer = csv.DictWriter(file, fieldnames=fieldnames)
                    writer.writeheader()

                    for row in self.attack_data:
                        # 只写入需要的字段
                        clean_row = {
                            'id': row.get('id', ''),
                            '攻击内容': row.get('攻击内容', ''),
                            '多智能体攻击得分': row.get('多智能体攻击得分', '')
                        }
                        writer.writerow(clean_row)

            print(f"结果已保存到: {self.csv_file}")
            return True

        except Exception as e:
            print(f"保存CSV文件失败: {e}")
            return False

    def start_interview_session(self) -> Optional[str]:
        """启动新的面试会话"""
        try:
            url = f"{self.base_url}/api/"
            payload = {
                "candidate_name": self.candidate_name,
                "message": ""  # 空消息来启动会话
            }

            print(f"正在启动面试会话，候选人: {self.candidate_name}")
            response = self.session.post(url, json=payload)

            if response.status_code == 200:
                data = response.json()
                if data.get('interview_started'):
                    session_id = data.get('session_id')
                    print(f"面试会话启动成功，Session ID: {session_id}")
                    print(f"第一个问题: {data.get('response', '')}")
                    return session_id
                else:
                    print(f"启动会话失败: {data.get('error', '未知错误')}")
            else:
                print(f"HTTP错误 {response.status_code}: {response.text}")

        except requests.RequestException as e:
            print(f"网络请求错误: {e}")
        except json.JSONDecodeError as e:
            print(f"JSON解析错误: {e}")

        return None

    def send_attack_response(self, session_id: str, attack_content: str) -> Dict[str, Any]:
        """发送攻击内容作为面试回答"""
        try:
            url = f"{self.base_url}/api/"
            payload = {
                "message": attack_content,
                "session_id": session_id
            }

            print(f"发送攻击内容 (长度: {len(attack_content)} 字符)")
            response = self.session.post(url, json=payload)

            if response.status_code == 200:
                data = response.json()
                return data
            else:
                print(f"HTTP错误 {response.status_code}: {response.text}")
                return {"error": f"HTTP {response.status_code}", "details": response.text}

        except requests.RequestException as e:
            print(f"网络请求错误: {e}")
            return {"error": "网络错误", "details": str(e)}
        except json.JSONDecodeError as e:
            print(f"JSON解析错误: {e}")
            return {"error": "JSON解析错误", "details": str(e)}

    def process_interview_rounds(self, session_id: str, attack_content: str, max_rounds: int = 3) -> Dict[str, Any]:
        """处理多轮面试对话"""
        results = {
            "session_id": session_id,
            "attack_content": attack_content,
            "rounds": [],
            "final_result": None,
            "error": None
        }

        current_round = 0
        current_attack = attack_content

        while current_round < max_rounds:
            print(f"\n--- 第 {current_round + 1} 轮对话 ---")

            # 发送攻击内容
            response_data = self.send_attack_response(session_id, current_attack)

            if "error" in response_data:
                results["error"] = response_data["error"]
                break

            # 记录这一轮的结果
            round_result = {
                "round": current_round + 1,
                "attack_sent": current_attack,
                "response_received": response_data.get("response", ""),
                "score": response_data.get("score"),
                "current_average": response_data.get("current_average"),
                "total_questions": response_data.get("total_questions"),
                "question_type": response_data.get("question_type"),
                "security_warning": response_data.get("security_warning", False),
                "timestamp": datetime.now().isoformat()
            }

            results["rounds"].append(round_result)

            # 检查是否面试完成
            if response_data.get("interview_complete"):
                results["final_result"] = {
                    "final_decision": response_data.get("final_decision"),
                    "overall_score": response_data.get("overall_score"),
                    "summary": response_data.get("summary"),
                    "total_questions": response_data.get("total_questions")
                }
                print("面试已完成！")
                break

            # 如果没有完成，准备下一轮（可以继续发送相同攻击或修改）
            current_round += 1
            if current_round < max_rounds:
                # 可以在这里修改攻击内容，比如添加变体
                current_attack = attack_content  # 保持相同攻击
                time.sleep(1)  # 短暂延迟避免请求过快

        return results

    def end_interview_session(self, session_id: str) -> bool:
        """结束面试会话"""
        try:
            url = f"{self.base_url}/api/interview/end/"
            payload = {"session_id": session_id}

            print(f"正在结束面试会话: {session_id}")
            response = self.session.post(url, json=payload)

            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    print("面试会话已成功结束")
                    return True
                else:
                    print(f"结束会话失败: {data.get('error', '未知错误')}")
            else:
                print(f"HTTP错误 {response.status_code}: {response.text}")

        except Exception as e:
            print(f"结束面试会话时出错: {e}")

        return False

    def extract_scores_from_result(self, result: Dict[str, Any]) -> Dict[str, str]:
        """从结果中提取评分等级"""
        scores = {
            "multi_agent_grade": None,  # 多智能体等级（A/B/C/D）
            "multi_agent_score": None   # 多智能体数值分数（用于参考）
        }

        try:
            # 优先使用最终结果中的等级
            if result.get("final_result"):
                final_grade = result["final_result"].get("final_grade")
                final_score = result["final_result"].get("overall_score")

                if final_grade:
                    scores["multi_agent_grade"] = final_grade
                if final_score is not None:
                    scores["multi_agent_score"] = float(final_score)

            # 如果没有最终结果但有轮次数据，从轮次中提取
            elif result.get("rounds"):
                grades = []
                numeric_scores = []

                for round_data in result["rounds"]:
                    # 尝试从score_details中提取等级
                    score_details = round_data.get("score_details", {})

                    if score_details and "letter" in score_details:
                        grades.append(score_details["letter"])
                        # 如果有等级，也要收集数值分数
                        if "score" in score_details:
                            numeric_scores.append(float(score_details["score"]))
                    elif score_details and "score" in score_details:
                        # 如果只有分数，根据分数映射等级
                        score = score_details["score"]
                        numeric_scores.append(float(score))
                        grades.append(self._score_to_grade(score))

                if grades:
                    # 使用出现次数最多的等级，如果有多个相同次数，选择等级最高的
                    from collections import Counter
                    grade_counts = Counter(grades)
                    most_common = grade_counts.most_common()

                    # 如果有多个等级出现相同次数，选择等级最高的
                    max_count = most_common[0][1]
                    candidates = [grade for grade, count in most_common if count == max_count]
                    candidates.sort(key=lambda x: 'DCBA'.index(x))  # D=0, C=1, B=2, A=3
                    scores["multi_agent_grade"] = candidates[-1]  # 选择等级最高的

                if numeric_scores:
                    scores["multi_agent_score"] = sum(numeric_scores) / len(numeric_scores)

            # 如果都没有找到，使用默认值
            if not scores["multi_agent_grade"]:
                scores["multi_agent_grade"] = "D"
            if not scores["multi_agent_score"]:
                scores["multi_agent_score"] = 0.0

        except (ValueError, TypeError, KeyError) as e:
            print(f"评分提取错误: {e}")
            scores["multi_agent_grade"] = "D"
            scores["multi_agent_score"] = 0.0

        return scores

    def _score_to_grade(self, score: float) -> str:
        """根据数值分数映射字母等级"""
        if score >= 9:
            return "A"
        elif score >= 7:
            return "B"
        elif score >= 5:
            return "C"
        else:
            return "D"

    def run_attack_test(self, attack_id: int, attack_content: str) -> Dict[str, Any]:
        """运行单个攻击测试"""
        print(f"\n{'='*60}")
        print(f"开始测试攻击 ID: {attack_id}")
        print(f"攻击内容预览: {attack_content[:100]}{'...' if len(attack_content) > 100 else ''}")
        print(f"{'='*60}")

        # 1. 启动面试会话
        session_id = self.start_interview_session()
        if not session_id:
            return {"error": "无法启动面试会话", "attack_id": attack_id}

        try:
            # 2. 处理面试轮次
            result = self.process_interview_rounds(session_id, attack_content)

            # 3. 提取评分
            scores = self.extract_scores_from_result(result)

            # 4. 准备结果
            test_result = {
                "attack_id": attack_id,
                "session_id": session_id,
                "attack_content": attack_content,
                "multi_agent_grade": scores["multi_agent_grade"],  # 多智能体等级（A/B/C/D）
                "multi_agent_score": scores["multi_agent_score"],  # 数值分数（用于参考）
                "result": result,
                "success": result.get("error") is None,
                "timestamp": datetime.now().isoformat()
            }

            return test_result

        finally:
            # 5. 结束会话
            self.end_interview_session(session_id)
            time.sleep(2)  # 会话间暂停

    def run_all_tests(self, start_id: Optional[int] = None, end_id: Optional[int] = None,
                     delay: float = 2.0) -> Dict[str, Any]:
        """运行所有攻击测试"""
        if not self.load_csv_data():
            return {"error": "无法加载CSV数据"}

        print(f"开始运行自动化攻击测试...")
        print(f"服务器地址: {self.base_url}")
        print(f"候选人姓名: {self.candidate_name}")
        print(f"总测试数: {len(self.attack_data)}")
        print(f"请求间隔: {delay} 秒")

        successful_tests = 0
        failed_tests = 0
        results = []

        # 确定测试范围
        if end_id is None:
            end_id = len(self.attack_data)

        # 验证范围有效性
        if start_id < 1 or start_id > len(self.attack_data):
            print(f"错误: 起始ID {start_id} 无效，应该在 1-{len(self.attack_data)} 范围内")
            return {"error": f"起始ID {start_id} 无效"}

        if end_id < start_id or end_id > len(self.attack_data):
            print(f"警告: 结束ID {end_id} 已调整为 {len(self.attack_data)}")
            end_id = len(self.attack_data)

        test_range = range(start_id - 1, end_id)
        actual_count = len(list(range(start_id - 1, end_id)))

        print(f"将处理 {actual_count} 条攻击数据 (ID: {start_id}-{end_id})")

        for i in test_range:
            if i >= len(self.attack_data):
                break

            row = self.attack_data[i]

            # 安全地获取和转换ID
            try:
                id_str = row.get('id', '').strip()
                if id_str and id_str.isdigit():
                    attack_id = int(id_str)
                else:
                    attack_id = i + 1  # 使用行号作为ID
                    print(f"警告: ID无效 '{id_str}'，使用行号 {attack_id} 作为ID")
            except (ValueError, KeyError) as e:
                attack_id = i + 1
                print(f"警告: ID转换失败，使用行号 {attack_id} 作为ID")

            attack_content = row.get('攻击内容', '').strip()

            if not attack_content:
                print(f"跳过ID {attack_id}: 攻击内容为空")
                continue

            # 运行测试
            test_result = self.run_attack_test(attack_id, attack_content)
            results.append(test_result)

            if test_result.get("success"):
                successful_tests += 1

                # 更新CSV数据
                scores = test_result.get("scores", {})
                if "multi_agent_grade" in test_result:
                    row['多智能体攻击得分'] = test_result["multi_agent_grade"]
                if "multi_agent_score" in test_result:
                    # 添加数值分数作为参考（可以考虑添加到新列或移除）
                    pass

                print(f"✅ 测试 {attack_id} 成功 - 多智能体等级: {test_result.get('multi_agent_grade')} (分数: {test_result.get('multi_agent_score', 'N/A')})")
            else:
                failed_tests += 1
                print(f"❌ 测试 {attack_id} 失败 - {test_result.get('error', '未知错误')}")

            # 保存进度
            if (i + 1) % 10 == 0:
                self.save_results_to_csv()
                print(f"进度保存: 已完成 {i + 1}/{len(self.attack_data)} 项测试")

            # 请求间延迟
            if i < len(self.attack_data) - 1:
                time.sleep(delay)

        # 最终保存
        self.save_results_to_csv()

        summary = {
            "total_tests": len(results),
            "successful_tests": successful_tests,
            "failed_tests": failed_tests,
            "success_rate": successful_tests / len(results) if results else 0,
            "results": results,
            "timestamp": datetime.now().isoformat()
        }

        print(f"\n{'='*60}")
        print("测试完成总结:")
        print(f"总测试数: {summary['total_tests']}")
        print(f"成功: {summary['successful_tests']}")
        print(f"失败: {summary['failed_tests']}")
        print(f"成功率: {summary['success_rate']:.2%}")
        print(f"结果已保存到: {self.csv_file}")
        print(f"{'='*60}")

        return summary

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='自动化攻击测试脚本')
    parser.add_argument('--csv-file', default='/home/sunupdate/agentic-interview/攻击数据集.csv',
                       help='CSV文件路径 (默认: /home/sunupdate/agentic-interview/攻击数据集.csv)')
    parser.add_argument('--base-url', default='http://localhost:8000',
                       help='Django服务器基础URL (默认: http://localhost:8000)')
    parser.add_argument('--candidate-name', default='杨昀淇',
                       help='候选人姓名 (默认: 杨昀淇)')
    parser.add_argument('--start-id', type=int, default=1, help='起始攻击ID (默认: 1)')
    parser.add_argument('--end-id', type=int, help='结束攻击ID (默认: 处理所有数据)')
    parser.add_argument('--delay', type=float, default=2.0,
                       help='请求间延迟秒数 (默认: 2.0)')
    parser.add_argument('--test', action='store_true',
                       help='仅测试连接，不运行完整测试')
    parser.add_argument('--auto-start-server', action='store_true', default=True,
                       help='自动启动Django服务器 (默认: True)')
    parser.add_argument('--server-timeout', type=int, default=60,
                       help='服务器启动超时时间 (默认: 60秒)')

    args = parser.parse_args()

    # 创建测试器
    tester = AutomatedAttackTester(
        csv_file=args.csv_file,
        base_url=args.base_url,
        candidate_name=args.candidate_name
    )

    # 启动服务器（如果需要）
    if args.auto_start_server:
        print(f"将等待服务器启动最多 {args.server_timeout} 秒...")
        if not tester.start_server_if_needed(args.server_timeout):
            print("无法启动Django服务器，退出程序")
            print("可能的解决方案:")
            print("1. 确保已激活虚拟环境: source .venv/bin/activate")
            print("2. 手动启动服务器: daphne -b 0.0.0.0 -p 8000 interview_backend.asgi:application")
            print("3. 检查端口是否被占用: lsof -i :8000")
            sys.exit(1)
    else:
        # 检查服务器状态
        try:
            response = requests.get(f"{args.base_url}/api/", timeout=5)
            if response.status_code != 200:
                print(f"警告: Django服务器响应异常 (状态码: {response.status_code})")
        except requests.RequestException:
            print("错误: 无法连接到Django服务器。请确保服务器正在运行。")
            print(f"启动命令: cd /home/sunupdate/agentic-interview && python manage.py runserver")
            sys.exit(1)

    if args.test:
        # 仅测试连接
        print("连接测试成功！Django服务器正常运行。")
        return

    # 运行测试
    try:
        summary = tester.run_all_tests(
            start_id=args.start_id,
            end_id=args.end_id,
            delay=args.delay
        )

        if "error" in summary:
            print(f"测试失败: {summary['error']}")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n用户中断测试")
        # 保存当前进度
        tester.save_results_to_csv()
        print("进度已保存")
    except Exception as e:
        print(f"测试过程中发生错误: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
