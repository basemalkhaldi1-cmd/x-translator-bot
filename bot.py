import os
import re
import time
import html
import asyncio
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

# قاموس حماية أسماء اللاعبين والأندية التي قد تُترجم حرفياً بالخطأ
PROPER_NAMES_MAP = {
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

SPORTS_KEYWORDS = [
    "هدف", "قوول", "قول", "جول", "يسجل", "سجل", "متقدم", "يتقدم", "التعادل", "تعادل",
    "الفوز", "يفوز", "خسارة", "يخسر", "مباراة", "المباراة", "شوط", "الشوط", "الدقيقة",
    "دوري", "الدوري", "أبطال", "كأس", "بطولة", "نهائي", "تأهل", "يتأهل", "مرمى", "مرماه",
    "شباك", "الشباك", "حارس", "مدرب", "لاعب", "تشكيلة", "ركلة", "جزاء", "فاول", "ركنية",
    "تسلل", "بطاقة", "حمراء", "صفراء", "طرد", "تمريرة", "أسيست", "هاتريك", "ثنائية",
    "برشلونة", "ريال", "مدريد", "ليفربول", "سيتي", "أرسنال", "ارسنال", "تشيلسي", "يونايتد",
    "بايرن", "باريس", "يوفنتوس", "ميلان", "إنتر", "انتر", "روما", "نابولي", "أتلتيكو",
    "أستون", "استون", "فيلا", "نيوكاسل", "توتنهام", "لشبونه", "لشبونة", "بنفيكا", "بورتو",
    "الهلال", "النصر", "الاتحاد", "الأهلي", "الاهلي", "الشباب", "الاتفاق", "القادسية",
    "صلاح", "مبابي", "فينيسيوس", "هالاند", "ميسي", "رونالدو", "بيلينجهام", "يامال",
    "شرقي", "مرموش", "حكيمي", "محرز", "الأول", "الاول", "الثاني", "الثالث", "الرابع", "ريمونتادا"
]

CACHED_GEMINI_MODELS = None

def get_gemini_models():
    global CACHED_GEMINI_MODELS
    if CACHED_GEMINI_MODELS is not None:
        return CACHED_GEMINI_MODELS

    default_models = ["gemini-2.5-flash", "gemini-3.5-flash", "gemini-flash-latest", "gemini-2.5-pro"]
    if not GEMINI_API_KEY:
        CACHED_GEMINI_MODELS = default_models
        return CACHED_GEMINI_MODELS

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
        res = requests.get(url, timeout=15)
        data = res.json()
        available = []
        for m in data.get("models", []):
            name = m.get("name", "")
            methods = m.get("supportedGenerationMethods", [])
            if "generateContent" in methods and "gemini" in name.lower():
                if any(x in name.lower() for x in ["tts", "image", "embedding", "veo", "audio", "vision"]):
                    continue
                available.append(name.replace("models/", ""))
        flash_models = [m for m in available if "flash" in m.lower()]
        other_models = [m for m in available if "flash" not in m.lower()]
        if flash_models or other_models:
            CACHED_GEMINI_MODELS = flash_models + other_models
            print(f"Discovered Gemini models: {CACHED_GEMINI_MODELS[:4]}")
            return CACHED_GEMINI_MODELS
    except Exception as e:
        print(f"Model discovery warning: {e}")

    CACHED_GEMINI_MODELS = default_models
    return CACHED_GEMINI_MODELS

def load_processed_ids():
    if os.path.exists(PROCESSED_FILE):
        with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
        if lines and lines[0] == "#v5":
            return set(lines[1:])
    with open(PROCESSED_FILE, "w", encoding="utf-8") as f:
        f.write("#v5\n")
    return set()

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

def build_ai_prompt(text):
    # تزويد الذكاء الاصطناعي بملاحظات الأسماء إن وجدت في النص
    hints = []
    for ar_name, en_name in PROPER_NAMES_MAP.items():
        if ar_name in text:
            hints.append(f'"{ar_name}" = {en_name}')
    hints_str = "\nName Glossary for this tweet: " + ", ".join(hints) if hints else ""

    return f"""You are an expert football journalist and translator.
Analyze the following Arabic tweet:
\"\"\"{text}\"\"\"{hints_str}

Instructions:
1. Check if this tweet is related to sports/football (matches, goals, players, clubs, transfers, statements, etc.). If it is NOT related to sports at all, reply ONLY with: NOT_SPORTS
2. BEFORE translating, carefully identify all football player names, coach names, and club names. Use their exact official English spelling (e.g., "شرقي" is the player Rayan Cherki, NOT "East/Eastern"; "الاتحاد" is Al-Ittihad, NOT "Union"; "النصر" is Al-Nassr, NOT "Victory"; "الأهلي" is Al-Ahli; "الهلال" is Al-Hilal).
3. Translate the tweet accurately into natural English matching the original tweet's exact meaning and tone:
   - Do NOT invent or add "GOAL!" or "GOAAAL!" unless the original Arabic tweet explicitly announces a live goal (like "قوووول" or "يسجل الهدف").
   - If it is a news update, stat, or quote, translate it cleanly as football news without adding extra exclamations.
   - Keep the translation concise (under 200 characters).
   - Output ONLY the final English tweet text, with no quotes or explanations."""

def filter_and_translate(text):
    prompt = build_ai_prompt(text)

    # 1. المحاولة الأولى: عبر Gemini AI مع اكتشاف تلقائي للطرازات الفعالة
    if GEMINI_API_KEY:
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        for model in get_gemini_models()[:4]:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
            try:
                response = requests.post(url, json=payload, timeout=20)
                res_json = response.json()
                if "candidates" in res_json:
                    result = res_json["candidates"][0]["content"]["parts"][0]["text"].strip()
                    if result:
                        return result
            except Exception as e:
                print(f"Gemini {model} error: {e}")

    # 2. المحاولة الثانية: عبر نموذج الذكاء الاصطناعي الاحتياطي (Pollinations OpenAI LLM)
    try:
        ai_res = requests.post(
            "https://text.pollinations.ai/openai",
            json={
                "model": "openai",
                "messages": [
                    {"role": "system", "content": "You are a professional football translator. Never translate player or club names literally."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.2
            },
            headers=HEADERS,
            timeout=25
        )
        if ai_res.status_code == 200:
            ai_json = ai_res.json()
            content = ai_json["choices"][0]["message"]["content"].strip()
            if content:
                return content
    except Exception as e:
        print(f"Backup AI error: {e}")

    # 3. الملاذ الأخير فقط عند انقطاع خدمات الذكاء الاصطناعي: استبدال الأسماء المحمية ثم الترجمة بدون إضافة قووول
    normalized = re.sub(r"(.)\1{2,}", r"\1", text)
    if not any(kw in text or kw in normalized for kw in SPORTS_KEYWORDS):
        return "NOT_SPORTS"

    cleaned = re.sub(r"(قو+ل|جو+ل)", "Goal!", text)
    cleaned = re.sub(r"(.)\1{2,}", r"\1", cleaned)
    for ar_name, en_name in sorted(PROPER_NAMES_MAP.items(), key=lambda x: -len(x[0])):
        cleaned = cleaned.replace(ar_name, en_name)

    try:
        res = requests.get(
            "https://translate.google.com/m",
            params={"sl": "ar", "tl": "en", "q": cleaned},
            headers=HEADERS,
            timeout=15
        )
        m = re.search(r'<div class="result-container">(.*?)</div>', res.text, re.DOTALL)
        if m:
            return html.unescape(m.group(1)).strip()
    except Exception:
        pass

    return "NOT_SPORTS"

async def check_and_post(client, user, processed_ids):
    tweets = await user.get_tweets('Tweets', count=5)
    for tweet in tweets:
        t_id = str(tweet.id)
        if t_id in processed_ids:
            continue

        if getattr(tweet, 'retweeted_tweet', None) is not None or getattr(tweet, 'in_reply_to_tweet_id', None) is not None:
            save_processed_id(t_id, processed_ids)
            continue

        clean_text = re.sub(r'https://t\.co/\S+', '', tweet.text or '').strip()
        if not clean_text:
            save_processed_id(t_id, processed_ids)
            continue

        print(f"New tweet detected {t_id}: {clean_text[:50]}...")
        translated_text = filter_and_translate(clean_text)

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
        print(f"Posted tweet {t_id} immediately!")
        await asyncio.sleep(3)

async def main():
    processed_ids = load_processed_ids()
    client = Client(language='en-US')
    client.set_cookies({'auth_token': TW_AUTH_TOKEN, 'ct0': TW_CT0})

    user = await client.get_user_by_screen_name(TARGET_USER)
    start_time = time.time()

    print(f"Starting live monitoring for @{TARGET_USER} every {CHECK_INTERVAL}s...")
    while (time.time() - start_time) < RUN_DURATION:
        try:
            await check_and_post(client, user, processed_ids)
        except Exception as e:
            print(f"Check error (waiting 30s): {e}")
            await asyncio.sleep(30)
        await asyncio.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())
