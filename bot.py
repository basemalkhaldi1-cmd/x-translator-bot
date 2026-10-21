import os
import re
import asyncio
import requests
from twikit import Client

TARGET_USER = "Amr13jn"
PROCESSED_FILE = "processed_ids.txt"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TW_AUTH_TOKEN = os.environ.get("TWITTER_AUTH_TOKEN")
TW_CT0 = os.environ.get("TWITTER_CT0")

def load_processed_ids():
    if os.path.exists(PROCESSED_FILE):
        with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def save_processed_id(tweet_id):
    with open(PROCESSED_FILE, "a", encoding="utf-8") as f:
        f.write(f"{tweet_id}\n")

def filter_and_translate(text):
    prompt = f"""You are an enthusiastic sports journalist and English football commentator.
Analyze the following Arabic tweet:
\"\"\"{text}\"\"\"

Task:
1. Determine if this tweet is related to sports (football, matches, goals, players, clubs, etc.).
2. If it is NOT sports-related, reply ONLY with: NOT_SPORTS
3. If it IS sports-related, translate it into exciting, authentic English football commentary style (use natural English football terms like 'GOAAAL!', match minutes, club/player names in English).
Do NOT include any extra notes or explanations. Return ONLY the translated English text."""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        response = requests.post(url, json=payload, timeout=25)
        res_json = response.json()
        translated = res_json['candidates'][0]['content']['parts'][0]['text'].strip()
        return translated
    except Exception as e:
        print(f"Translation error: {e}")
        return "NOT_SPORTS"

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

        # Skip retweets and replies
        if getattr(tweet, 'retweeted_tweet', None) is not None:
            save_processed_id(t_id)
            continue
        if getattr(tweet, 'in_reply_to_tweet_id', None) is not None:
            save_processed_id(t_id)
            continue

        # On first run, only post 1 latest sports tweet and mark older ones as read
        if is_first_run and posted_count >= 1:
            save_processed_id(t_id)
            continue

        clean_text = re.sub(r'https://t\.co/\S+', '', tweet.text or '').strip()
        if not clean_text:
            save_processed_id(t_id)
            continue

        print(f"Processing tweet {t_id}: {clean_text[:40]}...")
        translated_text = filter_and_translate(clean_text)

        if translated_text == "NOT_SPORTS" or "NOT_SPORTS" in translated_text:
            print(f"Tweet {t_id} skipped (Not sports).")
            save_processed_id(t_id)
            continue

        media_ids = []
        has_video = False

        if hasattr(tweet, 'media') and tweet.media:
            for idx, item in enumerate(tweet.media):
                media_type = getattr(item, 'type', '')
                if media_type == 'photo':
                    img_url = getattr(item, 'media_url_https', None)
                    if img_url:
                        img_data = requests.get(img_url, timeout=20).content
                        img_path = f"temp_{t_id}_{idx}.jpg"
                        with open(img_path, 'wb') as img_f:
                            img_f.write(img_data)
                        m_id = await client.upload_media(img_path)
                        media_ids.append(m_id)
                        if os.path.exists(img_path):
                            os.remove(img_path)
                elif media_type in ['video', 'animated_gif']:
                    has_video = True

        final_tweet_text = translated_text
        if has_video:
            final_tweet_text += f"\n\nhttps://x.com/{TARGET_USER}/status/{t_id}"

        print(f"Publishing: {final_tweet_text[:60]}...")
        await client.create_tweet(text=final_tweet_text, media_ids=media_ids if media_ids else None)
        save_processed_id(t_id)
        posted_count += 1
        print(f"Successfully posted tweet {t_id}!")
        await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
