"""
URLs pour l'API hardware (moteur, encodeur).
"""
from django.urls import path
from . import views

urlpatterns = [
    path('goto/', views.GotoView.as_view(), name='motor-goto'),
    path('jog/', views.JogView.as_view(), name='motor-jog'),
    path('stop/', views.StopView.as_view(), name='motor-stop'),
    path('encoder/', views.EncoderView.as_view(), name='encoder-status'),
    path('status/', views.MotorStatusView.as_view(), name='motor-status'),
]
