from django import forms

from apps.common.constants import DOCUMENT_TYPE_DNI, DOCUMENT_TYPE_CHOICES1, TIPO_PERSONA_CONSEJO_UNASAM, \
    TIPO_PERSONA_CONSEJO_FACULTAD
from apps.persona.models import Persona, Firmante


class PersonaForm(forms.ModelForm):
    tipo_documento = forms.ChoiceField(label='Tipo de documento', choices=DOCUMENT_TYPE_CHOICES1,
                                       initial=DOCUMENT_TYPE_DNI,
                                       widget=forms.Select(attrs={'class': 'form-control form-control-lg'})
                                       )
    apellido_paterno = forms.CharField(required=True)
    nombres = forms.CharField(required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    class Meta:
        model = Persona
        fields = (
            'tipo_documento', 'numero_documento', 'sexo', 'nombres', 'apellido_paterno', 'apellido_materno',
            'celular', 'email', 'facultad', 'cargo_miembro', 'tipo_persona', 'grado_academico'
        )

    def clean(self):
        cleaned_data = super().clean()
        tipo_persona = cleaned_data.get('tipo_persona')
        cargo_miembro = cleaned_data.get('cargo_miembro')
        facultad = cleaned_data.get('facultad')
        if tipo_persona in (TIPO_PERSONA_CONSEJO_UNASAM, TIPO_PERSONA_CONSEJO_FACULTAD):
            if tipo_persona == TIPO_PERSONA_CONSEJO_UNASAM:
                miembro_existente = Persona.objects.filter(tipo_persona=tipo_persona, es_activo=True,
                                                           cargo_miembro=cargo_miembro).exists()
                if miembro_existente:
                    self.add_error('cargo_miembro',
                                   'El cargo seleccionado ya existe para el consejo UNASAM')
            if tipo_persona == TIPO_PERSONA_CONSEJO_FACULTAD:
                miembro_existente = Persona.objects.filter(tipo_persona=tipo_persona, facultad=facultad, es_activo=True,
                                                           cargo_miembro=cargo_miembro).exists()
                if miembro_existente:
                    self.add_error('cargo_miembro',
                                   'El cargo seleccionado ya existe para el consejo Facultad')


class FirmanteForm(forms.ModelForm):
    persona = forms.ModelChoiceField(label="Firmante", required=True,
                                     queryset=Persona.objects.none(),
                                     widget=forms.Select(attrs={'class': 'form-control'}))
    firma = forms.FileField(label='Firma', widget=forms.FileInput(attrs={'class': 'form-control input-sm'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.data.get('persona'):
            self.fields['persona'].queryset = Persona.objects.only('id').filter(id=self.data.get('persona'))

    class Meta:
        model = Firmante
        fields = ('persona', 'ambito', 'facultad', 'firma')

    def clean(self):
        cleaned_data = super().clean()
        ambito = cleaned_data.get('ambito')
        if ambito and ambito == 'unasam':
            cleaned_data['facultad'] = None
        return cleaned_data
