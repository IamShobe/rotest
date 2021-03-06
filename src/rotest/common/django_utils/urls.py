"""Django definitions for the administrator site urls."""
from django.contrib import admin
from django.conf.urls import include, url

import rotest.frontend.urls

admin.autodiscover()
urlpatterns = [
    url(r'^$', include("frontend.urls")),
    url(r'^admin/', include(admin.site.urls)),
]
