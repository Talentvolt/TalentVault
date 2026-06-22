from django.urls import path
from .views import (
    ClientListView,
    ClientDetailView,
    ClientCreateView,
    ClientUpdateView,
    ClientDeleteView
)

app_name = 'clients'

urlpatterns = [
    path('', ClientListView.as_view(), name='client_list'),
    path('new/', ClientCreateView.as_view(), name='client_create'),
    path('<uuid:pk>/', ClientDetailView.as_view(), name='client_detail'),
    path('<uuid:pk>/edit/', ClientUpdateView.as_view(), name='client_edit'),
    path('<uuid:pk>/delete/', ClientDeleteView.as_view(), name='client_delete'),
]
