from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('biblioteca/', views.library, name='library'),
    path('item/<int:pk>/', views.item_detail, name='item_detail'),
    path('item/<int:pk>/favorito/', views.toggle_favorite, name='toggle_favorite'),
    path('conexoes/', views.connections, name='connections'),
]
