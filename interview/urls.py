from django.urls import path

from . import users

app_name = 'api'

urlpatterns = [
    # 用户管理 / 简历 / 结果（HTTP）
    # 注：面试主流程已迁移到 WebSocket（interview/consumers.py），这里不再保留 HTTP 入口
    path('create/', users.new_user, name='create_user'),
    path('check/', users.check_user, name='check_user'),
    path('verify/', users.verify_token, name='verify_token'),
    path('resume/', users.get_user_resume, name='get_user_resume'),
    path('resume/update/', users.update_user_resume, name='update_user_resume'),
    path('result/', users.get_interview_result, name='get_interview_result'),
]
