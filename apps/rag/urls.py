from django.urls import path

from . import views

app_name = "rag"

urlpatterns = [
    path("", views.library, name="library"),
    path("upload/", views.upload, name="upload"),
    path("<uuid:document_id>/status/", views.status, name="status"),
    path("<uuid:document_id>/delete/", views.delete, name="delete"),
]
