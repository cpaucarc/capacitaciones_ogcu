from django import forms
from django.forms import inlineformset_factory
from apps.capacitacion.models import Capacitacion, ResponsableFirma, ActaAsistencia, Modulo, EquipoProyecto
from apps.common.constants import CARGO_PROYECTO_CHOICES, EMISION_CERTIFICADO_UNICO, EMISION_CERTIFICADO_CHOICES


class CapacitacionForm(forms.ModelForm):
    nombre = forms.CharField(label='Nombre del Proyecto de Capacitación', widget=forms.TextInput(
        attrs={'class': 'form-control input-sm'}))
    fecha_inicio = forms.DateField(widget=forms.DateInput(format='%Y-%m-%d',
                                                          attrs={'class': 'form-control input-sm', 'type': 'date',
                                                                 'min': ''}), label='Fecha inicio')
    fecha_fin = forms.DateField(widget=forms.DateInput(format='%Y-%m-%d',
                                                       attrs={'class': 'form-control input-sm', 'type': 'date',
                                                              'min': ''}), label='Fecha Fin')
    descripcion_horario = forms.CharField(label='Descripción de horario', widget=forms.TextInput(
        attrs={'class': 'form-control input-sm'}))
    beneficiarios = forms.CharField(label='Beneficiario', widget=forms.TextInput(
        attrs={'class': 'form-control input-sm'}), required=False)
    canal_reunion = forms.CharField(label='Canal de la reunión', widget=forms.TextInput(
        attrs={'class': 'form-control input-sm'}))
    objetivo = forms.CharField(
        label='Objetivos',
        widget=forms.Textarea(attrs={
            'class': 'form-control input-sm',
            'rows': 4,
            'placeholder':'- Objetivo 1\n- Objetivo 2\n- Objetivo 3\n...'}),
        required=False)
    justificacion = forms.CharField(label='Justificación', widget=forms.TextInput(
        attrs={'class': 'form-control input-sm'}), required=False)
    certificacion = forms.CharField(label='Certificación', widget=forms.TextInput(
        attrs={'class': 'form-control input-sm'}))
    observacion = forms.CharField(label='Observación', widget=forms.TextInput(
        attrs={'class': 'form-control input-sm'}), required=False)
    ruta_proyecto_pdf = forms.FileField(label='Archivo PDF',
                                        widget=forms.FileInput(attrs={'class': 'form-control input-sm'}))
    persona_select = forms.CharField(required=False, label='Seleccionar Miembro',
                                     widget=forms.Select(attrs={'class': 'form-control input-sm'}))
    cargo_select = forms.ChoiceField(required=False, label='Seleccionar Cargo',
                                     choices=(('', '----------'),) + CARGO_PROYECTO_CHOICES,
                                     widget=forms.Select(attrs={'class': 'form-control input-sm'}))
    tipo_emision_certificado = forms.ChoiceField(required=True,
                                                 choices=EMISION_CERTIFICADO_CHOICES,
                                                 widget=forms.Select(attrs={'class': 'form-control input-sm'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    class Meta:
        model = Capacitacion
        fields = (
            'nombre', 'fecha_inicio', 'fecha_fin', 'descripcion_horario', 'canal_reunion',
            'beneficiarios', 'justificacion', 'objetivo', 'certificacion', 'ruta_proyecto_pdf',
            'observacion', 'tipo_emision_certificado'
        )


class ModuloForm(forms.ModelForm):
    temas = forms.CharField(
        widget=forms.Textarea(
            attrs={'class': 'form-control', 'rows': 4, 'cols': 50, 'placeholder': '- Tema 1\n- Tema 2\n- Tema 3\n...'}),
        required=False
    )
    nombre = forms.CharField(label='Nombre', widget=forms.TextInput(
        attrs={'class': 'form-control'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    class Meta:
        model = Modulo
        fields = ('nombre', 'horas_academicas', 'temas')


ModuloFormset = inlineformset_factory(Capacitacion, Modulo, form=ModuloForm, can_delete=True, extra=1)


class EquipoProyectoForm(forms.ModelForm):
    persona_id = forms.IntegerField(widget=forms.HiddenInput(attrs={'class': 'persona-id'}))
    cargo = forms.CharField(widget=forms.HiddenInput(attrs={'class': 'cargo-id'}))
    cargo_equipo = forms.CharField(
        widget=forms.TextInput(attrs={'readonly': True, 'class': 'cargo-equipo'})
    )
    persona_equipo = forms.CharField(
        widget=forms.TextInput(attrs={'readonly': True, 'class': 'persona-equipo'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    class Meta:
        model = EquipoProyecto
        fields = ('cargo', 'persona_id')

    def save(self, commit=True):
        form = super().save(commit=False)
        form.persona_id = self.cleaned_data['persona_id']
        return form


EquipoProyectoFormset = inlineformset_factory(Capacitacion, EquipoProyecto, form=EquipoProyectoForm, can_delete=True,
                                              extra=0)


class ResponsableFirmaForm(forms.ModelForm):
    persona_id = forms.IntegerField(widget=forms.HiddenInput(attrs={'class': 'persona-id'}))
    cargo = forms.CharField(widget=forms.HiddenInput(attrs={'class': 'cargo-id'}))
    cargo_firmante = forms.CharField(
        widget=forms.TextInput(attrs={'readonly': True, 'class': 'cargo-firmante'})
    )
    persona_firmante = forms.CharField(
        widget=forms.TextInput(attrs={'readonly': True, 'class': 'persona-firmante'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    class Meta:
        model = ResponsableFirma
        fields = ('persona_id', 'cargo')

    def save(self, commit=True):
        form = super().save(commit=False)
        form.persona_id = self.cleaned_data['persona_id']
        return form


ResponsableFirmaFormset = inlineformset_factory(Capacitacion, ResponsableFirma, form=ResponsableFirmaForm,
                                                can_delete=True, extra=0)


class ActaAsistenciaForm(forms.ModelForm):
    excel_asistencia = forms.FileField(label='Archivo Excel',
                                       widget=forms.FileInput(attrs={'class': 'form-control caja-xs'}))
    observacion = forms.CharField(required=False, label='Observación', widget=forms.TextInput(
        attrs={'class': 'form-control caja-xs'}))
    ruta_acta_pdf = forms.FileField(required=False, label='Archivo PDF',
                                    widget=forms.FileInput(attrs={'class': 'form-control caja-xs'}))

    def __init__(self, *args, **kwargs):
        id_capacitacion = kwargs.pop('id_capacitacion', None)
        super().__init__(*args, **kwargs)
        if id_capacitacion:
            self.fields['fechas_asistencia'] = forms.MultipleChoiceField(
                label='Fechas de asistencia',
                required=True,
                choices=self.get_fechas_asistencia(id_capacitacion),
                widget=forms.SelectMultiple(attrs={'class': 'form-control'}))

    class Meta:
        model = ActaAsistencia
        fields = ('ruta_acta_pdf', 'observacion', 'modulo')

    def get_fechas_asistencia(self, id_capacitacion):
        fechas = []
        if str(id_capacitacion).isdigit():
            c = Capacitacion.objects.filter(id=id_capacitacion).first()
            if c:
                inicio = c.fecha_inicio
                ano = str(c.fecha_inicio).split('-')[0]
                mes = str(c.fecha_inicio).split('-')[1]
                dia = int(str(c.fecha_inicio).split('-')[2])
                fin = c.fecha_fin
                if inicio and fin:
                    num_dias = 0
                    if inicio != fin:
                        dias = str(c.fecha_fin-c.fecha_inicio).split(' ')
                        num_dias = dias[0]
                    for x in range(0, int(num_dias)+1):
                        num_dia = '0{}'.format(dia) if dia <= 9 else dia
                        fechas.append(('{}-{}-{}'.format(ano, mes, num_dia), '{}-{}-{}'.format(ano, mes, num_dia)))
                        dia += 1
        return list(fechas)
