import streamlit as st
import requests
import json
import base64
from datetime import datetime
from google.cloud import firestore
from google.oauth2 import service_account

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Zelo - Cuidado Conectado", page_icon="❤️", layout="centered")

# CSS para estilização (Emulando o visual moderno do React/Tailwind)
st.markdown("""
    <style>
    .elder-card {
        padding: 20px;
        border-radius: 20px;
        border: 2px solid #3B82F6;
        margin-bottom: 20px;
        background-color: #f8fafc;
    }
    .stButton>button {
        width: 100%;
        border-radius: 15px;
        font-weight: bold;
    }
    .big-font { font-size: 30px !important; font-weight: 800; }
    </style>
    """, unsafe_allow_html=True)

# --- INICIALIZAÇÃO FIREBASE ---
# No Streamlit, você deve colocar suas credenciais em .streamlit/secrets.toml
if "db" not in st.session_state:
    try:
        # Tenta carregar dos Secrets do Streamlit
        creds_dict = json.loads(st.secrets["firebase_service_account"])
        creds = service_account.Credentials.from_service_account_info(creds_dict)
        st.session_state.db = firestore.Client(credentials=creds)
    except:
        st.error("Erro ao conectar ao Firebase. Configure as credenciais nos Secrets.")
        st.stop()

# --- HELPER: GEMINI TTS ---
def call_gemini_tts(text, api_key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Kore"}}}
        }
    }
    try:
        response = requests.post(url, json=payload)
        data = response.json()
        audio_base64 = data['candidates'][0]['content']['parts'][0]['inlineData']['data']
        return audio_base64
    except:
        return None

# --- ESTADO GLOBAL ---
if "profile" not in st.session_state: st.session_state.profile = None
if "selected_elder_id" not in st.session_state: st.session_state.selected_elder_id = None

# --- FUNÇÕES DE DADOS ---
def get_elders():
    docs = st.session_state.db.collection('elders').stream()
    return [{**doc.to_dict(), "id": doc.id} for doc in docs]

def add_elder(name, age, gender):
    import random, string
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    new_elder = {
        "name": name,
        "age": age,
        "gender": gender,
        "accessCode": code,
        "meds": [],
        "logs": [],
        "helpRequested": False,
        "photo": "👴" if gender == "M" else "👵"
    }
    st.session_state.db.collection('elders').add(new_elder)

def mark_med_taken(elder_id, elder_data, med_id):
    now = datetime.now()
    new_log = {
        "medId": med_id,
        "medName": next(m['name'] for m in elder_data['meds'] if m['id'] == med_id),
        "time": now.strftime("%H:%M"),
        "date": now.strftime("%d/%m/%Y"),
        "status": "taken"
    }
    updated_logs = [new_log] + elder_data.get('logs', [])
    st.session_state.db.collection('elders').document(elder_id).update({
        "logs": updated_logs[:30]
    })

# --- INTERFACE: SELEÇÃO DE PERFIL ---
if st.session_state.profile is None:
    st.title("❤️ Zelo")
    st.subheader("Cuidado conectado em tempo real")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("SOU CUIDADOR", use_container_width=True):
            st.session_state.profile = "caregiver"
            st.rerun()
    with col2:
        if st.button("SOU IDOSO", use_container_width=True):
            st.session_state.profile = "elder"
            st.rerun()

# --- INTERFACE: CUIDADOR ---
elif st.session_state.profile == "caregiver":
    st.sidebar.button("Sair", on_click=lambda: st.session_state.clear())
    st.title("👨‍⚕️ Painel do Cuidador")
    
    elders = get_elders()
    
    if st.session_state.selected_elder_id is None:
        with st.expander("➕ Registrar Novo Idoso"):
            name = st.text_input("Nome")
            age = st.number_input("Idade", min_value=0, max_value=120)
            gender = st.selectbox("Gênero", ["M", "F"])
            if st.button("Salvar Registro"):
                add_elder(name, age, gender)
                st.success("Registrado!")
                st.rerun()
        
        st.write("### Meus Idosos")
        for e in elders:
            with st.container():
                col_a, col_b = st.columns([4, 1])
                col_a.write(f"**{e['name']}** ({e['age']} anos) - Código: `{e['accessCode']}`")
                if col_b.button("Ver", key=e['id']):
                    st.session_state.selected_elder_id = e['id']
                    st.rerun()
                if e.get('helpRequested'):
                    st.error("🚨 Pedido de ajuda ativo!")

    else:
        # Visão detalhada do idoso
        current_elder = next(e for e in elders if e['id'] == st.session_state.selected_elder_id)
        if st.button("⬅️ Voltar"):
            st.session_state.selected_elder_id = None
            st.rerun()
            
        st.divider()
        st.header(f"{current_elder['photo']} {current_elder['name']}")
        
        tab1, tab2 = st.tabs(["Medicamentos", "Histórico"])
        
        with tab1:
            with st.popover("➕ Adicionar Medicamento"):
                m_name = st.text_input("Nome do Remédio")
                m_dose = st.text_input("Dose")
                m_freq = st.text_input("Horário/Freq")
                if st.button("Adicionar"):
                    new_med = {"id": str(datetime.now().timestamp()), "name": m_name, "dosage": m_dose, "freq": m_freq}
                    meds = current_elder.get('meds', [])
                    meds.append(new_med)
                    st.session_state.db.collection('elders').document(current_elder['id']).update({"meds": meds})
                    st.rerun()
            
            for m in current_elder.get('meds', []):
                st.info(f"💊 **{m['name']}** - {m['dosage']} ({m['freq']})")

        with tab2:
            for log in current_elder.get('logs', []):
                st.write(f"✅ {log['time']} - {log['medName']}")

# --- INTERFACE: IDOSO ---
elif st.session_state.profile == "elder":
    if st.session_state.selected_elder_id is None:
        st.title("🔑 Acesso do Idoso")
        code_input = st.text_input("Digite seu código de 6 dígitos", max_chars=6).upper()
        if st.button("ENTRAR"):
            elders = get_elders()
            found = next((e for e in elders if e['accessCode'] == code_input), None)
            if found:
                st.session_state.selected_elder_id = found['id']
                st.rerun()
            else:
                st.error("Código não encontrado.")
    else:
        elders = get_elders()
        current_elder = next(e for e in elders if e['id'] == st.session_state.selected_elder_id)
        
        st.markdown(f"<p class='big-font'>Olá, {current_elder['name']}!</p>", unsafe_allow_html=True)
        
        today = datetime.now().strftime("%d/%m/%Y")
        
        for med in current_elder.get('meds', []):
            is_taken = any(l['medId'] == med['id'] and l['date'] == today for l in current_elder.get('logs', []))
            
            with st.container():
                st.markdown(f"""<div class='elder-card' style='border-color: {"#10b981" if is_taken else "#3b82f6"}'>
                    <h2>{'✅' if is_taken else '💊'} {med['name']}</h2>
                    <p>{med['dosage']} • {med['freq']}</p>
                </div>""", unsafe_allow_html=True)
                
                if not is_taken:
                    col_tts, col_done = st.columns(2)
                    with col_tts:
                        if st.button(f"🔊 Ouvir", key=f"tts_{med['id']}"):
                            # Nota: Requer API KEY do Gemini configurada nos secrets
                            audio_b64 = call_gemini_tts(f"Está na hora de tomar o {med['name']}", st.secrets["GEMINI_API_KEY"])
                            if audio_b64:
                                st.audio(base64.b64decode(audio_b64), format="audio/wav")
                    
                    with col_done:
                        if st.button(f"JÁ TOMEI", key=f"btn_{med['id']}", type="primary"):
                            mark_med_taken(current_elder['id'], current_elder, med['id'])
                            st.rerun()

        st.divider()
        if st.button("🆘 PEDIR AJUDA", type="secondary", use_container_width=True):
            st.session_state.db.collection('elders').document(current_elder['id']).update({"helpRequested": True})
            st.warning("Ajuda solicitada ao seu cuidador!")
