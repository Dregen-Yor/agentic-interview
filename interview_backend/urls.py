"""
面试后端项目的URL配置。

`urlpatterns`列表将URL路由到视图。更多信息请参阅：
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
示例：
函数视图
    1. 添加导入：from my_app import views
    2. 向urlpatterns添加URL：path('', views.home, name='home')
基于类的视图
    1. 添加导入：from other_app.views import Home
    2. 向urlpatterns添加URL：path('', Home.as_view(), name='home')
包含另一个URLconf
    1. 导入include()函数：from django.urls import include, path
    2. 向urlpatterns添加URL：path('blog/', include('blog.urls'))
"""
# from django.contrib import admin  # 管理后台（已注释）
from django.urls import path, include

# URL模式配置
urlpatterns = [
    # path('admin/', admin.site.urls),  # 管理后台URL（已注释）
    path('api/', include('interview.urls')),  # 面试API路由
]
