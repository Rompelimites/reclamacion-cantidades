import pdfplumber
import pandas as pd
import re
import calendar
from datetime import date, datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple, Set

# --- HELPERS DE EXTRACCIÓN ROBUSTA ---

def extract_last_amount(text: str) -> float:
    """
    Busca todos los importes (ej: 1.200,50) en una línea y devuelve el ÚLTIMO.
    Si no encuentra ninguno, devuelve 0.0.
    """
    if not text: return 0.0
    # Regex para moneda europea: 1.000,00 o 100,00
    matches = re.findall(r"\b\d{1,3}(?:\.\d{3})*,\d{2}\b", text)
    if not matches: return 0.0
    
    try:
        last_val = matches[-1]
        return float(last_val.replace('.', '').replace(',', '.'))
    except:
        return 0.0

def clean_code_universal(text: Optional[str]) -> str:
    """
    Limpieza UNIVERSAL de códigos de turno.
    """
    if not isinstance(text, str): return ""
    text = text.strip().upper()
    if not text: return ""
    
    if text in ["V", "VAC", "V.", "VAC."]: return "V"
    if text.startswith("V ") or text.startswith("VAC "): return "V"
    
    text = re.sub(r'NORM', '', text)
    text = text.replace('+', '').strip()
    
    BLACKLIST = ['NORM', 'TURNO', 'DIA', 'MES', 'AJUSTES', 'H.', 'H', 'TOTAL', 'FIRMA', 'SELLO']
    if text in BLACKLIST: return ""
    
    match = re.search(r"([A-ZÑ0-9]{2,10})", text)
    if match:
        candidate = match.group(1)
        if candidate in BLACKLIST: return ""
        return candidate
    return ""

# --- PARSING DE LEYENDAS Y ESTRUCTURA ---

def parse_absenteeism_legend(text_content: str) -> Dict[str, str]:
    absent_map = {}
    pattern = r'(?:^|\n|")([A-Z]{1,5})\s*:[^"]*?"\s*,?\s*"?([^"\n]+)"?'
    
    for match in re.finditer(pattern, text_content):
        code = match.group(1).upper()
        desc = match.group(2).strip().replace('"', '')
        if len(desc) < 3 or re.match(r"\d{1,2}:\d{2}", desc): continue 
        absent_map[code] = desc
        
    if not absent_map:
        pattern_simple = r"(^|\n)\s*([A-Z]{2,5})(\s*[:\.-]?\s+)(.+)"
        for match in re.finditer(pattern_simple, text_content):
            try:
                code_s = match.group(2).strip()
                desc_s = match.group(4).strip()
                if len(desc_s) > 3 and not re.match(r"\d{1,2}:\d{2}", desc_s):
                    absent_map[code_s] = desc_s
            except: pass
    return absent_map

def extract_holidays_from_text(text_content: str, year: int) -> List[date]:
    holidays = set()
    pattern_strict = r"(\d{2}/\d{2}/\d{4})\s*:"
    for match in re.finditer(pattern_strict, text_content):
        try:
            d = datetime.strptime(match.group(1), "%d/%m/%Y").date()
            if d.year == year: holidays.add(d)
        except ValueError: pass
        
    month_map = {
        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
        "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
    }
    pattern_text = r"\b(\d{1,2})\s+(?:de\s+)?([a-zA-Z]+)"
    for match in re.finditer(pattern_text, text_content):
        try:
            day = int(match.group(1))
            month = month_map.get(match.group(2).lower())
            if month:
                try: 
                    d = date(year, month, day)
                    if d not in holidays: holidays.add(d)
                except: pass
        except: pass
    return sorted(list(holidays))

def parse_shifts_legend(text_content: str) -> Dict[str, Any]:
    detected_shifts: Dict[str, Any] = {}
    pattern_shifts = r"(?P<code>[A-Z0-9]+):\s*.*?(?P<start>\d{1,2}:\d{2})-(?P<end>\d{1,2}:\d{2})"
    for match in re.finditer(pattern_shifts, text_content):
        try:
            code = match.group("code")
            fmt = "%H:%M"
            t_start = datetime.strptime(match.group("start"), fmt)
            t_end = datetime.strptime(match.group("end"), fmt)
            if t_end < t_start: t_end += timedelta(days=1)
            duration = (t_end - t_start).total_seconds() / 3600.0
            detected_shifts[code] = {
                'start': match.group("start"), 'end': match.group("end"), 
                'hours': round(duration, 2), 'is_vacation': False
            }
        except: pass

    if re.search(r"\bV\b.*?(Vacaciones|0\s*h)", text_content, re.IGNORECASE):
        detected_shifts['V'] = {'start': None, 'end': None, 'hours': 0.0, 'is_vacation': True}
    return detected_shifts

def extract_data_from_pdf(pdf_path: str, year: Optional[int] = None) -> Tuple[pd.DataFrame, Dict[str, Any], List[date]]:
    if year is None: year = datetime.now().year
    
    data: List[Dict[str, Any]] = []
    detected_shifts: Dict[str, Any] = {}
    detected_holidays: List[date] = []
    
    month_map = {
        "Ene": 1, "Feb": 2, "Mar": 3, "Abr": 4, "May": 5, "Jun": 6,
        "Jul": 7, "Ago": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dic": 12,
        "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6,
        "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12,
        "Enero": 1, "Febrero": 2, "Marzo": 3, "Abril": 4, "Mayo": 5, "Junio": 6,
        "Julio": 7, "Agosto": 8, "Septiembre": 9, "Octubre": 10, "Noviembre": 11, "Diciembre": 12,
        "ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6,
        "JUL": 7, "AGO": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DIC": 12
    }

    try:
        with pdfplumber.open(pdf_path) as pdf:
            print("--- INICIO PROCESO (UNIVERSAL MODE - PARSER.PY) ---")
            
            # 1. Full Text
            full_text_list = []
            for page in pdf.pages: full_text_list.append(page.extract_text() or "")
            full_text = "\n".join(full_text_list)
            
            detected_shifts = parse_shifts_legend(full_text)
            absent_map = parse_absenteeism_legend(full_text) 
            detected_holidays = extract_holidays_from_text(full_text, year)
            holidays_set = set(detected_holidays) # Set lookup O(1)
            
            # 2. Process Tables
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        if not row or not row[0]: continue
                        
                        first_cell = str(row[0]).strip()
                        found_month = None
                        for m_name, m_num in month_map.items():
                            if re.match(rf"(?i)^{re.escape(m_name)}\b", first_cell):
                                found_month = m_num
                                break
                        
                        if found_month:
                            try: _, num_days = calendar.monthrange(year, found_month)
                            except: num_days = 31
                            
                            for day_idx in range(1, len(row)):
                                current_day = day_idx
                                if current_day > num_days: break
                                
                                raw_cell = row[day_idx]
                                cell_text = str(raw_cell) if raw_cell else ""
                                
                                # LIMPIEZA UNIVERSAL
                                code = clean_code_universal(cell_text)
                                
                                if not code: continue
                                
                                # Regla Explicita: V siempre es Vacaciones
                                if code == 'V':
                                    if 'V' not in detected_shifts:
                                        detected_shifts['V'] = {
                                            'hours': 0.0,
                                            'is_vacation': True,
                                            'type': 'Absentismo',
                                            'description': 'Vacaciones (Detectado)'
                                        }

                                # A. Absentismo Conocido
                                elif code in absent_map:
                                    if code not in detected_shifts:
                                        print(f"   [TABLA] Aplicando Absentismo ({code}): {absent_map[code]}")
                                        detected_shifts[code] = {
                                            'hours': 0.0,
                                            'is_vacation': True,
                                            'type': 'Absentismo',
                                            'description': absent_map[code]
                                        }
                                
                                # B. Desconocido (UNKNOWN)
                                elif code not in detected_shifts:
                                    print(f"   [UNKNOWN] Código desconocido detectado: {code}")
                                    detected_shifts[code] = {
                                        'hours': 0.0, 
                                        'type': 'UNKNOWN',
                                        'description': 'Código Nuevo Detectado'
                                    }
                                
                                # Create Entry
                                current_date = date(year, found_month, current_day)
                                entry = {
                                    "Fecha": current_date,
                                    "Mes": found_month,
                                    "Dia": current_day,
                                    "Codigo": code,
                                    "Tipo_Jornada": "Ordinario"
                                }
                                
                                # Check Holiday
                                if current_date in holidays_set:
                                    entry["Tipo_Jornada"] = "Festivo"
                                    # print(f"   [FESTIVO] Marcado: {current_date}")

                                data.append(entry)

    except Exception as e:
        print(f"Error crítico: {e}")
        return pd.DataFrame(data), {}, []

    df = pd.DataFrame(data)
    return df, detected_shifts, detected_holidays

def get_unique_codes(df: pd.DataFrame) -> List[str]:
    if df.empty or 'Codigo' not in df.columns: return []
    codes = df['Codigo'].unique().tolist()
    return sorted([str(c) for c in codes if c and str(c).strip()])

def get_vacation_periods(df: pd.DataFrame) -> List[Tuple[date, date]]:
    if df.empty or 'Codigo' not in df.columns: return 0, []
    v_days_df = df[df['Codigo'] == 'V']
    if v_days_df.empty: return 0, []
    dates = sorted(v_days_df['Fecha'].unique())
    if not dates: return 0, []
    periods = []
    curr_start = dates[0]
    curr_end = dates[0]
    for i in range(1, len(dates)):
        if (dates[i] - dates[i-1]).days == 1: curr_end = dates[i]
        else:
            periods.append((curr_start, curr_end)); curr_start = dates[i]; curr_end = dates[i]
    periods.append((curr_start, curr_end))
    return len(dates), periods

# --- CORE: ANÁLISIS DE NÓMINA (FIX CRÍTICO) ---

# --- CORE: ANÁLISIS DE NÓMINA (CORREGIDO) ---

def parse_payroll_text(text: str) -> Dict[str, Any]:
    results = {
        'salario_base': 0.0, 
        'antiguedad': 0.0, 
        'plus_convenio': 0.0, 
        'nocturnidad': 0.0,
        'festividad': 0.0, # Nuevo campo variable
        'dietas': 0.0,
        'paga_extra': 0.0, 
        'year': datetime.now().year,
        'company': "N/D", 
        'worker': "N/D",
        'categoria': "N/D"
    }
    
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    full_text_upper = text.upper()
    
    # 1. Búsqueda de Año
    match_year = re.search(r"\b(202\d)\b", text)
    if match_year: results['year'] = int(match_year.group(1))

    # 2. Extracción de Trabajador / Categoría / Fecha (Regex Específico)
    # Patrón: (Nombre) (Categoría: TES/Cond) (Fecha Antigüedad)
    # Ej: JOSE PEREZ TES CONDUCTOR 01/05/2020
    worker_regex = re.compile(r"^(.+?)\s+(TES\s+.*?|CONDUCTOR.*?)\s+(\d{2}/\d{2}/\d{4})", re.IGNORECASE)
    
    found_worker = False
    for line in lines[:30]:
        if "TRABAJADOR" in line.upper(): continue # Skip label line
        
        match = worker_regex.search(line)
        if match:
            results['worker'] = match.group(1).strip()
            results['categoria'] = match.group(2).strip()
            results['antiguedad_fecha'] = match.group(3) 
            found_worker = True
            break
            
    # Fallback si no encuentra regex estricto
    if not found_worker:
        for i, line in enumerate(lines[:30]):
            if "TRABAJADOR" in line.upper():
                if ":" in line: 
                    results['worker'] = line.split(":")[1].strip()
                elif i+1 < len(lines):
                    results['worker'] = lines[i+1].strip()
                break

    # 3. Empresa (Lógica Mejorada)
    # Ignorar NIFs o líneas numéricas. Buscar S.L, S.A, AMBULANCIAS.
    for i, line in enumerate(lines[:20]):
        upper = line.upper()
        if "DOMICILIO" in upper: continue
        
        # Filtros negativos
        if "NIF" in upper or "CIF" in upper: continue
        if re.match(r"^\d", line): continue # Empieza por numero (CP, Telefono)
        
        # Filtros positivos
        if "AMBULANCIAS" in upper or "S.L." in upper or "S.A." in upper or "UTE" in upper:
            results['company'] = line.strip()
            break
        
        # Fallback: Si está cerca de la cabecera "EMPRESA"
        if "EMPRESA" in upper:
            if i+1 < len(lines) and not "DOMICILIO" in lines[i+1].upper():
                potential = lines[i+1].strip()
                if not re.match(r"^[A-Z]\-?\d", potential): # No es CIF
                    results['company'] = potential
                    break

    # 4. EXTRACCIÓN ECONÓMICA (REGLA LAST NUMBER)
    for line in lines:
        upper = line.upper()
        
        # Saltamos líneas de cabecera/informativas
        if "TOTAL DEVENGADO" in upper or "TOTAL A PERCIBIR" in upper: continue
        if "EUROS" in upper or "UNIDADES" in upper: continue
        
        # A. Salario Base
        if "SALARIO BASE" in upper and "PAGA" not in upper:
            val = extract_last_amount(line)
            if val > results['salario_base']: results['salario_base'] = val
            
        # B. Antigüedad
        if "ANTIGUEDAD" in upper and "PAGA" not in upper:
            val = extract_last_amount(line)
            if val > results['antiguedad']: results['antiguedad'] = val
            
        # C. Plus Convenio
        if "PLUS CONVENIO" in upper and "SALARIO BASE" not in upper:
            val = extract_last_amount(line)
            if val > results['plus_convenio']: results['plus_convenio'] = val
            
        # D. Nocturnidad
        if ("NOCTURNIDAD" in upper or "NOCTURNO" in upper) and "HORAS" not in upper:
            val = extract_last_amount(line)
            # Acumulativo si hay varias líneas (raro pero posible)
            if val > results['nocturnidad']: results['nocturnidad'] = val
            
        # E. Festividad
        if "FESTIV" in upper or "DOMINGO" in upper:
             val = extract_last_amount(line)
             if val > results['festividad']: results['festividad'] = val

        # F. Dietas
        if "DIETA" in upper or "MANUTENCION" in upper:
            val = extract_last_amount(line)
            if val > results['dietas']: results['dietas'] = val
            
        # G. Paga Extra (Prorratas)
        if "PAGA EXTRA" in upper or "PAGA BENEFICIOS" in upper:
            val = extract_last_amount(line)
            if val > 0: results['paga_extra'] = val


    # --- CÁLCULOS FINALES ---
    base_calc = results['salario_base'] + results['antiguedad']
    results['tercera_paga_teorica'] = base_calc
    
    is_prorated = False
    if "PRORRATA" in full_text_upper or "P.P." in full_text_upper: is_prorated = True
    elif results['paga_extra'] > 0 and results['paga_extra'] < (base_calc * 0.4):
        is_prorated = True
        
    results['is_prorated'] = is_prorated
    if is_prorated: results['tercera_paga'] = 0.0
    else: results['tercera_paga'] = base_calc

    return results

def extract_payroll_data(pdf_path: str) -> Dict[str, Any]:
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for p in pdf.pages: text += (p.extract_text() or "") + "\n"
    except: return {}
    return parse_payroll_text(text)

def analyze_annual_payroll(pdf_files: List[Any]) -> Dict[str, Any]:
    """
    Analiza múltiples nóminas con lógica híbrida:
    - Conceptos Estructurales (Fijos): MAX()
    - Conceptos Variables (Nocturnidad, Dietas): SUM()
    """
    aggregated = {
        'salario_base': 0.0, 'antiguedad': 0.0, 'plus_convenio': 0.0, 
        'nocturnidad': 0.0, 'festividad': 0.0, 'dietas': 0.0, 'total_abonado_tercera': 0.0,
        'year': datetime.now().year, 'company': "N/D", 'worker': "N/D", 'categoria': "N/D"
    }
    
    count_payrolls = 0
    for pdf_file in pdf_files:
        try:
            text = ""
            with pdfplumber.open(pdf_file) as pdf:
                for p in pdf.pages: text += (p.extract_text() or "") + "\n"
            data = parse_payroll_text(text)
            count_payrolls += 1
            
            # 1. CONCEPTOS FIJOS (Estructurales) -> Usamos MAX para encontrar el valor nominal
            if data['salario_base'] > aggregated['salario_base']: aggregated['salario_base'] = data['salario_base']
            if data['antiguedad'] > aggregated['antiguedad']: aggregated['antiguedad'] = data['antiguedad']
            if data['plus_convenio'] > aggregated['plus_convenio']: aggregated['plus_convenio'] = data['plus_convenio']
            
            # 2. CONCEPTOS VARIABLES (Acumulativos) -> Usamos SUM para total anual auditado
            aggregated['nocturnidad'] += data.get('nocturnidad', 0.0)
            aggregated['festividad'] += data.get('festividad', 0.0)
            aggregated['dietas'] += data.get('dietas', 0.0)
            
            # Datos Informativos (Overwrite con el último válido)
            if data['year'] > 2020: aggregated['year'] = data['year']
            if data['worker'] and data['worker'] != "N/D": aggregated['worker'] = data['worker']
            if data['categoria'] and data['categoria'] != "N/D": aggregated['categoria'] = data['categoria']
            if data['company'] and data['company'] != "N/D": aggregated['company'] = data['company']
            
            # 3. Paga Extra (Suma)
            if "PAGA BENEFICIOS" in text.upper() or "PAGA MARZO" in text.upper():
                 if data['paga_extra'] > (data['salario_base'] * 0.5):
                    aggregated['total_abonado_tercera'] += data['paga_extra']
                
        except Exception: continue

    aggregated['tercera_paga_teorica'] = aggregated['salario_base'] + aggregated['antiguedad']
    return aggregated
