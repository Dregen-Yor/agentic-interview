from django.urls import path
from . import views, users

app_name = 'api'

urlpatterns = [
    # 指向主面试聊天页面的路由
    path('', views.index, name='index'),

    # 现有用户管理的路由
    # 访问地址: /api/create/
    path('create/', users.new_user, name='create_user'),

    path('check/', users.check_user, name='check_user'),

    path('verify/', users.verify_token, name='verify_token'),

    path('resume/', users.get_user_resume, name='get_user_resume'),

    path('resume/update/', users.update_user_resume, name='update_user_resume'),

    path('result/', users.get_interview_result, name='get_interview_result'),

    path('face2faceChat/', views.face2face_chat, name='face2face_chat'),
] 