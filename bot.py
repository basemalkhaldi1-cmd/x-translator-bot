import os
import re
import time
import json
import asyncio
import urllib.parse
import requests
from twikit import Client

TARGET_USER = "Amr13jn"
PROCESSED_FILE = "processed_ids.txt"
CHECK_INTERVAL = 20
RUN_DURATION = 280

GEMINI_API_KEY = (os.environ.get("GEMINI_API_KEY") or "").strip()
TW_AUTH_TOKEN = (os.environ.get("TWITTER_AUTH_TOKEN") or "").strip().strip('"').strip("'")
TW_CT0 = (os.environ.get("TWITTER_CT0") or "").strip().strip('"').strip("'")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
}

PROPER_NAMES_MAP = {
    "سلطان تنكر": "Sultan Tanker",
    "تنكر": "Tanker",
    "ريان شرقي": "Rayan Cherki",
    "شرقي": "Cherki",
    "براهيم دياز": "Brahim Diaz",
    "إبراهيم دياز": "Brahim Diaz",
    "أنيس حاج موسى": "Anis Hadj Moussa",
    "حاج موسى": "Hadj Moussa",
    "رامي بن سبعيني": "Ramy Bensebaini",
    "بن سبعيني": "Bensebaini",
    "ريان آيت نوري": "Rayan Ait-Nouri",
    "آيت نوري": "Ait-Nouri",
    "سعيد بن رحمة": "Said Benrahma",
    "بن رحمة": "Benrahma",
    "محمد الأمين عمورة": "Mohamed Amoura",
    "عمورة": "Amoura",
    "أمين غويري": "Amine Gouiri",
    "غويري": "Gouiri",
    "حسام عوار": "Houssem Aouar",
    "عوار": "Aouar",
    "فارس شايبي": "Fares Chaibi",
    "شايبي": "Chaibi",
    "عمر مرموش": "Omar Marmoush",
    "مرموش": "Marmoush",
    "محمد صلاح": "Mohamed Salah",
    "أشرف حكيمي": "Achraf Hakimi",
    "حكيمي": "Hakimi",
    "حكيم زياش": "Hakim Ziyech",
    "زياش": "Ziyech",
    "نصير مزراوي": "Noussair Mazraoui",
    "مزراوي": "Mazraoui",
    "يوسف النصيري": "Youssef En-Nesyri",
    "النصيري": "En-Nesyri",
    "سفيان أمرابط": "Sofyan Amrabat",
    "أمرابط": "Amrabat",
    "بلال الخنوس": "Bilal El Khannouss",
    "الخنوس": "El Khannouss",
    "إسماعيل الصيباري": "Ismael Saibari",
    "الصيباري": "Saibari",
    "سفيان رحيمي": "Soufiane Rahimi",
    "رحيمي": "Rahimi",
    "نايف أكرد": "Nayef Aguerd",
    "أكرد": "Aguerd",
    "ياسين بونو": "Yassine Bounou",
    "بونو": "Bounou",
    "رياض محرز": "Riyad Mahrez",
    "محرز": "Mahrez",
}

WORKING_MODEL = None
CACHED_GEMINI_MODELS = None

def get_gemini_models():
    global CACHED_GEMINI_MODELS
    if CACHED_GEMINI_MODELS is not None:
        return CACHED_GEMINI_MODELS

    priority = [
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-flash-latest",
        "gemini-flash-lite-latest",
        "gemini-3-flash-preview",
        "gemini-2.5-pro",
    ]
    discovered = []

    if GEMINI_API_KEY:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
            res = requests.get(url, timeout=15)
            data = res.json()
            for m in reversed(data.get("models", [])):
                name = m.get("name", "").replace("models/", "")
                methods = m.get("supportedGenerationMethods", [])
                if "generateContent" not in methods or "gemini" not in name.lower():
                    continue
                if any(bad in name.lower() for bad in ["1.0", "1.5", "2.0", "tts", "image", "embedding", "veo", "audio", "vision", "aqa"]):
                    continue
                if name not in priority and name not in discovered:
                    discovered.append(name)
        except Exception as e:
            print(f"Model discovery warning: {e}")

    CACHED_GEMINI_MODELS = priority + discovered
    return CACHED_GEMINI_MODELS

def load_processed_ids():
    if os.path.exists(PROCESSED_FILE):
        with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
        if lines and lines[0] == "#v6":
            return set(lines[1:]), False
    with open(PROCESSED_FILE, "w", encoding="utf-8") as f:
        f.write("#v6\n")
    return set(), True

def save_processed_id(tweet_id, processed_set):
    processed_set.add(str(tweet_id))
    with open(PROCESSED_FILE, "a", encoding="utf-8") as f:
        f.write(f"{tweet_id}\n")

def fit_tweet_length(translated_text, video_link=None):
    max_len = 210 if video_link else 250
    text = translated_text.strip().strip('"').strip("'")
    if len(text) > max_len:
        cut = text[:max_len].rsplit(" ", 1)[0]
        text = (cut if cut else text[:max_len]) + "..."
    if video_link:
        return f"{text}\n\n{video_link}"
    return text

def parse_ai_response(raw_text):
    text = (raw_text or "").strip()
    if not text or "<html" in text.lower() or "403 forbidden" in text.lower() or "502 bad gateway" in text.lower():
        return None
    if text.startswith("{"):
        try:
            data = json.loads(text)
            if "choices" in data:
                return data["choices"][0]["message"]["content"].strip()
            if "error" in data:
                return None
        except Exception:
            pass
    return text

def build_ai_prompt(text):
    hints = []
    for ar_name, en_name in PROPER_NAMES_MAP.items():
        if ar_name in text:
            hints.append(f'"{ar_name}" = {en_name}')
    hints_str = "\nVerified Name Glossary: " + ", ".join(hints) if hints else ""

    return f"""You are an expert football journalist and Arabic-to-English sports translator.
Analyze and translate the following Arabic tweet:
\"\"\"{text}\"\"\"{hints_str}

Strict Rules:
1. If this tweet is NOT related to sports/football at all, reply ONLY with: NOT_SPORTS
2. PLAYER & CLUB NAME VERIFICATION (CRITICAL):
   - Before translating, identify all player names, coach names, and club names in the tweet.
   - NEVER translate a person's name or surname literally as an Arabic verb or adjective!
   - Examples: "سلطان تنكر" is the player "Sultan Tanker" (NOT "Sultan denies"!); "ريان شرقي" is "Rayan Cherki" (NOT "East"!); "الاتحاد" is "Al-Ittihad"; "النصر" is "Al-Nassr"; "الأهلي" is "Al-Ahli"; "الهلال" is "Al-Hilal"; "الشباب" is "Al-Shabab"; "القادسية" is "Al-Qadsiah".
   - Any word paired with a player's first name or following words like "اللاعب" / "يسجل" / "هدف" is a proper name and MUST be transliterated phonetically as a name.
3. FAITHFUL TONE & CONTENT:
   - Translate the exact meaning of the tweet into natural English football style.
   - Do NOT add "GOAL!" unless the Arabic tweet itself is announcing a goal being scored.
   - Keep it concise (under 200 characters).
   - Output ONLY the final English tweet text with no quotes or extra commentary."""

def filter_and_translate(text):
    global WORKING_MODEL
    prompt = build_ai_prompt(text)

    # 1. المحاولة الأولى عبر Gemini AI
    if GEMINI_API_KEY:
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1}
        }
        models_to_try = [WORKING_MODEL] + [m for m in get_gemini_models() if m != WORKING_MODEL] if WORKING_MODEL else get_gemini_models()
        for model in models_to_try[:5]:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
            try:
                response = requests.post(url, json=payload, timeout=20)
                res_json = response.json()
                if "candidates" in res_json:
                    result = res_json["candidates"][0]["content"]["parts"][0]["text"].strip()
                    if result:
                        WORKING_MODEL = model
                        print(f"Translated via Gemini ({model}): {result}")
                        return result
            except Exception as e:
                print(f"Gemini {model} error: {e}")

    # 2. المحاولة الثانية عبر OpenAI LLM (Pollinations Direct POST)
    try:
        ai_res = requests.post(
            "https://text.pollinations.ai/",
            json={
                "model": "openai",
                "messages": [
                    {"role": "system", "content": "You are a professional football translator. Never translate player or club names literally as verbs or adjectives."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1
            },
            headers=HEADERS,
            timeout=25
        )
        if ai_res.status_code == 200:
            parsed = parse_ai_response(ai_res.text)
            if parsed:
                print(f"Translated via OpenAI (POST): {parsed}")
                return parsed
    except Exception as e:
        print(f"OpenAI POST error: {e}")

    # 3. المحاولة الثالثة عبر OpenAI LLM (Pollinations Direct GET)
    try:
        encoded = urllib.parse.quote(prompt)
        ai_get = requests.get(
            f"https://text.pollinations.ai/{encoded}?model=openai",
            headers=HEADERS,
            timeout=25
        )
        if ai_get.status_code == 200:
            parsed = parse_ai_response(ai_get.text)
            if parsed:
                print(f"Translated via OpenAI (GET): {parsed}")
                return parsed
    except Exception as e:
        print(f"OpenAI GET error: {e}")

    print("AI endpoints did not respond; waiting for next cycle.")
    return None

async def check_and_post(client, user, processed_ids, is_first_run):
    tweets = await user.get_tweets('Tweets', count=5)
    posted_in_first = 0

    for tweet in tweets:
        t_id = str(tweet.id)
        if t_id in processed_ids:
            continue

        if getattr(tweet, 'retweeted_tweet', None) is not None or getattr(tweet, 'in_reply_to_tweet_id', None) is not None:
            save_processed_id(t_id, processed_ids)
            continue

        if is_first_run and posted_in_first >= 1:
            save_processed_id(t_id, processed_ids)
            continue

        clean_text = re.sub(r'https://t\.co/\S+', '', tweet.text or '').strip()
        if not clean_text:
            save_processed_id(t_id, processed_ids)
            continue

        print(f"New tweet detected {t_id}: {clean_text[:60]}...")
        translated_text = filter_and_translate(clean_text)

        if translated_text is None:
            continue

        if translated_text == "NOT_SPORTS" or "NOT_SPORTS" in translated_text:
            save_processed_id(t_id, processed_ids)
            continue

        media_ids = []
        video_link = None

        if hasattr(tweet, 'media') and tweet.media:
            for idx, item in enumerate(tweet.media):
                media_type = getattr(item, 'type', '')
                if media_type == 'photo':
                    img_url = getattr(item, 'media_url', None) or getattr(item, 'media_url_https', None)
                    if img_url:
                        img_data = requests.get(img_url, headers=HEADERS, timeout=20).content
                        img_path = f"temp_{t_id}_{idx}.jpg"
                        with open(img_path, 'wb') as img_f:
                            img_f.write(img_data)
                        m_id = await client.upload_media(img_path)
                        media_ids.append(m_id)
                        if os.path.exists(img_path):
                            os.remove(img_path)
                elif media_type in ['video', 'animated_gif']:
                    src_id = getattr(item, 'source_status_id', None) or t_id
                    video_link = f"https://x.com/i/status/{src_id}/video/1"

        final_tweet_text = fit_tweet_length(translated_text, video_link)
        await client.create_tweet(text=final_tweet_text, media_ids=media_ids if media_ids else None)
        save_processed_id(t_id, processed_ids)
        posted_in_first += 1
        print(f"Posted tweet {t_id} immediately!")
        await asyncio.sleep(3)

async def main():
    processed_ids, is_first_run = load_processed_ids()
    client = Client(language='en-US')
    client.set_cookies({'auth_token': TW_AUTH_TOKEN, 'ct0': TW_CT0})

    user = await client.get_user_by_screen_name(TARGET_USER)
    start_time = time.time()

    print(f"Starting AI live monitoring for @{TARGET_USER} every {CHECK_INTERVAL}s...")
    while (time.time() - start_time) < RUN_DURATION:
        try:
            await check_and_post(client, user, processed_ids, is_first_run)
            is_first_run = False
        except Exception as e:
            print(f"Check error (waiting 30s): {e}")
            await asyncio.sleep(30)
        await asyncio.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())
