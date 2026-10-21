import os
import re
import json
import asyncio
import requests
from twikit import Client

TARGET_USER = "Amr13jn"
PROCESSED_FILE = "processed_ids.txt"
COOKIES_FILE = "cookies.json"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TW_USERNAME = os.environ.get("TWITTER_USERNAME")
TW_EMAIL = os.environ.get("TWITTER_EMAIL")
TW_PASSWORD = os.environ.get("TWITTER_PASSWORD")

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
1. Determine if this tweet is related to sports (football, matches, goals, players, etc.).
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
    client = Client(language='en-US')

    # Login or load cookies
    if os.path.exists(COOKIES_FILE):
        client.load_cookies(COOKIES_FILE)
    else:
        await client.login(auth_info_1=TW_USERNAME, auth_info_2=TW_EMAIL, password=TW_PASSWORD)
        client.save_cookies(COOKIES_FILE)

    print(f"Fetching latest tweets for @{TARGET_USER}...")
    user = await client.get_user_by_screen_name(TARGET_USER)
    tweets = await user.get_tweets('Tweets')

    for tweet in tweets:
        if str(tweet.id) in processed_ids:
            continue

        # Skip retweets and replies
        if getattr(tweet, 'retweeted_tweet', None) is not None:
            save_processed_id(tweet.id)
            continue
        if getattr(tweet, 'in_reply_to_tweet_id', None) is not None:
            save_processed_id(tweet.id)
            continue

        clean_text = tweet.text
        if not clean_text:
            save_processed_id(tweet.id)
            continue

        print(f"Processing tweet {tweet.id}: {clean_text[:40]}...")
        translated_text = filter_and_translate(clean_text)

        if translated_text == "NOT_SPORTS":
            print(f"Tweet {tweet.id} skipped (Not sports).")
            save_processed_id(tweet.id)
            continue

        # Handle media
        media_ids = []
        has_video = False

        if hasattr(tweet, 'media') and tweet.media:
            for item in tweet.media:
                media_type = getattr(item, 'type', '')
                if media_type == 'photo':
                    img_url = getattr(item, 'media_url_https', None)
                    if img_url:
                        img_data = requests.get(img_url).content
                        img_path = f"temp_{tweet.id}.jpg"
                        with open(img_path, 'wb') as img_f:
                            img_f.write(img_data)
                        m_id = await client.upload_media(img_path, media_type='image/jpeg')
                        media_ids.append(m_id)
                        if os.path.exists(img_path):
                            os.remove(img_path)
                elif media_type in ['video', 'animated_gif']:
                    has_video = True

        final_tweet_text = translated_text
        if has_video:
            final_tweet_text += f"\n\nhttps://x.com/{TARGET_USER}/status/{tweet.id}"

        print(f"Publishing: {final_tweet_text[:60]}...")
        await client.create_tweet(text=final_tweet_text, media_ids=media_ids if media_ids else None)
        save_processed_id(tweet.id)
        print(f"Successfully posted tweet {tweet.id}!")
        await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
