from django.contrib import admin

from apps.persona.models import Facultad


@admin.register(Facultad)
class FacultadAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nombre')
