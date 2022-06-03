import io
import os
import uuid

from PyPDF2 import PdfFileReader, PdfFileWriter
from django.http import HttpResponse
from django.views import View
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.pdfgen.canvas import Canvas

from config.settings import STATIC_ROOT


class PdfCertView(View):
    filename = ''
    disposition = 'inline'

    def get(self, request, *args, **kwargs):
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = '{}; filename={}'.format(self.disposition, self.filename)
        c = Canvas(response)
        c.setFont('Times-Roman', 6)
        c._doc.setTitle(self.filename)
        c = self.process_canvas(c)
        c.save()
        return response

    def process_canvas(self, _canvas):
        raise NotImplementedError
