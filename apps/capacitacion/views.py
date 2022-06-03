import base64
import os
import re
import uuid

import qrcode
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.mail import EmailMessage
from django.db import IntegrityError, transaction
from django.db.models import F, Value
from django.db.models.functions import Concat
from django.forms import inlineformset_factory
from django.http import HttpResponseRedirect, JsonResponse, FileResponse, Http404
from django.contrib import messages
from datetime import datetime
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, UpdateView, TemplateView
from django.urls import reverse
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Table, Paragraph, Image
from reportlab.graphics.barcode import code128
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK, HTTP_400_BAD_REQUEST
from rest_framework.views import APIView

from apps.capacitacion.forms import (CapacitacionForm, ActaAsistenciaForm, ModuloFormset,
                                     ModuloForm, EquipoProyectoFormset, EquipoProyectoForm)
from apps.capacitacion.models import (Capacitacion, ResponsableFirma, ActaAsistencia, DetalleAsistencia,
                                      NotaParticipante, Modulo, HistorialRevision, HistorialRevisionConsejo,
                                      EquipoProyecto, CertEmitido)
from apps.common.constants import (ESTADO_PROYECTO_REGISTRADO, DOCUMENT_TYPE_DNI, DOCUMENT_TYPE_CE,
                                   ESTADO_PROYECTO_VALIDADO, ESTADO_PROYECTO_CANCELADO, ESTADO_PROYECTO_CULMINADO,
                                   ESTADO_PROYECTO_OBSERVADO, TIPO_PERSONA_CONSEJO_UNASAM, AMBITO_UNASAM,
                                   TIPO_PERSONA_CONSEJO_FACULTAD, AMBITO_FACULTAD, EMISION_CERTIFICADO_UNICO,
                                   ESTADO_PROYECTO_POR_VALIDAR, EMISION_CERTIFICADO_MODULOS,
                                   EMISION_CERTIFICADO_UNICO_Y_MODULOS, CARGO_CERT_EMITIDO_ASISTENTE,
                                   TIPO_CERT_EMITIDO_UNICO, TIPO_CERT_EMITIDO_MODULO, ABREVIATURA_GRADO)
from apps.common.datatables_pagination import datatable_page
from apps.common.utils import PdfCertView
from apps.login.views import BaseLogin
from apps.persona.models import Persona, Firmante
from config.settings import MEDIA_ROOT, STATIC_ROOT
import pandas as pd
from reportlab.lib.pagesizes import letter


class CapacitacionCreateView(LoginRequiredMixin, BaseLogin, CreateView):
    template_name = 'capacitacion/crear.html'
    model = Capacitacion
    form_class = CapacitacionForm
    msg = None

    def dispatch(self, request, *args, **kwargs):
        if not (self.request.session.get('tipo_persona', None) == TIPO_PERSONA_CONSEJO_FACULTAD
                or self.request.session.get('username', None) == 'admin'):
            return redirect("login:403")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        context = self.get_context_data()
        modulo_formset = context['modulo_formset']
        equipo_formset = context['equipo_formset']
        if modulo_formset.is_valid() and equipo_formset.is_valid():
            cont = 0
            for m in modulo_formset:
                if m.cleaned_data.get('DELETE') is False:
                    cont += 1
            if cont == 0:
                self.msg = 'Falta agregar las horas y temario por módulo'
                return self.form_invalid(form)
            cont1 = 0
            for e in equipo_formset:
                if e.cleaned_data.get('DELETE') is False:
                    cont1 += 1
            if cont1 == 0:
                self.msg = 'Falta agregar miembro del equipo del proyecto de capacitación'
                return self.form_invalid(form)
            ruta = self.request.FILES['ruta_proyecto_pdf']
            extension = ruta.name.split(".")[-1]
            ruta.name = f"{uuid.uuid4()}.{extension}"
            if extension != 'pdf':
                self.msg = 'El archivo seleccionado no es formato PDF'
                return self.form_invalid(form)
            capacitacion = form.save(commit=False)
            capacitacion.ruta_proyecto_pdf = ruta
            capacitacion.creado_por = self.request.user.username
            if self.request.session.get('tipo_persona') == TIPO_PERSONA_CONSEJO_FACULTAD:
                capacitacion.ambito = AMBITO_FACULTAD
                capacitacion.facultad = self.request.user.persona.facultad
            else:
                capacitacion.ambito = AMBITO_UNASAM
            capacitacion = form.save()
            mod_formset = modulo_formset.save(commit=False)
            for m in mod_formset:
                m.capacitacion = capacitacion
                m.save()
            equip_formset = equipo_formset.save(commit=False)
            for e in equip_formset:
                e.capacitacion = capacitacion
                e.save()
            return HttpResponseRedirect(self.get_success_url())
        else:
            return self.form_invalid(form)

    def form_invalid(self, form):
        if self.msg:
            messages.warning(self.request, self.msg)
        else:
            messages.warning(self.request, 'Ha ocurrido un error al crear el Proyecto de capacitación')
        return super().form_invalid(form)

    def get_modulo_formset(self):
        return ModuloFormset(self.request.POST or None)

    def get_equipo_formset(self):
        return EquipoProyectoFormset(self.request.POST or None)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'modulo_formset': self.get_modulo_formset(),
            'equipo_formset': self.get_equipo_formset(),
        })
        return context

    def get_success_url(self):
        messages.success(self.request, 'Proyecto de capacitación creado')
        return reverse('capacitacion:crear_capacitacion')


class CapacitacionUpdateView(LoginRequiredMixin, BaseLogin, UpdateView):
    template_name = 'capacitacion/crear.html'
    model = Capacitacion
    form_class = CapacitacionForm
    msg = None
    ids_errors = []

    def dispatch(self, request, *args, **kwargs):
        if not (self.request.session.get('tipo_persona', None) == TIPO_PERSONA_CONSEJO_FACULTAD
                or self.request.session.get('username', None) == 'admin'):
            return redirect("login:403")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        context = self.get_context_data()
        ruta = None
        if self.object.estado not in (
                ESTADO_PROYECTO_POR_VALIDAR, ESTADO_PROYECTO_REGISTRADO, ESTADO_PROYECTO_OBSERVADO):
            self.msg = 'solo puede editar si la capacitación tiene estado Por validar, Registrado o Observado'
            return self.form_invalid(form)
        modulos_formset = ModuloFormset(self.request.POST or None, instance=self.object)
        equipo_formset = context['equipo_formset']
        if modulos_formset.is_valid() and equipo_formset.is_valid():
            equipo_formset = equipo_formset.save(commit=False)
            equipo_array = []
            for f in equipo_formset:
                equipo_array.append('{}-{}'.format(f.cargo, f.persona))
            equipo_array_repetidos = set(equipo_array)
            if len(equipo_array_repetidos) != len(equipo_array):
                self.msg = 'No puede duplicarse el mismo cargo para un solo miembro'
                return self.form_invalid(form)
            if self.request.FILES:
                ruta = self.request.FILES['ruta_proyecto_pdf']
                extension = ruta.name.split(".")[-1]
                ruta.name = f"{uuid.uuid4()}.{extension}"
                if extension != 'pdf':
                    self.msg = 'El archivo seleccionado no es formato PDF'
                    return self.form_invalid(form)
            capacitacion = form.save(commit=False)
            if ruta:
                capacitacion.ruta_proyecto_pdf = ruta
            if self.request.session.get('tipo_persona') == TIPO_PERSONA_CONSEJO_FACULTAD:
                capacitacion.ambito = AMBITO_FACULTAD
                capacitacion.facultad = self.request.user.persona.facultad
            else:
                capacitacion.ambito = AMBITO_UNASAM
            capacitacion.modificado_por = self.request.user.username
            capacitacion.save()
            for m_form in modulos_formset:
                if m_form.cleaned_data.get('id'):
                    if m_form.cleaned_data.get('DELETE'):
                        try:
                            Modulo.objects.filter(id=m_form.cleaned_data.get('id').id).delete()
                        except Exception:
                            self.msg = 'No se puede eliminar el módulo, tiene acta de asistencia registrada'
                            self.ids_errors.append(m_form.cleaned_data.get('id').id)
                            return self.form_invalid(form)
                    else:
                        Modulo.objects.filter(id=m_form.cleaned_data.get('id').id).update(
                            horas_academicas=m_form.cleaned_data.get('horas_academicas'),
                            temas=m_form.cleaned_data.get('temas'),
                            capacitacion=capacitacion,
                        )
                else:
                    if not m_form.cleaned_data.get('DELETE'):
                        m_form.save()
            self.object.equipoproyecto_set.all().delete()
            for e in equipo_formset:
                e.capacitacion = capacitacion
                e.save()

            return HttpResponseRedirect(self.get_success_url())
        else:
            return self.form_invalid(form)

    def form_invalid(self, form):
        if self.msg:
            messages.warning(self.request, self.msg)
        else:
            messages.warning(self.request, 'Ha ocurrido un error al crear el Proyecto de capacitación')
        return super().form_invalid(form)

    def get_equipo_formset(self):
        equipo = self.object.equipoproyecto_set.all()
        formset_initial = [{'id': e.id, 'cargo': e.cargo, 'cargo_equipo': e.get_cargo_display(),
                            'persona_id': e.persona_id, 'persona_equipo': e.persona}
                           for e in equipo]
        formset_equipo = inlineformset_factory(Capacitacion, EquipoProyecto, form=EquipoProyectoForm,
                                               can_delete=True, extra=equipo.count())
        formset = formset_equipo(
            data=self.request.POST or None,
            initial=formset_initial,
        )
        return formset

    def get_modulo_formset(self):
        modulos = self.object.modulo_set.all()
        formset_initial = [{'id': m.id, 'horas_academicas': m.horas_academicas, 'temas': m.temas, 'nombre': m.nombre}
                           for m in modulos]
        formset_modulos = inlineformset_factory(Capacitacion, Modulo, form=ModuloForm, can_delete=True,
                                                extra=modulos.count())
        formset = formset_modulos(
            data=self.request.POST or None,
            initial=formset_initial,
        )
        return formset

    def get_archivo_cargado(self):
        archivo = '{}'.format(self.object.ruta_proyecto_pdf).replace('proyectos/', '').replace('.pdf', '')
        return archivo

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'modulo_formset': self.get_modulo_formset(),
            'equipo_formset': self.get_equipo_formset(),
            'archivo': self.get_archivo_cargado() if self.object.ruta_proyecto_pdf else '',
            'ids_errors': self.ids_errors,
        })
        return context

    def get_success_url(self):
        messages.success(self.request, 'Proyecto de capacitación actualizado')
        return reverse('capacitacion:crear_capacitacion')


class ListaCapacitacionView(LoginRequiredMixin, BaseLogin, View):
    def get(self, request, *args, **kwargs):
        search_param = self.request.GET.get('search[value]')
        filtro = self.request.GET.get('filtro')
        capacitaciones = Capacitacion.objects.none()
        if filtro:
            ''
        else:
            capacitaciones = Capacitacion.objects.filter(creado_por=self.request.user.username
                                                         ).order_by('-fecha_creacion')
        if len(search_param) > 3:
            capacitaciones = capacitaciones.filter(nombre__icontains=search_param)
        draw, page = datatable_page(capacitaciones, request)
        lista_equipos_data = []
        cont = 0
        for a in page.object_list:
            cont = cont + 1
            mm = 0
            mod_cont = 0
            color = ''
            asistencia = ''
            for m in a.modulo_set.all():
                mod_cont += 1
                acta = ActaAsistencia.objects.filter(modulo=m).order_by('fecha_creacion').first()
                if acta:
                    mm += 1
                    asistencia = asistencia + '''<a class="btn btn-success btn-xs" 
                    style="margin-top:2px;margin-left:2px;" href="{}">{}</a>'''.format(
                        reverse('capacitacion:ver_acta_asistencia', kwargs={'id': acta.id}), 'Ver acta {}'.format(mm))
                else:
                    if mod_cont == mm + 1:
                        if a.estado in (ESTADO_PROYECTO_VALIDADO, ESTADO_PROYECTO_OBSERVADO):
                            asistencia = asistencia + '''<a class='btn btn-primary btn-xs' 
                            style="margin-top:2px;margin-left:2px;" href='{}'>{}</a>'''.format(
                                reverse('capacitacion:crear_acta_asistencia', kwargs={'id': m.id}),
                                'Crear acta {}'.format(mod_cont))
            boton_envia_revision = ''
            if a.estado == ESTADO_PROYECTO_VALIDADO:
                color = 'text-success'
            elif a.estado == ESTADO_PROYECTO_OBSERVADO:
                color = 'text-warning'
                boton_envia_revision = '''<button class="btn btn-success btn-xs parevision" data-id={}>
                                        Enviar a revision</button>'''.format(a.id)
            elif a.estado == ESTADO_PROYECTO_CULMINADO:
                color = 'text-info'
            elif a.estado == ESTADO_PROYECTO_POR_VALIDAR:
                color = 'text-warning'
            elif a.estado == ESTADO_PROYECTO_CANCELADO:
                color = 'text-danger'
            elif a.estado == ESTADO_PROYECTO_REGISTRADO:
                boton_envia_revision = '''<button class="btn btn-success btn-xs parevision" data-id={}>
                                        Enviar a revision</button>'''.format(a.id)
            lista_equipos_data.append([
                cont,
                a.nombre,
                '{} al {}'.format(a.fecha_inicio, a.fecha_fin),
                mod_cont,
                a.observacion_revision or '-',
                '<label class="{}">{}</label>{}'.format(color, a.get_estado_display(), boton_envia_revision),
                ('''<button class="btn btn-info btn-xs" id="ver_archivo_pdf" data-archivo={}>
                  Ver PDF</button>'''.format(a.ruta_proyecto_pdf) if a.ruta_proyecto_pdf else ''
                 ),
                asistencia,
                self.get_boton_editar(a),
                self.get_boton_eliminar(a) if a.estado == ESTADO_PROYECTO_REGISTRADO else '',
            ])
        data = {
            'draw': draw,
            'recordsTotal': capacitaciones.count(),
            'recordsFiltered': capacitaciones.count(),
            'data': lista_equipos_data
        }
        return JsonResponse(data)

    def get_boton_eliminar(self, a):
        boton_eliminar = '''<button class="btn btn-danger btn-sm eliminarc" data-id={0}>
                      <i class="fa fa-trash"></i></button>'''
        boton_eliminar = boton_eliminar.format(a.id)
        boton = '{0}'.format(boton_eliminar)
        return boton

    def get_boton_editar(self, a):
        link = reverse('capacitacion:editar', kwargs={'pk': a.id})
        boton_editar = '<a class="btn btn-warning btn-sm" href="{0}"><i class="fa fa-edit"></i></a>'
        boton_editar = boton_editar.format(link)
        boton = '{0}'.format(boton_editar)
        return boton


class ProyectoDescargaPdf(LoginRequiredMixin, View):
    def get(self, request, **kwargs):
        archivo = kwargs["archivo"]
        try:
            return FileResponse(open(F'{MEDIA_ROOT}/proyectos/{archivo}.pdf', 'rb'), content_type='application/pdf')
        except FileNotFoundError:
            raise Http404()


class EliminarCapacitacionView(LoginRequiredMixin, APIView):
    def get(self, request, *args, **kwargs):
        capacitacion = get_object_or_404(Capacitacion, id=self.kwargs.get('pk'))
        tipo_msg = ''
        if capacitacion and capacitacion.estado != ESTADO_PROYECTO_REGISTRADO:
            tipo_msg = 'warning'
            msg = f'No se puede eliminar, solo se puede eliminar un proyecto en estado registrado'
        else:
            capacitacion.delete()
            msg = f'Capacitación eliminado correctamente'
        return Response({'msg': msg, 'tipo_msg': tipo_msg}, HTTP_200_OK)


class EnviaParaRevisionView(LoginRequiredMixin, APIView):
    def get(self, request, *args, **kwargs):
        capacitacion = get_object_or_404(Capacitacion, id=self.kwargs.get('pk'))
        tipo_msg = ''
        capacitacion.estado = ESTADO_PROYECTO_POR_VALIDAR
        capacitacion.save()
        msg = f'Capacitación envíado para revisión correctamente'
        return Response({'msg': msg, 'tipo_msg': tipo_msg}, HTTP_200_OK)


class EliminarActaView(LoginRequiredMixin, APIView):
    def get(self, request, *args, **kwargs):
        acta = get_object_or_404(ActaAsistencia, id=self.kwargs.get('pk'))
        tipo_msg = ''
        if acta and (acta.modulo.capacitacion.estado != ESTADO_PROYECTO_OBSERVADO
                     and acta.modulo.capacitacion.estado != ESTADO_PROYECTO_VALIDADO):
            tipo_msg = 'warning'
            msg = 'Solo se puede eliminar si el estado del proyecto de capacitación es validado o observado'
        else:
            acta.notaparticipante_set.all().delete()
            acta.detalleasistencia_set.all().delete()
            acta.evidencia_set.all().delete()
            acta.delete()
            msg = 'Acta eliminado correctamente'
        return Response({'msg': msg, 'tipo_msg': tipo_msg}, HTTP_200_OK)


class EliminarResponsableFirmanteView(LoginRequiredMixin, APIView):
    def get(self, request, *args, **kwargs):
        responsable_firma = get_object_or_404(ResponsableFirma, id=self.kwargs.get('pk'))
        responsable_firma.delete()
        tipo_msg = ''
        msg = 'Firmante asignado quitado correctamente'
        return Response({'msg': msg, 'tipo_msg': tipo_msg}, HTTP_200_OK)


class ActaAsistenciaCreateView(LoginRequiredMixin, BaseLogin, CreateView):
    template_name = 'capacitacion/crear_acta_asistencia.html'
    model = ActaAsistencia
    form_class = ActaAsistenciaForm
    msg = None
    numdoc = None

    def dispatch(self, request, *args, **kwargs):
        if not (self.request.session.get('tipo_persona', None) == TIPO_PERSONA_CONSEJO_FACULTAD
                or self.request.session.get('username', None) == 'admin'):
            return redirect("login:403")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({
            'id_capacitacion': self.kwargs.get('id'),
        })
        return kwargs

    def validate(self, date_text):
        try:
            fec = datetime.strptime(date_text, '%d-%m-%Y').date()
            return fec
        except ValueError:
            return False

    def post(self, request, *args, **kwargs):
        form = self.form_class(request.POST)
        ruta_acta_pdf = None
        context = {
            'tipo_persona': self.request.session.get('tipo_persona'),
            'tipo_persona_desc': self.request.session.get('tipo_persona_desc'),
            'username': self.request.session.get('username'),
            'fullname': self.request.session.get('fullname'),
            'form': form
        }
        if request.FILES:
            ruta_excel_asistencia = request.FILES['excel_asistencia']
            archivo_excel = pd.read_excel(ruta_excel_asistencia)
            extension = ruta_excel_asistencia.name.split(".")[-1]
            ruta_excel_asistencia.name = f"{uuid.uuid4()}.{extension}"
            if extension != 'xlsx':
                self.msg = 'El archivo no es un .xlsx'
                messages.warning(self.request, self.msg)
                return render(request, self.template_name, context)
            if request.FILES.get('ruta_acta_pdf', False):
                ruta_acta_pdf = request.FILES['ruta_acta_pdf']
                extension = ruta_acta_pdf.name.split(".")[-1]
                ruta_acta_pdf.name = f"{uuid.uuid4()}.{extension}"
                if extension != 'pdf':
                    self.msg = 'El archivo no es un .pdf'
                    messages.warning(self.request, self.msg)
                    return render(request, self.template_name, context)
            modulo = get_object_or_404(Modulo, pk=self.kwargs.get('id'))
            if modulo.capacitacion.estado not in (ESTADO_PROYECTO_VALIDADO, ESTADO_PROYECTO_OBSERVADO):
                self.msg = 'No puede crear acta de asistencia porque el proyecto no está en estado validado o observado'
                messages.warning(self.request, self.msg)
                return render(request, self.template_name, context)
            datos = archivo_excel.values.tolist()
            columnas = archivo_excel.columns.tolist()
            # numdoc = archivo_excel['num_doc'].values
            cant_fechas = len(columnas) - 8
            array_fechas = []
            array_acta = []
            array_asistencia = []
            cont_error = 0
            for f in range(7, cant_fechas + 7):
                if self.validate(columnas[f]):
                    array_fechas.append(self.validate(columnas[f]))
                else:
                    cont_error += 1
            if cont_error > 0:
                self.msg = 'Verificar que las cabeceras fecha tengan el formato DD-MM-YYYY'
                messages.warning(self.request, self.msg)
                return render(request, self.template_name, context)
            if (columnas[0] != 'tipo_doc' or columnas[1] != 'num_doc' or columnas[2] != 'nombres'
                    or columnas[3] != 'apellido_paterno' or columnas[5] != 'sexo' or columnas[6] != 'correo'
                    or columnas[len(columnas) - 1] != 'resultado'):
                self.msg = '''Las cabeceras del excel tienen que tener el siguiente formato: tipo_doc, num_doc,
                            nombres, apellido_paterno, apellido_materno, sexo("M" o "F"), correo, fechas(DD-MM-YYYY),
                             resultado'''
                messages.warning(self.request, self.msg)
                return render(request, self.template_name, context)
            cont = 0
            for d in datos:
                cont += 1
                tipdoc = DOCUMENT_TYPE_DNI if d[0] == 'DNI' else DOCUMENT_TYPE_CE
                if d[0] == 'DNI':
                    if str(d[1]).isdigit() and len(str(d[1])) == 8:
                        self.numdoc = d[1]
                    else:
                        self.msg = 'Error en el número de documento!. Verificar el Excel'.format(cont)
                elif d[0] == 'CE':
                    if str(d[1]).isdigit():
                        self.numdoc = d[1]
                    else:
                        self.msg = 'Error en el número de documento!. Verificar el Excel'.format(cont)
                else:
                    self.msg = 'Error en el tipo de documento, solo está permitido DNI y CE'
                if d[len(columnas) - 1] not in ('APROBADO', 'DESAPROBADO'):
                    self.msg = 'Error en el campo resultado, solo está permitido: APROBADO o DESAPROBADO (en Mayúscula)'
                elif not (d[2] or d[3]):
                    self.msg = 'Verifique que estén completo el apellido paterno y nombres de los participantes'
                elif d[5] not in ('M', 'F'):
                    self.msg = 'Las opciones par el campo sexo es "M" o "F". Corregir'
                elif not d[6]:
                    self.msg = '''Verifique que esté completo los datos de correo electrónico ya que es un dato
                                  obligatorio'''
                elif d[6]:
                    if not re.match('^[(a-z0-9\_\-\.)]+@[(a-z0-9\_\-\.)]+\.[(a-z)]{2,15}$', d[6].lower()):  # noqa
                        self.msg = 'Formato de correo incorrecto, revisar el archivo Excel'
                array_a = []
                for f in range(7, cant_fechas + 7):
                    array_a.append(str(d[f]))
                    if d[f] not in ('P', 'F'):
                        self.msg = 'La asistencia por fecha debe ser "P" o "F". Verificar'
                array_asistencia.append(",".join(array_a))
                if self.msg:
                    messages.warning(self.request, self.msg)
                    return render(request, self.template_name, context)
                else:
                    persona = Persona.objects.filter(tipo_documento=tipdoc, numero_documento=self.numdoc).first()
                if persona:
                    persona.sexo = '1' if d[5] == 'M' else '2'
                    persona.email = d[6].lower() if d[6] else ''
                    persona.save()
                    array_acta.append({
                        'id_persona': persona.id,
                        'resultado': d[len(columnas) - 1]
                    })
                else:
                    array_acta.append({
                        'id_persona': '',
                        'tipo_doc': tipdoc,
                        'num_doc': self.numdoc,
                        'nombres': d[2].upper(),
                        'apellido_paterno': d[3].upper(),
                        'apellido_materno': d[4].upper() if d[4] else '',
                        'sexo': d[5],
                        'correo': d[6].lower() if d[6] else '',
                        'resultado': d[len(columnas) - 1]
                    })
            cont = 0
            # Crear Acta de asistencia
            acta = ActaAsistencia.objects.create(
                ruta_acta_pdf=ruta_acta_pdf,
                observacion='',
                modulo=modulo,
                creado_por=self.request.user.username,
            )
            for asistencia in array_asistencia:
                if not array_acta[cont].get('id_persona'):
                    persona = Persona.objects.create(
                        tipo_documento=array_acta[cont].get('tipo_doc'),
                        numero_documento=array_acta[cont].get('num_doc'),
                        nombres=array_acta[cont].get('nombres'),
                        apellido_paterno=array_acta[cont].get('apellido_paterno'),
                        apellido_materno=array_acta[cont].get('apellido_materno'),
                        sexo='1' if array_acta[cont].get('sexo') == 'M' else '2',
                        email=array_acta[cont].get('correo')
                    )
                    persona_id = persona.id
                else:
                    persona_id = array_acta[cont].get('id_persona')
                # crea nota
                NotaParticipante.objects.create(
                    acta_asistencia=acta,
                    resultado=array_acta[cont].get('resultado'),
                    persona_id=persona_id,
                )
                cc = 0
                for a in asistencia.split(','):
                    DetalleAsistencia.objects.create(
                        fecha=array_fechas[cc],
                        estado=a,
                        persona_id=persona_id,
                        acta_asistencia=acta,
                    )
                    cc += 1
                cont += 1

            return HttpResponseRedirect(self.get_success_url())
        else:
            messages.warning(self.request, self.msg)
            return render(request, self.template_name, context)

    def get_success_url(self):
        messages.success(self.request, 'Acta de asistencia creado')
        return reverse('capacitacion:crear_capacitacion')


class VerActaAsistenciaView(LoginRequiredMixin, BaseLogin, TemplateView):
    template_name = 'capacitacion/ver_acta_asistencia.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        acta = get_object_or_404(ActaAsistencia, pk=self.kwargs.get('id'))
        fechas_unicas = acta.detalleasistencia_set.only('fecha', 'estado').distinct('fecha').order_by('fecha')
        participantes = acta.detalleasistencia_set.only('persona').distinct('persona')
        array_asistencia = []
        for p in participantes:
            detalles = DetalleAsistencia.objects.filter(persona_id=p.persona_id, acta_asistencia=acta).order_by('fecha')
            array_a = []
            for d in detalles:
                array_a.append(d.estado)
            array_asistencia.append({
                'id_acta': d.acta_asistencia_id,
                'id_persona': d.persona_id,
                'numero_documento': p.persona.numero_documento,
                'apellido_paterno': p.persona.apellido_paterno,
                'apellido_materno': p.persona.apellido_materno,
                'nombres': p.persona.nombres,
                'estados': array_a,
                'resultado': acta.notaparticipante_set.filter(persona=p.persona).last().resultado,
            })
        context.update({
            'acta': acta,
            'fechas_unicas': fechas_unicas,
            'list_participantes': sorted(array_asistencia, key=lambda x: x['apellido_paterno'])
        })
        return context


class VerActaAsistenciaModalView(LoginRequiredMixin, BaseLogin, TemplateView):
    template_name = 'capacitacion/ver_acta_asistencia_modal.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        mostrar_pdf = True
        mostrar_pdf_unico = True
        permitido = True
        capacitacion = get_object_or_404(Capacitacion, pk=self.kwargs.get('capacitacion_id'))
        acta = get_object_or_404(ActaAsistencia, pk=self.kwargs.get('id'))
        if capacitacion != acta.modulo.capacitacion:
            permitido = False
        if capacitacion.tipo_emision_certificado == EMISION_CERTIFICADO_UNICO:
            ultimo_modulo = capacitacion.modulo_set.all().last()
            if ultimo_modulo != acta.modulo:
                mostrar_pdf = False
        if capacitacion.tipo_emision_certificado == EMISION_CERTIFICADO_UNICO_Y_MODULOS:
            ultimo_modulo = capacitacion.modulo_set.all().last()
            if ultimo_modulo != acta.modulo:
                mostrar_pdf_unico = False
        fechas_unicas = acta.detalleasistencia_set.only('fecha', 'estado').distinct('fecha').order_by('fecha')
        participantes = acta.detalleasistencia_set.only('persona').distinct('persona')
        array_asistencia = []
        for p in participantes:
            detalles = DetalleAsistencia.objects.filter(persona_id=p.persona_id, acta_asistencia=acta).order_by('fecha')
            array_a = []
            for d in detalles:
                array_a.append(d.estado)
            array_asistencia.append({
                'id_acta': d.acta_asistencia_id,
                'id_persona': d.persona_id,
                'numero_documento': p.persona.numero_documento,
                'apellido_paterno': p.persona.apellido_paterno,
                'apellido_materno': p.persona.apellido_materno,
                'nombres': p.persona.nombres,
                'estados': array_a,
                'resultado': acta.notaparticipante_set.filter(persona=p.persona).last().resultado,
            })
        context.update({
            'acta': acta,
            'es_permitido': permitido,
            'fechas_unicas': fechas_unicas,
            'list_participantes': sorted(array_asistencia, key=lambda x: x['apellido_paterno']),
            'estado_capacitacion': capacitacion.estado,
            'username': self.request.session.get('username', None),
            'tipo_persona': self.request.session.get('tipo_persona', None),
            'miembros_equipo': capacitacion.equipoproyecto_set.all(),
            'mostrar_pdf': mostrar_pdf,
            'mostrar_pdf_unico': mostrar_pdf_unico,
            'capacitacion_id': capacitacion.id,
            'tipo_emision_cert': capacitacion.tipo_emision_certificado,
        })
        return context


class GeneraCertificadoPdf(LoginRequiredMixin, PdfCertView):
    filename = 'Certificado-{}.pdf'.format(timezone.now().strftime('%d/%m/%Y %H:%M:%S'))
    disposition = 'attachment'
    canvas = None
    id_acta = None
    participantes = None
    capacitacion = None
    path_code_qr = None
    horas_academicas = 0
    nota_participante = None
    temarios = []
    fecha_culminado = None
    persona = None
    cantidad_cert = 0
    equipo_proyecto = []
    mostrar_pdf = False
    miembro = None
    correlativo = None

    def dispatch(self, request, *args, **kwargs):
        self.filename = 'Certificado-{}.pdf'.format(timezone.now().strftime('%d/%m/%Y %H:%M:%S'))
        if not self.kwargs.get('capacitacion', None):
            self.capacitacion = get_object_or_404(Capacitacion, pk=self.kwargs.get('id_capacitacion'))
        else:
            self.capacitacion = self.kwargs.get('capacitacion', None)
        if not self.kwargs.get('persona', None):
            self.persona = get_object_or_404(Persona, pk=self.kwargs.get('id_persona'))
        else:
            self.persona = self.kwargs.get('persona', None)
        self.fecha_culminado = self.capacitacion.historialrevision_set.filter(
            estado=ESTADO_PROYECTO_CULMINADO).last().fecha_creacion
        modulo = None
        self.temarios = []
        self.equipo_proyecto = []
        self.miembro = None
        for modulo in self.capacitacion.modulo_set.all():
            self.temarios.append(modulo.temas)
            self.horas_academicas = self.horas_academicas + modulo.horas_academicas
        self.mostrar_pdf = NotaParticipante.objects.filter(acta_asistencia__modulo=modulo,
                                                           persona=self.persona, resultado='APROBADO').last()
        if self.kwargs.get('cargo', None):
            cargo = self.kwargs.get('cargo', None)
        else:
            cargo = self.request.GET.get('cargo', None)
        if cargo:
            self.miembro = self.capacitacion.equipoproyecto_set.filter(
                persona=self.persona, cargo=cargo).first()
            self.mostrar_pdf = True if self.miembro else False
            self.correlativo = CertEmitido.objects.filter(modulo__capacitacion=self.capacitacion,
                                                          persona=self.miembro.persona,
                                                          cargo=cargo,
                                                          tipo=TIPO_CERT_EMITIDO_UNICO).first().correlativo
        else:
            self.correlativo = CertEmitido.objects.filter(modulo__capacitacion=self.capacitacion,
                                                          persona=self.persona,
                                                          cargo=CARGO_CERT_EMITIDO_ASISTENTE,
                                                          tipo=TIPO_CERT_EMITIDO_UNICO).first().correlativo
        self.cantidad_cert = 1
        code_qr = default_storage.save('temp_code_qr.png', ContentFile(''))
        self.path_code_qr = default_storage.path(code_qr)
        return super().dispatch(request, *args, **kwargs)

    def process_canvas(self, c):
        self.canvas = c
        self.encabezado()
        if self.mostrar_pdf:
            self.get_certificados()
        return c

    def encabezado(self):
        lWidth, lHeight = 'A4'
        self.canvas.setPageSize((lHeight, lWidth))
        self.style = getSampleStyleSheet()['BodyText']
        self.style.fontName = 'Times-Bold'
        self.style.alignment = TA_CENTER
        self.style.fontSize = 11
        self.style1 = getSampleStyleSheet()['Normal']
        self.style1.fontSize = 6
        self.style2 = getSampleStyleSheet()['Normal']
        self.style2.fontSize = 30
        self.style2.alignment = TA_CENTER
        self.style2.fontName = 'Times-Bold'
        self.style3 = getSampleStyleSheet()['Normal']
        self.style3.fontSize = 12
        self.style3.alignment = TA_CENTER
        self.style4 = getSampleStyleSheet()['Normal']
        self.style4.fontSize = 12
        self.style4.fontName = 'Times-Roman'
        self.style4.alignment = TA_JUSTIFY
        self.style4.padding = '20px'
        self.style5 = getSampleStyleSheet()['Normal']
        self.style5.fontSize = 16
        self.style5.alignment = TA_CENTER

    def generar_code_qr(self):
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data("https://www.google.com")
        qr.make(fit=True)

        img = qr.make_image(fill_color='black', back_color='white')
        img.save(self.path_code_qr)
        imagen = os.path.join(self.path_code_qr)
        width = 60
        y_start = 1
        self.canvas.drawImage(ImageReader(imagen), 270, y_start - 55, width=width, preserveAspectRatio=True,
                              mask='auto')
        os.remove(self.path_code_qr)

    def obtener_path_temporal_firma(self, id, firma):
        path = ''
        try:
            decode = base64.b64decode(firma)
            filename = default_storage.save('firma_{}_temp.jpg'.format(id), ContentFile(decode))
            path = default_storage.path(filename)
        except:  # noqa
            pass
        return path

    def get_certificados(self, **kwargs):
        mes = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Setiembre",
               "Octubre", "Noviembre", "Diciembre"]
        table_style1 = [
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.black, None, (2, 2, 1)),
            ('BOX', (0, 0), (-1, -1), 0.25, colors.black),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ('FONTSIZE', (0, 1), (0, -1), 10),
        ]
        model_cert1 = os.path.join(F'{STATIC_ROOT}', 'img', 'mod_cert1.png')
        self.canvas.drawImage(ImageReader(model_cert1), -4, -2, 620, 795)
        table_style4 = [('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('FONTSIZE', (0, 0), (-1, -1), 20), ]
        data2 = [[]] * 4
        data = [[]] * 4
        data6 = [[]] * 4
        contador = 0
        # Datos del certificado
        model_cert1 = os.path.join(F'{STATIC_ROOT}', 'img', 'mod_cert1.png')
        self.canvas.drawImage(ImageReader(model_cert1), -4, -2, 620, 795)
        cabecera1 = Paragraph('UNIVERSIDAD NACIONAL', style=self.style5)
        cabecera2 = Paragraph('SANTIAGO ANTUNEZ DE MAYOLO', style=self.style5)
        w, h = cabecera1.wrap(400, 0)
        cabecera1.drawOn(self.canvas, 105, 750 - h)
        w, h = cabecera2.wrap(400, 0)
        cabecera2.drawOn(self.canvas, 105, 728 - h)
        logo_unasam = os.path.join(F'{STATIC_ROOT}', 'img', 'logo-unasam.jpg')
        self.canvas.drawImage(ImageReader(logo_unasam), 231, 565, 147, 120)
        titulo = Paragraph('CERTIFICADO', style=self.style2)
        data2[0] = [titulo]
        ta = Table(data=data2, rowHeights=20, repeatCols=1, colWidths=610)
        ta.setStyle(table_style4)
        w, h = ta.wrap(0, 0)
        ta.drawOn(self.canvas, 1, 475)
        otorgado = Paragraph('Otorgado a:', style=self.style3)
        w, h = otorgado.wrap(100, 0)
        otorgado.drawOn(self.canvas, 45, 470 - h)
        # Nombre del participante
        contador += 1
        n_correlativo = ''
        if 'PRESENCIAL' in self.capacitacion.canal_reunion.upper():
            tipo_canal = 'presencial'
        else:
            tipo_canal = 'virtual'
        if self.miembro:
            parrafo1 = Paragraph('''Por haber participado en calidad de <b>"{}"</b> en el Curso de
                                 <b>"{}"</b>, llevado a cabo en forma {}, del {} al {} con una duración de <b>{} horas 
                                 académicas</b>.'''.format(self.miembro.get_cargo_display(),
                                                           self.capacitacion.nombre,
                                                           tipo_canal,
                                                           self.capacitacion.fecha_inicio.strftime('%d/%m/%Y'),
                                                           self.capacitacion.fecha_fin.strftime('%d/%m/%Y'),
                                                           self.horas_academicas),
                                 style=self.style4)
            data[0] = ['', self.persona.nombre_completo, '']
            res_correlativo = CertEmitido.objects.filter(modulo__capacitacion=self.capacitacion,
                                                         persona=self.persona,
                                                         cargo=self.persona.cargo,
                                                         tipo=TIPO_CERT_EMITIDO_UNICO).first()
            if res_correlativo:
                n_correlativo = res_correlativo.correlativo
        else:
            parrafo1 = Paragraph('''Por haber participado en calidad de <b>"Asistente"</b> en el Curso de
                                     <b>"{}"</b>, llevado a cabo en forma {}, del {} al {} con una duración de <b>{}
                                      horas académicas</b>.'''.format(self.capacitacion.nombre, tipo_canal,
                                                                      self.capacitacion.fecha_inicio.strftime(
                                                                          '%d/%m/%Y'),
                                                                      self.capacitacion.fecha_fin.strftime('%d/%m/%Y'),
                                                                      self.horas_academicas), style=self.style4)
            res_correlativo = CertEmitido.objects.filter(modulo__capacitacion=self.capacitacion,
                                                         persona=self.persona,
                                                         cargo=CARGO_CERT_EMITIDO_ASISTENTE,
                                                         tipo=TIPO_CERT_EMITIDO_UNICO).first()
            if res_correlativo:
                n_correlativo = res_correlativo.correlativo
            data[0] = ['', self.persona.nombre_completo, '']
        data[1] = ['', '', '']
        data[2] = ['', '', '']
        data[3] = ['', parrafo1, '']
        tab = Table(data=data, rowHeights=20, repeatCols=1, colWidths=[55, 500, 55])
        tab.setStyle(table_style4)
        w, h = tab.wrap(0, 0)
        tab.drawOn(self.canvas, 1, 400)
        self.canvas.setFont('Helvetica', 10)
        self.canvas.drawString(100, 365, 'Huaraz, {} de {} de {}'.format(self.fecha_culminado.day,
                                                                         mes[self.fecha_culminado.month],
                                                                         self.fecha_culminado.year))

        responsables_firma = self.capacitacion.responsablefirma_set.all()
        cx = 0
        cant_firmas = responsables_firma.count()
        table_style = [
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
        ]
        for f in responsables_firma:
            data3 = [['']]
            data4 = [['']] * 4
            path_temp_firma = ''
            if f.firmante.firma:
                path_temp_firma = self.obtener_path_temporal_firma(f.id, f.firmante.firma)
            if path_temp_firma:
                a = Image(path_temp_firma, width=85, height=85)
                data3[0] = [a]
            tt = Table(data=data3, rowHeights=70, repeatCols=1, colWidths=230)
            tt.setStyle(table_style)
            w, h = tt.wrap(0, 0)
            if cant_firmas == 2:
                tt.drawOn(self.canvas, 65 + cx, 250)
            else:
                tt.drawOn(self.canvas, 50 + cx, 250)
            data4[0] = ['---------------------------------------------------------']
            data4[1] = [f.firmante]
            data4[2] = [f.get_tipo_firma_display()]
            tt = Table(data=data4, rowHeights=10, repeatCols=1, colWidths=230)
            tt.setStyle(table_style)
            w, h = tt.wrap(0, 0)
            if cant_firmas == 2:
                tt.drawOn(self.canvas, 65 + cx, 215)
            else:
                tt.drawOn(self.canvas, 37 + cx, 215)
            if cant_firmas == 2:
                cx += 250
            else:
                cx += 150
            if path_temp_firma:
                os.remove(path_temp_firma)
        self.generar_code_qr()
        titulo1 = Paragraph('VICERRECTORADO ACADÉMICO', style=self.style3)
        sub_titulo1 = Paragraph('Consejo de Capacitación, Especialización y Actualización Docente',
                                style=self.style3)
        titulo2 = Paragraph('CCEAD UNASAM', style=self.style3)
        data6[0] = [titulo1]
        data6[1] = [sub_titulo1]
        data6[2] = [titulo2]
        ta = Table(data=data6, rowHeights=20, repeatCols=1, colWidths=610)
        ta.setStyle(table_style4)
        w, h = ta.wrap(0, 0)
        ta.drawOn(self.canvas, 1, 4)
        self.canvas.showPage()
        cxx = 0
        conta = 0
        codigo_barra = code128.Code128(barWidth=1.2, barHeight=25)
        codigo_barra.value = n_correlativo
        codigo_barra.drawOn(self.canvas, x=215, y=745)
        self.canvas.drawString(278, 730, n_correlativo)
        if len(self.temarios) == 1:
            temas = self.temarios[0].split('\n')
            data1 = [[]] * (len(temas) + 1)
            conta += 1
            mod = Paragraph('Temario', style=self.style)
            data1[0] = [mod]
            for x in range(1, len(temas) + 1):
                data1[x] = [temas[x - 1].strip()]
            tbl = Table(data=data1, rowHeights=30, repeatCols=1, colWidths=[513])
            tbl.setStyle(table_style1)
            w, h = tbl.wrap(0, 0)
            tbl.drawOn(self.canvas, 50 + cxx, 700 - h)
            cxx += 20
            self.canvas.showPage()
        else:
            for t in self.temarios:
                temas = t.split('\n')
                data1 = [[]] * (len(temas) + 1)
                conta += 1
                mod = Paragraph('Temario del Módulo {}'.format(conta), style=self.style)
                data1[0] = [mod]
                trow = 20
                espace = 0
                tem = 0
                for x in range(1, len(temas) + 1):
                    te3 = temas[x - 1].strip()
                    tem += 1
                    if len(temas[x - 1].strip()) >= 90:
                        trow = 30
                        espace = 30
                        te = temas[x - 1].strip()[:90]
                        pos_te = te.rfind(' ')
                        te1 = temas[x - 1].strip()[:pos_te]
                        te2 = temas[x - 1].strip()[pos_te:]
                        te3 = '{}\n  {}'.format(te1, te2)
                    data1[x] = [te3]
                tbl = Table(data=data1, rowHeights=trow, repeatCols=1, colWidths=[513])
                tbl.setStyle(table_style1)
                w, h = tbl.wrap(0, 0)
                tbl.drawOn(self.canvas, 50, (700 - h) - cxx + espace)
                cxx += 50 + (tem * 20)
            self.canvas.showPage()


class BandejaValidacionView(LoginRequiredMixin, BaseLogin, TemplateView):
    template_name = 'capacitacion/bandeja_validacion.html'

    def dispatch(self, request, *args, **kwargs):
        if not (self.request.session.get('tipo_persona', None) == TIPO_PERSONA_CONSEJO_UNASAM
                or self.request.session.get('username', None) == 'admin'):
            return redirect("login:403")
        return super().dispatch(request, *args, **kwargs)


class ListaCapacitacionValidarView(LoginRequiredMixin, BaseLogin, View):
    array_modulos = []

    def get(self, request, *args, **kwargs):
        search_param = self.request.GET.get('search[value]')
        filtro = self.request.GET.get('filtro')
        capacitaciones = Capacitacion.objects.none()
        if filtro:
            ''
        else:
            capacitaciones = Capacitacion.objects.all().exclude(
                estado=ESTADO_PROYECTO_REGISTRADO).order_by('-fecha_creacion')
        if len(search_param) > 3:
            capacitaciones = capacitaciones.filter(nombre__icontains=search_param)
        draw, page = datatable_page(capacitaciones, request)
        lista_equipos_data = []
        cont = 0
        for a in page.object_list:
            cont = cont + 1
            asistencia = ''
            select1 = ''
            select2 = ''
            select3 = ''
            select4 = ''
            select5 = ''
            color = ''
            if a.estado == ESTADO_PROYECTO_POR_VALIDAR:
                select1 = 'selected'
                color = 'text-warning'
            elif a.estado == ESTADO_PROYECTO_VALIDADO:
                select2 = 'selected'
                color = 'text-success'
            elif a.estado == ESTADO_PROYECTO_CANCELADO:
                select3 = 'selected'
                color = 'text-danger'
            elif a.estado == ESTADO_PROYECTO_CULMINADO:
                select4 = 'selected'
                color = 'text-info'
            elif a.estado == ESTADO_PROYECTO_OBSERVADO:
                select5 = 'selected'
                color = 'text-warning'
            mod_cont = 0
            mm = 0
            self.array_modulos = []
            for m in a.modulo_set.all():
                self.array_modulos.append(m)
                mod_cont += 1
                acta = ActaAsistencia.objects.filter(modulo=m).order_by('fecha_creacion').first()
                if acta:
                    mm += 1
                    asistencia = asistencia + '''<button class="btn btn-success btn-xs v-acta" data-id="{}" 
                    capacitacion-id="{}" style="margin-top:2px;margin-left:2px;"> Ver acta {}
                    </button>'''.format(acta.id, a.id, mm)
            combo = '''<input type='hidden' value='{}' id='estado-{}'>
                   <select id='accion_revisar' class='{} form-control' data-id='{}'>
                   <option value='por_validar' {}>Por validar</option>
                   <option value='validado' {}>Validado</option>""
                   <option value='cancelado' {}>Cancelado</option>
                   <option value='culminado' {}>Culminado</option>
                   <option value='observado' {}>Observado</option>
                   </select><label id="msje1_{}"></label>
               '''.format(a.estado, a.id, color, a.id, select1, select2, select3, select4, select5, a.id)
            lista_equipos_data.append([
                cont,
                '<p style="font-size:14px;">{}</p>'.format(a.facultad or '-'),
                '<p style="font-size:14px;">{}</p>'.format(a.nombre),
                '<label style="font-size:12px;">{} al {}</label>'.format(a.fecha_inicio, a.fecha_fin),
                ('''<button class="btn btn-info btn-xs" id="ver_archivo_pdf" data-archivo={}>
                  Ver</button>'''.format(a.ruta_proyecto_pdf) if a.ruta_proyecto_pdf else ''
                 ),
                asistencia,
                a.observacion_revision or '-',
                combo if a.estado != ESTADO_PROYECTO_CULMINADO else '<label class="text-info"> {}</label>'.format(
                    a.get_estado_display()),
                self.get_boton_bandeja_asignar_firmante(a) if a.estado == ESTADO_PROYECTO_VALIDADO else '',
                self.get_boton_genera_certificados(a) if a.estado == ESTADO_PROYECTO_CULMINADO else '',
                (self.get_boton_envia_correo(a) if a.estado == ESTADO_PROYECTO_CULMINADO else '')
            ])
        data = {
            'draw': draw,
            'recordsTotal': capacitaciones.count(),
            'recordsFiltered': capacitaciones.count(),
            'data': lista_equipos_data
        }
        return JsonResponse(data)

    def get_boton_bandeja_asignar_firmante(self, a):
        link = reverse('capacitacion:bandeja_asignar_firmante', kwargs={'id': a.id})
        if a.responsablefirma_set.exists():
            boton = '<a class="btn btn-success btn-sm" href="{0}"><i class="fa fa-eye"></i></a>'
        else:
            boton = '<a class="btn btn-warning btn-sm" href="{0}"><i class="fa fa-plus"></i></a>'
        boton = boton.format(link)
        boton = '{0}'.format(boton)
        return boton

    def get_boton_genera_certificados(self, a):
        botones = ''
        if a.tipo_emision_certificado == EMISION_CERTIFICADO_UNICO:
            link = reverse('capacitacion:generar_certificados', kwargs={'id': a.id})
            boton = ''
            if a.responsablefirma_set.exists():
                boton = '<a class="btn btn-success btn-xs" href="{0}"><i class="fa fa-print"> Único PDF</i></a>'
            boton = boton.format(link)
            boton = '{0}'.format(boton)
            return boton
        elif a.tipo_emision_certificado == EMISION_CERTIFICADO_MODULOS:
            cc = 0
            for m in self.array_modulos:
                cc += 1
                link = reverse('capacitacion:generar_certificados_por_mod', kwargs={'id': a.id, 'id_modulo': m.id})
                boton = ''
                if a.responsablefirma_set.exists():
                    boton = '''<a class="btn btn-success btn-xs" href="{}" style="margin-top:2px;margin-left:2px;">
                            <i class="fa fa-print"> Modulo{} PDF</i></a>'''.format(link, cc)
                botones = botones + '{}'.format(boton)
            return botones
        elif a.tipo_emision_certificado == EMISION_CERTIFICADO_UNICO_Y_MODULOS:
            cc = 0
            link1 = reverse('capacitacion:generar_certificados', kwargs={'id': a.id})
            bot = '''<a class="btn btn-success btn-xs" href="{0}" style="margin-top:2px;margin-left:2px;">
                  <i class="fa fa-print"> Único PDF</i></a>'''.format(link1)
            for m in self.array_modulos:
                cc += 1
                link = reverse('capacitacion:generar_certificados_por_mod', kwargs={'id': a.id, 'id_modulo': m.id})
                boton = ''
                if a.responsablefirma_set.exists():
                    boton = '''<a class="btn btn-success btn-xs" href="{}" style="margin-top:2px;margin-left:2px;">
                                <i class="fa fa-print"> Modulo{} PDF</i></a>'''.format(link, cc)
                botones = botones + '{}'.format(boton)

            return bot + botones

    def get_boton_envia_correo(self, a):
        botones = ''
        if a.tipo_emision_certificado == EMISION_CERTIFICADO_UNICO:
            if a.se_envio_correo:
                return '<label class="text-success">Correo enviado</label>'
            boton = ''
            if a.responsablefirma_set.exists():
                boton = '''<button class="btn btn-info btn-xs enviar-correo ev-{}" data-id="{}">
                <i class="fa fa-envelope"> Enviar</i></button>'''
            boton = boton.format(a.id, a.id)
            boton = '{0}'.format(boton)
            return boton
        elif a.tipo_emision_certificado == EMISION_CERTIFICADO_MODULOS:
            cc = 0
            for m in self.array_modulos:
                cc += 1
                boton = ''
                if a.responsablefirma_set.exists():
                    if m.se_envio_correo:
                        boton = '<label class="text-success">mod{} enviado</label>'.format(cc)
                    else:
                        boton = '''<button class="btn btn-info btn-xs enviar-correo-mod evm-{}" data-id="{}" 
                                data-modulo="{}" style="margin-top:2px;margin-left:2px;"><i class="fa fa-envelope">
                                Enviar mod{}</i></button>'''.format(m.id, a.id, m.id, cc)
                botones = botones + '{}'.format(boton)
            return botones

        elif a.tipo_emision_certificado == EMISION_CERTIFICADO_UNICO_Y_MODULOS:
            cc = 0
            if a.se_envio_correo:
                boton1 = '<label class="text-success">Correo enviado</label>'.format(cc)
            else:
                boton1 = '''<button class="btn btn-info btn-xs enviar-correo ev-{}" data-id="{}">
                <i class="fa fa-envelope"> Enviar</i></button>'''
            for m in self.array_modulos:
                cc += 1
                boton = ''
                if a.responsablefirma_set.exists():
                    if m.se_envio_correo:
                        boton = '<label class="text-success">mod{} enviado</label>'.format(cc)
                    else:
                        boton = '''<button class="btn btn-info btn-xs enviar-correo-mod evm-{}" data-id="{}" 
                                data-modulo="{}" style="margin-top:2px;margin-left:2px;"><i class="fa fa-envelope">
                                Enviar mod{}</i></button>'''.format(m.id, a.id, m.id, cc)
                botones = botones + '{}'.format(boton)
            return boton1 + botones


class ObservaCapacitacionView(LoginRequiredMixin, APIView):
    def post(self, request, *args, **kwargs):
        if request.method == 'POST':
            data = request.POST
            capacitacion_id = data.get('id')
            if data.get('observacion') and len(data.get('observacion')) < 4:
                errors = 'Ingrese como mínimo 4 caracteres'
                return JsonResponse({'error': f"{errors}"}, status=HTTP_400_BAD_REQUEST)
            if capacitacion_id and data.get('observacion'):
                miembros_consejo = Persona.objects.filter(tipo_persona=TIPO_PERSONA_CONSEJO_UNASAM)
                if not miembros_consejo:
                    errors = 'No existe miembros del consejo UNASAM registrados, no puede realizar esta acción'
                    return JsonResponse({'error': f"{errors}"}, status=HTTP_400_BAD_REQUEST)
                capacitacion = get_object_or_404(Capacitacion, pk=capacitacion_id)
                capacitacion.observacion_revision = data.get('observacion')
                capacitacion.estado = ESTADO_PROYECTO_OBSERVADO
                capacitacion.save()
                revision = HistorialRevision.objects.create(creado_por=self.request.user.username,
                                                            capacitacion=capacitacion, estado=ESTADO_PROYECTO_OBSERVADO,
                                                            observacion=data.get('observacion'))
                for miembro in miembros_consejo:
                    HistorialRevisionConsejo.objects.create(ambito=AMBITO_UNASAM,
                                                            cargo_miembro=miembro.cargo_miembro,
                                                            persona=miembro,
                                                            revision=revision)
                msg = 'OK'
                return JsonResponse({'data': msg})
            else:
                errors = 'Error al realizar el registro, Realize la búsqueda e intente nuevamente'
                return JsonResponse({'error': f"{errors}"}, status=HTTP_400_BAD_REQUEST)


class RevisarCapacitacionView(LoginRequiredMixin, APIView):
    def post(self, request, *args, **kwargs):
        if request.method == 'POST':
            data = request.POST
            capacitacion_id = data.get('id')
            estado = data.get('estado')
            res = True
            if capacitacion_id:
                miembros_consejo = Persona.objects.filter(tipo_persona=TIPO_PERSONA_CONSEJO_UNASAM)
                if not miembros_consejo:
                    errors = 'No existe miembros del consejo UNASAM registrados, no puede realizar esta acción'
                    return JsonResponse({'error': f"{errors}"}, status=HTTP_400_BAD_REQUEST)
                capacitacion = get_object_or_404(Capacitacion, pk=capacitacion_id)
                if estado == ESTADO_PROYECTO_CULMINADO:
                    if capacitacion.responsablefirma_set.all().count() < 2:
                        errors = '''No se puede dar por culminado porque debe contar como mínimo con 2 firmantes
                                 asignados'''
                        return JsonResponse({'error': f"{errors}"}, status=HTTP_400_BAD_REQUEST)
                    modulos = [m for m in capacitacion.modulo_set.all()]
                    actas = [a for a in ActaAsistencia.objects.filter(modulo__capacitacion=capacitacion).order_by(
                        'modulo_id')]
                    if len(modulos) != len(actas):
                        errors = '''No se puede dar por culminado porque cuenta con módulo(s) sin acta de asistencia'''
                        return JsonResponse({'error': f"{errors}"}, status=HTTP_400_BAD_REQUEST)
                    res = self.insert_emision_cert(capacitacion, capacitacion.tipo_emision_certificado, modulos, actas)
                if res:
                    capacitacion.estado = estado
                    capacitacion.observacion_revision = None
                    capacitacion.save()
                    revision = HistorialRevision.objects.create(creado_por=self.request.user.username,
                                                                capacitacion=capacitacion, estado=estado)
                    for miembro in miembros_consejo:
                        HistorialRevisionConsejo.objects.create(ambito=AMBITO_UNASAM,
                                                                cargo_miembro=miembro.cargo_miembro,
                                                                persona=miembro,
                                                                revision=revision)
                        msg = 'OK'
                        return JsonResponse({'data': msg})
                else:
                    errors = 'Error al realizar el registro, Realize la búsqueda e intente nuevamente'
                    return JsonResponse({'error': f"{errors}"}, status=HTTP_400_BAD_REQUEST)
            else:
                errors = 'Error al realizar el registro, Realize la búsqueda e intente nuevamente'
                return JsonResponse({'error': f"{errors}"}, status=HTTP_400_BAD_REQUEST)

    def insert_emision_cert(self, capacitacion, tipo_emision_cert, modulos, actas_asistencias):
        res = False
        if tipo_emision_cert in (EMISION_CERTIFICADO_UNICO, EMISION_CERTIFICADO_UNICO_Y_MODULOS):
            aprobados = []
            desaprobados = []
            array_equipo_proyecto = []
            for acta in actas_asistencias:
                nota_participantes = NotaParticipante.objects.filter(acta_asistencia_id=acta.id).order_by('persona_id')
                persona_id = ''
                cc = 0
                desaprobado = 0
                for n in nota_participantes:
                    if n.resultado.upper() == 'DESAPROBADO':
                        cc += 1
                    if persona_id != n.persona_id:
                        persona_id = n.persona_id
                        desaprobado += cc
                        cc = 0
                        if desaprobado == 0:
                            aprobados.append(n.persona)
                        else:
                            desaprobados.append(n.persona)
                            desaprobado = 0
            ultimo_modulo = modulos[-1]
            array_participantes_aprobados = set(aprobados) - set(desaprobados)
            for equipo in capacitacion.equipoproyecto_set.all():
                array_equipo_proyecto.append(equipo)
            contador = 0
            try:
                for p in list(array_participantes_aprobados) + list(array_equipo_proyecto):
                    contador += 1
                    if contador > len(array_participantes_aprobados):
                        cert_emitido_existente = CertEmitido.objects.filter(modulo=ultimo_modulo, persona=p.persona,
                                                                            cargo=p.cargo,
                                                                            tipo=TIPO_CERT_EMITIDO_UNICO).first()
                        if not cert_emitido_existente:
                            CertEmitido.objects.create(modulo=ultimo_modulo, persona=p.persona, cargo=p.cargo,
                                                       creado_por=self.request.user.username,
                                                       modificado_por=self.request.user.username)
                    else:
                        cert_emitido_existente = CertEmitido.objects.filter(modulo=ultimo_modulo, persona=p,
                                                                            cargo=CARGO_CERT_EMITIDO_ASISTENTE,
                                                                            tipo=TIPO_CERT_EMITIDO_UNICO).first()
                        if not cert_emitido_existente:
                            CertEmitido.objects.create(modulo=ultimo_modulo, persona=p,
                                                       creado_por=self.request.user.username,
                                                       modificado_por=self.request.user.username,
                                                       cargo=CARGO_CERT_EMITIDO_ASISTENTE)
                res = True
            except Exception:
                res = False
        if tipo_emision_cert in (EMISION_CERTIFICADO_MODULOS, EMISION_CERTIFICADO_UNICO_Y_MODULOS):
            try:
                for m in modulos:
                    array_participantes_aprobados = []
                    array_equipo_proyecto = []
                    nota_participantes = NotaParticipante.objects.filter(
                        acta_asistencia__modulo=m, resultado__iexact='APROBADO').order_by('persona_id')
                    for equipo in capacitacion.equipoproyecto_set.all():
                        array_equipo_proyecto.append(equipo)
                    for n in nota_participantes:
                        array_participantes_aprobados.append(n.persona)
                    contador = 0
                    for p in list(array_participantes_aprobados) + list(array_equipo_proyecto):
                        contador += 1
                        if contador > len(array_participantes_aprobados):
                            cert_emitido_existente = CertEmitido.objects.filter(modulo=m, persona=p.persona,
                                                                                cargo=p.cargo,
                                                                                tipo=TIPO_CERT_EMITIDO_MODULO).first()
                            if not cert_emitido_existente:
                                CertEmitido.objects.create(modulo=m, persona=p.persona, cargo=p.cargo,
                                                           tipo=TIPO_CERT_EMITIDO_MODULO,
                                                           creado_por=self.request.user.username,
                                                           modificado_por=self.request.user.username)
                        else:
                            cert_emitido_existente = CertEmitido.objects.filter(modulo=m, persona=p,
                                                                                cargo=CARGO_CERT_EMITIDO_ASISTENTE,
                                                                                tipo=TIPO_CERT_EMITIDO_MODULO).first()
                            if not cert_emitido_existente:
                                CertEmitido.objects.create(modulo=m, persona=p, tipo=TIPO_CERT_EMITIDO_MODULO,
                                                           creado_por=self.request.user.username,
                                                           modificado_por=self.request.user.username,
                                                           cargo=CARGO_CERT_EMITIDO_ASISTENTE)
                res = True
            except Exception:
                res = False
        return res


class BandejaAsignarFirmanteView(LoginRequiredMixin, BaseLogin, TemplateView):
    template_name = 'capacitacion/asignar_firmante.html'

    def dispatch(self, request, *args, **kwargs):
        if not (self.request.session.get('tipo_persona', None) == TIPO_PERSONA_CONSEJO_UNASAM
                or self.request.session.get('username', None) == 'admin'):
            return redirect("login:403")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        capacitacion = get_object_or_404(Capacitacion, pk=self.kwargs.get('id'))
        firmantes = ResponsableFirma.objects.filter(capacitacion=capacitacion)
        context = super().get_context_data(**kwargs)
        context.update({
            'capacitacion': capacitacion,
            'firmantes': firmantes,
        })
        return context


class ListaFirmanteAmbitoView(LoginRequiredMixin, View):
    def get(self, request):
        data = [{'id': '', 'nombre': '----------'}]
        ambito = request.GET.get('ambito', '')
        id_facultad = request.GET.get('id_facultad', '')
        if ambito == 'unasam':
            firmantes = Firmante.objects.filter(ambito=ambito).annotate(
                nombre=Concat(F('persona__apellido_paterno'), Value(' '), F('persona__apellido_materno'), Value(' '),
                              F('persona__nombres'))).values('id', 'nombre')
        else:
            if id_facultad:
                firmantes = Firmante.objects.filter(facultad_id=id_facultad).annotate(
                    nombre=Concat(F('persona__apellido_paterno'), Value(' '), F('persona__apellido_materno'),
                                  Value(' '), F('persona__nombres'))).values('id', 'nombre')
            else:
                firmantes = Firmante.objects.filter(ambito=AMBITO_FACULTAD).annotate(
                    nombre=Concat(F('persona__apellido_paterno'), Value(' '), F('persona__apellido_materno'),
                                  Value(' '), F('persona__nombres'))).values('id', 'nombre')
        if firmantes:
            data = data + list(firmantes)
        return JsonResponse({'data': data})


class AsignarFirmanteView(LoginRequiredMixin, APIView):
    def post(self, request, *args, **kwargs):
        if request.method == 'POST':
            data = request.POST
            id_capacitacion = data.get('id_capacitacion')
            id_firmante = data.get('id_firmante')
            tipo_firma = data.get('id_tipo_firma')
            responsable_firma = ResponsableFirma.objects.filter(capacitacion_id=id_capacitacion).count()
            if responsable_firma == 3:
                errors = 'Error al asignar al firmante, solo puede asignar a 3 firmantes por proyecto de capacitación'
                return Response({'error': f"{errors}"}, HTTP_400_BAD_REQUEST)
            try:
                ResponsableFirma.objects.create(tipo_firma=tipo_firma, firmante_id=id_firmante,
                                                capacitacion_id=id_capacitacion)
                msg = 'OK'
                return JsonResponse({'data': msg})
            except IntegrityError:
                return JsonResponse({'error': "Ya existe el cargo para el firmante seleccionado"},
                                    status=HTTP_400_BAD_REQUEST)
            except Exception as ex:
                errors = 'Error al asignar al firmante recargue la página e intente nuevamente'
                return Response({'error': f"{errors}"}, HTTP_400_BAD_REQUEST)


class GenerarMultipleCertificadosPdfView(LoginRequiredMixin, PdfCertView):
    filename = 'Certificado-{}.pdf'.format(timezone.now().strftime('%d/%m/%Y %H:%M:%S'))
    disposition = 'attachment'
    canvas = None
    id_acta = None
    participantes = None
    capacitacion = None
    path_code_qr = None
    array_equipo_proyecto = []
    horas_academicas = 0
    temarios = []
    cantidad_cert = 0
    fecha_culminado = None
    correlativo = None
    array_participantes_aprobados = []

    def dispatch(self, request, *args, **kwargs):
        self.array_participantes_aprobados = []
        self.array_equipo_proyecto = []
        self.filename = 'Certificado-{}.pdf'.format(timezone.now().strftime('%d/%m/%Y %H:%M:%S'))
        self.capacitacion = get_object_or_404(Capacitacion, pk=kwargs.get('id'))
        self.fecha_culminado = self.capacitacion.historialrevision_set.filter(
            estado=ESTADO_PROYECTO_CULMINADO).last().fecha_creacion
        actas_asistencias = ActaAsistencia.objects.filter(modulo__capacitacion=self.capacitacion).order_by('modulo_id')
        aprobados = []
        desaprobados = []
        self.temarios = []
        for acta in actas_asistencias:
            self.temarios.append(acta.modulo.temas)
            self.horas_academicas = self.horas_academicas + acta.modulo.horas_academicas
            nota_participantes = NotaParticipante.objects.filter(acta_asistencia_id=acta.id).order_by('persona_id')
            persona_id = ''
            cc = 0
            desaprobado = 0
            for n in nota_participantes:
                if n.resultado.upper() == 'DESAPROBADO':
                    cc += 1
                if persona_id != n.persona_id:
                    persona_id = n.persona_id
                    desaprobado += cc
                    cc = 0
                    if desaprobado == 0:
                        aprobados.append(n.persona)
                    else:
                        desaprobados.append(n.persona)
                        desaprobado = 0
        self.array_participantes_aprobados = set(aprobados) - set(desaprobados)
        for equipo in self.capacitacion.equipoproyecto_set.all():
            self.array_equipo_proyecto.append(equipo)
        self.cantidad_cert = len(self.array_participantes_aprobados) + len(self.array_equipo_proyecto)
        code_qr = default_storage.save('temp_code_qr.png', ContentFile(''))
        self.path_code_qr = default_storage.path(code_qr)
        return super().dispatch(request, *args, **kwargs)

    def process_canvas(self, c):
        self.canvas = c
        self.encabezado()
        self.get_certificados()
        return c

    def encabezado(self):
        lWidth, lHeight = 'A4'
        self.canvas.setPageSize((lHeight, lWidth))
        self.style = getSampleStyleSheet()['BodyText']
        self.style.fontName = 'Times-Bold'
        self.style.alignment = TA_CENTER
        self.style.fontSize = 11
        self.style1 = getSampleStyleSheet()['Normal']
        self.style1.fontSize = 6
        self.style2 = getSampleStyleSheet()['Normal']
        self.style2.fontSize = 30
        self.style2.alignment = TA_CENTER
        self.style2.fontName = 'Times-Bold'
        self.style3 = getSampleStyleSheet()['Normal']
        self.style3.fontSize = 12
        self.style3.alignment = TA_CENTER
        self.style4 = getSampleStyleSheet()['Normal']
        self.style4.fontSize = 12
        self.style4.fontName = 'Times-Roman'
        self.style4.alignment = TA_JUSTIFY
        self.style4.padding = '20px'
        self.style5 = getSampleStyleSheet()['Normal']
        self.style5.fontSize = 16
        self.style5.alignment = TA_CENTER

    def generar_code_qr(self):
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data("https://www.google.com")
        qr.make(fit=True)

        img = qr.make_image(fill_color='black', back_color='white')
        img.save(self.path_code_qr)
        imagen = os.path.join(self.path_code_qr)
        width = 60
        y_start = 1
        self.canvas.drawImage(ImageReader(imagen), 270, y_start - 55, width=width, preserveAspectRatio=True,
                              mask='auto')
        os.remove(self.path_code_qr)

    def obtener_path_temporal_firma(self, id, firma):
        path = ''
        try:
            decode = base64.b64decode(firma)
            filename = default_storage.save('firma_{}_temp.jpg'.format(id), ContentFile(decode))
            path = default_storage.path(filename)
        except:  # noqa
            pass
        return path

    def get_certificados(self, **kwargs):
        mes = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Setiembre",
               "Octubre", "Noviembre", "Diciembre"]
        table_style1 = [
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.black, None, (2, 2, 1)),
            ('BOX', (0, 0), (-1, -1), 0.25, colors.black),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ('FONTSIZE', (0, 1), (0, -1), 10),
        ]
        model_cert1 = os.path.join(F'{STATIC_ROOT}', 'img', 'mod_cert1.png')
        self.canvas.drawImage(ImageReader(model_cert1), -4, -2, 620, 795)
        table_style4 = [('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('FONTSIZE', (0, 0), (-1, -1), 20), ]
        data2 = [[]] * 4
        data = [[]] * 4
        data6 = [[]] * 4
        contador = 0
        for p in list(self.array_participantes_aprobados) + list(self.array_equipo_proyecto):
            # Datos del certificado
            model_cert1 = os.path.join(F'{STATIC_ROOT}', 'img', 'mod_cert1.png')
            self.canvas.drawImage(ImageReader(model_cert1), -4, -2, 620, 795)
            cabecera1 = Paragraph('UNIVERSIDAD NACIONAL', style=self.style5)
            cabecera2 = Paragraph('SANTIAGO ANTUNEZ DE MAYOLO', style=self.style5)
            w, h = cabecera1.wrap(400, 0)
            cabecera1.drawOn(self.canvas, 105, 750 - h)
            w, h = cabecera2.wrap(400, 0)
            cabecera2.drawOn(self.canvas, 105, 728 - h)
            logo_unasam = os.path.join(F'{STATIC_ROOT}', 'img', 'logo-unasam.jpg')
            self.canvas.drawImage(ImageReader(logo_unasam), 231, 565, 147, 120)
            titulo = Paragraph('CERTIFICADO', style=self.style2)
            data2[0] = [titulo]
            ta = Table(data=data2, rowHeights=20, repeatCols=1, colWidths=610)
            ta.setStyle(table_style4)
            w, h = ta.wrap(0, 0)
            ta.drawOn(self.canvas, 1, 475)
            otorgado = Paragraph('Otorgado a:', style=self.style3)
            w, h = otorgado.wrap(100, 0)
            otorgado.drawOn(self.canvas, 45, 470 - h)
            # Nombre del participante
            contador += 1
            n_correlativo = ''
            if 'PRESENCIAL' in self.capacitacion.canal_reunion.upper():
                tipo_canal = 'presencial'
            else:
                tipo_canal = 'virtual'
            if contador > len(self.array_participantes_aprobados):
                parrafo1 = Paragraph('''Por haber participado en calidad de <b>"{}"</b> en el Curso de
                                 <b>"{}"</b>, llevado a cabo en forma {}, del {} al {} con una duración de <b>{} horas 
                                 académicas</b>.'''.format(p.get_cargo_display(),
                                                           self.capacitacion.nombre,
                                                           tipo_canal,
                                                           self.capacitacion.fecha_inicio.strftime('%d/%m/%Y'),
                                                           self.capacitacion.fecha_fin.strftime('%d/%m/%Y'),
                                                           self.horas_academicas),
                                     style=self.style4)
                data[0] = ['', p.persona.nombre_completo, '']
                res_correlativo = CertEmitido.objects.filter(modulo__capacitacion=self.capacitacion,
                                                             persona=p.persona,
                                                             cargo=p.cargo,
                                                             tipo=TIPO_CERT_EMITIDO_UNICO).first()
                if res_correlativo:
                    n_correlativo = res_correlativo.correlativo
            else:
                parrafo1 = Paragraph('''Por haber participado en calidad de <b>"Asistente"</b> en el Curso de
                                     <b>"{}"</b>, llevado a cabo en forma {}, del {} al {} con una duración de <b>{}
                                      horas académicas</b>.'''.format(self.capacitacion.nombre, tipo_canal,
                                                                      self.capacitacion.fecha_inicio.strftime(
                                                                          '%d/%m/%Y'),
                                                                      self.capacitacion.fecha_fin.strftime('%d/%m/%Y'),
                                                                      self.horas_academicas), style=self.style4)
                res_correlativo = CertEmitido.objects.filter(modulo__capacitacion=self.capacitacion,
                                                             persona=p,
                                                             cargo=CARGO_CERT_EMITIDO_ASISTENTE,
                                                             tipo=TIPO_CERT_EMITIDO_UNICO).first()
                if res_correlativo:
                    n_correlativo = res_correlativo.correlativo
                data[0] = ['', p.nombre_completo, '']
            data[1] = ['', '', '']
            data[2] = ['', '', '']
            data[3] = ['', parrafo1, '']
            tab = Table(data=data, rowHeights=20, repeatCols=1, colWidths=[55, 500, 55])
            tab.setStyle(table_style4)
            w, h = tab.wrap(0, 0)
            tab.drawOn(self.canvas, 1, 400)
            self.canvas.setFont('Helvetica', 10)
            self.canvas.drawString(100, 365, 'Huaraz, {} de {} de {}'.format(self.fecha_culminado.day,
                                                                             mes[self.fecha_culminado.month],
                                                                             self.fecha_culminado.year))
            responsables_firma = self.capacitacion.responsablefirma_set.all()
            cx = 0
            cant_firmas = responsables_firma.count()
            table_style = [
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
            ]
            for f in responsables_firma:
                data3 = [['']]
                data4 = [['']] * 4
                path_temp_firma = ''
                if f.firmante.firma:
                    path_temp_firma = self.obtener_path_temporal_firma(f.id, f.firmante.firma)
                if path_temp_firma:
                    a = Image(path_temp_firma, width=85, height=85)
                    data3[0] = [a]
                tt = Table(data=data3, rowHeights=70, repeatCols=1, colWidths=230)
                tt.setStyle(table_style)
                w, h = tt.wrap(0, 0)
                if cant_firmas == 2:
                    tt.drawOn(self.canvas, 65 + cx, 250)
                else:
                    tt.drawOn(self.canvas, 50 + cx, 250)
                data4[0] = ['---------------------------------------------------------']
                data4[1] = [f.firmante]
                data4[2] = [f.get_tipo_firma_display()]
                tt = Table(data=data4, rowHeights=10, repeatCols=1, colWidths=230)
                tt.setStyle(table_style)
                w, h = tt.wrap(0, 0)
                if cant_firmas == 2:
                    tt.drawOn(self.canvas, 65 + cx, 215)
                else:
                    tt.drawOn(self.canvas, 37 + cx, 215)
                if cant_firmas == 2:
                    cx += 250
                else:
                    cx += 150
                if path_temp_firma:
                    os.remove(path_temp_firma)
            # footer
            self.generar_code_qr()
            titulo1 = Paragraph('VICERRECTORADO ACADÉMICO', style=self.style3)
            sub_titulo1 = Paragraph('Consejo de Capacitación, Especialización y Actualización Docente',
                                    style=self.style3)
            titulo2 = Paragraph('CCEAD UNASAM', style=self.style3)
            data6[0] = [titulo1]
            data6[1] = [sub_titulo1]
            data6[2] = [titulo2]
            ta = Table(data=data6, rowHeights=20, repeatCols=1, colWidths=610)
            ta.setStyle(table_style4)
            w, h = ta.wrap(0, 0)
            ta.drawOn(self.canvas, 1, 4)
            self.canvas.showPage()
            cxx = 0
            conta = 0
            codigo_barra = code128.Code128(barWidth=1.2, barHeight=25)
            codigo_barra.value = n_correlativo
            codigo_barra.drawOn(self.canvas, x=215, y=745)
            self.canvas.drawString(278, 730, n_correlativo)
            if len(self.temarios) == 1:
                temas = self.temarios[0].split('\n')
                data1 = [[]] * (len(temas) + 1)
                conta += 1
                mod = Paragraph('Temario', style=self.style)
                data1[0] = [mod]
                for x in range(1, len(temas) + 1):
                    data1[x] = [temas[x - 1].strip()]
                tbl = Table(data=data1, rowHeights=30, repeatCols=1, colWidths=[513])
                tbl.setStyle(table_style1)
                w, h = tbl.wrap(0, 0)
                tbl.drawOn(self.canvas, 50 + cxx, 700 - h)
                cxx += 20
                self.canvas.showPage()
            else:
                for t in self.temarios:
                    temas = t.split('\n')
                    data1 = [[]] * (len(temas) + 1)
                    conta += 1
                    mod = Paragraph('Temario del Módulo {}'.format(conta), style=self.style)
                    data1[0] = [mod]
                    trow = 20
                    espace = 0
                    tem = 0
                    for x in range(1, len(temas) + 1):
                        te3 = temas[x - 1].strip()
                        tem += 1
                        if len(temas[x - 1].strip()) >= 90:
                            trow = 30
                            espace = 30
                            te = temas[x - 1].strip()[:90]
                            pos_te = te.rfind(' ')
                            te1 = temas[x - 1].strip()[:pos_te]
                            te2 = temas[x - 1].strip()[pos_te:]
                            te3 = '{}\n  {}'.format(te1, te2)
                        data1[x] = [te3]
                    tbl = Table(data=data1, rowHeights=trow, repeatCols=1, colWidths=[513])
                    tbl.setStyle(table_style1)
                    w, h = tbl.wrap(0, 0)
                    tbl.drawOn(self.canvas, 50, (700 - h) - cxx + espace)
                    cxx += 50 + (tem * 20)
                self.canvas.showPage()


class EnvioCertificadoMultiCorreo(View):
    persona = None
    capacitacion = None
    filename = 'Certificado_{}.pdf'
    horas_academicas = 0
    array_participantes_aprobados = 0

    def get(self, request, *args, **kwargs):
        self.capacitacion = Capacitacion.objects.filter(pk=kwargs.get('id_capacitacion')).first()
        actas_asistencias = ActaAsistencia.objects.filter(modulo__capacitacion=self.capacitacion)
        if self.capacitacion and actas_asistencias:
            aprobados = []
            desaprobados = []
            self.temarios = []
            self.array_equipo_proyecto = []
            array_errores = []
            array_enviados = []
            for acta in actas_asistencias:
                self.temarios.append(acta.modulo.temas)
                self.horas_academicas = self.horas_academicas + acta.modulo.horas_academicas
                nota_participantes = NotaParticipante.objects.filter(acta_asistencia_id=acta.id).order_by('persona_id')
                persona_id = ''
                cc = 0
                desaprobado = 0
                for n in nota_participantes:
                    if n.resultado.upper() == 'DESAPROBADO':
                        cc += 1
                    if persona_id != n.persona_id:
                        persona_id = n.persona_id
                        desaprobado += cc
                        cc = 0
                        if desaprobado == 0:
                            aprobados.append(n.persona)
                        else:
                            desaprobados.append(n.persona)
                            desaprobado = 0
            self.array_participantes_aprobados = set(aprobados) - set(desaprobados)
            for equipo in self.capacitacion.equipoproyecto_set.all():
                self.array_equipo_proyecto.append(equipo)
            ccc = 0
            for p in list(self.array_participantes_aprobados) + list(self.array_equipo_proyecto):
                ccc += 1
                if ccc > len(self.array_participantes_aprobados):
                    nombre_completo = '{}-{}'.format(p.persona.numero_documento, p.persona.nombre_completo)
                    correo_e = p.persona.email
                    cargo = p.cargo
                    persona_id = p.persona_id
                else:
                    nombre_completo = '{}-{}'.format(p.numero_documento, p.nombre_completo)
                    correo_e = p.email
                    cargo = None
                    persona_id = p.id
                kwargs.update({'id_capacitacion': self.capacitacion.id, 'id_persona': persona_id,
                               'capacitacion': self.capacitacion, 'cargo': cargo})
                response = GeneraCertificadoPdf.as_view()(request, **kwargs)
                if response.status_code == HTTP_200_OK:
                    self.filename = self.filename.format(timezone.now().strftime('%d_%m_%Y'))
                    pdf = default_storage.save(self.filename, ContentFile(response.content))
                    path_pdf = default_storage.path(pdf)
                    try:
                        asunto = 'UNASAM - Certificado del curso de: {}'.format(self.capacitacion.nombre)
                        mensaje = '''<p>Estimado (a) {},</p>
                                     <p> Se envía adjunto su Certificado.</p>'''.format(nombre_completo)
                        remitente = settings.EMAIL_HOST_USER
                        destinatarios = [correo_e]
                        email = EmailMessage(asunto, mensaje, remitente, destinatarios)
                        email.content_subtype = "html"
                        email.attach_file(path_pdf)
                        if correo_e and email.send(fail_silently=False):
                            array_enviados.append(nombre_completo)
                            if path_pdf:
                                os.remove(path_pdf)
                        else:
                            array_errores.append(nombre_completo)
                            if path_pdf:
                                os.remove(path_pdf)
                    except Exception as ex:
                        array_errores.append(nombre_completo)
                        if path_pdf:
                            os.remove(path_pdf)
            if array_enviados:
                self.capacitacion.se_envio_correo = True
                self.capacitacion.save(update_fields=['se_envio_correo'])
            return JsonResponse({'errores': array_errores, 'enviados': array_enviados}, status=HTTP_200_OK)
        else:
            return JsonResponse({}, status=HTTP_400_BAD_REQUEST)


class EnvioCertificadoCorreo(View):
    persona = None
    capacitacion = None
    modulo = None
    filename = 'Certificado_{}.pdf'
    horas_academicas = 0
    array_participantes_aprobados = 0

    def get(self, request, *args, **kwargs):
        self.capacitacion = Capacitacion.objects.filter(pk=kwargs.get('id_capacitacion')).first()
        self.persona = Persona.objects.filter(pk=kwargs.get('id_persona')).first()
        kwargs.update({'persona': self.persona, 'capacitacion': self.capacitacion,
                       'cargo': self.request.GET.get('cargo', '')})
        response = GeneraCertificadoPdf.as_view()(request, **kwargs)
        if response.status_code == HTTP_200_OK:
            array_enviados = []
            array_errores = []
            self.filename = self.filename.format(timezone.now().strftime('%d_%m_%Y'))
            pdf = default_storage.save(self.filename, ContentFile(response.content))
            path_pdf = default_storage.path(pdf)
            try:
                asunto = 'UNASAM - Certificado del curso de: {}'.format(self.capacitacion.nombre)
                mensaje = '''<p>Estimado (a) {},</p>
                             <p> Se envía adjunto su Certificado.</p>'''.format(self.persona.nombre_completo)
                remitente = settings.EMAIL_HOST_USER
                destinatarios = [self.persona.email]
                email = EmailMessage(asunto, mensaje, remitente, destinatarios)
                email.content_subtype = "html"
                email.attach_file(path_pdf)
                if self.persona.email and email.send(fail_silently=False):
                    array_enviados.append('{}-{}'.format(self.persona.numero_documento, self.persona.nombre_completo))
                    if path_pdf:
                        os.remove(path_pdf)
                else:
                    array_errores.append('{}-{}'.format(self.persona.numero_documento, self.persona.nombre_completo))
                    if path_pdf:
                        os.remove(path_pdf)
            except Exception as ex:
                array_errores.append('{}-{}'.format(self.persona.numero_documento, self.persona.nombre_completo))
                if path_pdf:
                    os.remove(path_pdf)
            return JsonResponse({'errores': array_errores, 'enviados': array_enviados}, status=HTTP_200_OK)
        else:
            return JsonResponse({}, status=HTTP_400_BAD_REQUEST)


class GeneraCertificadoPdfPorModulo(LoginRequiredMixin, PdfCertView):
    filename = 'Certificado-{}.pdf'.format(timezone.now().strftime('%d/%m/%Y %H:%M:%S'))
    disposition = 'attachment'
    canvas = None
    id_acta = None
    participantes = None
    capacitacion = None
    path_code_qr = None
    horas_academicas = 0
    nota_participante = None
    temarios = []
    fecha_culminado = None
    persona = None
    cantidad_cert = 0
    equipo_proyecto = []
    mostrar_pdf = True
    miembro = None
    modulo = None
    correlativo = None

    def dispatch(self, request, *args, **kwargs):
        self.filename = 'Certificado-{}.pdf'.format(timezone.now().strftime('%d/%m/%Y %H:%M:%S'))
        if not self.kwargs.get('capacitacion', None):
            self.capacitacion = get_object_or_404(Capacitacion, pk=self.kwargs.get('id_capacitacion'))
        else:
            self.capacitacion = self.kwargs.get('capacitacion', None)
        if not self.kwargs.get('persona', None):
            self.persona = get_object_or_404(Persona, pk=self.kwargs.get('id_persona'))
        else:
            self.persona = self.kwargs.get('persona', None)
        if not self.kwargs.get('modulo', None):
            self.modulo = get_object_or_404(Modulo, pk=self.kwargs.get('id_modulo'))
        else:
            self.modulo = self.kwargs.get('modulo', None)
        self.temarios = []
        self.equipo_proyecto = []
        self.miembro = None
        if self.kwargs.get('cargo', None):
            cargo = self.kwargs.get('cargo', None)
        else:
            cargo = self.request.GET.get('cargo', None)
        if cargo:
            self.miembro = self.capacitacion.equipoproyecto_set.filter(
                persona=self.persona, cargo=cargo).first()
            self.mostrar_pdf = True if self.miembro else False
            self.correlativo = CertEmitido.objects.filter(modulo=self.modulo,
                                                          persona=self.miembro.persona,
                                                          cargo=cargo,
                                                          tipo=TIPO_CERT_EMITIDO_MODULO).first().correlativo
        else:
            self.correlativo = CertEmitido.objects.filter(modulo=self.modulo,
                                                          persona=self.persona,
                                                          cargo=CARGO_CERT_EMITIDO_ASISTENTE,
                                                          tipo=TIPO_CERT_EMITIDO_MODULO).first().correlativo
        self.cantidad_cert = 1
        code_qr = default_storage.save('temp_code_qr.png', ContentFile(''))
        self.path_code_qr = default_storage.path(code_qr)
        return super().dispatch(request, *args, **kwargs)

    def process_canvas(self, c):
        self.canvas = c
        self.encabezado()
        if self.mostrar_pdf:
            self.get_certificados()
        return c

    def encabezado(self):
        lWidth, lHeight = 'A4'
        self.canvas.setPageSize((lHeight, lWidth))
        self.style = getSampleStyleSheet()['BodyText']
        self.style.fontName = 'Times-Bold'
        self.style.alignment = TA_CENTER
        self.style.fontSize = 11
        self.style1 = getSampleStyleSheet()['Normal']
        self.style1.fontSize = 6
        self.style2 = getSampleStyleSheet()['Normal']
        self.style2.fontSize = 30
        self.style2.alignment = TA_CENTER
        self.style2.fontName = 'Times-Bold'
        self.style3 = getSampleStyleSheet()['Normal']
        self.style3.fontSize = 12
        self.style3.alignment = TA_CENTER
        self.style4 = getSampleStyleSheet()['Normal']
        self.style4.fontSize = 12
        self.style5 = getSampleStyleSheet()['Normal']
        self.style5.fontSize = 16
        self.style5.alignment = TA_CENTER
        self.style4.fontName = 'Times-Roman'
        self.style4.alignment = TA_JUSTIFY
        self.style4.padding = '20px'

    def generar_code_qr(self):
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data("https://www.google.com")
        qr.make(fit=True)

        img = qr.make_image(fill_color='black', back_color='white')
        img.save(self.path_code_qr)
        imagen = os.path.join(self.path_code_qr)
        width = 60
        y_start = 1
        self.canvas.drawImage(ImageReader(imagen), 270, y_start - 55, width=width, preserveAspectRatio=True,
                              mask='auto')
        os.remove(self.path_code_qr)

    def obtener_path_temporal_firma(self, id, firma):
        path = ''
        try:
            decode = base64.b64decode(firma)
            filename = default_storage.save('firma_{}_temp.jpg'.format(id), ContentFile(decode))
            path = default_storage.path(filename)
        except:  # noqa
            pass
        return path

    def get_certificados(self, **kwargs):
        mes = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Setiembre",
               "Octubre", "Noviembre", "Diciembre"]
        table_style1 = [
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.black, None, (2, 2, 1)),
            ('BOX', (0, 0), (-1, -1), 0.25, colors.black),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ('FONTSIZE', (0, 1), (0, -1), 10),
        ]
        table_style4 = [('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('FONTSIZE', (0, 0), (-1, -1), 20)]
        fecha_inicio = DetalleAsistencia.objects.filter(acta_asistencia__modulo=self.modulo).first().fecha
        fecha_fin = DetalleAsistencia.objects.filter(acta_asistencia__modulo=self.modulo).last().fecha
        self.horas_academicas = self.modulo.horas_academicas
        if not self.miembro:
            self.mostrar_pdf = NotaParticipante.objects.filter(acta_asistencia__modulo=self.modulo,
                                                               persona=self.persona, resultado='APROBADO').last()
        if self.miembro or self.mostrar_pdf:
            data2 = [[]] * 4
            data = [[]] * 4
            contador = 0
            # Datos del certificado
            model_cert1 = os.path.join(F'{STATIC_ROOT}', 'img', 'mod_cert1.png')
            self.canvas.drawImage(ImageReader(model_cert1), -4, -2, 620, 795)
            cabecera1 = Paragraph('UNIVERSIDAD NACIONAL', style=self.style5)
            cabecera2 = Paragraph('SANTIAGO ANTUNEZ DE MAYOLO', style=self.style5)
            w, h = cabecera1.wrap(400, 0)
            cabecera1.drawOn(self.canvas, 105, 750 - h)
            w, h = cabecera2.wrap(400, 0)
            cabecera2.drawOn(self.canvas, 105, 728 - h)
            logo_unasam = os.path.join(F'{STATIC_ROOT}', 'img', 'logo-unasam.jpg')
            self.canvas.drawImage(ImageReader(logo_unasam), 231, 565, 147, 120)
            titulo = Paragraph('CERTIFICADO', style=self.style2)
            data2[0] = [titulo]
            ta = Table(data=data2, rowHeights=20, repeatCols=1, colWidths=610)
            ta.setStyle(table_style4)
            w, h = ta.wrap(0, 0)
            ta.drawOn(self.canvas, 1, 475)
            otorgado = Paragraph('Otorgado a:', style=self.style3)
            w, h = otorgado.wrap(100, 0)
            otorgado.drawOn(self.canvas, 45, 470 - h)
            # Nombre del participante
            contador += 1
            if 'PRESENCIAL' in self.capacitacion.canal_reunion.upper():
                tipo_canal = 'presencial'
            else:
                tipo_canal = 'virtual'
            if self.miembro:
                parrafo1 = Paragraph('''Por haber participado en calidad de <b>"{}"</b> en el Curso de
                 <b>"{}"</b>, llevado a cabo en forma {}, del {} al {} con una duración de <b>{} horas 
                 académicas</b>.'''.format(self.miembro.get_cargo_display(),
                                           self.modulo.nombre,
                                           tipo_canal,
                                           fecha_inicio.strftime('%d/%m/%Y'),
                                           fecha_fin.strftime('%d/%m/%Y'),
                                           self.horas_academicas),
                                     style=self.style4)
                data[0] = ['', self.persona.nombre_completo, '']
            else:
                parrafo1 = Paragraph('''Por haber participado en calidad de <b>"Asistente"</b> en el Curso de
                 <b>"{}"</b>, llevado a cabo en forma {}, del {} al {} con una duración de <b>{} horas 
                 académicas</b>.'''.format(self.modulo.nombre, tipo_canal, fecha_inicio.strftime('%d/%m/%Y'),
                                           fecha_fin.strftime('%d/%m/%Y'), self.horas_academicas), style=self.style4)
                data[0] = ['', self.persona.nombre_completo, '']
            data[1] = ['', '', '']
            data[2] = ['', '', '']
            data[3] = ['', parrafo1, '']
            tab = Table(data=data, rowHeights=20, repeatCols=1, colWidths=[55, 500, 55])
            tab.setStyle(table_style4)
            w, h = tab.wrap(0, 0)
            tab.drawOn(self.canvas, 1, 400)
            self.canvas.setFont('Helvetica', 10)
            self.canvas.drawString(100, 365, 'Huaraz, {} de {} de {}'.format(fecha_fin.day,
                                                                             mes[fecha_fin.month],
                                                                             fecha_fin.year))
            responsables_firma = self.capacitacion.responsablefirma_set.all()
            cx = 0
            cant_firmas = responsables_firma.count()
            table_style = [
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
            ]
            for f in responsables_firma:
                data3 = [['']]
                data4 = [['']] * 4
                path_temp_firma = ''
                if f.firmante.firma:
                    path_temp_firma = self.obtener_path_temporal_firma(f.id, f.firmante.firma)
                if path_temp_firma:
                    a = Image(path_temp_firma, width=85, height=85)
                    data3[0] = [a]
                tt = Table(data=data3, rowHeights=70, repeatCols=1, colWidths=230)
                tt.setStyle(table_style)
                w, h = tt.wrap(0, 0)
                if cant_firmas == 2:
                    tt.drawOn(self.canvas, 65 + cx, 250)
                else:
                    tt.drawOn(self.canvas, 50 + cx, 250)
                grado = dict(ABREVIATURA_GRADO).get(f.firmante.persona.grado_academico, '')
                data4[0] = ['']
                data4[1] = ['{} {}'.format(grado, f.firmante).title()]
                data4[2] = [f.get_tipo_firma_display()]
                data4[3] = [f.firmante.ambito.upper()]
                tt = Table(data=data4, rowHeights=10, repeatCols=1, colWidths=230)
                tt.setStyle(table_style)
                w, h = tt.wrap(0, 0)
                if cant_firmas == 2:
                    tt.drawOn(self.canvas, 65 + cx, 215)
                else:
                    tt.drawOn(self.canvas, 37 + cx, 215)
                if cant_firmas == 2:
                    cx += 250
                else:
                    cx += 150
                if path_temp_firma:
                    os.remove(path_temp_firma)
            # footer
            self.generar_code_qr()
            titulo1 = Paragraph('VICERRECTORADO ACADÉMICO', style=self.style3)
            sub_titulo = Paragraph('Consejo de Capacitación, Especialización y Actualización Docente',
                                   style=self.style3)
            titulo2 = Paragraph('CCEAD UNASAM', style=self.style3)
            data2[0] = [titulo1]
            data2[1] = [sub_titulo]
            data2[2] = [titulo2]
            ta = Table(data=data2, rowHeights=20, repeatCols=1, colWidths=610)
            ta.setStyle(table_style4)
            w, h = ta.wrap(0, 0)
            ta.drawOn(self.canvas, 1, 4)
            self.canvas.showPage()
            cxx = 0
            conta = 0
            codigo_barra = code128.Code128(barWidth=1.2, barHeight=25)
            codigo_barra.value = self.correlativo
            codigo_barra.drawOn(self.canvas, x=215, y=745)
            self.canvas.drawString(278, 730, self.correlativo)
            temas = self.modulo.temas.split('\n')
            data1 = [[]] * (len(temas) + 1)
            conta += 1
            mod = Paragraph('Temario', style=self.style)
            data1[0] = [mod]
            for x in range(1, len(temas) + 1):
                data1[x] = [temas[x - 1].strip()]
            tbl = Table(data=data1, rowHeights=25, repeatCols=1, colWidths=[513])
            tbl.setStyle(table_style1)
            w, h = tbl.wrap(0, 0)
            tbl.drawOn(self.canvas, 50 + cxx, 700 - h)
            cxx += 20
            self.canvas.showPage()


class EnvioCertificadoPorModuloCorreo(View):
    persona = None
    capacitacion = None
    modulo = None
    filename = 'Certificado_{}.pdf'
    horas_academicas = 0
    array_participantes_aprobados = 0

    def get(self, request, *args, **kwargs):
        self.capacitacion = Capacitacion.objects.filter(pk=kwargs.get('id_capacitacion')).first()
        self.persona = Persona.objects.filter(pk=kwargs.get('id_persona')).first()
        self.modulo = Modulo.objects.filter(pk=kwargs.get('id_modulo')).first()
        kwargs.update({'persona': self.persona, 'capacitacion': self.capacitacion, 'modulo': self.modulo,
                       'cargo': self.request.GET.get('cargo', '')})
        response = GeneraCertificadoPdfPorModulo.as_view()(request, **kwargs)
        if response.status_code == HTTP_200_OK:
            array_enviados = []
            array_errores = []
            self.filename = self.filename.format(timezone.now().strftime('%d_%m_%Y'))
            pdf = default_storage.save(self.filename, ContentFile(response.content))
            path_pdf = default_storage.path(pdf)
            try:
                asunto = 'UNASAM - Certificado del curso de: {}'.format(self.modulo.nombre)
                mensaje = '''<p>Estimado (a) {},</p>
                             <p> Se envía adjunto su Certificado.</p>'''.format(self.persona.nombre_completo)
                remitente = settings.EMAIL_HOST_USER
                destinatarios = [self.persona.email]
                email = EmailMessage(asunto, mensaje, remitente, destinatarios)
                email.content_subtype = "html"
                email.attach_file(path_pdf)
                if self.persona.email and email.send(fail_silently=False):
                    array_enviados.append('{}-{}'.format(self.persona.numero_documento, self.persona.nombre_completo))
                    if path_pdf:
                        os.remove(path_pdf)
                else:
                    array_errores.append('{}-{}'.format(self.persona.numero_documento, self.persona.nombre_completo))
                    if path_pdf:
                        os.remove(path_pdf)
            except Exception as ex:
                array_errores.append('{}-{}'.format(self.persona.numero_documento, self.persona.nombre_completo))
                if path_pdf:
                    os.remove(path_pdf)
            return JsonResponse({'errores': array_errores, 'enviados': array_enviados}, status=HTTP_200_OK)
        else:
            return JsonResponse({}, status=HTTP_400_BAD_REQUEST)


class GenerarMultipleCertificadosPorModPdfView(LoginRequiredMixin, PdfCertView):
    filename = 'Certificado-{}.pdf'.format(timezone.now().strftime('%d/%m/%Y %H:%M:%S'))
    disposition = 'attachment'
    canvas = None
    id_acta = None
    participantes = None
    capacitacion = None
    path_code_qr = None
    array_participantes_aprobados = []
    array_equipo_proyecto = []
    horas_academicas = 0
    temarios = []
    cantidad_cert = 0
    fecha_culminado = None
    modulo = None
    fecha_inicio = None
    fecha_fin = None

    def dispatch(self, request, *args, **kwargs):
        self.array_participantes_aprobados = []
        self.array_equipo_proyecto = []
        self.filename = 'Certificado-{}.pdf'.format(timezone.now().strftime('%d/%m/%Y %H:%M:%S'))
        self.capacitacion = get_object_or_404(Capacitacion, pk=kwargs.get('id'))
        self.modulo = get_object_or_404(Modulo, pk=kwargs.get('id_modulo'))
        self.fecha_inicio = DetalleAsistencia.objects.filter(acta_asistencia__modulo=self.modulo).first().fecha
        self.fecha_fin = DetalleAsistencia.objects.filter(acta_asistencia__modulo=self.modulo).last().fecha
        actas_asistencias = ActaAsistencia.objects.filter(modulo=self.modulo).order_by('modulo_id')
        aprobados = []
        desaprobados = []
        self.temarios = []
        for acta in actas_asistencias:
            self.temarios.append(acta.modulo.temas)
            self.horas_academicas = self.horas_academicas + acta.modulo.horas_academicas
            nota_participantes = NotaParticipante.objects.filter(acta_asistencia_id=acta.id).order_by('persona_id')
            persona_id = ''
            cc = 0
            desaprobado = 0
            for n in nota_participantes:
                if n.resultado.upper() == 'DESAPROBADO':
                    cc += 1
                if persona_id != n.persona_id:
                    persona_id = n.persona_id
                    desaprobado += cc
                    cc = 0
                    if desaprobado == 0:
                        aprobados.append(n.persona)
                    else:
                        desaprobados.append(n.persona)
                        desaprobado = 0
        self.array_participantes_aprobados = set(aprobados) - set(desaprobados)
        for equipo in self.capacitacion.equipoproyecto_set.all():
            self.array_equipo_proyecto.append(equipo)
        self.cantidad_cert = len(self.array_participantes_aprobados) + len(self.array_equipo_proyecto)
        code_qr = default_storage.save('temp_code_qr.png', ContentFile(''))
        self.path_code_qr = default_storage.path(code_qr)
        return super().dispatch(request, *args, **kwargs)

    def process_canvas(self, c):
        self.canvas = c
        self.encabezado()
        self.get_certificados()
        return c

    def encabezado(self):
        lWidth, lHeight = 'A4'
        self.canvas.setPageSize((lHeight, lWidth))
        self.style = getSampleStyleSheet()['BodyText']
        self.style.fontName = 'Times-Bold'
        self.style.alignment = TA_CENTER
        self.style.fontSize = 11
        self.style1 = getSampleStyleSheet()['Normal']
        self.style1.fontSize = 6
        self.style2 = getSampleStyleSheet()['Normal']
        self.style2.fontSize = 30
        self.style2.alignment = TA_CENTER
        self.style2.fontName = 'Times-Bold'
        self.style3 = getSampleStyleSheet()['Normal']
        self.style3.fontSize = 12
        self.style3.alignment = TA_CENTER
        self.style4 = getSampleStyleSheet()['Normal']
        self.style4.fontSize = 12
        self.style4.fontName = 'Times-Roman'
        self.style4.alignment = TA_JUSTIFY
        self.style4.padding = '20px'
        self.style5 = getSampleStyleSheet()['Normal']
        self.style5.fontSize = 16
        self.style5.alignment = TA_CENTER

    def generar_code_qr(self):
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data("https://www.google.com")
        qr.make(fit=True)

        img = qr.make_image(fill_color='black', back_color='white')
        img.save(self.path_code_qr)
        imagen = os.path.join(self.path_code_qr)
        width = 60
        y_start = 1
        self.canvas.drawImage(ImageReader(imagen), 270, y_start-55, width=width, preserveAspectRatio=True,
                              mask='auto')
        os.remove(self.path_code_qr)

    def obtener_path_temporal_firma(self, id, firma):
        path = ''
        try:
            decode = base64.b64decode(firma)
            filename = default_storage.save('firma_{}_temp.jpg'.format(id), ContentFile(decode))
            path = default_storage.path(filename)
        except:  # noqa
            pass
        return path

    def get_certificados(self, **kwargs):
        mes = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Setiembre",
               "Octubre", "Noviembre", "Diciembre"]
        table_style1 = [
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.black, None, (2, 2, 1)),
            ('BOX', (0, 0), (-1, -1), 0.25, colors.black),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ('FONTSIZE', (0, 1), (0, -1), 10),
        ]
        model_cert1 = os.path.join(F'{STATIC_ROOT}', 'img', 'mod_cert1.png')
        self.canvas.drawImage(ImageReader(model_cert1), -4, -2, 620, 795)
        table_style4 = [('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('FONTSIZE', (0, 0), (-1, -1), 20), ]
        data2 = [[]] * 4
        data = [[]] * 4
        data6 = [[]] * 4
        contador = 0
        for p in list(self.array_participantes_aprobados) + list(self.array_equipo_proyecto):
            # Datos del certificado
            model_cert1 = os.path.join(F'{STATIC_ROOT}', 'img', 'mod_cert1.png')
            self.canvas.drawImage(ImageReader(model_cert1), -4, -2, 620, 795)
            cabecera1 = Paragraph('UNIVERSIDAD NACIONAL', style=self.style5)
            cabecera2 = Paragraph('SANTIAGO ANTUNEZ DE MAYOLO', style=self.style5)
            w, h = cabecera1.wrap(400, 0)
            cabecera1.drawOn(self.canvas, 105, 750 - h)
            w, h = cabecera2.wrap(400, 0)
            cabecera2.drawOn(self.canvas, 105, 728 - h)
            logo_unasam = os.path.join(F'{STATIC_ROOT}', 'img', 'logo-unasam.jpg')
            self.canvas.drawImage(ImageReader(logo_unasam), 231, 565, 147, 120)
            titulo = Paragraph('CERTIFICADO', style=self.style2)
            data2[0] = [titulo]
            ta = Table(data=data2, rowHeights=20, repeatCols=1, colWidths=610)
            ta.setStyle(table_style4)
            w, h = ta.wrap(0, 0)
            ta.drawOn(self.canvas, 1, 475)
            otorgado = Paragraph('Otorgado a:', style=self.style3)
            w, h = otorgado.wrap(100, 0)
            otorgado.drawOn(self.canvas, 45, 470 - h)
            # Nombre del participante
            contador += 1
            n_correlativo = ''
            if 'PRESENCIAL' in self.capacitacion.canal_reunion.upper():
                tipo_canal = 'presencial'
            else:
                tipo_canal = 'virtual'
            if contador > len(self.array_participantes_aprobados):
                parrafo1 = Paragraph('''Por haber participado en calidad de <b>"{}"</b> en el Curso de
                                     <b>"{}"</b>, llevado a cabo en forma {}, del {} al {} con una duración de <b>{}
                                      horas académicas</b>.'''.format(p.get_cargo_display(),
                                                                      self.modulo.nombre,
                                                                      tipo_canal,
                                                                      self.fecha_inicio.strftime('%d/%m/%Y'),
                                                                      self.fecha_fin.strftime('%d/%m/%Y'),
                                                                      self.horas_academicas),
                                     style=self.style4)
                data[0] = ['', p.persona.nombre_completo, '']
                res_correlativo = CertEmitido.objects.filter(modulo=self.modulo,
                                                             persona=p.persona,
                                                             cargo=p.cargo,
                                                             tipo=TIPO_CERT_EMITIDO_MODULO).first()
                if res_correlativo:
                    n_correlativo = res_correlativo.correlativo
            else:
                parrafo1 = Paragraph('''Por haber participado en calidad de <b>"Asistente"</b> en el Curso de
                                     <b>"{}"</b>, llevado a cabo en forma {}, del {} al {} con una duración de <b>{}
                                      horas académicas</b>.'''.format(
                    self.modulo.nombre, tipo_canal, self.fecha_inicio.strftime('%d/%m/%Y'),
                    self.fecha_fin.strftime('%d/%m/%Y'), self.horas_academicas), style=self.style4)
                data[0] = ['', p.nombre_completo, '']
                res_correlativo = CertEmitido.objects.filter(modulo=self.modulo,
                                                             persona=p,
                                                             cargo=CARGO_CERT_EMITIDO_ASISTENTE,
                                                             tipo=TIPO_CERT_EMITIDO_MODULO).first()
                if res_correlativo:
                    n_correlativo = res_correlativo.correlativo
            data[1] = ['', '', '']
            data[2] = ['', '', '']
            data[3] = ['', parrafo1, '']
            tab = Table(data=data, rowHeights=20, repeatCols=1, colWidths=[55, 500, 55])
            tab.setStyle(table_style4)
            w, h = tab.wrap(0, 0)
            tab.drawOn(self.canvas, 1, 400)
            self.canvas.setFont('Helvetica', 10)
            self.canvas.drawString(100, 365, 'Huaraz, {} de {} de {}'.format(self.fecha_fin.day,
                                                                             mes[self.fecha_fin.month],
                                                                             self.fecha_fin.year))
            responsables_firma = self.capacitacion.responsablefirma_set.all()
            cx = 0
            cant_firmas = responsables_firma.count()
            table_style = [
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
            ]
            for f in responsables_firma:
                data3 = [['']]
                data4 = [['']] * 3
                path_temp_firma = ''
                if f.firmante.firma:
                    path_temp_firma = self.obtener_path_temporal_firma(f.id, f.firmante.firma)
                if path_temp_firma:
                    a = Image(path_temp_firma, width=85, height=85)
                    data3[0] = [a]
                tt = Table(data=data3, rowHeights=70, repeatCols=1, colWidths=230)
                tt.setStyle(table_style)
                w, h = tt.wrap(0, 0)
                if cant_firmas == 2:
                    tt.drawOn(self.canvas, 65 + cx, 250)
                else:
                    tt.drawOn(self.canvas, 50 + cx, 250)
                data4[0] = ['---------------------------------------------------------']
                data4[1] = [f.firmante]
                data4[2] = [f.get_tipo_firma_display()]
                tt = Table(data=data4, rowHeights=10, repeatCols=1, colWidths=230)
                tt.setStyle(table_style)
                w, h = tt.wrap(0, 0)
                if cant_firmas == 2:
                    tt.drawOn(self.canvas, 65 + cx, 215)
                else:
                    tt.drawOn(self.canvas, 37 + cx, 215)
                if cant_firmas == 2:
                    cx += 250
                else:
                    cx += 150
                if path_temp_firma:
                    os.remove(path_temp_firma)
            self.generar_code_qr()
            titulo1 = Paragraph('VICERRECTORADO ACADÉMICO', style=self.style3)
            sub_titulo1 = Paragraph('Consejo de Capacitación, Especialización y Actualización Docente',
                                    style=self.style3)
            titulo2 = Paragraph('CCEAD UNASAM', style=self.style3)
            data6[0] = [titulo1]
            data6[1] = [sub_titulo1]
            data6[2] = [titulo2]
            ta = Table(data=data6, rowHeights=20, repeatCols=1, colWidths=610)
            ta.setStyle(table_style4)
            w, h = ta.wrap(0, 0)
            ta.drawOn(self.canvas, 1, 4)
            self.canvas.showPage()
            cxx = 0
            conta = 0
            codigo_barra = code128.Code128(barWidth=1.2, barHeight=25)
            codigo_barra.value = n_correlativo
            codigo_barra.drawOn(self.canvas, x=215, y=745)
            self.canvas.drawString(278, 730, n_correlativo)
            if len(self.temarios) == 1:
                temas = self.temarios[0].split('\n')
                data1 = [[]] * (len(temas) + 1)
                conta += 1
                mod = Paragraph('Temario', style=self.style)
                data1[0] = [mod]
                for x in range(1, len(temas) + 1):
                    data1[x] = [temas[x - 1].strip()]
                tbl = Table(data=data1, rowHeights=30, repeatCols=1, colWidths=[513])
                tbl.setStyle(table_style1)
                w, h = tbl.wrap(0, 0)
                tbl.drawOn(self.canvas, 50 + cxx, 700 - h)
                cxx += 20
                self.canvas.showPage()
            else:
                for t in self.temarios:
                    temas = t.split('\n')
                    data1 = [[]] * (len(temas) + 1)
                    conta += 1
                    mod = Paragraph('Temario del Módulo {}'.format(conta), style=self.style)
                    data1[0] = [mod]
                    trow = 30
                    espace = 30
                    tem = 0
                    for x in range(1, len(temas) + 1):
                        te3 = temas[x - 1].strip()
                        tem += 1
                        if len(temas[x - 1].strip()) >= 90:
                            trow = 30
                            espace = 30
                            te = temas[x - 1].strip()[:90]
                            pos_te = te.rfind(' ')
                            te1 = temas[x - 1].strip()[:pos_te]
                            te2 = temas[x - 1].strip()[pos_te:]
                            te3 = '{}\n  {}'.format(te1, te2)
                        data1[x] = [te3]
                    tbl = Table(data=data1, rowHeights=trow, repeatCols=1, colWidths=[513])
                    tbl.setStyle(table_style1)
                    w, h = tbl.wrap(0, 0)
                    tbl.drawOn(self.canvas, 50, (700 - h) - cxx + espace)
                    cxx += 50 + (tem * 20)
                self.canvas.showPage()


class EnvioCertificadoMultiCorreoMod(View):
    persona = None
    capacitacion = None
    filename = 'Certificado_{}.pdf'
    horas_academicas = 0
    array_participantes_aprobados = 0
    modulo = None
    temarios = []
    array_equipo_proyecto = []

    def get(self, request, *args, **kwargs):
        self.capacitacion = Capacitacion.objects.filter(pk=kwargs.get('id_capacitacion')).first()
        self.modulo = Modulo.objects.filter(pk=kwargs.get('id_modulo')).first()
        actas_asistencias = ActaAsistencia.objects.filter(modulo=self.modulo)
        if self.capacitacion and actas_asistencias:
            aprobados = []
            desaprobados = []
            self.temarios = []
            self.array_equipo_proyecto = []
            array_errores = []
            array_enviados = []
            for acta in actas_asistencias:
                self.temarios.append(acta.modulo.temas)
                self.horas_academicas = self.horas_academicas + acta.modulo.horas_academicas
                nota_participantes = NotaParticipante.objects.filter(acta_asistencia_id=acta.id).order_by('persona_id')
                persona_id = ''
                cc = 0
                desaprobado = 0
                for n in nota_participantes:
                    if n.resultado.upper() == 'DESAPROBADO':
                        cc += 1
                    if persona_id != n.persona_id:
                        persona_id = n.persona_id
                        desaprobado += cc
                        cc = 0
                        if desaprobado == 0:
                            aprobados.append(n.persona)
                        else:
                            desaprobados.append(n.persona)
                            desaprobado = 0
            self.array_participantes_aprobados = set(aprobados) - set(desaprobados)
            for equipo in self.capacitacion.equipoproyecto_set.all():
                self.array_equipo_proyecto.append(equipo)
            ccc = 0
            for p in list(self.array_participantes_aprobados) + list(self.array_equipo_proyecto):
                ccc += 1
                if ccc > len(self.array_participantes_aprobados):
                    nombre_completo = '{}-{}'.format(p.persona.numero_documento, p.persona.nombre_completo)
                    correo_e = p.persona.email
                    cargo = p.cargo
                    persona_id = p.persona_id
                else:
                    nombre_completo = '{}-{}'.format(p.numero_documento, p.nombre_completo)
                    correo_e = p.email
                    cargo = None
                    persona_id = p.id
                kwargs.update({'id_capacitacion': self.capacitacion.id, 'id_persona': persona_id,
                               'modulo': self.modulo, 'capacitacion': self.capacitacion, 'cargo': cargo})
                response = GeneraCertificadoPdfPorModulo.as_view()(request, **kwargs)
                if response.status_code == HTTP_200_OK:
                    self.filename = self.filename.format(timezone.now().strftime('%d_%m_%Y'))
                    pdf = default_storage.save(self.filename, ContentFile(response.content))
                    path_pdf = default_storage.path(pdf)
                    try:
                        asunto = 'UNASAM - Certificado del curso de: {}'.format(self.modulo.nombre)
                        mensaje = '''<p>Estimado (a) {},</p>
                                     <p> Se envía adjunto su Certificado.</p>'''.format(nombre_completo)
                        remitente = settings.EMAIL_HOST_USER
                        destinatarios = [correo_e]
                        email = EmailMessage(asunto, mensaje, remitente, destinatarios)
                        email.content_subtype = "html"
                        email.attach_file(path_pdf)
                        if correo_e and email.send(fail_silently=False):
                            array_enviados.append(nombre_completo)
                            if path_pdf:
                                os.remove(path_pdf)
                        else:
                            array_errores.append(nombre_completo)
                            if path_pdf:
                                os.remove(path_pdf)
                    except Exception as ex:
                        array_errores.append(nombre_completo)
                        if path_pdf:
                            os.remove(path_pdf)
            if array_enviados:
                self.modulo.se_envio_correo = True
                self.modulo.save(update_fields=['se_envio_correo'])
            return JsonResponse({'errores': array_errores, 'enviados': array_enviados}, status=HTTP_200_OK)
        else:
            return JsonResponse({}, status=HTTP_400_BAD_REQUEST)
