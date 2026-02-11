import pandas as pd
from datetime import datetime, timedelta

def calculate_hours(df, user_mapping, prices, holidays):
    """
    Aplica el mapeo de horas y calcula importes económicos.
    
    df: DataFrame con columna 'Codigo' y 'Fecha'
    user_mapping: Dict { 'Code': {'total': float, 'nocturnal': float} }
    prices: Dict con precios globales
    holidays: Lista de strings 'YYYY-MM-DD' o objetos date
    """
    if df.empty:
        return df
        
    # Validar columna de código
    col_codigo = 'Codigo' if 'Codigo' in df.columns else 'Codigo_Limpio'
    if col_codigo not in df.columns:
        print(f"Error: No se encuentra columna de código en {df.columns}")
        return df

    # Convertir holidays a set de fechas para búsqueda rápida
    holiday_set = set()
    for h in holidays:
        try:
            holiday_set.add(pd.to_datetime(h).date())
        except:
            pass

    # Preparar listas para nuevas columnas
    total_horas = []
    horas_nocturnas = []
    tipos_jornada = []
    total_euros = []

    for _, row in df.iterrows():
        code = row[col_codigo]
        fecha = row['Fecha']
        day_date = pd.to_datetime(fecha).date()
        
        # Obtener datos del turno (Default 0.0 si no existe)
        shift_data = user_mapping.get(code, {'total': 0.0, 'nocturnal': 0.0})
        h_total = float(shift_data.get('total', 0.0))
        h_noct = float(shift_data.get('nocturnal', 0.0))
        
        # Determinar tipo de jornada y tarifa base
        # Prioridad: Festivo > Domingo > Normal
        
        is_sunday = day_date.weekday() == 6
        is_holiday = day_date in holiday_set
        
        # Precios base (defaults por si fallan referencias)
        p_normal = prices.get('price_normal', 0.0)
        p_extra = prices.get('price_extra', 0.0)
        plus_h = prices.get('plus_holiday', 0.0)
        plus_s = prices.get('plus_sunday', 0.0)
        plus_n = prices.get('plus_nocturnal', 0.0)

        rate = p_normal
        tipo = "Normal"
        
        if is_holiday:
            rate = p_normal + plus_h
            tipo = "Festivo"
        elif is_sunday:
            rate = p_normal + plus_s
            tipo = "Domingo"
            
        # Cálculo económico
        # Diurnas pagan a tasa base (o penalizada/premiada según tipo)
        # Nocturnas pagan a tasa base + plus nocturnidad
        
        h_diurnas = max(0.0, h_total - h_noct)
        
        pago_base = h_diurnas * rate
        pago_noct = h_noct * (rate + plus_n)
        
        total_dia = pago_base + pago_noct
        
        total_horas.append(h_total)
        horas_nocturnas.append(h_noct)
        tipos_jornada.append(tipo)
        total_euros.append(total_dia)

    # Asignar columnas de forma segura
    df_result = df.copy()
    df_result['Horas_Totales'] = total_horas
    df_result['Horas_Nocturnas'] = horas_nocturnas
    df_result['Tipo_Jornada'] = tipos_jornada
    df_result['Total_Euros'] = total_euros
    
    return df_result

def calculate_nocturnal_hours(start_str: str, end_str: str) -> float:
    """
    Calcula horas nocturnas en el rango 22:00 - 06:00.
    """
    try:
        if not start_str or not end_str: return 0.0
        
        fmt = "%H:%M"
        t_start = datetime.strptime(start_str, fmt)
        t_end = datetime.strptime(end_str, fmt)
        
        # Normalizar a una fecha base (ej: 2000-01-01)
        d1 = datetime(2000, 1, 1)
        d2 = datetime(2000, 1, 2)
        
        start_dt = d1.replace(hour=t_start.hour, minute=t_start.minute)
        end_dt = d1.replace(hour=t_end.hour, minute=t_end.minute)
        
        # Si acaba antes de empezar, es el dia siguiente
        if end_dt < start_dt:
            end_dt = end_dt.replace(day=2)
            
        total_noc = 0.0
        
        # Ventanas nocturnas:
        # 1. Madrugada del dia 1: 00:00 - 06:00
        nw1_start = d1.replace(hour=0, minute=0)
        nw1_end = d1.replace(hour=6, minute=0)
        
        # 2. Noche del dia 1 hasta Madrugada dia 2: 22:00 - 06:00(+1)
        nw2_start = d1.replace(hour=22, minute=0)
        nw2_end = d2.replace(hour=6, minute=0)
        
        # Intersección con Ventana 1
        latest_start = max(start_dt, nw1_start)
        earliest_end = min(end_dt, nw1_end)
        if earliest_end > latest_start:
            total_noc += (earliest_end - latest_start).total_seconds()
            
        # Intersección con Ventana 2
        latest_start = max(start_dt, nw2_start)
        earliest_end = min(end_dt, nw2_end)
        if earliest_end > latest_start:
            total_noc += (earliest_end - latest_start).total_seconds()
            
        return round(total_noc / 3600.0, 2)
    except:
        return 0.0
