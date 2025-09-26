#!/usr/bin/env python3
"""
简单易懂的攻击测试监控脚本
"""

import os
import time
from datetime import datetime
import re

def parse_log_file():
    """解析日志文件，提取关键信息"""
    log_file = "attack_output.log"

    if not os.path.exists(log_file):
        return None

    with open(log_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # 解析信息
    info = {
        'total_tests': 103,  # 从之前的信息知道
        'completed_tests': 0,
        'success_count': 0,
        'grades': {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'E': 0},
        'current_test': 0,
        'last_update': None,
        'errors': 0
    }

    # 统计已完成的测试
    completed_matches = re.findall(r'✅ 测试 (\d+) 成功', content)
    info['completed_tests'] = len(completed_matches)

    # 统计成功次数
    success_matches = re.findall(r'✅ 测试 .* 成功', content)
    info['success_count'] = len(success_matches)

    # 统计各等级评分
    grade_matches = re.findall(r'等级: ([A-E])', content)
    for grade in grade_matches:
        if grade in info['grades']:
            info['grades'][grade] += 1

    # 统计错误
    error_matches = re.findall(r'HTTP错误|Error|错误', content)
    info['errors'] = len(error_matches)

    # 查找当前正在处理的测试
    current_matches = re.findall(r'开始测试攻击 ID: (\d+)', content)
    if current_matches:
        info['current_test'] = int(current_matches[-1])

    # 获取文件修改时间
    if os.path.exists(log_file):
        info['last_update'] = datetime.fromtimestamp(os.path.getmtime(log_file))

    return info

def print_status():
    """打印易懂的状态信息"""
    os.system('clear')  # 清屏

    print("🚀 攻击测试监控面板")
    print("=" * 50)

    info = parse_log_file()
    if not info:
        print("⏳ 等待日志文件生成...")
        return

    # 基本信息
    progress = (info['completed_tests'] / info['total_tests']) * 100
    print(".1f"
    print(f"📊 总进度: {info['completed_tests']}/{info['total_tests']} 个测试")

    # 当前状态
    if info['current_test'] > 0:
        print(f"🎯 正在处理: 第 {info['current_test']} 个测试")

    # 成功率
    if info['completed_tests'] > 0:
        success_rate = (info['success_count'] / info['completed_tests']) * 100
        print(".1f"
    # 评分分布
    print("
📈 评分分布:"    total_graded = sum(info['grades'].values())
    if total_graded > 0:
        for grade, count in info['grades'].items():
            if count > 0:
                percentage = (count / total_graded) * 100
                bar = "█" * int(percentage / 5)  # 简单的条形图
                print("6")
    else:
        print("  暂无评分数据"

    # 错误统计
    if info['errors'] > 0:
        print(f"\n⚠️  错误次数: {info['errors']}")

    # 时间信息
    if info['last_update']:
        print(f"\n⏰ 最后更新: {info['last_update'].strftime('%H:%M:%S')}")

    # 进度条
    bar_length = 30
    filled_length = int(bar_length * progress / 100)
    bar = "█" * filled_length + "░" * (bar_length - filled_length)
    print(f"\n📊 进度条: [{bar}] {progress:.1f}%")

def check_if_running():
    """检查脚本是否还在运行"""
    import subprocess
    try:
        result = subprocess.run(['pgrep', '-f', 'automated_attack_test.py'],
                              capture_output=True, text=True)
        return result.returncode == 0
    except:
        return False

def main():
    print("🎯 启动简单监控模式...")
    print("💡 按 Ctrl+C 退出监控")

    try:
        while True:
            print_status()

            # 检查脚本是否还在运行
            if not check_if_running():
                print("\n" + "=" * 50)
                print("🔴 检测到脚本已停止运行!")
                print("💡 可以使用以下命令查看完整结果:")
                print("   tail -50 attack_output.log")
                print("   grep '等级:' attack_output.log")
                break

            print("\n🔄 5秒后刷新... (Ctrl+C 退出)")
            time.sleep(5)

    except KeyboardInterrupt:
        print("\n👋 监控已停止")
        print("💡 脚本仍在后台运行，可以随时重新启动监控")

if __name__ == "__main__":
    main()






