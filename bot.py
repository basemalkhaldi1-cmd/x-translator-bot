import os
import re
import html
import asyncio
import requests
from twikit import Client

TARGET_USER = "Amr13jn"
PROCESSED_FILE = "processed_ids.txt"

GEMINI_API_KEY = (os.environ.get("GEMINI_API_KEY") or "").strip()
TW_AUTH_TOKEN = (os.environ.get("TWITTER_AUTH_TOKEN") or "").strip().strip('"').strip("'")
TW_CT0 = (os.environ.get("TWITTER_CT0") or "").strip().strip('"').strip("'")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
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
    "الأول", "الاول", "الثاني", "الثالث", "الرابع", "الخامس", "ريمونتادا"
]

def load_processed_ids():
    if os.path.exists(PROCESSED_FILE):
        with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
        if lines and lines[0] == "#v4":
            return set(lines[1:])
    with open(PROCESSED_FILE, "w", encoding="utf-8") as f:
        f.write("#v4\n")
    return set()

def save_processed_id(tweet_id):
    with open(PROCESSED_FILE, "a", encoding="utf-8") as f:
        f.write(f"{tweet_id}\n")

def is_sports_tweet(text):
    normalized = re.sub(r"(.)\1{2,}", r"\1", text)
    return any(kw in text or kw in normalized for kw in SPORTS_KEYWORDS)

def free_fallback_translate(text):
    if not is_sports_tweet(text):
        return "NOT_SPORTS"

    has_goal = bool(re.search(r"(قو+ل|جو+ل|هد+ف|يسجل)", text))
    cleaned = re.sub(r"(قو+ل|جو+ل)", "هدف!", text)
    cleaned = re.sub(r"(.)\1{2,}", r"\1", cleaned)

    translated = ""

    # Route 1: Google Translate Mobile Web
    try:
        res = requests.get(
            "https://translate.google.com/m",
            params={"sl": "ar", "tl": "en", "q": cleaned},
            headers=HEADERS,
            timeout=15
        )
        m = re.search(r'<div class="result-container">(.*?)</div>', res.text, re.DOTALL)
        if m:
            translated = html.unescape(m.group(1)).strip()
    except Exception as e:
        print(f"Route 1 error: {e}")

    # Route 2: Google Translate GTX API
    if not translated:
        try:
            res = requests.get(
                "https://translate.googleapis.com/translate_a/single",
                params={"client": "gtx", "sl": "ar", "tl": "en", "dt": "t", "q": cleaned},
                headers=HEADERS,
                timeout=15
            )
            data = res.json()
            translated = "".join(part[0] for part in data[0] if part and part[0]).strip()
        except Exception as e:
            print(f"Route 2 error: {e}")

    # Route 3: MyMemory Free Translation API
    if not translated:
        try:
            res = requests.get(
                "https://api.mymemory.translated.net/get",
                params={"q": cleaned[:450], "langpair": "ar|en"},
                headers=HEADERS,
                timeout=15
            )
            data = res.json()
            translated = (data.get("responseData", {}).get("translatedText") or "").strip()
        except Exception as e:
            print(f"Route 3 error: {e}")

    if not translated:
        return "NOT_SPORTS"

    if has_goal and "GOAAAL" not in translated.upper():
        translated = f"🚨 GOAAAL! ⚽🔥\n{translated}"
    return translated

def filter_and_translate(text):
    if GEMINI_API_KEY:
        prompt = f"""You are an enthusiastic sports journalist and English football commentator.
Analyze the following Arabic tweet:
\"\"\"{text}\"\"\"

Task:
1. Determine if this tweet is related to sports (football, matches, goals, players, clubs, etc.).
2. If it is NOT sports-related, reply ONLY with: NOT_SPORTS
3. If it IS sports-related, translate it into exciting, authentic English football commentary style (use natural English football terms like 'GOAAAL!', match minutes, club/player names in English).
Do NOT include any extra notes or explanations. Return ONLY the translated English text."""

        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        for model in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
            try:
                response = requests.post(url, json=payload, timeout=15)
                res_json = response.json()
                if "candidates" in res_json:
                    return res_json["candidates"][0]["content"]["parts"][0]["text"].strip()
            except Exception:
                pass

    print("Using built-in free sports translator...")
    return free_fallback_translate(text)

async def main():
    processed_ids = load_processed_ids()
    is_first_run = len(processed_ids) == 0

    client = Client(language='en-US')
    client.set_cookies({'auth_token': TW_AUTH_TOKEN, 'ct0': TW_CT0})

    print(f"Fetching latest tweets for @{TARGET_USER}...")
    user = await client.get_user_by_screen_name(TARGET_USER)
    tweets = await user.get_tweets('Tweets')

    posted_count = 0

    for tweet in tweets:
        t_id = str(tweet.id)
        if t_id in processed_ids:
            continue

        if getattr(tweet, 'retweeted_tweet', None) is not None:
            save_processed_id(t_id)
            continue
        if getattr(tweet, 'in_reply_to_tweet_id', None) is not None:
            save_processed_id(t_id)
            continue

        if is_first_run and posted_count >= 1:
            save_processed_id(t_id)
            continue

        clean_text = re.sub(r'https://t\.co/\S+', '', tweet.text or '').strip()
        if not clean_text:
            save_processed_id(t_id)
            continue

        print(f"Processing tweet {t_id}: {clean_text[:50]}...")
        translated_text = filter_and_translate(clean_text)

        if translated_text == "NOT_SPORTS" or "NOT_SPORTS" in translated_text:
            print(f"Tweet {t_id} skipped (Not sports).")
            save_processed_id(t_id)
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

        final_tweet_text = translated_text
        if video_link:
            final_tweet_text += f"\n\n{video_link}"

        print(f"Publishing tweet: {final_tweet_text}")
        await client.create_tweet(text=final_tweet_text, media_ids=media_ids if media_ids else None)
        save_processed_id(t_id)
        posted_count += 1
        print(f"Successfully posted tweet {t_id}!")
        await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
