from django.db import models


class AuditableModel(models.Model):
    creado_por = models.CharField('creado por', max_length=20, editable=False, blank=True, null=True)
    modificado_por = models.CharField('modificado por', max_length=20, editable=False, blank=True, null=True)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    fecha_creacion = models.DateTimeField('fecha de creación', auto_now_add=True, editable=False, blank=True, null=True) # noqa
    fecha_modificacion = models.DateTimeField('fecha de modificación', auto_now=True, editable=False)

    class Meta:
        abstract = True


class BaseModel(AuditableModel, TimeStampedModel):

    class Meta:
        abstract = True
