#!/usr/bin/env python
"""Django管理工具的命令行实用程序。"""
import os
import sys


def main():
    """运行管理任务。"""
    # 设置Django设置模块的环境变量
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'interview_backend.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "无法导入Django。确保它已安装并在您的PYTHONPATH环境变量中可用吗？"
            "是否忘记激活虚拟环境？"
        ) from exc
    # 执行命令行参数
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
