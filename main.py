import streamlit as st

import pandas as pd
from datetime import date, datetime, time, timedelta

# --- IMPORTS FROM UNIVERSAL PARSER ---
from src.parser import extract_data_from_pdf, extract_payroll_data, get_unique_codes, get_vacation_periods
from src.exporter import generate_excel
from src.calculator import calculate_nocturnal_hours

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Informe Jurídico - Reclamación Turnos", page_icon="⚖️", layout="wide")

# --- ESTILOS CSS PREMIUM (DARK + WHITE CARDS) ---
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* Fondo General Dark */
    .stApp { 
        background-color: #0e1117; 
        color: #fafafa;
    }
    
    /* Tipografía Global (Encabezados Blancos) */
    h1, h2, h3 { color: #ffffff !important; font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; }
    p, div, span, label { color: #e0e0e0; }
    
    /* Card Style (Contenedores) - BLANCO */
    .card {
        background-color: #ffffff;
        color: #333333; /* Texto Oscuro */
        padding: 1.5rem;
        border-radius: 10px;
        box_shadow: 0 4px 6px rgba(0,0,0,0.3);
        margin-bottom: 1rem;
        border: 1px solid #41444e;
    }
    
    /* FORCE BOLD ON ALL TEXT INSIDE CARDS/EXPANDERS */
    /* Target Streamlit Expanders internals explicitly */
    div[data-testid="stExpander"] p,
    div[data-testid="stExpander"] span,
    div[data-testid="stExpander"] div,
    div[data-testid="stExpander"] label {
        font-weight: 700 !important;
        color: #333333 !important;
    }
    
    /* FIX INPUTS VISIBILITY: Force White BG + Black Text */
    div[data-baseweb="input"] {
        background-color: #ffffff !important;
        border: 1px solid #ccc !important;
    }
    input {
        color: #ffffff !important;
        font-weight: 700 !important;
    }
    
    /* Arreglar Cuadro Azul (st.info): Texto Blanco */
    div[data-testid="stAlert"] {
        color: #FFFFFF !important;
    }
    div[data-testid="stAlert"] p, div[data-testid="stAlert"] span {
        color: #FFFFFF !important;
    }
    
    /* Arreglar Cabecera Expander: Fondo Claro, Texto Negro */
    div[data-testid="stExpander"] > details > summary {
        background-color: #f0f2f6 !important; /* Gris muy claro */
        color: #000000 !important;
        font-weight: bold !important;
    }
    /* Icono de la flechita del expander en negro */
    div[data-testid="stExpander"] > details > summary svg {
        fill: #000000 !important;
        color: #000000 !important;
    }

    /* Etiquetas (Labels) en Negro */
    label, .st-emotion-cache-1629p8f {
        color: #000000 !important;
        font-weight: bold !important;
    }
    
    .card, .card * {
        font-weight: 700 !important;
        color: #333333 !important;
    }
    
    /* Métricas Grandes - BLANCO */
    .metric-container {
        text-align: center;
        padding: 1rem;
        background: #ffffff;
        border-radius: 10px;
        box_shadow: 0 2px 4px rgba(0,0,0,0.2);
        border-left: 5px solid #4dabf7;
    }
    
    .metric-container * {
        font-weight: 700 !important;
    }

    .metric-value { font-size: 2.5rem; color: #333333 !important; } /* Texto Oscuro */
    .metric-label { font-size: 0.9rem; color: #666666 !important; text-transform: uppercase; letter-spacing: 1px; } /* Gris Oscuro */
    
    /* Colores High Contrast (Para fondo BLANCO) */
    .text-success { color: #28a745 !important; font-weight: 800 !important; }
    .text-danger { color: #dc3545 !important; font-weight: 800 !important; }
    .text-warning { color: #ffc107 !important; font-weight: 800 !important; }
    .text-primary { color: #007bff !important; font-weight: 800 !important; }
    
    /* Alertas Dark (Mantener estéticas) */
    .stAlert { background-color: #262730; border: 1px solid #444; color: #eee; }
    
    /* Botones */
    .stButton>button {
        width: 100%;
        border-radius: 8px;
        font-weight: 700 !important;
        transition: all 0.2s;
        background-color: #1f77b4;
        color: white;
        border: none;
    }
    .stButton>button:hover {
        background-color: #165683;
    }
    
    /* FIX: Expander Headers & Content High Contrast */
    details {
        background-color: #ffffff;
        border-radius: 5px;
        border: 1px solid #e0e0e0;
        margin-bottom: 10px;
        color: #000000;
    }
    summary {
        background-color: #f0f2f6;
        color: #000000 !important;
        padding: 10px;
        border-radius: 5px;
        font-weight: 700 !important; /* BOLD */
        cursor: pointer;
    }
    details[open] summary {
        border-bottom: 1px solid #e0e0e0;
        border-bottom-left-radius: 0;
        border-bottom-right-radius: 0;
    }
    
    /* FIX: Sidebar Festivos High Contrast */
    .holiday-box {
        background-color: #ffffff; 
        padding: 15px; 
        border-radius: 8px; 
        border: 1px solid #d1d5db;
    }
    
    .holiday-box * {
        font-weight: 700 !important;
        color: #000000 !important;
    }

    .holiday-item {
        color: #000000 !important;
        margin-bottom: 6px;
        border-bottom: 1px solid #f0f0f0;
        padding-bottom: 4px;
    }
    </style>
""", unsafe_allow_html=True)

# --- ESTADO DE SESIÓN ---
if 'step' not in st.session_state: st.session_state.step = 1
if 'df_raw' not in st.session_state: st.session_state.df_raw = pd.DataFrame()
if 'detected_shifts' not in st.session_state: st.session_state.detected_shifts = {}
if 'detected_holidays' not in st.session_state: st.session_state.detected_holidays = [] # Nueva variable de estado

# Variables para inputs auto-rellenados
if 'auto_worker_name' not in st.session_state: st.session_state.auto_worker_name = ""
if 'auto_company_name' not in st.session_state: st.session_state.auto_company_name = ""
if 'payroll_data' not in st.session_state: st.session_state.payroll_data = {}

def reset_app():
    st.session_state.step = 1
    st.session_state.df_raw = pd.DataFrame()
    st.session_state.detected_shifts = {}
    st.session_state.detected_holidays = []
    st.rerun()

# ==========================================
# SIDEBAR (PASO 1 + CONFIGURACIÓN)
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=60)
    st.title("Reclamación AI (VERSION ACTUALIZADA)")
    st.caption("Sistema de Análisis Jurídico v2.5")
    st.markdown("---")
    
    # 1.1 CARGA
    st.header("📂 1. Carga de Archivos")
    
    # Variables de estado para año
    if 'auto_year' not in st.session_state: st.session_state.auto_year = 2025
    
    uploaded_file = st.file_uploader("Cuadrante (PDF)", type=['pdf'])
    
    # Input de Año vinculado a session_state
    year = st.number_input("Año Fiscal", min_value=2020, max_value=2030, value=st.session_state.auto_year, key="input_year")
    
    uploaded_payrolls = st.file_uploader("Nóminas (Auditoría Anual)", type=['pdf'], accept_multiple_files=True)
    
    if uploaded_payrolls:
        if st.button("🕵️ Auditoría Anual (Detectar Pagos)"):
             with st.spinner("Analizando historial de nóminas..."):
                try:
                    # Importamos la nueva función
                    from src.parser import analyze_annual_payroll
                    p_data = analyze_annual_payroll(uploaded_payrolls)
                    
                    if p_data:
                        st.session_state.payroll_data = p_data
                        
                        # Auto-rellenar datos
                        if p_data.get('worker'): st.session_state.auto_worker_name = p_data['worker']
                        if p_data.get('company'): st.session_state.auto_company_name = p_data['company']
                        if p_data.get('year'): st.session_state.auto_year = int(p_data['year'])
                            
                        st.success(f"✅ Auditoría Completada: Detectado {p_data.get('total_abonado_tercera',0):.2f}€ abonados.")
                        st.rerun()
                except Exception as e: st.error(f"Error: {e}")

    # --- DATOS RAW AUDITORÍA (DEBUG) ---
    if st.session_state.payroll_data:
        # Visualización Compacta en Sidebar
        with st.expander("🔍 Auditoría (Datos Raw)", expanded=False):
            st.json(st.session_state.payroll_data)

    # --- GESTOR DE FESTIVOS (SOLO LECTURA) ---
    if st.session_state.step >= 2:
        st.markdown("---")
        st.header("🎉 Días Festivos Detectados")
        
        current_holidays = sorted(list(set(st.session_state.detected_holidays)))
        
        if not current_holidays:
            st.caption("No hay festivos detectados.")
        else:
            html_list = ""
            for h in current_holidays:
                f_date = h.strftime('%d/%m/%Y')
                html_list += f"<div class='holiday-item'>📅 {f_date}</div>"
            
            st.markdown(f'<div class="holiday-box">{html_list}</div>', unsafe_allow_html=True)


    # --- 1.2 DATOS & CONFIGURACIÓN  ---
    st.markdown("---")
    st.header("⚙️ 2. Auditoría y Configuración")
    
    p_data = st.session_state.payroll_data
    
    # ---------------------------------------------------------
    # GESTIÓN ECONÓMICA Y AUDITORÍA
    # ---------------------------------------------------------
    with st.expander("💸 Datos Económicos (Editable)", expanded=True):
        
        # Fila 1: Datos Personales (Markdown)
        c1, c2, c3 = st.columns(3)
        c1.markdown(f"👤 **Trabajador:**\n{p_data.get('worker', 'N/D')}")
        c2.markdown(f"📋 **Categoría:**\n{p_data.get('categoria', 'N/D')}")
        c3.markdown(f"📅 **Antigüedad:**\n{p_data.get('antiguedad_fecha', 'N/D')}")
        
        st.markdown(f"🏢 **Empresa:** {p_data.get('company', 'N/D')}")
        
        # A. Conceptos Fijos (Estructurales -> MAX)
        st.markdown("**Conceptos Fijos (Convenio):**")
        base_salary = st.number_input("Salario Base (€)", value=float(p_data.get('salario_base', 0.0)), step=10.0)
        seniority = st.number_input("Antigüedad (€)", value=float(p_data.get('antiguedad', 0.0)), step=10.0)
        plus_agreement = st.number_input("Plus Convenio (€)", value=float(p_data.get('plus_convenio', 0.0)), step=10.0)
        
        # B. Precio Hora Ordinaria
        # Fórmula Usuario: (Base + Antigüedad + Plus) / 160
        total_fijo_mes = base_salary + seniority + plus_agreement
        hourly_rate = total_fijo_mes / 160.0
        
        st.info(f"ℹ️ Precio Hora Calc: **{hourly_rate:.4f} €**\n(Base: {total_fijo_mes:.2f}€ / 160h)")
        
        # C. Conceptos Variables (Auditados -> SUM)
        st.markdown("---")
        st.markdown("**Variables Detectados (Total Anual):**")
        
        # Diseño Compacto: Tabla Markdown Manual para evitar cortes
        st.markdown(f"""
        | Concepto | Total Anual (€) |
        | :--- | ---: |
        | 🌙 **Nocturnidad** | **{p_data.get('nocturnidad', 0.0):.2f} €** |
        | 🎉 **Festividad** | **{p_data.get('festividad', 0.0):.2f} €** |
        | 🥪 **Dietas** | **{p_data.get('dietas', 0.0):.2f} €** |
        """)
        
    # LOGICA 3ª PAGA
    teorica_val = float(p_data.get('tercera_paga_teorica', 0.0))
    abonado_val = float(p_data.get('total_abonado_tercera', 0.0))
    diferencia_reclamar = max(0.0, teorica_val - abonado_val)
    
    include_extra_pay = st.checkbox("Reclamar 3ª Paga (Beneficios)", value=not p_data.get('is_prorated', False))
    if include_extra_pay:
         st.metric("Deuda 3ª Paga", f"{diferencia_reclamar:.2f} €", delta=f"- Abonado: {abonado_val:.2f}€")

    # DICCIONARIO PRECIOS (Interfaz con Exporter)
    prices = {
        'price_normal': hourly_rate,
        'base_salary': base_salary,
        'seniority': seniority,
        'plus_agreement': plus_agreement,
        'annual_pay': 160,
        'include_extra_pay': include_extra_pay,
        'val_extra_pay': diferencia_reclamar,
        'categoria': p_data.get('categoria', 'N/D'),
        'nocturnidad_devengada': p_data.get('nocturnidad', 0.0),
        'festividad_devengada': p_data.get('festividad', 0.0), # Para comparar
        'dietas_devengadas': p_data.get('dietas', 0.0)
    }
    
    # ---------------------------------------------------------
    # SMART ALERTS (AUDITORÍA CRUZADA)
    # ---------------------------------------------------------
    # Verificar si hay horas nocturnas en los turnos vs nómina
    hay_horas_nocturnas = False
    
    if 'local_mapping' in locals():
        for code, info in local_mapping.items():
            if info.get('nocturnal', 0) > 0: hay_horas_nocturnas = True
    
    if hay_horas_nocturnas and p_data.get('nocturnidad', 0.0) == 0:
        st.warning("⚠️ **ALERTA AUDITOR:** Detectadas horas nocturnas en cuadrante, pero 0€ en concepto Nocturnidad.", icon="🔦")

    st.markdown("---")
    if st.button("🔄 Reiniciar App"): reset_app()



# ==========================================
# ÁREA PRINCIPAL
# ==========================================
st.title("Reclamación de Turnos - Informe Jurídico")

# --- LÓGICA PASO 1 (PROCESAR SI HAY ARCHIVO) ---
if uploaded_file and st.session_state.step == 1:
    col_kpi1, col_kpi2 = st.columns(2)
    col_kpi1.info(f"📄 Archivo Cargado: {uploaded_file.name}")
    col_kpi2.metric("Precio Hora Calc.", f"{hourly_rate:.2f} €")
    
    if st.button("🚀 Analizar Cuadrante Ahora", type="primary"):
        with st.spinner("Procesando estructura del PDF..."):
            try:
                df, detected_shifts, detected_holidays = extract_data_from_pdf(uploaded_file, year)
                codes = get_unique_codes(df)
                
                if df.empty:
                    st.error("No se detectaron turnos válidos.")
                else:
                    st.session_state.df_raw = df
                    st.session_state.unique_codes = codes
                    st.session_state.detected_shifts = detected_shifts
                    st.session_state.detected_holidays = detected_holidays # Persistencia de festivos
                    st.session_state.step = 2
                    st.rerun()
            except Exception as e:
                st.error(f"Error crítico: {e}")

# ==========================================
# PASO 2: RESOLUCIÓN Y VALIDACIÓN
# ==========================================
elif st.session_state.step == 2:
    st.subheader("2. Validación de Códigos Detectados")
    
    # --- ÁREA: CÓDIGOS DESCONOCIDOS (EXPANDER AMARILLO) ---
    detected = st.session_state.detected_shifts
    unknowns = [c for c, info in detected.items() if info.get('type') == 'UNKNOWN']
    
    if unknowns:
        with st.expander("⚠️ Se requieren aclaraciones (Códigos Nuevos)", expanded=True):
            st.markdown("""<style>div[data-testid="stExpander"] div[role="button"] p {font-size: 1.1rem; color: #ffd740;}</style>""", unsafe_allow_html=True)
            st.caption("El sistema ha encontrado códigos que no estaban en la leyenda. Por favor, identifícalos.")
            
            for u_code in unknowns:
                cols_u = st.columns([1, 2, 2])
                with cols_u[0]:
                    st.markdown(f"### `{u_code}`")
                with cols_u[1]:
                    opt = st.radio(
                        "Tipo de registro",
                        ["Absentismo / Descanso", "Turno de Trabajo", "Ignorar (Basura)"],
                        key=f"rad_{u_code}",
                        label_visibility="collapsed"
                    )
                with cols_u[2]:
                    if opt == "Turno de Trabajo":
                        c1, c2 = st.columns(2)
                        u_start = c1.text_input("Entrada", value="08:00", key=f"s_{u_code}")
                        u_end = c2.text_input("Salida", value="15:00", key=f"e_{u_code}")
                        try:
                            fmt = "%H:%M"
                            t1 = datetime.strptime(u_start, fmt); t2 = datetime.strptime(u_end, fmt)
                            if t2 < t1: t2 += timedelta(days=1)
                            dur = (t2 - t1).total_seconds() / 3600.0
                            st.session_state.detected_shifts[u_code] = {'start': u_start, 'end': u_end, 'hours': round(dur, 2), 'type': 'Work', 'description': 'Usuario (Trabajo)'}
                        except: pass
                    elif "Ignorar" in opt:
                        st.session_state.detected_shifts[u_code]['type'] = 'DELETE'
                    else:
                        st.session_state.detected_shifts[u_code] = {'hours': 0.0, 'is_vacation': True, 'type': 'Absentismo', 'description': 'Usuario (Descanso)'}
                st.markdown("---")


    # --- ÁREA: FESTIVOS (NUEVO) ---
    st.markdown("### 🗓️ Días Festivos Activos")
    
    active_holidays = sorted(list(set(st.session_state.detected_holidays)))
    if active_holidays:
        cols_h = st.columns(4)
        for i, h in enumerate(active_holidays):
             with cols_h[i % 4]:
                 st.markdown(f"""
                 <div style="background-color:#ffffff; padding:10px; border-radius:8px; border-left:4px solid #ffc107; margin-bottom:10px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                     <strong style="color:#333;">{h.strftime('%d/%m/%Y')}</strong><br>
                     <span style="font-size:0.8em; color:#666;">Festivo</span>
                 </div>
                 """, unsafe_allow_html=True)
    else:
        st.info("No hay días festivos configurados. Usa la barra lateral para añadirlos.")

    st.markdown("---")

    # --- ÁREA: CÓDIGOS VÁLIDOS (GRID) ---
    st.markdown("### Configuración de Horas")
    
    with st.form("hours_mapping_form"):
        local_mapping = {}
        valid_codes = [c for c in st.session_state.unique_codes if st.session_state.detected_shifts.get(c, {}).get('type') != 'DELETE']
        
        # Calcular periodos de vacaciones antes del bucle de configuración
        _, all_vac_periods = get_vacation_periods(st.session_state.df_raw)
        
        cols = st.columns(3)
        for i, code in enumerate(sorted(valid_codes)):
            with cols[i % 3]:
                info = st.session_state.detected_shifts.get(code, {})
                es_vac = info.get('is_vacation', False) or code == 'V'
                val_h = info.get('hours', 0.0)
                start_t = info.get('start'); end_t = info.get('end'); desc = info.get('description', '')
                
                # --- 1. Cabecera del Turno con Detalles Horarios ---
                # Si es Vacaciones (código V), mostramos los rangos
                if code == 'V' or es_vac:
                     # Formatear rangos
                     v_dates_str = []
                     for vs, ve in all_vac_periods:
                         # Formato: (01/08)-(15/08)
                         v_dates_str.append(f"({vs.strftime('%d/%m')}) - ({ve.strftime('%d/%m')})")
                     
                     if v_dates_str:
                         # Separar por <br>
                         ranges_html = "<br>".join(v_dates_str)
                         header_text = f"🌴 {code}<br><span style='font-size:0.85em; font-weight:normal; color:#555;'>{ranges_html}</span>"
                     else:
                         header_text = f"🌴 {code}"
                else:
                     header_text = f"🏷️ {code}"
                     if start_t and end_t:
                        header_text += f" ({start_t} - {end_t} | {val_h}h)"
                
                # Card Visual (White BG)
                border = "#007bff" 
                if es_vac: border = "#28a745"
                
                bg_color = "#ffffff"
                
                st.markdown(f"""
                <div style="background-color:{bg_color}; padding:15px; border-radius:10px; border-left:4px solid {border}; margin-bottom:10px; box-shadow: 0 2px 4px rgba(0,0,0,0.2);">
                    <div style="display:flex; justify-content:space-between;">
                        <strong style="color:#000000; font-size:1.1em;">{header_text}</strong>
                    </div>
                    <div style="color:#555555; font-size:0.9em; margin-top:5px;">{desc[:40]}</div>
                </div>
                """, unsafe_allow_html=True)
                
                # --- 2. Tooltip con Explicación Literal ---
                EXPLICACION_DETALLADA = """
Te explico por qué pone 8.25 en lugar de 8.15:
Las nóminas y los cálculos de dinero siempre funcionan con horas decimales, no con minutos de reloj.
Una hora tiene 60 minutos.
15 minutos es exactamente un cuarto de hora (1/4).
Si divides 1 entre 4, te da 0.25 (un cuarto).
"""
                if es_vac or val_h == 0.0:
                     st.markdown(f"**Estado:** 🌴 Vacaciones / Descanso")
                     local_mapping[code] = {'total': 0.0, 'nocturnal': 0.0}
                else:
                    c_in1, c_in2 = st.columns(2)
                    tot = c_in1.number_input("Total", 0.0, 24.0, float(val_h), 0.25, key=f"ht_{code}", help=EXPLICACION_DETALLADA)
                    noc = c_in2.number_input("Noc.", 0.0, 24.0, 0.0, 0.25, key=f"nt_{code}")
                    local_mapping[code] = {'total': tot, 'nocturnal': noc}
        
        st.markdown("---")
        if st.form_submit_button("✅ Confirmar y Calcular Informe", type="primary"):
            st.session_state.mapping = local_mapping
            to_del = [c for c, inf in st.session_state.detected_shifts.items() if inf.get('type') == 'DELETE']
            if to_del: st.session_state.df_raw = st.session_state.df_raw[~st.session_state.df_raw['Codigo'].isin(to_del)]
            st.session_state.step = 3
            st.rerun()

    # --- SMART ALERT (FUERA DEL FORM) ---
    # Verificar si hay horas nocturnas en los turnos
    hay_horas_nocturnas = False
    for code, info in local_mapping.items():
        if info.get('nocturnal', 0) > 0:
            hay_horas_nocturnas = True
            break
            
    p_data = st.session_state.get('payroll_data', {})
    nocturnidad_pagada = float(p_data.get('nocturnidad', 0.0))
    
    if hay_horas_nocturnas and nocturnidad_pagada == 0:
        st.error("⚠️ ALERTA CRÍTICA: Se han detectado horas nocturnas en los turnos pero NO aparece concepto NOCTURNIDAD en la nómina. Verifica esto.", icon="🚨")

# ==========================================
# PASO 3: DASHBOARD DE RESULTADOS
# ==========================================
elif st.session_state.step == 3:
    st.markdown("## 📊 Dashboard de Resultados")
    
    # Procesamiento
    df = st.session_state.df_raw.copy()
    mapping = st.session_state.mapping
    detected_info = st.session_state.detected_shifts
    
    def calculate_rest_debt(dh):
        if 7.5 <= dh <= 8.5: return 0.5
        elif 11.5 <= dh <= 12.5: return 1.0
        elif 23.5 <= dh <= 24.5: return 2.0
        else: return round(dh * (1/12), 2)

    df['Horas_Totales'] = df['Codigo'].apply(lambda x: mapping.get(x, {}).get('total', 0.0))
    df['Horas_Nocturnas'] = df['Codigo'].apply(lambda x: mapping.get(x, {}).get('nocturnal', 0.0))
    
    df['Deuda_Descanso_Horas'] = 0.0
    for idx, row in df.iterrows():
        cod = row['Codigo']
        h_total = row['Horas_Totales']
        info = detected_info.get(cod, {})
        es_absentismo = info.get('type') == 'Absentismo' or info.get('is_vacation')
        if not es_absentismo and h_total > 0:
            df.at[idx, 'Deuda_Descanso_Horas'] = calculate_rest_debt(h_total)

    total_deuda_horas = df['Deuda_Descanso_Horas'].sum()
    total_recl_euros = total_deuda_horas * prices['price_normal']
    grand_total = total_recl_euros + prices['val_extra_pay']
    
    # --- RESUMEN EJECUTIVO (3 COLUMNAS) ---
    col_sum1, col_sum2, col_sum3 = st.columns(3)
    
    col_sum1.markdown(f"""
    <div class="metric-container" style="border-left-color: #ff5252;">
        <div class="metric-label">Deuda Horas Descanso</div>
        <div class="metric-value text-danger">{total_deuda_horas:.2f} h</div>
    </div>""", unsafe_allow_html=True)
    
    col_sum2.markdown(f"""
    <div class="metric-container" style="border-left-color: #448aff;">
        <div class="metric-label">Valor Monetario (Base)</div>
        <div class="metric-value text-primary">{total_recl_euros:.2f} €</div>
    </div>""", unsafe_allow_html=True)
    
    col_sum3.markdown(f"""
    <div class="metric-container" style="border-left-color: #69f0ae; background-color: #ffffff;">
        <div class="metric-label">TOTAL A RECLAMAR</div>
        <div class="metric-value text-success">{grand_total:.2f} €</div>
    </div>""", unsafe_allow_html=True)
    
    if prices['include_extra_pay']:
        st.caption(f"* Incluye {prices['val_extra_pay']:.2f} € de 3ª Paga Extra")
    
    st.markdown("---")
    
    # --- VISUALIZACIÓN VACACIONES ---
    _, vac_periods = get_vacation_periods(df)
    if vac_periods:
        st.subheader("🏖️ Períodos de Vacaciones Detectados")
        cols_vac = st.columns(len(vac_periods) if len(vac_periods) <= 3 else 3)
        for i, (v_start, v_end) in enumerate(vac_periods):
            days = (v_end - v_start).days + 1
            with cols_vac[i % 3]:
                st.markdown(f"""
                <div class="card" style="border-left: 5px solid #17a2b8; padding: 1rem;">
                    <strong style="color:#17a2b8;">Periodo {i+1}</strong><br>
                    📅 {v_start.strftime('%d/%m')} - {v_end.strftime('%d/%m')}<br>
                    <span style="font-size:0.9em; color:#666666;">Duration: {days} días</span>
                </div>
                """, unsafe_allow_html=True)
        st.markdown("---")
    
    # --- VISUALIZACIÓN MENSUAL (GRID 2 COLUMNAS) ---
    st.subheader("📅 Desglose Mensual")
    
    # Agrupar
    df['Mes_Num'] = df['Fecha'].apply(lambda x: x.month)
    monthly = df.groupby('Mes_Num')['Deuda_Descanso_Horas'].sum()
    months = sorted(monthly.index.unique())
    month_names = {1:"Enero", 2:"Febrero", 3:"Marzo", 4:"Abril", 5:"Mayo", 6:"Junio", 
                   7:"Julio", 8:"Agosto", 9:"Septiembre", 10:"Octubre", 11:"Noviembre", 12:"Diciembre"}
    
    # === Custom CSS para estilizar los Expanders como Cards ===
    # Truco: Inyectar CSS que haga que el expander parezca la tarjeta anterior
    # Selector aproximado en versiones modernas: [data-testid="stExpander"]
    st.markdown("""
    <style>
    /* Estilo Base del Expander (Card) */
    [data-testid="stExpander"] {
        background-color: #ffffff;
        border-radius: 8px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
        border: 1px solid #e5e7eb; /* Borde sutil */
        margin-bottom: 1rem;
    }
    
    /* El Header del Expander (Donde va el Título) */
    [data-testid="stExpander"] summary {
        color: #000000 !important; /* Negro Puro */
        font-weight: 700;
        font-size: 1.1rem;
    }
    
    /* Forzar color en elementos hijos del summary (p, span, strong) */
    [data-testid="stExpander"] summary p, 
    [data-testid="stExpander"] summary span,
    [data-testid="stExpander"] summary strong {
        color: #000000 !important;
    }

    /* Icono del Expander (Flecha) */
    [data-testid="stExpander"] summary svg {
        color: #000000 !important; /* También la flecha en negro */
    }
    
    /* Contenido del Expander (Forzar Negro) */
    [data-testid="stExpander"] [data-testid="stExpanderDetails"] {
        border-top: 1px solid #f3f4f6;
        padding-top: 0.5rem;
        color: #000000 !important;
    }
    
    /* Forzar color en párrafos dentro del expander */
    [data-testid="stExpander"] [data-testid="stExpanderDetails"] p {
        color: #000000 !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # Grid Logic (Lista Vertical Simple con Expanders Integrados)
    for m_num in months:
        debt_val = monthly[m_num]
        m_name = month_names.get(m_num, str(m_num)).upper()
        
        # Lógica de Color para el Label
        # Usamos Markdown Color Syntax: :color[texto]
        if debt_val > 0:
            debt_md = f":red[**-{debt_val:.2f} h**]"
            border_color = "#ef4444" 
        else:
            debt_md = f":green[**SIN DEUDA**]"
            border_color = "#22c55e"

        # Label del Expander: "ENERO               -2.00 h"
        expander_label = f"**{m_name}**  —  {debt_md}"
        
        with st.expander(expander_label, expanded=False):
            # --- DETALLE DIARIO ---
            month_df = df[df['Mes_Num'] == m_num]
            # Ordenar por día para consistencia
            month_df = month_df.sort_values('Dia')
            
            for _, row in month_df.iterrows():
                d_str = row['Fecha'].strftime("%d")
                cod = row['Codigo']
                debt = row['Deuda_Descanso_Horas']
                info = detected_info.get(cod, {})
                start = info.get('start', '?')
                end = info.get('end', '?')
                
                # Formato: 📅 Día DD | ⏱️ HH:MM-HH:MM | ❌ Deuda: -X.XX h
                # Estilo Neutro (NEGRO PURO) + ROJO SOLO EN LA DEUDA
                # Usamos HTML directo para evitar que Streamlit "resetee" el color
                
                # Base Style (Negro)
                base_html = f"<div style='color:#000000; font-size:1rem; margin-bottom:4px;'><strong>📅 Día {d_str}</strong> | ⏱️ {start}-{end} ({cod})"
                
                if debt > 0:
                    st.markdown(f"{base_html} | <span style='color:#dc3545; font-weight:bold;'>❌ Deuda: -{debt:.2f} h</span></div>", unsafe_allow_html=True)
                elif info.get('is_vacation'):
                    # Buscar el periodo exacto
                    vac_range_str = ""
                    for v_start, v_end in vac_periods:
                        if v_start <= row['Fecha'] <= v_end:
                            vac_range_str = f"{v_start.strftime('%d/%m')}–{v_end.strftime('%d/%m')}"
                            break
                    
                    st.markdown(f"<div style='color:#000000; font-size:1rem; margin-bottom:4px;'><strong>📅 Día {d_str}</strong> | V 🌴 <strong>{vac_range_str}</strong></div>", unsafe_allow_html=True)
                else:
                    st.markdown(f"{base_html} | <span style='color:#28a745; font-weight:bold;'>✅ Correcto</span></div>", unsafe_allow_html=True)

    # --- EXPORTAR ---
    st.markdown("---")
    col_d1, col_d2 = st.columns([1, 2])
    with col_d1:
        if st.button("⬅️ Revisar Configuración"):
            st.session_state.step = 2
            st.rerun()
            
    with col_d2:
        # Recuperar festivos de la sesión
        current_holidays = st.session_state.detected_holidays
        
        # Recuperar metadatos para informe
        p_data_final = st.session_state.get('payroll_data', {})
        worker_name = p_data_final.get('worker', st.session_state.get('auto_worker_name', 'Trabajador'))
        company_name = p_data_final.get('company', st.session_state.get('auto_company_name', 'Empresa'))
        
        excel_data = generate_excel(df, detected_info, prices, current_holidays, worker_name, company_name)
        st.download_button(
            "📥 Descargar Informe Jurídico (Excel)",
            data=excel_data,
            file_name="Informe_Reclamacion.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )
