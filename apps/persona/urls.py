from django.urls import path
from apps.persona.views import (BuscarPersonaAPIView, PersonaCreateView, ListaPersonaView, PersonaUpdateView,
                                EliminarPersonaView, FirmanteCreateView, ListaFirmanteView, EliminarFirmanteView,
                                FirmanteUpdateView)
app_name = 'persona'
urlpatterns = [
    path('crear-persona', PersonaCreateView.as_view(), name='crear_persona'),
    path('buscar-persona', BuscarPersonaAPIView.as_view(), name='buscar-persona'),
    path('listar-persona', ListaPersonaView.as_view(), name='listar_persona'),
    path('editar-persona/<str:pk>/', PersonaUpdateView.as_view(), name='editar_persona'),
    path('eliminar/<str:pk>', EliminarPersonaView.as_view(), name='eliminar_persona'),
    path('crear-firmante', FirmanteCreateView.as_view(), name='crear_firmante'),
    path('listar-firmante', ListaFirmanteView.as_view(), name='listar_firmante'),
    path('eliminar-firmante/<str:pk>', EliminarFirmanteView.as_view(), name='eliminar_firmante'),
    path('editar-firmante/<str:pk>/', FirmanteUpdateView.as_view(), name='editar_firmante'),
]
