"""
面试后端项目的ASGI配置。

它将ASGI可调用对象暴露为名为``application``的模块级变量。

有关此文件的更多信息，请参阅
https://docs.djangoproject.com/en/5.1/howto/deployment/asgi/
"""

import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

import interview.routing

# 设置Django设置模块环境变量
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "interview_backend.settings")
# 尽早初始化Django ASGI应用程序以确保在导入可能导入ORM模型的代码之前填充AppRegistry
django_asgi_app = get_asgi_application()

# ASGI应用程序配置
# 配置协议类型路由器以处理HTTP和WebSocket连接
application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,  # HTTP协议处理
        "websocket": AllowedHostsOriginValidator(  # WebSocket协议处理，带有主机验证
            AuthMiddlewareStack(URLRouter(interview.routing.websocket_urlpatterns))
        ),
    }
)
