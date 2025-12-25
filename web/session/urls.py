"""
Session API URL configuration.
"""

from django.urls import path

from . import views

urlpatterns = [
    path('current/', views.current_session, name='session-current'),
    path('history/', views.session_history, name='session-history'),
    path('history/<str:session_id>/', views.session_detail, name='session-detail'),
    path('save/', views.save_session, name='session-save'),
    path('delete/<str:session_id>/', views.delete_session, name='session-delete'),
]
