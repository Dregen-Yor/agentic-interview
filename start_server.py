#!/usr/bin/env python3
"""
Django服务器启动脚本
用于自动化测试前的服务器启动
"""

import subprocess
import time
import sys
import os
import signal
import requests

def start_django_server(port: int = 8000, timeout: int = 30):
    """
    启动Django开发服务器

    Args:
        port: 服务器端口
        timeout: 启动超时时间（秒）

    Returns:
        subprocess.Popen: 服务器进程对象
    """
    print(f"正在启动Django服务器 (端口: {port})...")

    # 设置环境变量
    env = os.environ.copy()
    env.setdefault('DJANGO_SETTINGS_MODULE', 'interview_backend.settings')

    # 启动服务器进程
    try:
        process = subprocess.Popen(
            [sys.executable, 'manage.py', 'runserver', f'0.0.0.0:{port}'],
            cwd='/home/sunupdate/agentic-interview',
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        print(f"Django服务器进程已启动 (PID: {process.pid})")

        # 等待服务器启动
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = requests.get(f'http://localhost:{port}/api/', timeout=2)
                if response.status_code == 200:
                    print("Django服务器启动成功！")
                    return process
            except requests.RequestException:
                pass

            time.sleep(1)

        print(f"等待服务器启动超时 ({timeout}秒)")
        process.terminate()
        return None

    except Exception as e:
        print(f"启动Django服务器失败: {e}")
        return None

def stop_django_server(process):
    """停止Django服务器"""
    if process and process.poll() is None:
        print(f"正在停止Django服务器 (PID: {process.pid})...")
        try:
            process.terminate()
            process.wait(timeout=10)
            print("Django服务器已停止")
        except subprocess.TimeoutExpired:
            print("强制终止Django服务器...")
            process.kill()
            process.wait()

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Django服务器启动脚本')
    parser.add_argument('--port', type=int, default=8000, help='服务器端口 (默认: 8000)')
    parser.add_argument('--timeout', type=int, default=30, help='启动超时时间 (默认: 30秒)')

    args = parser.parse_args()

    server_process = start_django_server(args.port, args.timeout)

    if server_process:
        print("服务器已启动，按Ctrl+C停止...")

        def signal_handler(signum, frame):
            stop_django_server(server_process)
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        try:
            server_process.wait()
        except KeyboardInterrupt:
            stop_django_server(server_process)
    else:
        print("服务器启动失败")
        sys.exit(1)
