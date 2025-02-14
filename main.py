import os, re, json, openai, random, time, requests, shutil, datetime
from pydub import AudioSegment
from flask import Flask, request, jsonify
from linebot.exceptions import InvalidSignatureError
from linebot.v3.messaging import MessagingApi, Configuration, ApiClient
from linebot.v3.webhooks import MessageEvent, PostbackEvent, FollowEvent
from linebot.v3.messaging.models import ReplyMessageRequest, TextMessage, FlexMessage, FlexContainer, ImageMessage, PushMessageRequest
from linebot.v3.webhooks.models import TextMessageContent
from linebot.v3.webhooks.models import AudioMessageContent
from linebot.v3.webhook import WebhookHandler
from groq import Groq
from dotenv import load_dotenv
from flask import send_from_directory
from types import SimpleNamespace
from bs4 import BeautifulSoup
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync
import cloudscraper

# Load Environment Arguments
load_dotenv()

# Grab API Key from .env
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")
STABILITY_API_KEY = os.getenv("STABILITY_API_KEY")
HUGGING_TOKENS = os.getenv("HUGGING_TOKENS")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_SEARCH_KEY = os.getenv("GOOGLE_SEARCH_KEY")
GOOGLE_CX = os.getenv("GOOGLE_CX")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
CWB_API_KEY = os.getenv("CWB_API_KEY")
CWB_API_URL = "https://opendata.cwb.gov.tw/api/v1/rest/datastore/F-D0047-091"
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
BASE_URL = "https://render-linebot-masp.onrender.com"

# 初始化 Spotipy
spotify_auth = SpotifyClientCredentials(client_id=SPOTIFY_CLIENT_ID, client_secret=SPOTIFY_CLIENT_SECRET)
spotify_api = spotipy.Spotify(auth_manager=spotify_auth)
sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=SPOTIFY_CLIENT_ID, client_secret=SPOTIFY_CLIENT_SECRET))

# Grab Allowed Users and Group ID from .env
allowed_users_str = os.getenv("ALLOWED_USERS", "")
ALLOWED_USERS = {uid.strip() for uid in allowed_users_str.split(",") if uid.strip()}
allowed_groups_str = os.getenv("ALLOWED_GROUPS", "")
ALLOWED_GROUPS = {gid.strip() for gid in allowed_groups_str.split(",") if gid.strip()}

# Initailize LINE API (v3)
config = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
messaging_api = MessagingApi(ApiClient(config))
handler = WebhookHandler(LINE_CHANNEL_SECRET)
client = Groq(api_key=GROQ_API_KEY)

# Initialize Flask 
app = Flask(__name__)

# 城市對應表（避免輸入錯誤）
CITY_MAPPING = {
    # 台灣縣市
    "台北": "Taipei",
    "新北": "New Taipei",
    "桃園": "Taoyuan",
    "台中": "Taichung",
    "台南": "Tainan",
    "高雄": "Kaohsiung",
    "基隆": "Keelung",
    "新竹": "Hsinchu",
    "嘉義": "Chiayi",
    "苗栗": "Miaoli",
    "彰化": "Changhua",
    "南投": "Nantou",
    "雲林": "Yunlin",
    "嘉義": "Chiayi",
    "屏東": "Pingtung",
    "宜蘭": "Yilan",
    "花蓮": "Hualien",
    "台東": "Taitung",
    "澎湖": "Penghu",
    "金門": "Kinmen",
    "連江": "Lienchiang",  # 馬祖

    # 世界大都市
    "東京": "Tokyo",
    "大阪": "Osaka",
    "京都": "Kyoto",
    "首爾": "Seoul",
    "釜山": "Busan",
    "曼谷": "Bangkok",
    "新加坡": "Singapore",
    "吉隆坡": "Kuala Lumpur",
    "胡志明": "Ho Chi Minh City",
    "河內": "Hanoi",
    "雅加達": "Jakarta",
    "香港": "Hong Kong",
    "澳門": "Macau",
    "北京": "Beijing",
    "上海": "Shanghai",
    "廣州": "Guangzhou",
    "深圳": "Shenzhen",
    "倫敦": "London",
    "巴黎": "Paris",
    "柏林": "Berlin",
    "阿姆斯特丹": "Amsterdam",
    "羅馬": "Rome",
    "馬德里": "Madrid",
    "紐約": "New York",
    "洛杉磯": "Los Angeles",
    "芝加哥": "Chicago",
    "舊金山": "San Francisco",
    "華盛頓": "Washington",
    "多倫多": "Toronto",
    "溫哥華": "Vancouver",
    "墨西哥城": "Mexico City",
    "布宜諾斯艾利斯": "Buenos Aires",
    "悉尼": "Sydney",
    "墨爾本": "Melbourne",
    "開普敦": "Cape Town",
    "開羅": "Cairo",
    "杜拜": "Dubai",
    "伊斯坦堡": "Istanbul",
    "莫斯科": "Moscow"
}

# Record AI model choosen by User
user_ai_choice = {}

# Global dictionary for translation
user_translation_config = {}    

@app.route("/", methods=["GET"])
def home():
    return "狗蛋 啟動！"

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory("static", filename)

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "未收到簽名")
    body = request.get_data(as_text=True)

    # 🔍 Log Webhook Data
    print(f"📢 [DEBUG] Webhook Received: {body}")

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("❌ [ERROR] Webhook Signature 驗證失敗")
        return "Invalid signature", 400
    except Exception as e:
        print(f"❌ [ERROR] Webhook 處理錯誤: {e}")

    return "OK", 200

@handler.add(FollowEvent)
def handle_follow(event):
    """當用戶加好友時，立即發送選單"""
    command_list = (
            "📝 支援的指令：\n"
            "1. 換模型: 更換 AI 語言模型 \n\t\t（預設為 Deepseek-R1）\n"
            "2. 給我id: 顯示 LINE 個人 ID\n"
            "3. 群組id: 顯示 LINE 群組 ID\n"
            "4. 狗蛋出去: 機器人離開群組\n"
            "5. 當前模型: 機器人現正使用的模型\n"
            "6. 狗蛋生成: 生成圖片\n"
            "7. 我要翻譯: 翻譯語言\n"
            "8. 停止翻譯: 停止翻譯\n"
            "9. 狗蛋情勒 狗蛋的超能力"
        )
    reply_request = ReplyMessageRequest(
        replyToken=event.reply_token,
        messages=[TextMessage(text=command_list)]
    )
    send_response(event, reply_request)

# ----------------------------------
# Support Function
# ----------------------------------
def safe_api_call(api_func, request_obj, retries=3, backoff_factor=1.0):
    for i in range(retries):
        try:
            return api_func(request_obj)
        except Exception as e:
            if "429" in str(e):
                wait_time = backoff_factor * (2 ** i)
                print(f"🔄 Rate limit: {wait_time} 秒後重試...")
                time.sleep(wait_time)
            else:
                print(f"❌ API call error: {e}")
                raise
    raise Exception("API call failed after retries")

def send_limit_message(event):
    """
    嘗試使用 push_message 發送「很抱歉，使用已達上限」訊息，
    並採用指數退避機制重試若遇到 429 錯誤。
    """
    target_id = event.source.group_id if event.source.type == "group" else event.source.user_id
    limit_msg = TextMessage(text="很抱歉，使用已達上限")
    push_req = PushMessageRequest(
        to=target_id,
        messages=[limit_msg]
    )
    retries = 3
    backoff_factor = 1.0
    for i in range(retries):
        try:
            messaging_api.push_message(push_req)
            print("成功發送使用已達上限訊息給使用者")
            return
        except Exception as err:
            err_str = str(err)
            if "429" in err_str or "monthly limit" in err_str:
                wait_time = backoff_factor * (2 ** i)
                print(f"push_message 發送失敗 (429)，{wait_time} 秒後重試...")
                time.sleep(wait_time)
            else:
                print(f"push_message 發送失敗: {err}")
                break
    print("最終無法發送使用已達上限訊息給使用者")

# ----------------------------------
# Main Function
# ----------------------------------
# Response Function - Sort by event "reply_message" or "push_message"
def send_response(event, reply_request):
    """
    發送回覆訊息：如果發送失敗且捕捉到 429（超過使用量限制），
    嘗試改用 send_limit_message() 來告知使用者。
    """
    try:
        if getattr(event, "_is_audio", False):
            to = event.source.group_id if event.source.type == "group" else event.source.user_id
            push_req = PushMessageRequest(
                to=to,
                messages=reply_request.messages
            )
            messaging_api.push_message(push_req)
        else:
            messaging_api.reply_message(reply_request)
    except Exception as e:
        err_str = str(e)
        if "429" in err_str or "monthly limit" in err_str:
            print("❌ 捕捉到 429 錯誤，表示使用已達上限")
            send_limit_message(event)
        else:
            print(f"❌ LINE Reply Error: {e}")

# TextMessage Handler
@handler.add(MessageEvent)  # 預設處理 MessageEvent
def handle_message(event):
    """處理 LINE 文字訊息，根據指令回覆或提供 AI 服務"""
    # 檢查 event.message 是否存在
    if not hasattr(event, "message"):
        return

    # 判斷 message 資料型態：
    if isinstance(event.message, dict):
        msg_type = event.message.get("type")
        msg_text = event.message.get("text", "")
    elif hasattr(event.message, "type"):
        msg_type = event.message.type
        msg_text = getattr(event.message, "text", "")
    else:
        return
    
    # 若事件已經被處理過，則直接返回
    if getattr(event, "_processed", False):
        return

    # 如果是從語音轉錄而來的事件，也可以標記為已處理
    if getattr(event, "_is_audio", False):
        event._processed = True

    if msg_type != "text":
        return

    # 取得使用者與群組資訊（採用 snake_case）
    user_message = msg_text.strip().lower()
    user_id = event.source.user_id
    group_id = event.source.group_id if event.source.type == "group" else None

    # 檢查目前選用的 AI 模型
    if group_id and group_id in user_ai_choice:
        ai_model = user_ai_choice[group_id]
    else:
        ai_model = user_ai_choice.get(user_id, "deepseek-r1-distill-llama-70b")

    print(f"📢 [DEBUG] {user_id if not group_id else group_id} 當前模型: {ai_model}")

    # (1) 「給我id」：若訊息中同時包含「給我」和「id」
    if "給我" in user_message and "id" in user_message:
        reply_text = f"您的 User ID 是：\n{user_id}"
        if group_id:
            reply_text += f"\n這個群組的 ID 是：\n{group_id}"
        reply_request = ReplyMessageRequest(
            replyToken=event.reply_token,
            messages=[TextMessage(text=reply_text)]
        )
        send_response(event, reply_request)
        return

    # (2) 「群組id」：在群組中，若訊息中同時包含「群組」和「id」
    if group_id and "群組" in user_message and "id" in user_message:
        reply_text = f"這個群組的 ID 是：\n{group_id}"
        reply_request = ReplyMessageRequest(
            replyToken=event.reply_token,
            messages=[TextMessage(text=reply_text)]
        )
        send_response(event, reply_request)
        return

    # (2-2) 若為個人訊息卻要求群組指令，回覆錯誤訊息
    if group_id is None and "群組" in user_message and "id" in user_message:
        reply_request = ReplyMessageRequest(
            replyToken=event.reply_token,
            messages=[TextMessage(text="❌ 此指令僅限群組使用")]
        )
        send_response(event, reply_request)
        return
    
    # (2-3) Random response from default pool
    if "狗蛋" in user_message and "情勒" in user_message:
        target_id = group_id if group_id is not None else user_id
        random_reply(event.reply_token, target_id, messaging_api)
        return

    # (3) 「狗蛋指令」：列出所有支援指令
    if "指令" in user_message and "狗蛋" in user_message:
        command_list = (
            "📝 支援的指令：\n"
            "1. 換模型: 更換 AI 語言模型 \n\t\t（預設為 Deepseek-R1）\n"
            "2. 狗蛋出去: 機器人離開群組\n"
            "3. 當前模型: 機器人現正使用的模型\n"
            "4. 狗蛋生成: 生成圖片\n"
            "5. 狗蛋介紹: 人物或角色的說明\n"
            "6. 狗蛋搜圖: 即時搜圖\n"
            "7. 狗蛋唱歌: 串連Spotify試聽\n"
            "8. 狗蛋氣象: 確認當前天氣\n"
            "9. 狗蛋預報: 確認三天天氣預報\n"
            "10. 狗蛋情勒: 狗蛋的超能力"
        )
        reply_request = ReplyMessageRequest(
            replyToken=event.reply_token,
            messages=[TextMessage(text=command_list)]
        )
        send_response(event, reply_request)
        return

    # # (4) AI 服務指令：檢查使用權限
    # if event.source.type != "group":
    #     if user_id not in ALLOWED_USERS:
    #         reply_request = ReplyMessageRequest(
    #             replyToken=event.reply_token,
    #             messages=[TextMessage(text="❌ 你沒有權限使用 AI 服務")]
    #         )
    #         send_response(event, reply_request)
    #         return
    # else:
    #     if group_id not in ALLOWED_GROUPS:
    #         reply_request = ReplyMessageRequest(
    #             replyToken=event.reply_token,
    #             messages=[TextMessage(text="❌ 本群組沒有權限使用 AI 服務")]
    #         )
    #         send_response(event, reply_request)
    #         return
    #     if user_id not in ALLOWED_USERS and "狗蛋" in user_message:
    #         reply_request = ReplyMessageRequest(
    #             replyToken=event.reply_token,
    #             messages=[TextMessage(text="❌ 你沒有權限使用 AI 服務")]
    #         )
    #         send_response(event, reply_request)
    #         return
    #     # 處理「狗蛋出去」指令（僅適用於群組）
    #     if "狗蛋" in user_message and "出去" in user_message and group_id:
    #         try:
    #             reply_request = ReplyMessageRequest(
    #             replyToken=event.reply_token,
    #             messages=[TextMessage(text="我也不想留, 掰")]
    #             )
    #             send_response(event, reply_request)
    #             messaging_api.leave_group(group_id)
    #             print(f"🐶 狗蛋已離開群組 {group_id}")
    #         except Exception as e:
    #             print(f"❌ 無法離開群組: {e}")
    #         return


    # (4) AI Group Command
    if event.source.type == "group":
        # 處理「狗蛋出去」指令（僅適用於群組）
        if "狗蛋" in user_message and "出去" in user_message and group_id:
            try:
                reply_request = ReplyMessageRequest(
                replyToken=event.reply_token,
                messages=[TextMessage(text="我也不想留, 掰")]
                )
                send_response(event, reply_request)
                messaging_api.leave_group(group_id)
                print(f"🐶 狗蛋已離開群組 {group_id}")
            except Exception as e:
                print(f"❌ 無法離開群組: {e}")
            return

    # (4-a) 「狗蛋生成」指令（例如圖片生成）
    if "狗蛋生成" in user_message:
        prompt = user_message.split("狗蛋生成", 1)[1].strip()
        if not prompt:
            prompt = "一個美麗的風景"
        print(f"📢 [DEBUG] 圖片生成 prompt: {prompt}")
        # 直接傳入 event.reply_token，而不是 user id
        handle_generate_image_command(event.reply_token, prompt, messaging_api)
        return

    # (4-b) 「當前模型」指令
    if "模型" in user_message and "當前" in user_message:
        if group_id and group_id in user_ai_choice:
            model = user_ai_choice[group_id]
        else:
            model = user_ai_choice.get(user_id, "Deepseek-R1")
        reply_text = f"🤖 現在使用的 AI 模型是：\n{model}"
        reply_request = ReplyMessageRequest(
            replyToken=event.reply_token,
            messages=[TextMessage(text=reply_text)]
        )
        send_response(event, reply_request)
        return

    # (4-c) 「換模型」
    if "換" in user_message and "模型" in user_message:
        # 若此事件來自語音，則改用 push_message
        if getattr(event, "_is_audio", False):
            target = event.source.group_id if event.source.type == "group" else event.source.user_id
            send_ai_selection_menu(event.reply_token, target, use_push=True)
        else:
            send_ai_selection_menu(event.reply_token)
        return
    
    # (4-e)「狗蛋搜尋」指令：搜尋 + AI 總結
    if user_message.startswith("狗蛋搜尋"):
        search_query = user_message.replace("狗蛋搜尋", "").strip()
        
        if not search_query:
            reply_text = "請輸入要搜尋的內容，例如：狗蛋搜尋 OpenAI"
        else:
            print(f"📢 [DEBUG] 進行 Google 搜尋: {search_query}")
            search_results = google_search(search_query)

            if not search_results:
                reply_text = "❌ 找不到相關資料。"
            else:
                reply_text = summarize_with_openai(search_results, search_query)

        reply_request = ReplyMessageRequest(
            replyToken=event.reply_token,
            messages=[TextMessage(text=reply_text)]
        )
        send_response(event, reply_request)
        return
    
    # (4-f)狗蛋介紹 Image + AI 總結
    if user_message.startswith("狗蛋介紹"):
        # 解析人物名稱
        messages = []
        person_name = user_message.replace("狗蛋介紹", "").strip()
        if not person_name:
            reply_request = ReplyMessageRequest(
                replyToken=event.reply_token,
                messages=[TextMessage(text="請提供要查詢的人物名稱，例如：狗蛋介紹 川普")]
            )
            send_response(event, reply_request)
            return
        # 取得 AI 回應 + 圖片
        response_text, image_url = search_person_info(person_name)
        if image_url:
            messages.append(create_flex_message(response_text, image_url))  # 附加圖片

        reply_request = ReplyMessageRequest(
            replyToken=event.reply_token,
            messages=messages
        )
        send_response(event, reply_request)
        return

    # (4-g)狗蛋搜圖 Image search
    if user_message.startswith("狗蛋搜圖"):
        search_query = user_message.replace("狗蛋搜圖", "").strip()

        if not search_query:
            reply_text = "請提供要搜尋的內容，例如：狗蛋搜圖 日本女星"
            messages = [TextMessage(text=reply_text)]
        else:
            image_url = search_google_image(search_query)

            if image_url:
                messages = [create_flex_message(f"「{search_query}」的圖片 🔍", image_url)]
            else:
                messages = [TextMessage(text=f"找不到 {search_query} 的相關圖片 😢")]

        reply_request = ReplyMessageRequest(
            replyToken=event.reply_token,
            messages=messages
        )
        send_response(event, reply_request)
        return
    
    # (4-h)狗蛋唱歌 Spotify link
    if user_message.startswith("狗蛋唱歌"):
        song_name = user_message.replace("狗蛋唱歌", "").strip()
        song_data = search_spotify_song(song_name)

        if not song_data:
            reply_request = ReplyMessageRequest(
                replyToken=event.reply_token,
                messages=[TextMessage(text="❌ 沒找到這首歌，請試試別的！")]
            )
        else:
            mp3_url = song_data.get("preview_url")
            if mp3_url:
                hosted_m4a_url = download_and_host_audio(mp3_url)  # 轉換為 m4a

                if hosted_m4a_url:
                    reply_request = ReplyMessageRequest(
                        replyToken=event.reply_token,
                        messages=[
                            TextMessage(text=f"🎶 這是 {song_data['name']} 的預覽音頻 🎵"),
                            AudioMessageContent(original_content_url=hosted_m4a_url, duration=30000)
                        ]
                    )
                else:
                    reply_request = ReplyMessageRequest(
                        replyToken=event.reply_token,
                        messages=[TextMessage(text="❌ 轉換歌曲失敗，請稍後再試！")]
                    )
            else:
                reply_request = ReplyMessageRequest(
                    replyToken=event.reply_token,
                    messages=[TextMessage(text=f"🎵 {song_data['name']} 的歌曲連結：{song_data['song_url']} ）")]
                )

        send_response(event, reply_request)
        return

    # (4-i)狗蛋氣象
    # 如果使用者輸入 "台北天氣"，則查詢台北天氣
    if "氣象" in user_message and "狗蛋" in user_message:
        city = user_message.replace("狗蛋氣象", "").strip()
        
        if city:
            weather_info = get_weather_weatherapi(city)
        else:
            weather_info = "❌ 請輸入有效的城市名稱, 包含行政區（例如：竹北市、東勢鄉）"

        reply_request = ReplyMessageRequest(
            replyToken=event.reply_token,
            messages=[TextMessage(text=f"{weather_info}")]
        )
        send_response(event, reply_request)
        return
    
    # (4-j)狗蛋預報
    if "狗蛋" in user_message and "預報" in user_message:
        city = user_message.replace("狗蛋預報", "").strip()
        
        if city:
            weather_info = get_weather_forecast(city)
        else:
            weather_info = "❌ 請輸入有效的城市名稱, 包含行政區（例如：竹北市、東勢鄉）"

        reply_request = ReplyMessageRequest(
            replyToken=event.reply_token,
            messages=[TextMessage(text=f"{weather_info}")]
        )
        send_response(event, reply_request)
        return

    # (4-j)「狗蛋開車」
    if ("狗蛋開車") in user_message and ("最熱") not in user_message and ("最新") not in user_message:
        search_query = user_message.replace("狗蛋開車", "").strip()
        
        if not search_query:
            response_text = "請提供人名，例如：狗蛋開車 狗蛋"
            reply_request = ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=response_text)]
            )
        else:
            videos = get_video_data(search_query)  # ✅ 爬取影片
            # print(f"✅ [DEBUG] 爬取結果: {videos}")  # Debugging
            
            if not videos:
                print("❌ [DEBUG] 爬取結果為空，回傳純文字訊息")
                response_text = "找不到相關影片。"
                reply_request = ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=response_text)]
                )
            else:
                flex_message = create_flex_jable_message(videos)  # ✅ 生成 FlexMessage
                
                if flex_message is None:  # **確保 flex_message 不為 None**
                    print("❌ [DEBUG] FlexMessage 生成失敗，回傳純文字")
                    response_text = "找不到相關影片。"
                    reply_request = ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=response_text)]
                    )
                else:
                    # print(f"✅ [DEBUG] 生成的 FlexMessage: {flex_message}")
                    reply_request = ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[flex_message]
                    )
        send_response(event, reply_request)  
        return  

    # (4-k)「狗蛋開車最熱」
    if ("狗蛋開車") in user_message and ("最熱") in user_message:
        videos = get_video_data_hotest()  # ✅ 爬取影片
        print(f"✅ [DEBUG] 爬取結果: {videos}")  # Debugging
            
        if not videos:
            print("❌ [DEBUG] 爬取結果為空，回傳純文字訊息")
            response_text = "找不到相關影片。"
            reply_request = ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=response_text)]
            )
        else:
            flex_message = create_flex_jable_message(videos)  # ✅ 生成 FlexMessage
                
            if flex_message is None:  # **確保 flex_message 不為 None**
                print("❌ [DEBUG] FlexMessage 生成失敗，回傳純文字")
                response_text = "找不到相關影片。"
                reply_request = ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=response_text)]
                )
            else:
                # print(f"✅ [DEBUG] 生成的 FlexMessage: {flex_message}")
                reply_request = ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[flex_message]
                )
        send_response(event, reply_request)  
        return  
    
    # (4-m)「狗蛋開車最新」
    if ("狗蛋開車") in user_message and ("最新") in user_message:
        videos = get_video_data_newest()  # ✅ 爬取影片
        print(f"✅ [DEBUG] 爬取結果: {videos}")  # Debugging
            
        if not videos:
            print("❌ [DEBUG] 爬取結果為空，回傳純文字訊息")
            response_text = "找不到相關影片。"
            reply_request = ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=response_text)]
            )
        else:
            flex_message = create_flex_jable_message(videos)  # ✅ 生成 FlexMessage
                
            if flex_message is None:  # **確保 flex_message 不為 None**
                print("❌ [DEBUG] FlexMessage 生成失敗，回傳純文字")
                response_text = "找不到相關影片。"
                reply_request = ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=response_text)]
                )
            else:
                # print(f"✅ [DEBUG] 生成的 FlexMessage: {flex_message}")
                reply_request = ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[flex_message]
                )
        send_response(event, reply_request)  
        return 


    # (5) 若在群組中且訊息中不包含「狗蛋」，則不觸發 AI 回應
    if event.source.type == "group" and "狗蛋" not in user_message:
        return

    # (6) 預設：呼叫 AI 回應函式
    if event.source.type == "group":
        if group_id and group_id in user_ai_choice:
            ai_model = user_ai_choice[group_id]
        else:
            ai_model = "deepseek-r1-distill-llama-70b"
    else:
        ai_model = user_ai_choice.get(user_id, "deepseek-r1-distill-llama-70b")
    
    gpt_reply = ask_groq(user_message, ai_model)
    try:
        reply_request = ReplyMessageRequest(
            replyToken=event.reply_token,
            messages=[TextMessage(text=gpt_reply)]
        )
        send_response(event, reply_request)
    except Exception as e:
        print(f"❌ LINE Reply Error: {e}")

# AudioMessage Handler
@handler.add(MessageEvent, message=AudioMessageContent)
def handle_audio_message(event):
    user_id = event.source.user_id
    group_id = event.source.group_id if event.source.type == "group" else None
    reply_token = event.reply_token
    audio_id = event.message.id

    print(f"📢 [DEBUG] 收到語音訊息, ID: {audio_id}")
    audio_url = f"https://api-data.line.me/v2/bot/message/{audio_id}/content"
    headers = {"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}

    try:
        # 下載語音檔案
        response = requests.get(audio_url, headers=headers, stream=True)
        if response.status_code == 200:
            audio_path = f"/tmp/{audio_id}.m4a"
            with open(audio_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=1024):
                    f.write(chunk)
            print(f"📢 [DEBUG] 語音檔案已儲存: {audio_path}")

            # 呼叫轉錄及後續回覆（同步完成）
            transcribed_text, ai_response = transcribe_and_respond_with_gpt(audio_path)
            if not transcribed_text:
                # 如果轉錄失敗，立即回覆失敗訊息
                reply_request = ReplyMessageRequest(
                    replyToken=reply_token,
                    messages=[TextMessage(text="❌ 語音辨識失敗，請再試一次！")]
                )
                messaging_api.reply_message(reply_request)
                return

            print(f"📢 [DEBUG] Whisper 轉錄結果: {transcribed_text}")

            # 準備回覆訊息列表（全部用 reply_message 一次性回覆）
            messages = []

            # 回覆轉錄內容
            messages.append(TextMessage(text=f"🎙️ 轉錄內容：{transcribed_text}"))

            # 檢查是否有特殊指令
            if "狗蛋生成" in transcribed_text:
                prompt = transcribed_text.split("狗蛋生成", 1)[1].strip()
                if not prompt:
                    prompt = "一隻可愛的小狗"
                print(f"📢 [DEBUG] 圖片生成 prompt: {prompt}")
                # 傳入 reply_token 而非 target_id
                handle_generate_image_command(event.reply_token, prompt, messaging_api)
                return


            if "狗蛋" in transcribed_text and "情勒" in transcribed_text:
                # 如果包含「狗蛋情勒」指令，回覆隨機訊息（模擬回覆）
                random_msg = random.choice([
                    "🥱你看我有想告訴你嗎？",
                    "😏我知道你在想什麼！",
                    "🤔你確定嗎？",
                    "😎好啦，不理你了！"
                ])
                messages.append(TextMessage(text=random_msg))
            elif event.source.type == "group" and "狗蛋" not in transcribed_text:
                print("群組語音訊息未明確呼喚 '狗蛋'，不進行ai回覆。")
                reply_request = ReplyMessageRequest(
                    replyToken=reply_token,
                    messages=messages
                )
                messaging_api.reply_message(reply_request)
                return
            else:
                # 預設情況下回覆 AI 回應
                messages.append(TextMessage(text=ai_response))

            # 使用 reply_message 一次性回覆所有訊息
            reply_request = ReplyMessageRequest(
                replyToken=reply_token,
                messages=messages
            )
            messaging_api.reply_message(reply_request)
        else:
            print(f"❌ [ERROR] 無法下載語音訊息, API 狀態碼: {response.status_code}")
            reply_request = ReplyMessageRequest(
                replyToken=reply_token,
                messages=[TextMessage(text="❌ 下載語音檔案失敗")]
            )
            messaging_api.reply_message(reply_request)
    except Exception as e:
        print(f"❌ [ERROR] 處理語音時發生錯誤: {e}")
        reply_request = ReplyMessageRequest(
            replyToken=reply_token,
            messages=[TextMessage(text="❌ 語音處理發生錯誤，請稍後再試！")]
        )
        messaging_api.reply_message(reply_request)

# Transcribe Function
def transcribe_and_respond_with_gpt(audio_path):
    """使用 GPT-4o Mini 進行語音轉文字並生成回應"""
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    with open(audio_path, "rb") as audio_file:
        files = {
            "file": (audio_path, audio_file, "audio/m4a"),
            "model": (None, "whisper-1"),
            "language": (None, "zh")
        }
        try:
            response = requests.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers=headers,
                files=files
            )
            if response.status_code == 200:
                result = response.json()
                transcribed_text = result.get("text", "").strip()
                print(f"📢 [DEBUG] Whisper 轉錄結果: {transcribed_text}")
                if not transcribed_text:
                    return None, "❌ 語音內容過短，無法辨識"

                # 直接使用 openai.ChatCompletion.create() 來呼叫 API
                completion = openai.ChatCompletion.create(
                    model="gpt-4o",  # 此處請確認您有權限使用該模型，若有需要可改為其他模型（例如 "gpt-3.5-turbo"）
                    messages=[
                        {"role": "system", "content": "你是一個名叫狗蛋的智能助手，請使用繁體中文回答。"},
                        {"role": "user", "content": transcribed_text}
                    ]
                )
                ai_response = completion.choices[0].message.content.strip()
                return transcribed_text, ai_response
            else:
                print(f"❌ [ERROR] Whisper API 回應錯誤: {response.text}")
                return None, "❌ 語音辨識失敗，請稍後再試"
        except Exception as e:
            print(f"❌ [ERROR] 語音轉文字 API 失敗: {e}")
            return None, "❌ 伺服器錯誤，請稍後再試"

# Post Handler
@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    group_id = event.source.group_id if event.source.type == "group" else None
    data = event.postback.data

    model_map = {
        "model_gpt4o": "GPT-4o",
        "model_gpt4o_mini": "GPT_4o_Mini",
        "model_deepseek": "deepseek-r1-distill-llama-70b",
        "model_llama3": "llama3-8b-8192",
    }
    if data in model_map:
        if group_id:
            user_ai_choice[group_id] = model_map[data]
        else:
            user_ai_choice[user_id] = model_map[data]
        print(f"📢 [DEBUG] {user_id if not group_id else group_id} 選擇模型: {model_map[data]}")
        reply_req = ReplyMessageRequest(
            replyToken=event.reply_token,
            messages=[TextMessage(text=f"已選擇語言模型: {model_map[data]}！\n\n🔄 輸入「換模型」可重新選擇")]
        )
        messaging_api.reply_message(reply_req)
        return

    reply_req = ReplyMessageRequest(
        replyToken=event.reply_token,
        messages=[TextMessage(text="未知選擇，請重試。")]
    )
    messaging_api.reply_message(reply_req)

def send_ai_selection_menu(reply_token, target=None, use_push=False):
    """發送 AI 選擇選單"""
    flex_contents_json = {
        "type": "carousel",
        "contents": [
            {
                "type": "bubble",
                "hero": {
                    "type": "image",
                    "url": f"{BASE_URL}/static/openai.png",
                    "size": "md"
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "justifyContent": "center",
                    "contents": [
                        {"type": "text", "text": "輕量強大-支援語音輸入", "weight": "bold", "size": "xl", "align": "center"},
                        {"type": "button", "style": "primary", "action": {"type": "postback", "label": "GPT-4o Mini", "data": "model_gpt4o_mini"}}
                    ]
                }
            },
            {
                "type": "bubble",
                "hero": {
                    "type": "image",
                    "url": f"{BASE_URL}/static/deepseek.png",
                    "size": "md"
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "justifyContent": "center",
                    "contents": [
                        {"type": "text", "text": "語意檢索強", "weight": "bold", "size": "xl", "align": "center"},
                        {"type": "button", "style": "primary", "action": {"type": "postback", "label": "Deepseek-R1", "data": "model_deepseek"}}
                    ]
                }
            },
            {
                "type": "bubble",
                "hero": {
                    "type": "image",
                    "url": f"{BASE_URL}/static/meta.jpg",
                    "size": "md"
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "justifyContent": "center",
                    "contents": [
                        {"type": "text", "text": "長文本適配", "weight": "bold", "size": "xl", "align": "center"},
                        {"type": "button", "style": "primary", "action": {"type": "postback", "label": "LLama3-8b", "data": "model_llama3"}}
                    ]
                }
            },
            {
                "type": "bubble",
                "hero": {
                    "type": "image",
                    "url": f"{BASE_URL}/static/giticon.png",  
                    "size": "md",
                    "aspectRatio": "1:1",
                    "aspectMode": "fit"
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "justifyContent": "center",
                    "contents": [
                        {"type": "text", "text": "高登基地", "weight": "bold", "size": "xl", "align": "center"},
                        {"type": "button", "style": "primary", "action": {"type": "uri", "label": "開啟基地", "uri": "https://gordonsay.github.io/gordonwu/personalpage/index_personal.html"}}
                    ]
                }
            }
        ]
    }

    try:
        # 將 flex JSON 轉為字串，再解析成 FlexContainer
        flex_json_str = json.dumps(flex_contents_json)
        flex_contents = FlexContainer.from_json(flex_json_str)
        flex_message = FlexMessage(
            alt_text="請選擇 AI 模型",
            contents=flex_contents
        )
        reply_request = ReplyMessageRequest(
            replyToken=reply_token,
            messages=[
                TextMessage(text="你好，我是狗蛋🐶 ！\n請選擇 AI 模型後發問。"),
                flex_message
            ]
        )
        if use_push and target:
            push_request = PushMessageRequest(
                to=target,
                messages=reply_request.messages
            )
            messaging_api.push_message(push_request)
        else:
            messaging_api.reply_message(reply_request)
    except Exception as e:
        print(f"❌ FlexMessage Error: {e}")

def ask_groq(user_message, model, retries=3, backoff_factor=1.0):
    """
    根據選擇的模型執行不同的 API：
      - 如果 model 為 "gpt-4o" 或 "gpt_4o_mini"，則呼叫 OpenAI API（原有邏輯）
      - 如果 model 為 "gpt-translation"，則使用翻譯模式，轉換為有效模型（例如 "gpt-3.5-turbo"）並使用翻譯 prompt
      - 否則使用 Groq API，並加入重試機制避免連線錯誤。
    """
    print(f"[ask_groq] 模型參數: {model}")

    for i in range(retries):
        try:
            if model.lower() in ["gpt-4o", "gpt_4o_mini"]:
                # OpenAI GPT-4o Mini
                openai_client = openai.ChatCompletion.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "user", "content": "你是一個名叫狗蛋的助手，盡量只使用繁體中文精簡跟朋友的語氣回答, 約莫50字內，限制不超過80字，除非當請求為翻譯時, 全部內容都需要完成翻譯不殘留原語言。"},
                        {"role": "user", "content": user_message}
                    ]
                )
                print(f"📢 [DEBUG] OpenAI API 回應: {openai_client}")
                return openai_client.choices[0].message.content.strip()

            elif model.lower() == "gpt-translation":
                # OpenAI 翻譯模式
                effective_model = "gpt-3.5-turbo"
                print(f"📢 [DEBUG] 呼叫 OpenAI API (翻譯模式)，使用模型: {effective_model}")
                response = openai.ChatCompletion.create(
                    model=effective_model,
                    messages=[
                        {"role": "system", "content": "你是一位專業翻譯專家，請根據使用者的需求精準且自然地翻譯以下內容。當請求為翻譯時, 全部內容一定都要完成翻譯不殘留原語言"},
                        {"role": "user", "content": user_message}
                    ]
                )
                return response.choices[0].message.content.strip()

            else:
                # Groq API，加入重試機制
                chat_completion = client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": "你是一個名叫狗蛋的助手，跟使用者是朋友關係, 盡量只使用繁體中文方式進行回答, 約莫50字內，限制不超過80字, 除非當請求為翻譯時, 全部內容都需要完成翻譯不殘留原語言。"},
                        {"role": "user", "content": user_message},
                    ],
                    model=model.lower(),
                )
                if not chat_completion.choices:
                    return "❌ 狗蛋無法回應，請稍後再試。"

                content = chat_completion.choices[0].message.content.strip()
                content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
                return content

        except requests.exceptions.RequestException as e:
            print(f"❌ API 連線失敗 (第 {i+1} 次)：{e}")
            time.sleep(backoff_factor * (2 ** i))  # 指數退避 (1s, 2s, 4s)

        except Exception as e:
            print(f"❌ AI API 呼叫錯誤: {e}")
            return "❌ 狗蛋伺服器錯誤，請稍後再試。"

    return "❌ 無法連線至 AI 服務，請稍後再試。"

def random_reply(reply_token, target, messaging_api):

    reply_messages = [
    "😏 哇，你終於想起家裡還有我這號人物了？",
    "🤔 小時候那麼乖，怎麼長大了反而學壞了？",
    "🙄 這麼多親戚，怎麼只有我記得幫忙？",
    "😎 你長大了嘛，什麼事都不用家人操心了，對吧？",
    "🥱 家裡是你旅館嗎？回來就吃飯，吃完就走？",
    "😂 現在會頂嘴了，長大了不起了是不是？",
    "😌 我們這輩子就這樣吧，下輩子不欠你的了。",
    "🤥 你說什麼都對，反正長輩講話都沒人聽啦。",
    "😇 嗯，你的道理聽起來很棒，但還是要聽我的。",
    "😏 這次考不好沒關係，反正你習慣了。",
    "🙄 每次說幫忙都說在忙，那你的忙是什麼時候結束？",
    "🥲 哦？家裡不是你的避風港嗎？怎麼一出事就消失？",
    "😌 反正我都是最閒的，你們才是最忙的嘛。",
    "😎 家裡的事跟你無關？行啊，以後財產分配也不關你的事。",
    "😒 啊～小時候那麼乖，怎麼現在只會氣人？",
    "🥱 沒事，你開心就好，家裡怎麼樣都不重要對吧？",
    "😏 你長大了，學會自己做決定了，出事可別找家裡哦。",
    "🙃 哇，難得見到你，你今天是客人還是家人？",
    "😇 你還記得家裡住哪嗎？怕你迷路呢。",
    "😌 好啦好啦，家裡的事你不用管，反正你最忙最累了。",
    "😏 哇，你終於有空理我了？",
    "🤔 你這麼忙，連回個訊息的時間都沒有嗎？",
    "😂 哦，你現在開始有標準了？當初不是什麼都可以？",
    "😇 哇，你的愛情觀好偉大喔，我配不上你呢。",
    "🙄 又在講大道理？還是說你根本沒打算解決問題？",
    "😎 我知道啊，你很特別，特別會讓人心累。",
    "🥱 你的承諾比天氣預報還不準呢。",
    "😏 你說你沒變？哦，那是我自己長大了啦。",
    "😂 你的愛是限量供應的嗎？怎麼輪到我時就沒了？",
    "😌 我們的關係就像天氣，時好時壞，全看你的心情。",
    "🙃 哇，這次冷戰比上次撐得更久，進步了呢！",
    "🥱 你每次都這樣，然後期待我當沒事？",
    "😇 哦，所以現在是我錯了？好啦，我認錯，滿意了吧？",
    "😏 你對別人都很好，對我特別不一樣呢，真特別。",
    "😂 你的道歉就像廣告，重複很多次但沒什麼用。",
    "🙄 哦，你現在才發現我是個不錯的人？晚了呢～",
    "😎 你說你不會再這樣？好啊，這是第幾次了呢？",
    "😌 你這麼愛自由，談什麼戀愛啊？去當風吧。",
    "😂 你說我們之間沒問題？對啊，問題都是我的。",
    "😇 嗯，分手後你過得很好，謝謝你讓我見識什麼叫成長。",
    "😏 哇，你的貢獻好大喔，真的沒有你不行呢！",
    "🤔 這麼簡單的事都搞不定，真的沒問題嗎？",
    "🙄 哦，所以這次的問題還是我的錯？好喔～",
    "😂 哇，你好忙啊，忙著讓別人幫你做事？",
    "😇 這種工作強度你都撐不住，那還是別做了吧？",
    "😏 哦，原來拖延時間也是你的專業技能之一啊？",
    "🥱 這次又是什麼理由？等一下要不要再編一個？",
    "😎 你的 KPI 是擺爛吧？怎麼還沒達標？",
    "😂 我以為你是來工作的，沒想到是來度假的。",
    "😇 你這個決定很有創意呢，特別容易出事的那種。",
    "🙄 這麼簡單的事都要問？你的腦子是裝飾品嗎？",
    "😏 你要的東西「剛剛」才發給你，剛剛是三天前。",
    "🥱 你的效率真讓人感動，感動到想哭。",
    "😌 你是來這裡解決問題的，還是來製造問題的？",
    "😂 哇，你的「馬上」和我的「馬上」果然不是同一個時區的。",
    "😎 你的領悟能力真的很獨特，特別慢。",
    "🙄 哦，現在是我的問題了？好啊，我背鍋習慣了。",
    "😏 你這麼會找藉口，不去當小說家真的可惜了。",
    "🥱 你真的不怕工作做不完嗎？還是你根本不打算做？",
    "😂 哇，你的職場生存技能是什麼？推卸責任嗎？"
    ]
    chosen_message = random.choice(reply_messages)
    reply_request = ReplyMessageRequest(
        replyToken=reply_token,
        messages=[TextMessage(text=chosen_message)]
    )
    if reply_token == "DUMMY":
        push_request = PushMessageRequest(
            to=target,
            messages=[TextMessage(text=chosen_message)]
        )
        messaging_api.push_message(push_request)
    else:
        messaging_api.reply_message(reply_request)

def generate_image_with_openai(prompt):
    """
    使用 OpenAI 圖像生成 API 生成圖片，返回圖片 URL。
    參數:
      prompt: 圖像生成提示文字
    """
    try:
        response = openai.Image.create(
            prompt=f"{prompt} 請根據上述描述生成圖片。如果描述涉及人物，以可愛卡通風格呈現, 要求面部比例正確，不出現扭曲、畸形或額外肢體，且圖像需高解析度且細節豐富；如果描述涉及事件且未指定風格，請以可愛卡通風格呈現；如果描述涉及物品，請生成清晰且精美的物品圖像，同時避免出現讓人覺得噁心或反胃的效果。",
            n=1,
            size="512x512"
        )
        data = response.get("data", [])
        if not data or len(data) == 0:
            print("❌ 生成圖片時沒有回傳任何資料")
            return None
        image_url = data[0].get("url")
        print(f"生成的圖片 URL：{image_url}")
        return image_url
    except Exception as e:
        print(f"❌ 生成圖像錯誤: {e}")
        return None

def async_generate_and_send_image(target_id, prompt, messaging_api):
    image_url = generate_image_with_openai(prompt)
    if image_url:
        push_request = PushMessageRequest(
            to=target_id,
            messages=[ImageMessage(original_content_url=image_url, preview_image_url=image_url)]
        )
        messaging_api.push_message(push_request)
    else:
        push_request = PushMessageRequest(
            to=target_id,
            messages=[TextMessage(text="❌ 圖片生成失敗，請稍後再試！")]
        )
        messaging_api.push_message(push_request)

def handle_generate_image_command(reply_token, prompt, messaging_api):
    """
    呼叫圖片生成 API 並使用 reply_message 一次性回覆所有訊息。
    注意：此流程必須在 reply token 有效期限內完成（約 60 秒）。
    """
    messages = []

    # 同步呼叫 OpenAI 圖像生成 API
    image_url = generate_image_with_openai(prompt)
    if image_url:
        messages.append(ImageMessage(original_content_url=image_url, preview_image_url=image_url))
        messages.append(TextMessage(text="生成完成, 你瞧瞧🐧"))
    else:
        messages.append(TextMessage(text="❌ 圖片生成失敗，請稍後再試！"))

    # 建立並發送 ReplyMessageRequest（只使用 reply_message）
    reply_request = ReplyMessageRequest(
        replyToken=reply_token,  # 這裡一定要傳入正確的 reply token
        messages=messages
    )
    try:
        messaging_api.reply_message(reply_request)
        print("成功使用 reply_message 回覆圖片生成結果")
    except Exception as e:
        print(f"❌ 發送圖片回覆時出錯: {e}")

def summarize_with_openai(search_results, query):
    """使用 OpenAI API 進行摘要"""
    if not search_results:
        print("❌ [DEBUG] 沒有搜尋結果，無法摘要！")
        return "找不到相關資料。"

    formatted_results = "\n".join(search_results)

    print(f"📢 [DEBUG] 傳送給 OpenAI 的內容:\n{formatted_results}")

    prompt = f"""
    使用者查詢: {query}

    以下是 Google 搜尋結果的標題與連結：
    {formatted_results}

    根據這些結果提供簡單明瞭的摘要（100 字內）。
    **請忽略新聞網站首頁或過期新聞（如 2017 回顧新聞），僅總結最新的有效內容**。
    **若資料多為天氣內容, 請確認日期符合後簡述推論天氣可能有什麼變化**。
    **若資料多為財金股市內容, 請簡述在這些資料內可以知道什麼趨勢**
    **若資料多娛樂八卦內容, 請簡述在這些資料內可以猜測有什麼事情發生了**
    """

    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": "你是一個智慧助理，依照這些資料, 條列總結跟附上連結。"},
                  {"role": "user", "content": prompt}]
    )

    reply_text = response["choices"][0]["message"]["content"].strip()

    print(f"📢 [DEBUG] OpenAI 回應: {reply_text}")

    return reply_text

def google_search(query):
    """使用 Google Custom Search API 進行搜尋"""
    url = f"https://www.googleapis.com/customsearch/v1?q={query}&key={GOOGLE_SEARCH_KEY}&cx={GOOGLE_CX}"
    response = requests.get(url)

    print(f"📢 [DEBUG] Google 搜尋 API 回應: {response.status_code}")
    print(f"📢 [DEBUG] Google API 回應內容: {response.text}")

    if response.status_code != 200:
        return None

    results = response.json()
    search_results = []
    
    if "items" in results:
        for item in results["items"][:5]:  # 取前 5 筆搜尋結果
            search_results.append(f"{item['title']} - {item['link']}")

    print(f"📢 [DEBUG] Google 搜尋結果: {search_results}")

    return search_results if search_results else None

def search_person_info(name):
    """使用 AI 生成人物簡介，並搭配 Google 圖片搜尋"""
    # 透過 AI 生成簡單描述
    prompt = f"請用簡單的方式介紹 {name} 是誰，並以 3-4 句話概述。"
    response_text = ask_groq(prompt, "deepseek-r1-distill-llama-70b")  # 調用 AI 來回答

    # 進行 Google 圖片搜尋
    google_url = f"https://www.google.com/search?q={name}&tbm=isch"
    headers = {"User-Agent": "Mozilla/5.0"}
    google_response = requests.get(google_url, headers=headers)

    if google_response.status_code == 200:
        soup = BeautifulSoup(google_response.text, "html.parser")
        images = soup.find_all("img")
        image_url = images[1]["src"] if len(images) > 1 else None  # 選擇第一張圖片
    else:
        image_url = None

    return response_text, image_url

def create_flex_message(text, image_url):
    if not image_url or not image_url.startswith("http"):
        return TextMessage(text="找不到適合的圖片，請嘗試其他關鍵字。")

    flex_content = {
        "type": "bubble",
        "hero": {
            "type": "image",
            "url": image_url,
            "size": "xl",
            "aspectRatio": "1:1",
            "aspectMode": "fit",
            "action": {  # ✅ 新增點擊圖片後放大
                "type": "uri",
                "uri": image_url
            }
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": text,
                    "wrap": True,
                    "weight": "bold",
                    "size": "md"
                }
            ]
        }
    }

    flex_json_str = json.dumps(flex_content)
    flex_contents = FlexContainer.from_json(flex_json_str)
    return FlexMessage(alt_text=text, contents=flex_contents)

def search_google_image(query):
    """搜尋 Google 圖片並返回第一張有效的圖片 URL"""
    google_url = f"https://www.google.com/search?q={query}&tbm=isch"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        response = requests.get(google_url, headers=headers)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            images = soup.find_all("img")

            for img in images[1:]:  # 跳過第一張（通常是 Google 標誌）
                image_url = img.get("src", "")
                if image_url.startswith("http"):  # 只回傳有效的 HTTP(S) 圖片
                    return image_url
    except Exception as e:
        print(f"❌ Google 搜圖錯誤: {e}")

    return None  # 找不到圖片時回傳 None

def search_spotify_song(song_name):
    """ 透過 Spotify API 搜尋歌曲並回傳預覽 URL 與歌曲連結 """
    try:
        results = sp.search(q=song_name, limit=1, type='track')
        if not results["tracks"]["items"]:
            return None  # 沒找到歌曲
        
        track = results["tracks"]["items"][0]
        return {
            "name": track["name"],
            "preview_url": track["preview_url"],  # 30 秒的音頻預覽
            "song_url": track["external_urls"]["spotify"]  # Spotify 播放連結
        }
    except Exception as e:
        print(f"❌ [ERROR] Spotify API 呼叫失敗: {e}")
        return None

def download_and_host_audio(preview_url, filename="song_preview"):
    """ 下載 Spotify 的 preview.mp3，轉換為 m4a，並存到 Flask 的 /static/ 目錄 """
    tmp_mp3 = f"/tmp/{filename}.mp3"  # 暫存 mp3
    tmp_m4a = f"/tmp/{filename}.m4a"  # 暫存 m4a
    static_m4a = f"./static/{filename}.m4a"  # 最終存放於 Flask 可訪問的 /static/
    hosted_url = f"{BASE_URL}/static/{filename}.m4a"  # 你的 Flask 伺服器網址

    try:
        response = requests.get(preview_url, stream=True)
        if response.status_code == 200:
            # 下載 mp3
            with open(tmp_mp3, "wb") as f:
                for chunk in response.iter_content(chunk_size=1024):
                    f.write(chunk)

            # 轉換為 m4a
            audio = AudioSegment.from_mp3(tmp_mp3)
            audio.export(tmp_m4a, format="ipod")  # "ipod" 會輸出 .m4a 格式
            
            # 移動檔案到 Flask 的 /static/ 目錄
            shutil.move(tmp_m4a, static_m4a)

            print(f"✅ 音檔轉換成功: {static_m4a}")
            return hosted_url
        else:
            print("❌ 下載失敗，狀態碼:", response.status_code)
            return None
    except Exception as e:
        print(f"❌ 下載或轉換失敗: {e}")
        return None

def get_weather_weatherapi(city):
    """ 使用 OpenWeather API 查詢天氣 """
    API_KEY = OPENWEATHER_API_KEY
    try:
        # 確保 city 是 OpenWeather 可接受的名稱
        city = CITY_MAPPING.get(city, city)

        url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={API_KEY}&units=metric&lang=zh_tw"
        print(f"📢 [DEBUG] 呼叫 API: {url}")  # 確保 city 轉換正確
        
        response = requests.get(url)
        data = response.json()

        if data.get("cod") != 200:
            print(f"❌ OpenWeather API 錯誤: {data}")  # Debug API 回應
            return "❌ 無法取得天氣資訊，請確認城市名稱是否正確"

        # 提取需要的天氣資訊
        temp = data["main"]["temp"]
        weather_desc = data["weather"][0]["description"]
        wind_speed = data["wind"]["speed"]
        humidity = data["main"]["humidity"]
        # 建立天氣描述
        weather_text = (
                f"🌡 溫度：{temp}°C\n"
                f"💧 濕度：{humidity}%\n"
                f"💨 風速：{wind_speed} m/s\n"
                f"🌤 天氣狀況：{weather_desc}"
        )
        # 讓 AI 進行天氣分析
        ai_analysis = analyze_weather_with_ai(city, temp, humidity, weather_desc, wind_speed)

        return f"🌍 {city} 即時天氣預報：\n{weather_text}\n\n🧑‍🔬 狗蛋關心您：\n{ai_analysis}"


    except requests.exceptions.RequestException as e:
        return f"❌ 取得天氣資料失敗: {e}"

def get_weather_forecast(city):
    """ 使用 OpenWeather API 查詢未來 3 天天氣趨勢 """
    # 確保 city 是 OpenWeather 可接受的名稱
    city = CITY_MAPPING.get(city, city)
    url = f"https://api.openweathermap.org/data/2.5/forecast?q={city}&appid={OPENWEATHER_API_KEY}&units=metric&lang=zh_tw"
    

    try:
        response = requests.get(url)
        data = response.json()
        print("🔍 狀態碼:", response.status_code)
        print("🔍 回應內容:", response.text)

        if data.get("cod") != "200":
            print(f"❌ OpenWeather API 錯誤: {data}")
            return "❌ 無法取得天氣預報，請確認城市名稱是否正確"

        daily_forecast = {}

        # 解析 5 天的 3 小時預測，整理成每日的天氣趨勢
        for forecast in data["list"]:
            date = forecast["dt_txt"].split(" ")[0]  # 只取日期
            temp = forecast["main"]["temp"]
            weather_desc = forecast["weather"][0]["description"]
            wind_speed = forecast["wind"]["speed"]
            humidity = forecast["main"]["humidity"]

            if date not in daily_forecast:
                daily_forecast[date] = {
                    "temp_min": temp,
                    "temp_max": temp,
                    "humidity": [],
                    "wind_speed": [],
                    "weather_desc": weather_desc
                }
            else:
                daily_forecast[date]["temp_min"] = min(daily_forecast[date]["temp_min"], temp)
                daily_forecast[date]["temp_max"] = max(daily_forecast[date]["temp_max"], temp)
                daily_forecast[date]["humidity"].append(humidity)
                daily_forecast[date]["wind_speed"].append(wind_speed)

        # 格式化輸出未來 3 天預測
        forecast_text = f"🌍 {city} 未來 3 天天氣趨勢：\n"
        today = datetime.date.today()
        count = 0

        for date, info in daily_forecast.items():
            if count >= 3:
                break
            avg_humidity = sum(info["humidity"]) // len(info["humidity"]) if info["humidity"] else 0
            avg_wind_speed = sum(info["wind_speed"]) / len(info["wind_speed"]) if info["wind_speed"] else 0
            forecast_text += (
                f"\n📅 {date}:\n"
                f"🌡 溫度: {info['temp_min']}°C ~ {info['temp_max']}°C\n"
                f"💧 濕度: {avg_humidity}%\n"
                f"💨 風速: {avg_wind_speed:.1f} m/s\n"
                f"🌤 天氣: {info['weather_desc']}\n"
            )
            count += 1

        # 讓 AI 進行天氣分析
        ai_analysis = analyze_weather_with_ai(city, temp, humidity, weather_desc, wind_speed)

        return f"{forecast_text}\n\n🧑‍🔬 狗蛋關心您：\n{ai_analysis}"

    except requests.exceptions.RequestException as e:
        return f"❌ 取得天氣資料失敗: {e}"

def analyze_weather_with_ai(city, temp, humidity, weather_desc, wind_speed):
    """ 使用 OpenAI 進行天氣分析，提供穿搭 & 注意事項 """

    prompt = f"""
    目前 {city} 的天氣條件如下：
    - 溫度：{temp}°C
    - 濕度：{humidity}%
    - 天氣狀況：{weather_desc}
    - 風速：{wind_speed} m/s

    根據這些數據：
    1. 給出適合的穿搭建議（例如：冷天穿什麼、熱天注意什麼）。
    2. 提供出門注意事項（如可能下雨、空氣品質不好、強風等）。
    3. 回應時請使用繁體中文，字數控制在 50 字內，並用口語化的方式回答。
    """

    # Groq API 邏輯 (保持不變)
    chat_completion = client.chat.completions.create(
        messages=[
                    {"role": "system", "content": "你是一個名叫狗蛋的助手，跟使用者是朋友關係, 盡量只使用繁體中文方式進行幽默回答, 約莫20字內，限制不超過50字"},
                    {"role": "user", "content": prompt},
                ],
        model="deepseek-r1-distill-llama-70b",)
    if not chat_completion.choices:
        return "❌ 狗蛋無法回應，請稍後再試。"
    content = chat_completion.choices[0].message.content.strip()
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    return content

def get_video_data(search_query):
    url = f"https://jable.tv/search/{search_query}/?sort_by=post_date"

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,  # ✅ 關閉 headless=False，提升速度
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = browser.new_context()
        page = context.new_page()

        # ✅ 避免被封鎖，使用 Stealth
        stealth_sync(page)

        # ✅ 隨機 User-Agent
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 15_2 like Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Mobile Safari/537.36",
        ]
        page.set_extra_http_headers({"User-Agent": random.choice(user_agents)})

        # ✅ **減少 `timeout` 時間，提升速度**
        page.goto(url, timeout=10000)  # **減少超時時間**
        page.wait_for_selector(".video-img-box", timeout=3000)  # **減少等待時間**
        
        # ✅ **直接解析 HTML，不用 `set_content()`**
        html = page.content()

        # **確保 HTML 內容不是 Cloudflare 防護頁**
        if "Just a moment..." in html or "challenge-error-text" in html:
            print("❌ Cloudflare 防護阻擋，無法獲取內容")
            browser.close()
            return []

        # ✅ **直接解析 HTML**
        videos = page.query_selector_all('.video-img-box')
        video_list = []

        for video in videos[:2]:  # **只取前 2 部影片**
            title_elem, img_elem = video.query_selector('.title a'), video.query_selector('.img-box img')

            title = title_elem.text_content().strip() if title_elem else "N/A"
            link = title_elem.get_attribute('href') if title_elem else "N/A"
            thumbnail = img_elem.get_attribute('data-src') or img_elem.get_attribute('src') if img_elem else "N/A"

            video_list.append({"title": title, "link": link, "thumbnail": thumbnail})

        # ✅ **確保瀏覽器完全關閉**
        browser.close()
        return video_list

def get_video_data_hotest():
    url = "https://jable.tv/hot/"
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = browser.new_context()
        page = context.new_page()

        # ✅ 避免被封鎖，使用 Stealth
        stealth_sync(page)

        # ✅ 隨機 User-Agent
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 15_2 like Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Mobile Safari/537.36",
        ]
        page.set_extra_http_headers({"User-Agent": random.choice(user_agents)})

        # ✅ **降低等待時間**
        page.goto(url, timeout=20000)  # **減少超時時間**
        page.wait_for_selector(".video-img-box", timeout=5000)  # **減少 selector 等待時間**

        # ✅ **直接解析 HTML，不用 set_content()**
        videos = page.query_selector_all('.video-img-box')

        video_list = []
        for video in videos[:3]:  # **取前三個影片**
            title_elem, img_elem = video.query_selector('.title a'), video.query_selector('.img-box img')

            title = title_elem.text_content().strip() if title_elem else "N/A"
            link = title_elem.get_attribute('href') if title_elem else "N/A"
            thumbnail = img_elem.get_attribute('data-src') or img_elem.get_attribute('src') if img_elem else "N/A"

            video_list.append({"title": title, "link": link, "thumbnail": thumbnail})

        # ✅ **減少記憶體佔用**
        browser.close()
        return video_list

def get_video_data_newest():
    url = "https://jable.tv/latest-updates/"
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = browser.new_context()
        page = context.new_page()

        # ✅ 避免被封鎖，使用 Stealth
        stealth_sync(page)

        # ✅ 隨機 User-Agent
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 15_2 like Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.99 Mobile Safari/537.36",
        ]
        page.set_extra_http_headers({"User-Agent": random.choice(user_agents)})

        # ✅ **降低等待時間**
        page.goto(url, timeout=20000)  # **減少超時時間**
        page.wait_for_selector(".video-img-box", timeout=5000)  # **減少 selector 等待時間**

        # ✅ **直接解析 HTML，不用 set_content()**
        videos = page.query_selector_all('.video-img-box')

        video_list = []
        for video in videos[:3]:  # **取前三個影片**
            title_elem, img_elem = video.query_selector('.title a'), video.query_selector('.img-box img')

            title = title_elem.text_content().strip() if title_elem else "N/A"
            link = title_elem.get_attribute('href') if title_elem else "N/A"
            thumbnail = img_elem.get_attribute('data-src') or img_elem.get_attribute('src') if img_elem else "N/A"

            video_list.append({"title": title, "link": link, "thumbnail": thumbnail})

        # ✅ **減少記憶體佔用**
        browser.close()
        return video_list


def create_flex_jable_message(videos):
    if not videos:
        return TextMessage(text="找不到相關影片，請嘗試其他關鍵字。")

    contents = []
    for video in videos:
        print(f"✅ [DEBUG] 準備加入影片: {video}")  # Debug 確認資料格式

        bubble = {
            "type": "bubble",
            "hero": {
                "type": "image",
                "url": video["thumbnail"],
                "size": "full",
                "aspectRatio": "16:9",
                "aspectMode": "cover",
                "action": {
                    "type": "uri",
                    "uri": video["link"]
                }
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": video["title"],
                        "weight": "bold",
                        "size": "md",
                        "wrap": True
                    }
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "action": {
                            "type": "uri",
                            "label": "觀看影片",
                            "uri": video["link"]
                        }
                    }
                ]
            }
        }
        contents.append(bubble)

    flex_message_content = {
        "type": "carousel",
        "contents": contents
    }

    # print(f"✅ [DEBUG] 最終 FlexMessage 結構: {json.dumps(flex_message_content, indent=2)}")  # Debug

    # ✅ **轉換為 JSON 字串，讓 `FlexContainer.from_json()` 可以解析**
    flex_json_str = json.dumps(flex_message_content)

    flex_contents = FlexContainer.from_json(flex_json_str)  # ✅ 解析 JSON 字串
    return FlexMessage(alt_text="搜尋結果", contents=flex_contents)


if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 5000))  # 使用 Render 提供的 PORT
    app.run(host="0.0.0.0", port=PORT)  # 移除 debug=True

