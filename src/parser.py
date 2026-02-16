import pdfplumber
import pandas as pd
import re
import calendar
from datetime import date, datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple, Set

# --- 1. LIMPIEZA Y UTILIDADES ---

def extract_last_amount(text: str) -> float:
    if not text: return 0.0
    clean_text = text.replace("€", "").strip()
    matches = re.findall(r"(?:\d{1,3}(?:\.\d{3})*,\d{2})", clean_text)
    if not matches: matches = re.findall(r"(?:\d{1,3}(?:,\d{3})*\.\d{2})", clean_text)
    if matches:
        last_val = matches[-1]
        if "," in last_val and "." in last_val: return float(last_val.replace('.', '').replace(',', '.'))
        elif "," in last_val: return float(last_val.replace(',', '.'))
        else: return float(last_val)
    return 0.0

def clean_code_universal(text: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Analiza la celda con REGLAS ESTRICTAS:
    1. Si hay NÚMERO (Turno) -> ES DÍA DE TRABAJO. (Buscamos siglas extra).
    2. Si hay "V" o "VAC" -> ES VACACIONES (Única excepción sin número).
    3. Si NO hay número NI vacaciones -> DÍA LIBRE / SALTADO (Aunque haya ENF, MTRI...).
    
    Retorna: (CÓDIGO_PRINCIPAL, SIGLAS_EXTRA)
    """
    if not isinstance(text, str): return None, None
    text_upper = text.replace("\n", " ").strip().upper()
    if not text_upper: return None, None

    # Listas de referencia
    GARBAGE = ["NORM", "[+]", "[]", "DIA", "DE", "LA", "EL"] 
    # Siglas que nos importan SOLO si acompañan a un número (salvo V/VAC)
    ACRONYMS = ["ENF", "MTRI", "MTRL", "DLD", "BAJA", "IT", "AP", "LIBRE", "PATER", "MATER", "L.D.", "LD", "ALTA"]
    
    found_shift = None
    found_acronym = None
    is_vacation = False
    
    tokens = text_upper.split()
    
    for token in tokens:
        # 0. Limpieza token
        clean_token = re.sub(r'[^A-Z0-9]', '', token)
        
        # 1. ¿Es Vacación?
        if clean_token in ["V", "VAC"]:
            is_vacation = True
            continue # Seguimos buscando por si hay más info, pero ya marcamos flag
            
        # 2. ¿Es Basura?
        if any(g in token for g in GARBAGE): continue

        # 3. ¿Es Sigla (Acronym)?
        is_acronym_token = False
        for ac in ACRONYMS:
            if ac in token or ac == clean_token:
                val = "MTRI" if "MTRL" in token else ac
                if val in ["L.D.", "LD"]: val = "DLD"
                
                if not found_acronym: found_acronym = val
                is_acronym_token = True
                break
        if is_acronym_token: continue

        # 4. ¿Es Turno Numérico?
        # Prioridad absoluta. Si encontramos uno, lo guardamos.
        # Si YA teníamos uno, PARAMOS (Regla del Límite).
        if re.match(r'^\d{3,4}$', clean_token) and clean_token not in ["2024", "2025", "2026"]:
             if found_shift:
                 break # Stop scanning tokens
             found_shift = clean_token
             continue

    # --- LÓGICA DE DECISIÓN FINAL ---
    
    # CASO A: VACACIONES (Gana a todo, es la excepción)
    if is_vacation:
        return "V", found_acronym # Retornamos "V" como código ppal
        
    # CASO B: HAY TURNO NUMÉRICO (Día de trabajo válido)
    if found_shift:
        return found_shift, found_acronym
        
    # CASO C: NO HAY TURNO NI VACACIONES -> DÍA SALTADO
    # (Incluso si hay found_acronym como "ENF", si no hay número, se ignora según orden usuario)
    return None, None
def get_unique_codes(df: pd.DataFrame) -> List[str]:
    if df.empty or 'Codigo' not in df.columns: return []
    codes = df['Codigo'].unique().tolist()
    return sorted([str(c) for c in codes if c and str(c).strip()])

def get_vacation_periods(df: pd.DataFrame) -> Tuple[int, List[Tuple[date, date]]]:
    if df.empty or 'Codigo' not in df.columns: return 0, []
    # SOLO cuenta como periodo de vacaciones si es explícitamente V o VAC
    v_days_df = df[df['Codigo'].isin(['V', 'VAC'])]
    if v_days_df.empty: return 0, []
    
    dates = sorted(v_days_df['Fecha'].unique())
    if not dates: return 0, []
    periods = []
    curr_start = dates[0]; curr_end = dates[0]
    for i in range(1, len(dates)):
        if (dates[i] - dates[i-1]).days == 1: curr_end = dates[i]
        else: periods.append((curr_start, curr_end)); curr_start = dates[i]; curr_end = dates[i]
    periods.append((curr_start, curr_end))
    return len(dates), periods

def extract_holidays_from_text(text_content: str, year: int) -> Set[date]:
    holidays = set()
    pattern_strict = r"(\d{2}/\d{2}/\d{4})"
    for match in re.finditer(pattern_strict, text_content):
        try:
            d = datetime.strptime(match.group(1), "%d/%m/%Y").date()
            if d.year == year: holidays.add(d)
        except ValueError: pass
    return holidays

# --- 2. INTELIGENCIA DE SIGNIFICADOS ---

def parse_dynamic_legend(text: str) -> Dict[str, Any]:
    legend = {}
    
    # 1. ESCANEO ROBUSTO POR PROXIMIDAD
    # En lugar de un solo regex gigante, buscamos códigos y rangos por separado y los casamos por distancia.

    # A. Buscar todos los códigos potenciales (3-4 dígitos aislados)
    # Preferimos los que tengan ":" después, pero aceptamos sin ":" si no hay mejor opción
    code_matches = list(re.finditer(r"\b(?P<code>\d{3,4})\b", text))
    
    # B. Buscar todos los rangos horarios robustos
    # 13:00-21:00, 8.00 - 15.00
    range_pat = r"(?P<rng>(?P<start>\d{1,2}[:.]\d{2})\s*[-–—]\s*(?P<end>\d{1,2}[:.]\d{2}))"
    range_matches = list(re.finditer(range_pat, text))
    
    PROXIMITY_LIMIT = 350 # Caracteres máx de distancia
    
    processed_codes = set()
    
    for cm in code_matches:
        code = cm.group("code")
        if code in processed_codes: continue # Ya procesado
        c_end = cm.end()
        
        # Buscar el rango que empiece DESPUÉS del código y esté más cerca
        best_rng = None
        min_dist = 9999
        
        for rm in range_matches:
            r_start = rm.start()
            if r_start > c_end:
                dist = r_start - c_end
                
                # Si está demasiado lejos, paramos (asumimos que ya es otra cosa)
                if dist > PROXIMITY_LIMIT: 
                    break 
                
                if dist < min_dist:
                    min_dist = dist
                    best_rng = rm
                    # Optimización: El primero que encontramos suele ser el correcto si están ordenados
                    break 
        
        if best_rng:
            try:
                s = best_rng.group("start").replace('.', ':')
                e = best_rng.group("end").replace('.', ':')
                
                fmt = "%H:%M"
                t_s = datetime.strptime(s, fmt); t_e = datetime.strptime(e, fmt)
                
                # Cálculo horas
                calc_end = t_e
                if t_e < t_s: calc_end += timedelta(days=1)
                hours = (calc_end - t_s).total_seconds() / 3600.0
                
                s_clean = t_s.strftime("%H:%M")
                e_clean = t_e.strftime("%H:%M")
                desc_time = f"{s_clean}-{e_clean}"
                
                legend[code] = {
                    'hours': round(hours, 2),
                    'is_vacation': False,
                    'description': f"Guardia ({desc_time})",
                    'type': 'Turno',
                    'start_time': s_clean,
                    'end_time': e_clean
                }
                processed_codes.add(code)
            except: pass

    # 2. DEFINICIONES MANUALES FORZOSAS (Sobrescriben o complementan)
    # AQUÍ APLICAMOS LA REGLA DEL USUARIO: "Solo V es vacación"
    manual_definitions = {
        # --- VACACIONES REALES ---
        "V":    {"desc": "Vacaciones", "type": "Vacaciones", "is_vac": True},
        "VAC":  {"desc": "Vacaciones", "type": "Vacaciones", "is_vac": True},
        
        # --- CUALQUIER OTRA COSA -> NO ES VACACIÓN ---
        "ENF":  {"desc": "Baja / Enfermedad", "type": "Absentismo", "is_vac": False},
        "MTRI": {"desc": "Permiso Matrimonio", "type": "Permiso", "is_vac": False},
        "MTRL": {"desc": "Permiso Matrimonio", "type": "Permiso", "is_vac": False},
        "DLD":  {"desc": "Día Libre Disposición", "type": "Permiso", "is_vac": False},
        "BAJA": {"desc": "Baja IT", "type": "Absentismo", "is_vac": False},
        "IT":   {"desc": "Incapacidad Temporal", "type": "Absentismo", "is_vac": False},
        "NORM": {"desc": "Turno Normal", "type": "Trabajo", "is_vac": False},
        "AP":   {"desc": "Asuntos Propios", "type": "Permiso", "is_vac": False},
        "L":    {"desc": "Libre", "type": "Descanso", "is_vac": False}, # Libre != Vacación
        "D":    {"desc": "Descanso", "type": "Descanso", "is_vac": False},
        "[+]":  {"desc": "⚠️ Dato Oculto (Ver PDF)", "type": "Error", "is_vac": False},
        "[]":   {"desc": "⚠️ Error Lectura", "type": "Error", "is_vac": False}
    }

    for code, info in manual_definitions.items():
        existing = legend.get(code, {})
        existing_hours = existing.get('hours', 0.0)
        
        # Preservar start/end si ya existían (ej: si NORM tuviera horario detectado)
        start = existing.get('start_time', None)
        end = existing.get('end_time', None)
        
        legend[code] = {
            'hours': existing_hours,
            'is_vacation': info['is_vac'], 
            'description': info['desc'],
            'type': info['type'],
            'start_time': start,
            'end_time': end
        }

    return legend

# --- 3. EXTRACCIÓN ESPACIAL ---

def extract_data_from_pdf(pdf_path: str, year: Optional[int] = None) -> Tuple[pd.DataFrame, Dict[str, Any], List[date]]:
    if year is None: year = datetime.now().year
    data: List[Dict[str, Any]] = []
    detected_codes_info = {} 
    
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
            
            detected_holidays = sorted(list(extract_holidays_from_text(full_text, year)))
            legend_info = parse_dynamic_legend(full_text)
            detected_codes_info.update(legend_info)

            for page in pdf.pages:
                tables = page.find_tables()
                for table in tables:
                    for row in table.rows:
                        if not row.cells[0]: continue
                        
                        first_cell_text = page.crop(row.cells[0]).extract_text()
                        if not first_cell_text: continue
                        first_cell_clean = first_cell_text.strip().upper()
                        
                        found_month = None
                        for m_name, m_num in month_map.items():
                            if first_cell_clean.startswith(m_name):
                                found_month = m_num; break
                        
                        if found_month:
                            try: _, num_days = calendar.monthrange(year, found_month)
                            except: num_days = 31
                            
                            for day_idx, cell in enumerate(row.cells):
                                if day_idx == 0: continue 
                                if day_idx > num_days: break 
                                if not cell: continue

                                x0, top, x1, bottom = cell
                                expanded_bbox = (x0, top, x1, bottom + 15) 
                                cell_raw_text = page.crop(expanded_bbox).extract_text() or ""
                                # --- PROCESADO MAESTRO (NUEVAS REGLAS) ---
                                code_shift, code_acronym = clean_code_universal(cell_raw_text)
                                
                                # Si code_shift es None (y no es V), es día libre -> IGNORAR
                                if not code_shift:
                                    continue
                                
                                # --- FORMATEO DE SALIDA (CÓDIGO + SIGLAS) ---
                                
                                final_code = code_shift
                                is_vacation = (code_shift == "V")
                                hours = 0.0
                                
                                # 1. Horas: Solo si el código es numérico y está en leyenda
                                if final_code.isdigit() and final_code in detected_codes_info:
                                    hours = detected_codes_info[final_code]['hours']
                                
                                # 2. Descripción: "CÓDIGO SIGLAS"
                                # Ejemplo: "708 ENF"
                                # Si es V: "V" (o V Vacaciones si preferimos, pero V es el código)
                                
                                parts = [final_code]
                                if code_acronym:
                                    parts.append(code_acronym)
                                    # Ojo: Si las siglas indican vacación pero el código no era V? 
                                    # (Raro con esta lógica estricta, pero posible si V está en siglas y codigo es 708)
                                    if code_acronym in ["V", "VAC"]: is_vacation = True
                                
                                # Buscar descripción textual en leyenda de las siglas
                                if code_acronym and code_acronym in detected_codes_info:
                                     # Opcional: ¿Queremos poner "ENF (Baja)" o solo "ENF"?
                                     # Usuario dijo: "pondremos el código y a continuación las siglas" -> Literal
                                     pass

                                final_desc = " ".join(parts) # Resultados tipo: "708 ENF", "1308", "V"

                                # Registrar código compuesto si es nuevo
                                if final_code not in detected_codes_info:
                                    detected_codes_info[final_code] = {
                                        'hours': hours,
                                        'is_vacation': is_vacation,
                                        'description': f"Turno {final_code}" if final_code.isdigit() else "Vacaciones"
                                    }

                                start_t = None
                                end_t = None
                                
                                # Recuperar horas de inicio/fin si existen en la leyenda
                                if final_code in detected_codes_info:
                                    start_t = detected_codes_info[final_code].get('start_time')
                                    end_t = detected_codes_info[final_code].get('end_time')

                                current_date = date(year, found_month, day_idx)
                                is_holiday = current_date in detected_holidays
                                
                                entry = {
                                    "Fecha": current_date, "Mes": found_month, "Dia": day_idx,
                                    "Codigo": final_desc, # Ponemos la descripción compuesta en la columna Código para ver "708 ENF"
                                    "Tipo_Jornada": "Festivo" if is_holiday else "Ordinario",
                                    "is_vacation": is_vacation, # Flag para post-procesado
                                    "Hora_Inicio": start_t,
                                    "Hora_Fin": end_t
                                }
                                data.append(entry)

    except Exception as e:
        print(f"Error parsing PDF: {e}")
        return pd.DataFrame(), {}, []
    
    # --- POST-PROCESADO: FILTRO DE VACACIONES ---
    data = filter_short_vacations(data)

    return pd.DataFrame(data), detected_codes_info, detected_holidays

def filter_short_vacations(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Elimina días de vacaciones que NO formen un bloque de más de 14 días.
    Regla usuario: "tienen que ser más de 14, si son menos de 14 no son vacaciones".
    """
    if not data: return []
    
    # Ordenar cronológicamente para detectar secuencias
    data.sort(key=lambda x: x['Fecha'])
    
    # Identificar índices que son vacaciones
    vac_indices = [i for i, x in enumerate(data) if x.get('is_vacation') or cast_to_str(x.get('Codigo')).startswith('V')]
    
    if not vac_indices: return data
    
    to_remove = set()
    current_block = []
    
    for i, idx in enumerate(vac_indices):
        if not current_block:
            current_block.append(idx)
        else:
            prev_idx = current_block[-1]
            prev_date = data[prev_idx]['Fecha']
            curr_date = data[idx]['Fecha']
            
            # Chequeamos continuidad (diferencia de 1 día)
            if (curr_date - prev_date).days == 1:
                current_block.append(idx)
            else:
                # Fin del bloque anterior
                # Si longitud <= 14, eliminar (debe ser > 14)
                if len(current_block) <= 14:
                     to_remove.update(current_block)
                current_block = [idx] # Iniciar nuevo bloque
    
    # Procesar último bloque
    if current_block and len(current_block) <= 14:
        to_remove.update(current_block)
    
    # Retornar lista filtrada
    return [x for i, x in enumerate(data) if i not in to_remove]

def cast_to_str(val: Any) -> str:
    return str(val) if val is not None else ""

# --- 4. NÓMINA (INTACTO) ---
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
        if es_paga_extra: results['paga_extra'] += amount; continue 
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