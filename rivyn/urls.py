from django.contrib import admin
from django.urls import include, path

from accounts.views import HomeView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('', HomeView.as_view(), name='home'),
]
