from django.contrib.auth.views import LogoutView
from django.urls import path

from accounts import views
from core import views as core_views

app_name = "accounts"

urlpatterns = [
    path("login/", views.welcome, name="welcome"),
    path("login/code/", views.code, name="code"),
    path("login/resend/", views.resend, name="resend"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("onboarding/", core_views.onboarding, name="onboarding"),
]
