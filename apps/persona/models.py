from django.core.validators import validate_email
from django.db import models

from apps.common.constants import (DOCUMENT_TYPE_CHOICES, DOCUMENT_TYPE_DNI, SEXO_CHOICES, TIPO_PERSONA_CHOICES,
                                   TIPO_PERSONA_PARTICIPANTE, CARGO_MIEMBRO_CHOICES, AMBITO_CHOICES, GRADO_CHOICES)
from apps.common.models import AuditableModel, TimeStampedModel


class Facultad(models.Model):
    codigo = models.CharField('Código', max_length=45)
    nombre = models.CharField('Nombre', max_length=250)

    def __str__(self):
        return '{nombre}'.format(nombre=self.nombre)


class Persona(AuditableModel, TimeStampedModel):
    tipo_documento = models.CharField(
        max_length=2, verbose_name='Tipo de documento', choices=DOCUMENT_TYPE_CHOICES, default=DOCUMENT_TYPE_DNI)
    numero_documento = models.CharField(max_length=15, verbose_name='Número de documento')
    sexo = models.CharField('Sexo', choices=SEXO_CHOICES, max_length=2)
    nombres = models.CharField('Nombre(s)', max_length=120, blank=True, null=True)
    apellido_paterno = models.CharField('Apellido paterno', max_length=120, blank=True, null=True)
    apellido_materno = models.CharField('Apellido materno', max_length=120, blank=True, null=True)
    celular = models.CharField(max_length=50, null=True, blank=True)
    email = models.CharField(max_length=200, null=True, blank=True, validators=[validate_email])
    facultad = models.ForeignKey(Facultad, on_delete=models.PROTECT, blank=True, null=True)
    cargo_miembro = models.CharField(max_length=25, choices=CARGO_MIEMBRO_CHOICES, blank=True, null=True)
    tipo_persona = models.CharField(max_length=25, choices=TIPO_PERSONA_CHOICES, default=TIPO_PERSONA_PARTICIPANTE)
    grado_academico = models.CharField(max_length=25, choices=GRADO_CHOICES, blank=True, null=True)
    es_activo = models.BooleanField(default=True)

    class Meta:
        unique_together = [('tipo_documento', 'numero_documento')]
        ordering = ['apellido_paterno']

    def __str__(self):
        return '{nombre_completo}'.format(nombre_completo=self.nombre_completo)

    @property
    def nombre_completo(self):
        return '{a_paterno} {a_materno} {nombres}'.format(
            nombres=self.nombres,
            a_paterno=self.apellido_paterno,
            a_materno=self.apellido_materno
        )

    def get_default_password_and_username(self):
        if self.numero_documento:
            return self.numero_documento
        elif self.nombres:
            return self.nombres.lower().replace(' ', '')


class Firmante(models.Model):
    persona = models.ForeignKey(Persona, on_delete=models.PROTECT)
    ambito = models.CharField(max_length=25, choices=AMBITO_CHOICES)
    facultad = models.ForeignKey(Facultad, on_delete=models.PROTECT, blank=True, null=True)
    firma = models.TextField()

    def __str__(self):
        return '{nombre_completo}'.format(nombre_completo=self.persona)
