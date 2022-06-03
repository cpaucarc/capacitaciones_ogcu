import base64
import uuid

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Value, Q
from django.db.models.functions import Concat
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views import View
from django.views.generic import CreateView, UpdateView
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK
from rest_framework.views import APIView

from apps.common.constants import DOCUMENT_TYPE_DNI, DOCUMENT_TYPE_CE
from apps.common.datatables_pagination import datatable_page
from apps.login.views import BaseLogin
from apps.persona.forms import PersonaForm, FirmanteForm
from apps.persona.models import Persona, Firmante


class PersonaCreateView(LoginRequiredMixin, BaseLogin, CreateView):
    template_name = 'persona/crear.html'
    model = Persona
    form_class = PersonaForm
    msg = None

    def form_valid(self, form):
        persona = form.save(commit=False)
        persona.creado_por = self.request.user.username
        persona.save()
        return HttpResponseRedirect(self.get_success_url())

    def form_invalid(self, form):
        if self.msg:
            messages.warning(self.request, self.msg)
        else:
            messages.warning(self.request, 'Ha ocurrido un error al crear a la persona')
        return super().form_invalid(form)

    def get_success_url(self):
        messages.success(self.request, 'Persona creada con éxito')
        return reverse('persona:crear_persona')


class PersonaUpdateView(LoginRequiredMixin, BaseLogin, UpdateView):
    template_name = 'persona/crear.html'
    model = Persona
    form_class = PersonaForm
    msg = None

    def form_valid(self, form):
        persona = form.save(commit=False)
        persona.modificado_por = self.request.user.username
        persona.save()
        return HttpResponseRedirect(self.get_success_url())

    def form_invalid(self, form):
        if self.msg:
            messages.warning(self.request, self.msg)
        else:
            messages.warning(self.request, 'Ha ocurrido un error al crear a la persona')
        return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'tip_persona': self.object.tipo_persona
        })
        return context

    def get_success_url(self):
        messages.success(self.request, 'Persona actualizada con éxito')
        return reverse('persona:crear_persona')


class BuscarPersonaAPIView(APIView):

    def get(self, request):
        numero_documento = self.request.GET.get('q', '')
        if numero_documento.isdigit() and len(numero_documento) == 8:
            tipo_documento = DOCUMENT_TYPE_DNI
        else:
            tipo_documento = DOCUMENT_TYPE_CE
        persona = Persona.objects.filter(tipo_documento=tipo_documento, numero_documento=numero_documento).first()
        data = []
        if persona:
            data.append({
                'id': persona.id,
                'text': persona.nombre_completo,
                'tipo_documento': persona.tipo_documento,
                'numero_documento': persona.numero_documento,
            })
        return Response(data, content_type='application/json')


class ListaPersonaView(LoginRequiredMixin, BaseLogin, View):
    def get(self, request, *args, **kwargs):
        search_param = self.request.GET.get('search[value]')
        filtro = self.request.GET.get('filtro')
        personas = Persona.objects.none()
        if filtro:
            ''
        else:
            personas = Persona.objects.filter(es_activo=True).order_by('-fecha_creacion')
        if len(search_param) > 3:
            personas = personas.annotate(
                search=Concat('apellido_paterno', Value(' '), 'apellido_materno', Value(' '), 'nombres')).filter(
                Q(search__icontains=search_param) | Q(numero_documento=search_param))
        draw, page = datatable_page(personas, request)
        lista_personas_data = []
        cont = 0
        for a in page.object_list:
            cont = cont + 1
            lista_personas_data.append([
                cont,
                '{} {}'.format(a.get_tipo_documento_display(), a.numero_documento),
                a.nombre_completo,
                a.celular or '-',
                a.email or '-',
                a.get_tipo_persona_display(),
                a.get_cargo_miembro_display() or '-',
                '{}'.format(a.facultad if a.facultad else '-'),
                self.get_boton_editar(a),
                self.get_boton_eliminar(a),
            ])
        data = {
            'draw': draw,
            'recordsTotal': personas.count(),
            'recordsFiltered': personas.count(),
            'data': lista_personas_data
        }
        return JsonResponse(data)

    def get_boton_eliminar(self, a):
        boton_eliminar = '''<button class="btn btn-danger btn-sm eliminarc" data-id={0}>
                      <i class="fa fa-trash"></i></button>'''
        boton_eliminar = boton_eliminar.format(a.id)
        boton = '{0}'.format(boton_eliminar)
        return boton

    def get_boton_editar(self, a):
        link = reverse('persona:editar_persona', kwargs={'pk': a.id})
        boton_editar = '<a class="btn btn-warning btn-sm" href="{0}"><i class="fa fa-edit"></i></a>'
        boton_editar = boton_editar.format(link)
        boton = '{0}'.format(boton_editar)
        return boton


class EliminarPersonaView(LoginRequiredMixin, APIView):
    def get(self, request, *args, **kwargs):
        persona = get_object_or_404(Persona, id=self.kwargs.get('pk'))
        tipo_msg = ''
        persona.delete()
        msg = f'Persona eliminada correctamente'
        return Response({'msg': msg, 'tipo_msg': tipo_msg}, HTTP_200_OK)


class FirmanteCreateView(LoginRequiredMixin, BaseLogin, CreateView):
    template_name = 'persona/crear_firmante.html'
    model = Firmante
    form_class = FirmanteForm
    msg = None

    def form_valid(self, form):
        archivo_64 = None
        if self.request.FILES:
            ruta = self.request.FILES['firma']
            if ruta.size > 70000:
                self.msg = 'El archivo seleccionado debe ser menor que 70kB'
                return self.form_invalid(form)
            extension = ruta.name.split(".")[-1]
            ruta.name = f"{uuid.uuid4()}.{extension}"
            if extension != 'png':
                self.msg = 'El archivo seleccionado no es formato png'
                return self.form_invalid(form)
            archivo_64 = self.enconde_png(ruta)
        firmante = form.save(commit=False)
        firmante.firma = archivo_64
        firmante.save()
        return HttpResponseRedirect(self.get_success_url())

    def form_invalid(self, form):
        if self.msg:
            messages.warning(self.request, self.msg)
        else:
            messages.warning(self.request, 'Ha ocurrido un error al agregar al firmante')
        return super().form_invalid(form)

    def enconde_png(self, firma):
        base64_message = None
        try:
            enconde = base64.b64encode(firma.read())
            base64_message = enconde.decode('utf-8')
        except:  # noqa
            pass
        return base64_message

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            '':''
        })
        return context

    def get_success_url(self):
        messages.success(self.request, 'Firmante creada con éxito')
        return reverse('persona:crear_firmante')


class FirmanteUpdateView(LoginRequiredMixin, BaseLogin, UpdateView):
    template_name = 'persona/crear_firmante.html'
    model = Firmante
    form_class = FirmanteForm
    msg = None

    def form_valid(self, form):
        archivo_64 = None
        if self.request.FILES:
            ruta = self.request.FILES['firma']
            if ruta.size > 70000:
                self.msg = 'El archivo seleccionado debe ser menor que 70kB'
                return self.form_invalid(form)
            extension = ruta.name.split(".")[-1]
            ruta.name = f"{uuid.uuid4()}.{extension}"
            if extension != 'png':
                self.msg = 'El archivo seleccionado no es formato png'
                return self.form_invalid(form)
            archivo_64 = self.enconde_png(ruta)
        firmante = form.save(commit=False)
        if archivo_64:
            firmante.firma = archivo_64
        firmante.save()
        return HttpResponseRedirect(self.get_success_url())

    def form_invalid(self, form):
        if self.msg:
            messages.warning(self.request, self.msg)
        else:
            messages.warning(self.request, 'Ha ocurrido un error al actualizar al firmante')
        return super().form_invalid(form)

    def enconde_png(self, firma):
        base64_message = None
        try:
            enconde = base64.b64encode(firma.read())
            base64_message = enconde.decode('utf-8')
        except:  # noqa
            pass
        return base64_message

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'ambito_firmante': self.object.ambito,
            'firma64': self.object.firma
        })
        return context

    def get_success_url(self):
        messages.success(self.request, 'Firmante actualizado con éxito')
        return reverse('persona:crear_firmante')


class ListaFirmanteView(LoginRequiredMixin, BaseLogin, View):
    def get(self, request, *args, **kwargs):
        search_param = self.request.GET.get('search[value]')
        filtro = self.request.GET.get('filtro')
        firmantes = Firmante.objects.none()
        if filtro:
            ''
        else:
            firmantes = Firmante.objects.all().order_by('-id')
        if len(search_param) > 3:
            firmantes = firmantes.annotate(search=Concat('persona__apellido_paterno', Value(' '),
                                                         'persona__apellido_materno', Value(' '),
                                                         'persona__nombres')).filter(search__icontains=search_param)
        draw, page = datatable_page(firmantes, request)
        lista_firmantes_data = []
        cont = 0
        for a in page.object_list:
            cont = cont + 1
            lista_firmantes_data.append([
                cont,
                '{} {}'.format(a.persona.get_tipo_documento_display(), a.persona.numero_documento),
                a.persona.nombre_completo,
                a.get_ambito_display(),
                '{}'.format(a.facultad if a.facultad else '-'),
                self.get_boton_editar(a),
                self.get_boton_eliminar(a),
            ])
        data = {
            'draw': draw,
            'recordsTotal': firmantes.count(),
            'recordsFiltered': firmantes.count(),
            'data': lista_firmantes_data
        }
        return JsonResponse(data)

    def get_boton_eliminar(self, a):
        boton_eliminar = '''<button class="btn btn-danger btn-sm eliminarc" data-id={0}>
                      <i class="fa fa-trash"></i></button>'''
        boton_eliminar = boton_eliminar.format(a.id)
        boton = '{0}'.format(boton_eliminar)
        return boton

    def get_boton_editar(self, a):
        link = reverse('persona:editar_firmante', kwargs={'pk': a.id})
        boton_editar = '<a class="btn btn-warning btn-sm" href="{0}"><i class="fa fa-edit"></i></a>'
        boton_editar = boton_editar.format(link)
        boton = '{0}'.format(boton_editar)
        return boton


class EliminarFirmanteView(LoginRequiredMixin, APIView):
    def get(self, request, *args, **kwargs):
        firmante = get_object_or_404(Firmante, id=self.kwargs.get('pk'))
        tipo_msg = ''
        firmante.delete()
        msg = f'Firmante eliminado correctamente'
        return Response({'msg': msg, 'tipo_msg': tipo_msg}, HTTP_200_OK)
