from django.urls import path
import stats.views as views

urlpatterns = [
    path("raw", views.index, name="stats"),
    path("", views.stats, name="index"),
    path("filter", views.stats_filter, name="filter"),
]
