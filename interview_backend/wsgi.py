"""
面试后端项目的WSGI配置。

它将WSGI可调用对象暴露为名为``application``的模块级变量。

有关此文件的更多信息，请参阅
https://docs.djangoproject.com/en/5.1/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

# 设置Django设置模块环境变量
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'interview_backend.settings')

# 获取WSGI应用程序
application = get_wsgi_application()
