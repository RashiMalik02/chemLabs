from django.urls import path
from . import views

urlpatterns = [
    path("start/",          views.start_reaction_view,  name="start_reaction"),
    path("stop/",           views.stop_reaction_view,   name="stop_reaction"),
    path("current/",        views.current_reaction_view, name="current_reaction"),
    path("video-feed/",     views.video_feed_view,      name="video_feed"),
    path("chemicals/",      views.chemicals_view,       name="chemicals"),
    path("set-chemical/",   views.set_chemical_view,    name="set_chemical"),
]