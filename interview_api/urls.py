from django.urls import path
from . import views

urlpatterns = [
    path('select-problems/', views.select_problems_api, name='select_problems_api'),
] 