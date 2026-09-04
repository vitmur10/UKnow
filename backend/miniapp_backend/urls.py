from django.conf import settings
from django.conf.urls.static import static
from django.http import FileResponse, Http404
from django.urls import path, re_path
from django.views.static import serve

from workspace.views import (
    message_media,
    message_voice,
    miniapp_auth,
    miniapp_bootstrap,
    miniapp_chat_history,
    miniapp_delete_message,
    miniapp_mark_read,
    miniapp_message_edits,
    miniapp_upload_attachment,
    miniapp_update_student,
)


def miniapp_index(request):
    index_path = settings.FRONTEND_DIST_DIR / "index.html"
    if not index_path.exists():
        raise Http404("Run npm run build in miniapp first")
    return FileResponse(open(index_path, "rb"))


urlpatterns = [
    path("api/miniapp/auth/", miniapp_auth, name="miniapp-auth"),
    path("api/miniapp/bootstrap/", miniapp_bootstrap, name="miniapp-bootstrap"),
    path("api/miniapp/chat/history/", miniapp_chat_history, name="miniapp-chat-history"),
    path("api/miniapp/student/update/", miniapp_update_student, name="miniapp-update-student"),
    path("api/miniapp/message/edits/", miniapp_message_edits, name="miniapp-message-edits"),
    path("api/miniapp/chat/read/", miniapp_mark_read, name="miniapp-mark-read"),
    path("api/miniapp/message/delete/", miniapp_delete_message, name="miniapp-delete-message"),
    path("api/miniapp/attachment/upload/", miniapp_upload_attachment, name="miniapp-upload-attachment"),
    path("api/messages/<int:message_id>/voice/", message_voice, name="message-voice"),
    path("api/messages/<int:message_id>/media/", message_media, name="message-media"),
    re_path(r"^miniapp/assets/(?P<path>.*)$", serve, {"document_root": settings.FRONTEND_DIST_DIR / "assets"}),
    re_path(r"^miniapp/?$", miniapp_index, name="miniapp-index-path"),
    re_path(r"^assets/(?P<path>.*)$", serve, {"document_root": settings.FRONTEND_DIST_DIR / "assets"}),
    path("", miniapp_index, name="miniapp-index"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
