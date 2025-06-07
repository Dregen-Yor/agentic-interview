from django.urls import path

urlpatterns = [
    # 在这里添加你的应用路由
    # 指向 create_user 视图的路由，用于创建新用户
    # 访问地址: /interview/create/
    path('create/', users.new_user, name='create_user'),

    path('check/', users.check_user, name='check_user'),

    path('verify/', users.verify_token, name='verify_token'),
] 