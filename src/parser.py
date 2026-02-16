import pdfplumber
import pandas as pd
import re
import calendar
from datetime import date, datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple, Set

# --- HELPERS GENERALES ---

def extract_last_amount(text: str) -> float:
    """Busca el último importe monetario válido en una línea."""
    if not text: return 0.0
    clean_text = text.replace("€", "").strip()
    matches = re.findall(r"(?:\d{1,3}(?:\.\d{3})*,\d{2})", clean_text)
    if not matches:
        matches = re.findall(r"(?:\d{1,3}(?:,\d{3})*\.\d{2})", clean_text)

    if matches:
        last_val = matches[-1]
        if "," in last_val and "." in last_val: 
            return float(last_val.replace('.', '').replace(',', '.'))
        elif "," in last_val: 
            return float(last_val.replace(',', '.'))
        else: 
            return float(last_val)
    return 0.0

def clean_code_universal(text: Optional[str]) -> str:
    """
    Limpia códigos de turno.
    FIX: Acepta códigos de absentismo (ENF, DLD, MTRI) y numéricos.
    """
    if not isinstance(text, str): return ""
    text = text.strip().upper()
    if not text: return ""
    
    # 1. Códigos de Texto Válidos (Incluyendo Absentismos detectados en tu PDF)
    VALID_CODES = ["M", "T", "N", "L", "V", "VAC", "LD", "L.D.", "D", 
                   "ENF", "BAJA", "DLD", "MTRI", "AP", "LIBRE"]
    if text in VALID_CODES: return text
    
    # 2. Códigos Numéricos (1208, 708...)
    if text.replace("-", "").isdigit(): return text
    
    # 3. Códigos Alfanuméricos cortos
    if len(text) <= 5 and re.match(r"^[A-Z0-9]+$", text): return text

    # Limpieza de basura
    text = re.sub(r'NORM', '', text)
    text = text.replace('+', '').strip()
    
    # Eliminar corchetes vacíos o basura de OCR
    if text in ["[]", "[ ]", "()", "( )"]: return ""

    BLACKLIST = ['NORM', 'TURNO', 'DIA', 'MES', 'AJUSTES', 'H.', 'H', 'TOTAL', 'FIRMA', 'SELLO', 'LIQUIDO', 'PAG.', 'PAGINA', 'CONCEPTO']
    if text in BLACKLIST: return ""
    
    if len(text) > 8: return "" 
    
    return text

def get_unique_codes(df: pd.DataFrame) -> List[str]:
    """Obtiene lista de códigos únicos."""
    if df.empty or 'Codigo' not in df.columns: return []
    codes = df['Codigo'].unique().tolist()
    return sorted([str(c) for c in codes if c and str(c).strip()])

def get_vacation_periods(df: pd.DataFrame) -> Tuple[int, List[Tuple[date, date]]]:
    """Calcula periodos de vacaciones."""
    if df.empty or 'Codigo' not in df.columns: return 0, []
    # Buscamos códigos que empiecen por V o contengan VAC
    v_days_df = df[df['Codigo'].str.contains(r'^V|VAC', regex=True, na=False)]
    
    if v_days_df.empty: return 0, []
    
    dates = sorted(v_days_df['Fecha'].unique())
    if not dates: return 0, []
    
    periods = []
    curr_start = dates[0]
    curr_end = dates[0]
    
    for i in range(1, len(dates)):
        if (dates[i] - dates[i-1]).days == 1:
            curr_end = dates[i]
        else:
            periods.append((curr_start, curr_end))
            curr_start = dates[i]
            curr_end = dates[i]
    periods.append((curr_start, curr_end))
    
    return len(dates), periods

def extract_holidays_from_text(text_content: str, year: int) -> List[date]:
    holidays = set()
    pattern_strict = r"(\d{2}/\d{2}/\d{4})"
    for match in re.finditer(pattern_strict, text_content):
        try:
            d = datetime.strptime(match.group(1), "%d/%m/%Y").date()
            if d.year == year: holidays.add(d)
        except ValueError: pass
    return sorted(list(holidays))

# --- NUEVA FUNCIÓN: LEER ABSENTISMO (ENF, DLD...) ---
def parse_absenteeism_legend(text: str) -> Dict[str, str]:
    """
    Busca patrones de absentismo en la leyenda.
    Ejemplo en PDF: "DLD 03. Dia de libre disposición"
    """
    legend = {}
    # Patrones específicos vistos en tu PDF
    patterns = [
        r"(?P<code>[A-Z]{2,4})\s*\d+\.\s*(?P<desc>[A-Za-z\s\.]+):", # DLD 03. Dia... :
        r"(?P<code2>[A-Z]{2,4})\n\d+\.\s*(?P<desc2>[A-Za-z\s\.]+)"  # Salto de línea
    ]
    
    for pat in patterns:
        for match in re.finditer(pat, text):
            try:
                if 'code' in match.groupdict():
                    c = match.group("code")
                    d = match.group("desc")
                else:
                    c = match.group("code2")
                    d = match.group("desc2")
                
                if c and d:
                    legend[c.strip()] = d.strip().replace('\n', ' ')
            except: pass
            
    return legend

# --- NUEVA FUNCIÓN: LEER LEYENDA DE TURNOS ---
def parse_shifts_legend_from_text(text: str) -> Dict[str, Any]:
    """
    Busca patrones como '1308 ... 08:00-21:00' en el texto del PDF.
    """
    detected_legend = {}
    pattern = r"(?P<code>\d{3,4})[:\s].*?(?P<start>\d{1,2}:\d{2})\s*-\s*(?P<end>\d{1,2}:\d{2})"
    
    for match in re.finditer(pattern, text):
        try:
            code = match.group("code")
            start_str = match.group("start")
            end_str = match.group("end")
            
            fmt = "%H:%M"
            t_start = datetime.strptime(start_str, fmt)
            t_end = datetime.strptime(end_str, fmt)
            
            if t_end < t_start:
                t_end += timedelta(days=1)
                
            hours = (t_end - t_start).total_seconds() / 3600.0
            
            detected_legend[code] = {
                'start': start_str,
                'end': end_str,
                'hours': round(hours, 2),
                'is_vacation': False,
                'description': f"Guardia ({start_str}-{end_str})"
            }
        except: pass
        
    return detected_legend

# --- PARSING DE CUADRANTE ---

def extract_data_from_pdf(pdf_path: str, year: Optional[int] = None) -> Tuple[pd.DataFrame, Dict[str, Any], List[date]]:
    if year is None: year = datetime.now().year
    data: List[Dict[str, Any]] = []
    detected_shifts = {} 
    detected_holidays = []
    
    month_map = {
        "ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6,
        "JUL": 7, "AGO": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DIC": 12,
        "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6,
        "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12
    }

    try:
        with pdfplumber.open(pdf_path) as pdf:
            full_text = ""
            for page in pdf.pages: full_text += (page.extract_text() or "") + "\n"
            
            # 1. Extraer Festivos (Set para evitar duplicados)
            holidays_set = set(extract_holidays_from_text(full_text, year))
            # FIX: Convertir a lista y ordenar UNA SOLA VEZ
            detected_holidays = sorted(list(holidays_set))
            
            # 2. Extraer Leyendas (Turnos y Absentismo)
            legend_shifts = parse_shifts_legend_from_text(full_text)
            absent_legend = parse_absenteeism_legend(full_text)
            
            detected_shifts.update(legend_shifts)

            # 3. Procesar Tablas
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        if not row or not row[0]: continue
                        first_cell = str(row[0]).strip().upper()
                        
                        found_month = None
                        for m_name, m_num in month_map.items():
                            if first_cell.startswith(m_name):
                                found_month = m_num
                                break
                        
                        if found_month:
                            try: _, num_days = calendar.monthrange(year, found_month)
                            except: num_days = 31
                            
                            for day_idx in range(1, len(row)):
                                if day_idx > num_days: break 
                                
                                raw_cell = row[day_idx]
                                cell_text = str(raw_cell) if raw_cell else ""
                                code = clean_code_universal(cell_text)
                                
                                if not code: continue
                                
                                # --- LÓGICA DE TIPOS ---
                                if code not in detected_shifts:
                                    # Por defecto
                                    is_vacation_code = code in ['V', 'VAC', 'LD', 'L.D.', 'D']
                                    desc = 'Turno Detectado'
                                    
                                    # Si está en leyenda de absentismo (ENF, DLD, MTRI)
                                    if code in absent_legend:
                                        is_vacation_code = True # Absentismo cuenta como "no trabajado" para cómputo de horas
                                        desc = absent_legend[code]
                                    
                                    # Si son números, es TRABAJO
                                    if code.isdigit() or code.replace("-", "").isdigit():
                                        is_vacation_code = False
                                    
                                    detected_shifts[code] = {
                                        'hours': 0.0, 
                                        'is_vacation': is_vacation_code,
                                        'description': desc
                                    }

                                current_date = date(year, found_month, day_idx)
                                is_holiday = current_date in holidays_set
                                
                                entry = {
                                    "Fecha": current_date, 
                                    "Mes": found_month, 
                                    "Dia": day_idx,
                                    "Codigo": code, 
                                    "Tipo_Jornada": "Festivo" if is_holiday else "Ordinario"
                                }
                                data.append(entry)
    except Exception as e:
        print(f"Error parsing PDF: {e}")
        return pd.DataFrame(), {}, []
    
    return pd.DataFrame(data), detected_shifts, detected_holidays

# --- PARSING DE NÓMINA (INTACTO) ---

def parse_payroll_text(text: str, tables: List[List[List[str]]] = None) -> Dict[str, Any]:
    results = {
        'salario_base': 0.0, 'antiguedad': 0.0, 'plus_convenio': 0.0, 
        'nocturnidad': 0.0, 'festividad': 0.0, 'dietas': 0.0,
        'paga_extra': 0.0, 'year': datetime.now().year,
        'company': "N/D", 'worker': "N/D", 'categoria': "N/D", 'antiguedad_fecha': "N/D",
        'tercera_paga': 0.0, 'is_prorated': False
    }
    
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    match_year = re.search(r"\b(202\d)\b", text)
    if match_year: results['year'] = int(match_year.group(1))

    if tables:
        for table in tables:
            if not table: continue
            for i, row in enumerate(table):
                row_str = " ".join([str(c).upper().replace('\n', ' ') for c in row if c])
                
                if "EMPRESA" in row_str and len(row) > 0:
                     if i + 1 < len(table):
                        empresa_val = table[i+1][0]
                        if empresa_val:
                            val_clean = str(empresa_val).replace('\n', ' ').strip()
                            BLACKLIST_CORP = ["CONCEPTO", "PRECIO", "IMPORTE", "TOTAL", "CUANTIA", "SELLO", "RECIBI", "FIRMA"]
                            is_valid = True
                            for bad_word in BLACKLIST_CORP:
                                if bad_word in val_clean: is_valid = False; break
                            if is_valid: results['company'] = val_clean

                if "TRABAJADOR" in row_str:
                    if i + 1 < len(table):
                        data_row = table[i+1]
                        if len(data_row) > 0 and data_row[0]:
                            results['worker'] = str(data_row[0]).replace('\n', ' ').strip()
                        if len(data_row) > 3 and data_row[3]:
                             results['categoria'] = str(data_row[3]).replace('\n', ' ').strip()
                        elif len(data_row) > 1 and data_row[1]: 
                             results['categoria'] = str(data_row[1]).replace('\n', ' ').strip()
                        for cell in data_row:
                            if cell:
                                date_match = re.search(r"(\d{2}/\d{2}/\d{4})", str(cell))
                                if date_match:
                                    results['antiguedad_fecha'] = date_match.group(1); break

    if results['company'] == "N/D":
        for line in lines[:25]:
            if "AMBULANCIAS" in line.upper():
                results['company'] = line.strip()
                break

    for line in lines:
        upper = line.upper()
        if "TOTAL" in upper or ("BASE" in upper and "COTIZACION" in upper): continue
        amount = extract_last_amount(line)
        if amount == 0.0: continue
        es_paga_extra = any(x in upper for x in ["PAGA", "EXTRA", "ATRASOS", "NAVIDAD", "BENEFICIOS"])
        if es_paga_extra:
            results['paga_extra'] += amount
            continue 
        if "SALARIO BASE" in upper: results['salario_base'] = amount
        elif "ANTIGUEDAD" in upper: results['antiguedad'] = amount
        elif "CONVENIO" in upper: 
            if "SEGURO" not in upper: results['plus_convenio'] = amount
        elif "NOCTURN" in upper: results['nocturnidad'] += amount
        elif "FESTIV" in upper: results['festividad'] += amount
        elif "DIETA" in upper or "MANUTENCION" in upper: results['dietas'] += amount

    base_calc = results['salario_base'] + results['antiguedad'] + results['plus_convenio']
    results['tercera_paga'] = base_calc
    return results

def extract_payroll_data(pdf_path: str) -> Dict[str, Any]:
    text = ""
    tables = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for p in pdf.pages: 
                text += (p.extract_text() or "") + "\n"
                extracted_tables = p.extract_tables()
                if extracted_tables: tables.extend(extracted_tables)
    except: return {}
    return parse_payroll_text(text, tables)

def analyze_annual_payroll(pdf_files: List[Any]) -> Dict[str, Any]:
    aggregated = {
        'salario_base': 0.0, 'antiguedad': 0.0, 'plus_convenio': 0.0, 
        'nocturnidad': 0.0, 'festividad': 0.0, 'dietas': 0.0, 'total_abonado_tercera': 0.0,
        'year': datetime.now().year, 'company': "N/D", 'worker': "N/D", 
        'categoria': "N/D", 'antiguedad_fecha': "N/D"
    }
    for pdf_file in pdf_files:
        data = extract_payroll_data(pdf_file)
        if data['salario_base'] > aggregated['salario_base']: aggregated['salario_base'] = data['salario_base']
        if data['antiguedad'] > aggregated['antiguedad']: aggregated['antiguedad'] = data['antiguedad']
        if data['plus_convenio'] > aggregated['plus_convenio']: aggregated['plus_convenio'] = data['plus_convenio']
        aggregated['nocturnidad'] += data.get('nocturnidad', 0.0)
        aggregated['festividad'] += data.get('festividad', 0.0)
        aggregated['dietas'] += data.get('dietas', 0.0)
        if data['worker'] != "N/D": aggregated['worker'] = data['worker']
        if data['company'] != "N/D" and data['company'] not in ["CONCEPTO", "PRECIO"]:
             aggregated['company'] = data['company']
        if data['categoria'] != "N/D": aggregated['categoria'] = data['categoria']
        if data['antiguedad_fecha'] != "N/D": aggregated['antiguedad_fecha'] = data['antiguedad_fecha']

    return aggregated