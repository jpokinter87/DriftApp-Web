"""
Session API URL configuration.

Endpoints:
    GET    /api/session/current/            - Session de tracking en cours
    GET    /api/session/history/            - Liste des sessions sauvegardées
    GET    /api/session/history/<id>/       - Détail d'une session passée
    POST   /api/session/save/               - Sauvegarde manuelle de la session
    DELETE /api/session/delete/<id>/        - Suppression d'une session
    GET    /api/session/night/              - Frise d'une nuit (journal + sessions)
"""

from django.urls import path

from . import views

urlpatterns = [
    path('current/', views.current_session, name='session-current'),
    path('history/', views.session_history, name='session-history'),
    path('history/<str:session_id>/', views.session_detail, name='session-detail'),
    path('save/', views.save_session, name='session-save'),
    path('delete/<str:session_id>/', views.delete_session, name='session-delete'),
    path('night/', views.night_report, name='session-night'),
]
