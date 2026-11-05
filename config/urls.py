from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.core.urls")),
    path("accounts/", include("apps.accounts.urls")),
    path("accounts/", include("django.contrib.auth.urls")),
    path("c/", include("apps.chat.urls")),
    path("documents/", include("apps.rag.urls")),
    path("usage/", include("apps.usage.urls")),
    path("api/v1/", include("apps.api.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

admin.site.site_header = "Chatbot Admin"
admin.site.site_title = "Chatbot Admin"
admin.site.index_title = "Operations"
