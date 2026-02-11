import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from io import BytesIO
import pandas as pd

def generate_excel(df, shift_mapping, prices, holidays, worker_name="N/D", company_name="N/D"):
    """
    Genera un Excel con:
    1. Pestaña "RESUMEN EJECUTIVO".
    2. Pestaña por cada Mes "ENERO", "FEBRERO", etc.
    """
    output = BytesIO()
    wb = openpyxl.Workbook()
    
    # --- ESTILOS COMUNES ---
    COLOR_HEADER_BG = "4F81BD"  # Azul solicitado
    COLOR_HEADER_FONT = "FFFFFF"
    
    # Estilo Rojo (Deuda)
    red_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
    red_font = Font(color="9C0006", bold=True)

    # Estilo Verde (Festivo)
    green_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
    green_font = Font(color="006100", bold=True)
    
    border_thin = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
    border_medium = Border(left=Side(style='medium'), right=Side(style='medium'), top=Side(style='medium'), bottom=Side(style='medium'))
    
    font_bold = Font(bold=True)
    font_title = Font(bold=True, size=14)
    font_subtitle = Font(bold=True, size=12)
    
    align_center = Alignment(horizontal='center', vertical='center')
    align_right = Alignment(horizontal='right', vertical='center')
    
    # ---------------------------------------------------------
    # HOJA 1: RESUMEN EJECUTIVO (MEJORADO)
    # ---------------------------------------------------------
    ws_summary = wb.active
    ws_summary.title = "RESUMEN EJECUTIVO"
    
    # 1. Cabecera del Informe
    ws_summary.merge_cells('B2:E2')
    ws_summary['B2'] = "INFORME TÉCNICO V3 - AUDITORÍA & RECLAMACIÓN"
    ws_summary['B2'].font = font_title
    ws_summary['B2'].alignment = align_center
    ws_summary['B2'].border = border_medium
    
    # Datos Extraídos (Parser Auditor)
    cat_prof = prices.get('categoria', 'N/D')
    
    ws_summary['B4'] = "TRABAJADOR:"
    ws_summary['C4'] = worker_name
    ws_summary['B5'] = "CATEGORÍA PROF:"
    ws_summary['C5'] = cat_prof
    ws_summary['B6'] = "EMPRESA:"
    ws_summary['C6'] = company_name
    ws_summary['B7'] = "FECHA INFORME:"
    ws_summary['C7'] = pd.Timestamp.now().strftime("%d/%m/%Y")
    
    for row in range(4, 8):
        ws_summary[f'B{row}'].font = font_bold
        ws_summary[f'C{row}'].alignment = Alignment(horizontal='left')
        
    # 2. Desglose de Conceptos Detectados
    ws_summary.merge_cells('B9:E9')
    ws_summary['B9'] = "CONCEPTOS SALARIALES DETECTADOS (MEDIA MENSUAL)"
    ws_summary['B9'].font = font_subtitle
    ws_summary['B9'].alignment = align_center
    ws_summary['B9'].fill = PatternFill(start_color="E0E0E0", end_color="E0E0E0", fill_type='solid')
    ws_summary['B9'].border = border_thin
    
    concepts = [
        ("Salario Base", prices.get('base_salary', 0)),
        ("Plus Convenio", prices.get('plus_agreement', 0)),
        ("Antigüedad", prices.get('seniority', 0)),
        ("Nocturnidad (Audit)", prices.get('nocturnidad', 0)),
        ("Dietas (Audit)", prices.get('dietas', 0)),
    ]
    
    curr = 11
    for name, val in concepts:
        ws_summary[f'B{curr}'] = name
        ws_summary[f'C{curr}'] = f"{val:.2f} €"
        curr += 1

    # Fórmula Precio Hora
    precio_hora = prices.get('price_normal', 0.0)
    ws_summary[f'B{curr+1}'] = "PRECIO HORA CALCULADO:"
    ws_summary[f'B{curr+1}'].font = font_bold
    ws_summary[f'C{curr+1}'] = f"{precio_hora:.4f} €"
    ws_summary[f'C{curr+1}'].font = Font(bold=True, size=12, color="0000FF")
    
    # ---------------------------------------------------------
    # HOJA 2: DETALLE MENSUAL (BLOQUES VISUALES)
    # ---------------------------------------------------------
    
    # Preparar datos
    df['Mes_Num'] = df['Fecha'].apply(lambda x: x.month)
    meses_ordenados = sorted(df['Mes_Num'].unique())
    
    month_names = {
        1:"ENERO", 2:"FEBRERO", 3:"MARZO", 4:"ABRIL", 5:"MAYO", 6:"JUNIO", 
        7:"JULIO", 8:"AGOSTO", 9:"SEPTIEMBRE", 10:"OCTUBRE", 11:"NOVIEMBRE", 12:"DICIEMBRE"
    }
    
    header_fill = PatternFill(start_color=COLOR_HEADER_BG, end_color=COLOR_HEADER_BG, fill_type='solid')
    header_font_style = Font(bold=True, color=COLOR_HEADER_FONT)
    holidays_set = set(holidays)

    # Crear única hoja
    ws_detail = wb.create_sheet("DETALLE MENSUAL")
    current_row = 1

    # Definir anchos
    widths = [12, 12, 12, 10, 10, 12, 15, 20, 15]
    for i, w in enumerate(widths, 1):
        ws_detail.column_dimensions[get_column_letter(i)].width = w

    for m_num in meses_ordenados:
        m_name = month_names.get(m_num, f"MES_{m_num}")
        
        # 1. SEPARADOR VISUAL (Bloque Azul)
        ws_detail.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=9)
        cell_title = ws_detail.cell(row=current_row, column=1, value=f"MES: {m_name}")
        cell_title.font = Font(bold=True, size=14, color="FFFFFF")
        cell_title.fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type='solid')
        cell_title.alignment = align_center
        current_row += 1
        
        # 2. CABECERAS
        headers = ["FECHA", "ENTRADA", "SALIDA", "CÓDIGO", "HORAS", "DEUDA (H)", "TIEMPO DESCANSO", "ESTADO", "IMPORTE (€)"]
        
        for col_num, header in enumerate(headers, 1):
            cell = ws_detail.cell(row=current_row, column=col_num, value=header)
            cell.font = header_font_style
            cell.fill = header_fill
            cell.alignment = align_center
            cell.border = border_thin
            
        current_row += 1
        
        # 3. DATOS
        df_month = df[df['Mes_Num'] == m_num].sort_values('Fecha')
        
        for _, row in df_month.iterrows():
            code = row.get('Codigo', '')
            info = shift_mapping.get(code, {})
            start = info.get('start', '-')
            end = info.get('end', '-')
            
            es_vacation = info.get('is_vacation')
            if es_vacation or code == 'V':
                start = "-"; end = "-"
                
            debt_h = row.get('Deuda_Descanso_Horas', 0.0)
            debt_minutes = int(round(debt_h * 60))
            if debt_h > 0:
                rest_str = f"{debt_minutes} min" 
            else:
                rest_str = "-"
            
            # Estado Logic
            date_obj = row['Fecha']
            is_holiday_manual = date_obj in holidays_set
            tipo = row.get('Tipo_Jornada', 'Ordinario')
            
            estado_texto = "Ordinario"
            if is_holiday_manual: estado_texto = "Festivo"
            elif tipo == "Festivo": estado_texto = "Festivo"
            elif es_vacation or code == 'V': estado_texto = "Vacaciones"
            elif info.get('type') == 'Absentismo': estado_texto = info.get('description', 'Absentismo')
            elif info.get('type') == 'Unknown': estado_texto = "Revisar"
            
            importe = debt_h * precio_hora
            
            # Escribir fila
            vals = [
                date_obj.strftime("%d/%m/%Y"), start, end, code, 
                row.get('Horas_Totales', 0), debt_h, rest_str, estado_texto, importe
            ]
            
            for c_idx, val in enumerate(vals, 1):
                cell = ws_detail.cell(row=current_row, column=c_idx, value=val)
                cell.alignment = align_center
                cell.border = border_thin
                
                # Format Importe
                if c_idx == 9: 
                    cell.number_format = '#,##0.00 €'
                    cell.alignment = align_right
                
                # Colores Condicionales
                # 6: Deuda (H), 7: Tiempo Descanso -> ROJO
                if c_idx in [6, 7] and debt_h > 0:
                    cell.fill = red_fill
                    cell.font = red_font
                    
                # 8: Estado -> Verde (Festivo)
                if c_idx == 8 and estado_texto == "Festivo":
                     cell.fill = green_fill
                     cell.font = green_font
                     # Pintar fecha también
                     ws_detail.cell(row=current_row, column=1).fill = green_fill

            current_row += 1
            
        # 4. ESPACIO EN BLANCO (Separador de Bloques)
        current_row += 2 # Dejar una fila vacía extra

    wb.save(output)
    output.seek(0)
    return output
