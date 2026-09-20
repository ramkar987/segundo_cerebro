from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('biblioteca/', views.library, name='library'),
    path('item/<int:pk>/', views.item_detail, name='item_detail'),
    path('item/<int:pk>/progresso/', views.item_progress, name='item_progress'),
    path('item/<int:pk>/favorito/', views.toggle_favorite, name='toggle_favorite'),
    path('relacao/<int:pk>/confirmar/', views.confirm_relation, name='confirm_relation'),
    path('relacao/<int:pk>/rejeitar/', views.reject_relation, name='reject_relation'),
    path('conexoes/', views.connections, name='connections'),
]
