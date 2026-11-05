from django.urls import path

from . import views

app_name = "chat"

urlpatterns = [
    path("", views.conversation_list, name="list"),
    path("new/", views.conversation_create, name="create"),
    path("search/", views.conversation_search, name="search"),
    path("<uuid:conversation_id>/", views.conversation_detail, name="detail"),
    path("<uuid:conversation_id>/messages/", views.conversation_messages, name="messages"),
    path("<uuid:conversation_id>/send/", views.conversation_send, name="send"),
    path("<uuid:conversation_id>/settings/", views.conversation_settings, name="settings"),
    path("<uuid:conversation_id>/archive/", views.conversation_archive, name="archive"),
    path("<uuid:conversation_id>/clear/", views.conversation_clear, name="clear"),
    path("<uuid:conversation_id>/delete/", views.conversation_delete, name="delete"),
    path("<uuid:conversation_id>/export/", views.conversation_export, name="export"),
]
