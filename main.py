import os, re, json, openai, random, time, requests
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
BASE_URL = "https://render-linebot-masp.onrender.com"


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
    """
    呼叫 LINE API，若遇到 429 錯誤則採取指數退避重試機制
    """
    for i in range(retries):
        try:
            return api_func(request_obj)
        except Exception as e:
            if "429" in str(e):
                wait_time = backoff_factor * (2 ** i)
                print(f"Rate limit encountered. Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                print(f"API call error: {e}")
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

    # # 先檢查是否有"停止翻譯"指令
    # if "停" in user_message and "翻譯" in user_message:
    #     if user_id in user_translation_config:
    #         user_translation_config[user_id]["enabled"] = False
    #     else:
    #         user_translation_config[user_id] = {"enabled": False, "method": "", "src": "", "tgt": ""}
    #     reply_request = ReplyMessageRequest(
    #         replyToken=event.reply_token,
    #         messages=[TextMessage(text="翻譯功能已停止。")]
    #     )
    #     messaging_api.reply_message(reply_request)
    #     return

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
            "5. 狗蛋情勒 狗蛋的超能力"
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
    
    # # (4-d) 「Translate」
    # if "我要" in user_message and "翻譯" in user_message:
    #     send_translation_menu(event.reply_token)
    #     send_source_language_menu(event.reply_token)
    #     send_target_language_menu(event.reply_token)
    #     return
    # # 如果使用者輸入格式 "翻譯語言: zh->en"，則解析並儲存設定，啟用翻譯
    # if user_message.startswith("翻譯語言:"):
    #     try:
    #         # 格式假設為 "翻譯語言: 源->目標"（例如 "翻譯語言: zh->en"）
    #         lang_setting = user_message.split(":", 1)[1].strip()
    #         src, tgt = lang_setting.split("->")
    #         src = src.strip()
    #         tgt = tgt.strip()
    #         if user_id not in user_translation_config:
    #             user_translation_config[user_id] = {}
    #         user_translation_config[user_id].update({"enabled": True, "source": src, "target": tgt})
    #         reply_text = f"翻譯設定已更新：{src} -> {tgt}"
    #     except Exception as e:
    #         reply_text = "翻譯設定格式錯誤，請使用格式：翻譯語言: zh->en"
    #     reply_request = ReplyMessageRequest(
    #         replyToken=event.reply_token,
    #         messages=[TextMessage(text=reply_text)]
    #     )
    #     messaging_api.reply_message(reply_request)
    #     return
    
    # # 檢查是否啟用了翻譯設定，若有則只進行翻譯並回覆翻譯結果，不執行 AI 回覆
    # if user_id in user_translation_config and user_translation_config[user_id].get("enabled"):
    #     config = user_translation_config[user_id]
    #     src_lang = config.get("src", "auto")  # 若未設定，可設為 "auto"
    #     tgt_lang = config.get("tgt", "en")    # 預設翻譯成英文
    #     # 封裝翻譯需求，這裡採用 ask_groq 的格式，model 傳入 "gpt-translation" 讓其使用翻譯專用分支
    #     prompt = f"請將下列文字從 {src_lang} 翻譯成 {tgt_lang}：\n{user_message}"
    #     translation = ask_groq(prompt, "gpt-translation")
    #     if translation:
    #         print(f"📢 [DEBUG] 翻譯結果：{translation}")
    #         reply_request = ReplyMessageRequest(
    #             replyToken=event.reply_token,
    #             messages=[TextMessage(text=f"翻譯結果：{translation}")]
    #         )
    #         # 如果 reply token 為 "DUMMY"，代表此事件來自語音轉錄流程，需用 push_message 發送
    #         if event.reply_token == "DUMMY":
    #             target_id = event.source.group_id if event.source.type == "group" else event.source.user_id
    #             push_request = PushMessageRequest(
    #                 to=target_id,
    #                 messages=reply_request.messages
    #             )
    #             messaging_api.push_message(push_request)
    #         else:
    #             messaging_api.reply_message(reply_request)
    #         return
    #     else:
    #         reply_request = ReplyMessageRequest(
    #             replyToken=event.reply_token,
    #             messages=[TextMessage(text="❌ 翻譯失敗，請稍後再試。")]
    #         )
    #         if event.reply_token == "DUMMY":
    #             target_id = event.source.group_id if event.source.type == "group" else event.source.user_id
    #             push_request = PushMessageRequest(
    #                 to=target_id,
    #                 messages=reply_request.messages
    #             )
    #             messaging_api.push_message(push_request)
    #         else:
    #             messaging_api.reply_message(reply_request)
    #         return

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

    if data in {"translate_gpt", "translate_google"}:
        if user_id not in user_translation_config:
            user_translation_config[user_id] = {"enabled": False, "method": "", "src": "", "tgt": ""}
        if data == "translate_gpt":
            user_translation_config[user_id]["method"] = "gpt"
            reply_text = "翻譯模型選擇：GPT"
        else:
            user_translation_config[user_id]["method"] = "google"
            reply_text = "翻譯模型選擇：Google"
        print(f"📢 [DEBUG] {user_id} 選擇翻譯方案: {user_translation_config[user_id]['method']}")
        reply_req = ReplyMessageRequest(
            replyToken=event.reply_token,
            messages=[TextMessage(text=reply_text)]
        )
        messaging_api.reply_message(reply_req)
        target = event.source.group_id if event.source.type == "group" else user_id
        send_source_language_menu("DUMMY", target=target, use_push=True)
        return

    if data.startswith("src_"):
        src_lang = data.split("_", 1)[1]
        if user_id not in user_translation_config:
            user_translation_config[user_id] = {"enabled": False, "method": "", "src": "", "tgt": ""}
        user_translation_config[user_id]["src"] = src_lang
        print(f"📢 [DEBUG] {user_id} 選擇來源語言: {src_lang}")
        reply_req = ReplyMessageRequest(
            replyToken=event.reply_token,
            messages=[TextMessage(text=f"來源語言已設定為 {src_lang}。\n請選擇翻譯目標語言：")]
        )
        messaging_api.reply_message(reply_req)
        target = event.source.group_id if event.source.type == "group" else user_id
        send_target_language_menu("DUMMY", target=target, use_push=True)
        return

    if data.startswith("tgt_"):
        tgt_lang = data.split("_", 1)[1]
        if user_id not in user_translation_config:
            user_translation_config[user_id] = {"enabled": False, "method": "", "src": "", "tgt": ""}
        user_translation_config[user_id]["tgt"] = tgt_lang
        user_translation_config[user_id]["enabled"] = True
        print(f"📢 [DEBUG] {user_id} 選擇目標語言: {tgt_lang}")
        reply_req = ReplyMessageRequest(
            replyToken=event.reply_token,
            messages=[TextMessage(text=f"翻譯設定完成：\n來源語言 {user_translation_config[user_id]['src']} -> 目標語言 {tgt_lang}\n請輸入欲翻譯內容:")]
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

def send_translation_menu(reply_token, target=None, use_push=False):
    """發送翻譯選擇選單，僅在輸入 '我要翻譯' 時出現"""
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
                        {"type": "text", "text": "精準但較緩慢", "weight": "bold", "size": "xl", "align": "center"}
                    ]
                },
                "footer": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {"type": "button", "action": {"type": "postback", "label": "選擇此方案", "data": "translate_gpt"}}
                    ]
                }
            },
            {
                "type": "bubble",
                "hero": {
                    "type": "image",
                    "url": f"{BASE_URL}/static/googletrans1.png",  # 請替換為實際圖片 URL
                    "size": "md"
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "justifyContent": "center",
                    "contents": [
                        {"type": "text", "text": "快速直覺", "weight": "bold", "size": "xl", "align": "center"}
                    ]
                },
                "footer": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {"type": "button", "action": {"type": "postback", "label": "選擇此方案", "data": "translate_google"}}
                    ]
                }
            }
        ]
    }

    try:
        flex_json_str = json.dumps(flex_contents_json)
        flex_contents = FlexContainer.from_json(flex_json_str)
        flex_message = FlexMessage(
            alt_text="請選擇翻譯方案",
            contents=flex_contents
        )
        reply_request = ReplyMessageRequest(
            replyToken=reply_token,
            messages=[
                TextMessage(text="請選擇翻譯方案："),
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
        print(f"❌ Translation FlexMessage Error: {e}")

def send_source_language_menu(reply_token, target=None, use_push=False):
    """
    發送翻譯來源語言選單，單一 bubble 內包含所有語言按鈕。
    語言選項：
      繁體中文：zh-TW
      簡體中文：zh-CN
      日文：ja
      英文：en
      韓文：ko
    """
    flex_contents_json = {
        "type": "bubble",
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "請選擇翻譯來源語言：",
                    "weight": "bold",
                    "size": "xl",
                    "align": "center"
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {
                            "type": "button",
                            "action": {
                                "type": "postback",
                                "label": "繁體中文",
                                "data": "src_zh-TW"
                            }
                        },
                        {
                            "type": "button",
                            "action": {
                                "type": "postback",
                                "label": "简体中文",
                                "data": "src_zh-CN"
                            }
                        }
                    ]
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {
                            "type": "button",
                            "action": {
                                "type": "postback",
                                "label": "日本語",
                                "data": "src_ja"
                            }
                        },
                        {
                            "type": "button",
                            "action": {
                                "type": "postback",
                                "label": "English",
                                "data": "src_en"
                            }
                        },
                        {
                            "type": "button",
                            "action": {
                                "type": "postback",
                                "label": "한국어",
                                "data": "src_ko"
                            }
                        }
                    ]
                }
            ]
        }
    }
    try:
        flex_json_str = json.dumps(flex_contents_json)
        flex_contents = FlexContainer.from_json(flex_json_str)
        flex_message = FlexMessage(
            alt_text="請選擇翻譯來源語言",
            contents=flex_contents
        )
        reply_request = ReplyMessageRequest(
            replyToken=reply_token,
            messages=[
                TextMessage(text="請選擇翻譯來源語言："),
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
        print(f"❌ Source Language FlexMessage Error: {e}")

def send_target_language_menu(reply_token, target=None, use_push=False):
    """
    發送翻譯目標語言選單，單一 bubble 內包含所有語言按鈕。
    語言選項：
      繁體中文：zh-TW
      簡體中文：zh-CN
      日文：ja
      英文：en
      韓文：ko
    """
    flex_contents_json = {
        "type": "bubble",
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "請選擇翻譯目標語言：",
                    "weight": "bold",
                    "size": "xl",
                    "align": "center"
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {
                            "type": "button",
                            "action": {
                                "type": "postback",
                                "label": "繁體中文",
                                "data": "tgt_zh-TW"
                            }
                        },
                        {
                            "type": "button",
                            "action": {
                                "type": "postback",
                                "label": "简体中文",
                                "data": "tgt_zh-CN"
                            }
                        }
                    ]
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {
                            "type": "button",
                            "action": {
                                "type": "postback",
                                "label": "日本語",
                                "data": "tgt_ja"
                            }
                        },
                        {
                            "type": "button",
                            "action": {
                                "type": "postback",
                                "label": "English",
                                "data": "tgt_en"
                            }
                        },
                        {
                            "type": "button",
                            "action": {
                                "type": "postback",
                                "label": "한국어",
                                "data": "tgt_ko"
                            }
                        }
                    ]
                }
            ]
        }
    }
    try:
        flex_json_str = json.dumps(flex_contents_json)
        flex_contents = FlexContainer.from_json(flex_json_str)
        flex_message = FlexMessage(
            alt_text="請選擇翻譯目標語言",
            contents=flex_contents
        )
        reply_request = ReplyMessageRequest(
            replyToken=reply_token,
            messages=[
                TextMessage(text="請選擇翻譯目標語言："),
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
        print(f"❌ Target Language FlexMessage Error: {e}")

def translate_with_gpt(text, src, tgt):
    """
    使用 OpenAI 的 GPT-3.5-turbo 進行翻譯，
    將輸入文字從 src 語言翻譯成 tgt 語言。

    參數:
      text: 要翻譯的文字
      src: 源語言代碼（例如 "zh-TW" 表示繁體中文、"zh-CN" 表示簡體中文、"ja" 表示日文、"en" 表示英文、"ko" 表示韓文）
      tgt: 目標語言代碼（例如 "en"、"zh-TW" 等）
    """
    prompt = f"請將下列文字從 {src} 翻譯成 {tgt}：\n{text}"
    try:
        # 注意：新版 OpenAI SDK 必須直接使用 openai.ChatCompletion.create()
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",  # 使用有效且您有權限使用的模型
            messages=[
                {"role": "system", "content": "你是一位專業的翻譯專家，請精準且自然地翻譯以下內容。"},
                {"role": "user", "content": prompt}
            ]
        )
        translation = response.choices[0].message.content.strip()
        return translation
    except Exception as e:
        print(f"❌ 翻譯錯誤: {e}")
        return None

def ask_groq(user_message, model):
    """
    根據選擇的模型執行不同的 API：
      - 如果 model 為 "gpt-4o" 或 "gpt_4o_mini"，則呼叫 OpenAI API（原有邏輯）
      - 如果 model 為 "gpt-translation"，則使用翻譯模式，轉換為有效模型（例如 "gpt-3.5-turbo"）並使用翻譯 prompt
      - 否則使用 Groq API
    """
    print(f"[ask_groq] 模型參數: {model}")
    try:
        if model.lower() in ["gpt-4o", "gpt_4o_mini"]:
            # (原有的 GPT-4o Mini 邏輯)
            openai_client = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "user", "content": "你是一個名叫狗蛋的助手，盡量只使用繁體中文精簡跟朋友的語氣的幽默回答, 約莫20字內，限制不超過50字，除非當請求為翻譯時, 全部內容都需要完成翻譯不殘留原語言。"},
                    {"role": "user", "content": user_message}
                ]
            )
            print(f"📢 [DEBUG] OpenAI API 回應: {openai_client}")
            return openai_client.choices[0].message.content.strip()

        elif model.lower() == "gpt-translation":
            # 對於翻譯任務，使用有效的模型（例如 gpt-3.5-turbo），並不強制回覆繁體中文
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
            # Groq API 邏輯 (保持不變)
            chat_completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "你是一個名叫狗蛋的助手，跟使用者是朋友關係, 盡量只使用繁體中文方式進行幽默回答, 約莫20字內，限制不超過50字, 除非當請求為翻譯時, 全部內容都需要完成翻譯不殘留原語言。"},
                    {"role": "user", "content": user_message},
                ],
                model=model.lower(),
            )
            if not chat_completion.choices:
                return "❌ 狗蛋無法回應，請稍後再試。"
            content = chat_completion.choices[0].message.content.strip()
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
            return content

    except Exception as e:
        print(f"❌ AI API 呼叫錯誤: {e}")
        return "❌ 狗蛋伺服器錯誤，請稍後再試。"

def random_reply(reply_token, target, messaging_api):

    reply_messages = [
        "🥱你看我有想告訴你嗎？",
        "😏真假, 怎那麼棒你阿",
        "🤔上次我有說過了, 下次還要說對吧",
        "😎年輕人要多忍耐 我也是這樣過來的",
        "你以前都不會這樣的🤷‍♂️",
        "我這是為了你好🤥"
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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # 使用 Render 提供的 PORT
    app.run(host="0.0.0.0", port=port, debug=False)  # 移除 debug=True
