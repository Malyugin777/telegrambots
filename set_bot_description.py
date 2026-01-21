import urllib.request
import json

TOKEN = '8222846501:AAE6lJ5xBispWUBzVmCr7tKfKSI1NcSlHyI'

short = 'Скачиваю видео из TikTok, Instagram, YouTube, Pinterest'

full = '''Быстрый загрузчик видео из соцсетей.

TikTok - без водяного знака
Instagram - посты, Reels, Stories
YouTube - Shorts и полные видео (до 2GB)
Pinterest - фото и видео

Реклама/Вопросы: @Alexey_buying777'''

def api_call(method, data):
    url = f'https://api.telegram.org/bot{TOKEN}/{method}'
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        return str(e)

print('Short:', api_call('setMyShortDescription', {'short_description': short}))
print('Full:', api_call('setMyDescription', {'description': full}))
