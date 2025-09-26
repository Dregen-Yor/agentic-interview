#!/usr/bin/env python3
"""
监控自动化攻击测试脚本的运行状态
"""

import os
import time
from datetime import datetime

def monitor_attack():
    print("🔍 监控自动化攻击测试脚本...")
    print("=" * 60)

    log_file = "attack_output.log"

    while True:
        if os.path.exists(log_file):
            # 获取文件信息
            size = os.path.getsize(log_file)
            modified_time = os.path.getmtime(log_file)
            modified_str = datetime.fromtimestamp(modified_time).strftime('%H:%M:%S')

            print(f"📄 日志文件大小: {size:,} bytes")
            print(f"⏰ 最后更新: {modified_str}")

            # 读取最后几行
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            if lines:
                print(f"\n📝 最新输出 (最后8行):")
                for line in lines[-8:]:
                    if line.strip():
                        print(f"   {line.strip()}")

                # 检查是否完成
                recent_lines = ''.join(lines[-10:]).lower()
                if any(keyword in recent_lines for keyword in ['完成', 'finished', 'done', '测试结束']):
                    print("\n✅ 脚本可能已完成运行!")
                    break

                # 检查进度
                total_tests = 103  # 从之前看到的信息
                current_progress = 0

                for line in reversed(lines[-50:]):  # 检查最近50行
                    if '开始测试攻击 ID:' in line:
                        try:
                            current_id = int(line.split('ID:')[-1].strip())
                            current_progress = current_id
                            break
                        except:
                            pass

                if current_progress > 0:
                    progress_percent = (current_progress / total_tests) * 100
                    print(".1f")
        else:
            print("⏳ 等待日志文件生成...")

        print(f"\n🔄 下次检查: {datetime.now().strftime('%H:%M:%S')}")
        print("-" * 40)

        # 检查进程是否还在运行
        import subprocess
        try:
            result = subprocess.run(['pgrep', '-f', 'automated_attack_test.py'],
                                  capture_output=True, text=True)
            if result.returncode == 0:
                print("🟢 脚本正在运行")
            else:
                print("🔴 脚本已停止")
                break
        except:
            print("⚠️ 无法检查进程状态")

        time.sleep(15)  # 每15秒检查一次

    print("\n" + "=" * 60)
    print("🎉 监控结束!")

if __name__ == "__main__":
    monitor_attack()
