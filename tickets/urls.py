from django.urls import path

from . import views

app_name = 'tickets'

urlpatterns = [
    path('', views.TicketListView.as_view(), name='list'),
    path('new/', views.TicketCreateView.as_view(), name='create'),
    path('<int:pk>/', views.TicketDetailView.as_view(), name='detail'),
    path('agent/', views.AgentTicketQueueView.as_view(), name='agent_queue'),
    path('agent/<int:pk>/', views.AgentTicketDetailView.as_view(), name='agent_detail'),
    path('agent/<int:pk>/status/', views.AgentTicketStatusUpdateView.as_view(), name='agent_status'),
    path('agent/<int:pk>/notes/', views.AgentTicketNoteCreateView.as_view(), name='agent_note_create'),
    path('agent/<int:pk>/regenerate/', views.AgentTicketRegenerateTriageView.as_view(), name='agent_regenerate_triage'),
    path('agent/<int:pk>/reply/', views.AgentTicketSendReplyView.as_view(), name='agent_send_reply'),
]
