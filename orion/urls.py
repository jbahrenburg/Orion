"""
URL configuration for orion project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path

from core import views as core_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path("", core_views.landing_page, name="landing"),

    path("signup/", core_views.signup, name="account_signup"),
    path("login/", core_views.login_view, name="account_login"),
    path("logout/", core_views.logout_view, name="account_logout"),

    path("films/", core_views.film_list, name="film_list"),
    path("films/add/", core_views.add_film, name="add_film"),
    path("films/rank/<int:user_film_id>", core_views.rank_film, name="rank_film"),
]
