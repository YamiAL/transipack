import csv
import json
import re
from io import BytesIO, StringIO

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.utils.text import slugify
from django.views.decorators.http import require_POST
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


MAX_ROWS = 100000
MAX_COLS = 80


def _safe_filename(title, ext):
    base = slugify(title or 'exportacion') or 'exportacion'
    return f'{base[:80]}.{ext}'


def _normalize_payload(payload):
    title = str(payload.get('title') or 'Exportacion').strip()[:180]
    headers = [str(h or '').strip() for h in (payload.get('headers') or [])][:MAX_COLS]
    rows = []
    for row in (payload.get('rows') or [])[:MAX_ROWS]:
        rows.append([str(cell if cell is not None else '').strip() for cell in row[:MAX_COLS]])
    footer = [str(cell if cell is not None else '').strip() for cell in (payload.get('footer') or [])][:MAX_COLS]
    if headers and rows:
        width = max(len(headers), max((len(r) for r in rows), default=0), len(footer))
        headers = (headers + [''] * width)[:width]
        rows = [(r + [''] * width)[:width] for r in rows]
        if footer:
            footer = (footer + [''] * width)[:width]
    return title, headers, rows, footer


def _to_excel_value(value):
    text = str(value).strip()
    if not text:
        return ''
    normalized = text.replace(' ', '').replace(',', '.')
    if re.fullmatch(r'-?\d+(\.\d+)?', normalized):
        try:
            if '.' in normalized:
                return float(normalized)
            number = int(normalized)
            if len(text) > 12:
                return text
            return number
        except (TypeError, ValueError):
            return text
    return text


def build_xlsx(title, headers, rows, footer):
    workbook = Workbook()
    sheet = workbook.active
    sheet_title = re.sub(r'[:\\/\?\*\[\]]', ' ', title)[:31] or 'Exportacion'
    sheet.title = sheet_title

    header_font = Font(bold=True, color='FFFFFF')
    header_fill = PatternFill('solid', fgColor='4886BD')
    footer_fill = PatternFill('solid', fgColor='D9E8F5')
    thin = Border(
        left=Side(style='thin', color='838A91'),
        right=Side(style='thin', color='838A91'),
        top=Side(style='thin', color='838A91'),
        bottom=Side(style='thin', color='838A91'),
    )
    wrap = Alignment(wrap_text=True, vertical='center')

    for col, header in enumerate(headers, 1):
        cell = sheet.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = wrap
        cell.border = thin

    for row_idx, row in enumerate(rows, 2):
        for col, value in enumerate(row, 1):
            cell = sheet.cell(row=row_idx, column=col, value=_to_excel_value(value))
            cell.alignment = wrap
            cell.border = thin

    if footer:
        footer_row = len(rows) + 2
        for col, value in enumerate(footer, 1):
            cell = sheet.cell(row=footer_row, column=col, value=_to_excel_value(value))
            cell.font = Font(bold=True)
            cell.fill = footer_fill
            cell.alignment = wrap
            cell.border = thin

    for col in range(1, max(len(headers), 1) + 1):
        max_len = len(str(headers[col - 1])) if col <= len(headers) else 8
        for row in rows[:200]:
            if col <= len(row):
                max_len = max(max_len, min(len(str(row[col - 1])), 60))
        sheet.column_dimensions[get_column_letter(col)].width = min(max(max_len + 2, 10), 45)

    sheet.auto_filter.ref = sheet.dimensions
    sheet.freeze_panes = 'A2'

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def build_csv(headers, rows, footer):
    buffer = StringIO()
    writer = csv.writer(buffer)
    if headers:
        writer.writerow(headers)
    writer.writerows(rows)
    if footer:
        writer.writerow(footer)
    return buffer.getvalue().encode('utf-8-sig')


def build_pdf(title, headers, rows, footer):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=title,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'ExportTitle',
        parent=styles['Heading1'],
        fontSize=12,
        alignment=TA_CENTER,
        spaceAfter=8,
    )
    cell_style = ParagraphStyle(
        'ExportCell',
        parent=styles['Normal'],
        fontSize=7,
        leading=9,
        alignment=TA_LEFT,
    )
    header_style = ParagraphStyle(
        'ExportHeader',
        parent=cell_style,
        fontName='Helvetica-Bold',
        textColor=colors.white,
    )

    def as_paragraphs(values, style):
        return [Paragraph(str(value or '').replace('\n', '<br/>') or '&nbsp;', style) for value in values]

    data = [as_paragraphs(headers, header_style)]
    for row in rows:
        data.append(as_paragraphs(row, cell_style))
    if footer:
        data.append(as_paragraphs(footer, header_style))

    col_count = max(len(headers), 1)
    usable_width = landscape(A4)[0] - 20 * mm
    col_width = usable_width / col_count
    table = Table(data, colWidths=[col_width] * col_count, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4886bd')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#838a91')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    if footer:
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#4886bd')),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ]))

    doc.build([Paragraph(title, title_style), Spacer(1, 4 * mm), table])
    return buffer.getvalue()


@login_required(login_url='login')
@require_POST
def exportar_documento(request):
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Solicitud de exportación inválida.'}, status=400)

    export_format = str(payload.get('format') or 'xlsx').lower()
    title, headers, rows, footer = _normalize_payload(payload)
    if not headers:
        return JsonResponse({'error': 'No hay columnas para exportar.'}, status=400)

    if export_format in ('xlsx', 'excel'):
        content = build_xlsx(title, headers, rows, footer)
        filename = _safe_filename(title, 'xlsx')
        content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    elif export_format == 'csv':
        content = build_csv(headers, rows, footer)
        filename = _safe_filename(title, 'csv')
        content_type = 'text/csv; charset=utf-8'
    elif export_format == 'pdf':
        content = build_pdf(title, headers, rows, footer)
        filename = _safe_filename(title, 'pdf')
        content_type = 'application/pdf'
    else:
        return JsonResponse({'error': 'Formato de exportación no soportado.'}, status=400)

    response = HttpResponse(content, content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response['Cache-Control'] = 'no-store'
    return response
