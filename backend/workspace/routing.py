from django.urls import path

from .consumers import TeacherChatConsumer

websocket_urlpatterns = [
    path("ws/teacher/", TeacherChatConsumer.as_asgi()),
]

