"""
ChatGPT-like AI responses using Google Gemini Free API
"""

import os
import aiohttp
import asyncio
from datetime import datetime

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"

GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite"
]

async def ask_ai(question: str, user_id: int = None) -> dict:
    """Ask AI a question using Google Gemini free API"""
    
    if not GEMINI_API_KEY:
        return {
            "success": False,
            "error": "Gemini API key not configured. Get free key at aistudio.google.com"
        }
    
    current_date = datetime.now().strftime("%B %d, %Y")
    
    system_prompt = f"""You are a helpful AI assistant. Today's date is {current_date}. 
Be concise and informative. Keep responses under 2000 characters for Telegram. 
For current events or recent news, mention that your knowledge may not be up-to-date."""
    
    last_error = None
    
    for model in GEMINI_MODELS:
        try:
            url = f"{GEMINI_API_URL}/{model}:generateContent?key={GEMINI_API_KEY}"
            
            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": f"{system_prompt}\n\nUser question: {question}"}
                        ]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.7,
                    "maxOutputTokens": 1000,
                    "topP": 0.95,
                    "topK": 40
                }
            }
            
            headers = {"Content-Type": "application/json"}
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    
                    response_text = await response.text()
                    
                    if response.status == 200:
                        try:
                            data = await response.json() if response_text else {}
                        except:
                            data = {}
                        
                        if 'candidates' in data and len(data['candidates']) > 0:
                            candidate = data['candidates'][0]
                            if 'content' in candidate and 'parts' in candidate['content']:
                                answer = candidate['content']['parts'][0].get('text', '')
                                
                                if answer:
                                    model_name = model.replace("gemini-", "Gemini ")
                                    return {
                                        "success": True,
                                        "answer": answer,
                                        "model": model_name
                                    }
                        
                        last_error = f"Empty response from {model}"
                    
                    elif response.status == 429:
                        last_error = "Rate limited, trying next model..."
                        continue
                    
                    elif response.status == 400:
                        try:
                            error_data = await response.json() if response_text else {}
                            error_msg = error_data.get('error', {}).get('message', response_text[:200])
                        except:
                            error_msg = response_text[:200]
                        last_error = f"API Error: {error_msg}"
                        if 'quota' in str(error_msg).lower() or 'rate' in str(error_msg).lower():
                            continue
                    
                    elif response.status == 403:
                        last_error = "API key invalid or disabled. Check your Gemini API key."
                        break
                    
                    else:
                        last_error = f"HTTP {response.status}: {response_text[:100]}"
                        continue
                        
        except asyncio.TimeoutError:
            last_error = "Request timed out"
            continue
        except Exception as e:
            last_error = f"Error: {str(e)[:100]}"
            continue
    
    return {
        "success": False,
        "error": last_error or "All models are currently busy. Please try again."
    }

async def ask_with_context(question: str, context: str = None, user_id: int = None) -> dict:
    """Ask AI with optional context"""
    
    if context:
        full_question = f"Context: {context}\n\nQuestion: {question}"
    else:
        full_question = question
    
    return await ask_ai(full_question, user_id)
