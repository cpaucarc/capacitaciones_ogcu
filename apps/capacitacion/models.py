from django.db import models

from apps.common.constants import (ESTADO_PROYECTO_REGISTRADO, ESTADO_PROYECTO_CHOICES,
                                   ESTADO_REVISION_COMISION_CHOICES, ESTADO_ASISTENCIA_CHOICES, TIPO_FIRMA_CHOICES,
                                   CARGO_MIEMBRO_CHOICES, EMISION_CERTIFICADO_CHOICES, AMBITO_CHOICES, AMBITO_FACULTAD,
                                   CARGO_PROYECTO_CHOICES, CARGO_CERT_EMITIDO_CHOICES, ESTADO_CERT_CHOICES,
                                   ESTADO_CERT_EMITIDO, EMISION_CERTIFICADO_UNICO, TIPO_CERT_EMITIDO_CHOICES,
                                   TIPO_CERT_EMITIDO_UNICO)
from apps.common.models import BaseModel
from apps.persona.models import Facultad, Firmante
from apps.persona.models import Persona


class Capacitacion(BaseModel):
    nombre = models.CharField(max_length=250)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    descripcion_horario = models.CharField(max_length=250, blank=True, null=True)
    canal_reunion = models.CharField(max_length=100, blank=True, null=True)
    beneficiarios = models.CharField(max_length=100, blank=True, null=True)
    justificacion = models.CharField(max_length=250, blank=True, null=True)
    objetivo = models.CharField(max_length=250, blank=True, null=True)
    certificacion = models.CharField(max_length=250, blank=True, null=True)
    ruta_proyecto_pdf = models.FileField(upload_to="proyectos", blank=True, null=True)
    observacion = models.CharField(max_length=250, blank=True, null=True)
    observacion_revision = models.CharField(max_length=250, blank=True, null=True)
    tipo_emision_certificado = models.CharField(max_length=45, choices=EMISION_CERTIFICADO_CHOICES)
    ambito = models.CharField(max_length=25, choices=AMBITO_CHOICES, default=AMBITO_FACULTAD)
    facultad = models.ForeignKey(Facultad, on_delete=models.PROTECT, blank=True, null=True)
    se_envio_correo = models.BooleanField(default=False)
    estado = models.CharField(max_length=25, choices=ESTADO_PROYECTO_CHOICES, default=ESTADO_PROYECTO_REGISTRADO)


class EquipoProyecto(models.Model):
    cargo = models.CharField(max_length=25, choices=CARGO_PROYECTO_CHOICES)
    persona = models.ForeignKey(Persona, on_delete=models.PROTECT)
    capacitacion = models.ForeignKey(Capacitacion, on_delete=models.PROTECT)

    class Meta:
        unique_together = [['cargo', 'persona', 'capacitacion']]


class Modulo(models.Model):
    nombre = models.CharField(max_length=45, blank=True, null=True)
    horas_academicas = models.PositiveIntegerField()
    temas = models.TextField(max_length=1000)
    se_envio_correo = models.BooleanField(default=False)
    capacitacion = models.ForeignKey(Capacitacion, on_delete=models.PROTECT)


class ResponsableFirma(models.Model):
    tipo_firma = models.CharField(max_length=45, choices=TIPO_FIRMA_CHOICES)
    firmante = models.ForeignKey(Firmante, on_delete=models.PROTECT)
    capacitacion = models.ForeignKey(Capacitacion, on_delete=models.PROTECT)

    class Meta:
        unique_together = [['tipo_firma', 'firmante', 'capacitacion']]


class ActaAsistencia(BaseModel):
    ruta_acta_pdf = models.FileField(upload_to="actas", blank=True, null=True)
    observacion = models.CharField(max_length=250, blank=True, null=True)
    modulo = models.OneToOneField(Modulo, on_delete=models.PROTECT)


class Evidencia(models.Model):
    ruta_evidencia_pdf = models.FileField(upload_to="evidencia_capacitacion", blank=True, null=True)
    descripcion = models.CharField(max_length=250, blank=True, null=False)
    acta_asistencia = models.ForeignKey(ActaAsistencia, on_delete=models.PROTECT)


class DetalleAsistencia(models.Model):
    fecha = models.DateField()
    estado = models.CharField(max_length=10, choices=ESTADO_ASISTENCIA_CHOICES)
    persona = models.ForeignKey(Persona, on_delete=models.PROTECT)
    acta_asistencia = models.ForeignKey(ActaAsistencia, on_delete=models.PROTECT)

    class Meta:
        unique_together = [['fecha', 'persona', 'acta_asistencia']]


class NotaParticipante(models.Model):
    acta_asistencia = models.ForeignKey(ActaAsistencia, on_delete=models.PROTECT)
    resultado = models.CharField(max_length=25, blank=True,  null=True)
    persona = models.ForeignKey(Persona, on_delete=models.PROTECT)

    class Meta:
        unique_together = [['acta_asistencia', 'persona']]


class HistorialRevision(BaseModel):
    capacitacion = models.ForeignKey(Capacitacion, on_delete=models.PROTECT)
    estado = models.CharField(max_length=25, choices=ESTADO_REVISION_COMISION_CHOICES)
    observacion = models.CharField(max_length=250, blank=True, null=False)


class HistorialRevisionConsejo(models.Model):
    ambito = models.CharField(max_length=25, choices=AMBITO_CHOICES)
    facultad = models.ForeignKey(Facultad, on_delete=models.PROTECT, blank=True, null=True)
    cargo_miembro = models.CharField(max_length=25, choices=CARGO_MIEMBRO_CHOICES)
    persona = models.ForeignKey(Persona, on_delete=models.PROTECT)
    revision = models.ForeignKey(HistorialRevision, on_delete=models.PROTECT)


class CertEmitido(BaseModel):
    tipo = models.CharField(max_length=45, choices=TIPO_CERT_EMITIDO_CHOICES, default=TIPO_CERT_EMITIDO_UNICO)
    modulo = models.ForeignKey(Modulo, on_delete=models.PROTECT)
    persona = models.ForeignKey(Persona, on_delete=models.PROTECT)
    cargo = models.CharField(max_length=25, choices=CARGO_CERT_EMITIDO_CHOICES)
    correlativo = models.CharField(max_length=15)
    estado = models.CharField(max_length=25, choices=ESTADO_CERT_CHOICES, default=ESTADO_CERT_EMITIDO)
