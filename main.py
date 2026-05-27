import os
from fastapi import FastAPI, Request, HTTPException
from linebot import LineBotApi, WebhookHandler
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    PostbackEvent
)
from linebot.exceptions import InvalidSignatureError
from diagnosis import (
    Q_MBTI_TYPE, Q_FALLBACK_TEXT,
    q_mbti_exist, q_fallback, q2, q3, q4, q5, q6,
    parse_mbti, fallback_to_axes,
    calc_risk, calc_surplus,
    determine_type, build_result
)

app = FastAPI()
line_bot_api = LineBotApi(os.environ["LINE_CHANNEL_ACCESS_TOKEN"])
handler = WebhookHandler(os.environ["LINE_CHANNEL_SECRET"])

sessions = {}

def get_session(uid):
    if uid not in sessions:
        sessions[uid] = {"step": 0}
    return sessions[uid]

def reply_text(token, text):
    line_bot_api.reply_message(token, TextSendMessage(text=text))

def reply_buttons(token, template_msg):
    line_bot_api.reply_message(token, template_msg)

@app.get("/")
def health():
    return {"status": "ok"}

@app.get("/callback")
def callback_get():
    return {"status": "ok"}

@app.post("/callback")
async def callback(request: Request):
    signature = request.headers.get("X-Line-Signature", "")
    body = await request.body()
    try:
        handler.handle(body.decode(), signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400)
    return "OK"

# ── テキストメッセージ（診断スタート・MBTI入力のみ）──
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    uid = event.source.user_id
    text = event.message.text.strip()
    token = event.reply_token
    s = get_session(uid)

    # リセット
    if text in ["リセット", "restart", "もう一度"]:
        sessions[uid] = {"step": 0}
        reply_text(token, "診断をリセットしました！\n「診断スタート」と送ってください👋")
        return

    # 開始
    if s["step"] == 0:
        if any(k in text for k in ["スタート", "診断", "start", "Start"]):
            s["step"] = 1
            reply_buttons(token, q_mbti_exist())
        else:
            reply_text(token, "「診断スタート」と送ってください！\nあなたのお金タイプを診断します🔍")
        return

    # MBTI入力（テキストで受け取る）
    if s["step"] == 2:
        if "わからない" in text or len(text) < 2:
            s["step"] = 3
            reply_buttons(token, q_fallback())
        else:
            intuitive, judging = parse_mbti(text)
            s["intuitive"] = intuitive
            s["judging"] = judging
            s["step"] = 4
            reply_buttons(token, q2())
        return

    # それ以外のテキストは案内
    reply_text(token, "ボタンから選んで回答してください😊\nやり直す場合は「リセット」と送ってください。")

# ── ポストバック（ボタン選択）──
@handler.add(PostbackEvent)
def handle_postback(event):
    uid = event.source.user_id
    data = event.postback.data
    token = event.reply_token
    s = get_session(uid)

    key, val = data.split(":")

    # Q1：MBTI経験有無
    if key == "mbti_exist":
        if val == "A":
            s["step"] = 2
            reply_text(token, Q_MBTI_TYPE)
        else:
            s["step"] = 3
            reply_buttons(token, q_fallback())
        return

    # 補完質問
    if key == "fallback":
        intuitive, judging = fallback_to_axes(val)
        s["intuitive"] = intuitive
        s["judging"] = judging
        s["step"] = 4
        reply_buttons(token, q2())
        return

    # Q2
    if key == "q2":
        s["q2"] = val
        s["step"] = 5
        reply_buttons(token, q3())
        return

    # Q3
    if key == "q3":
        s["q3"] = val
        s["step"] = 6
        reply_buttons(token, q4())
        return

    # Q4
    if key == "q4":
        s["q4"] = val
        s["step"] = 7
        reply_buttons(token, q5())
        return

    # Q5
    if key == "q5":
        s["q5"] = val
        s["step"] = 8
        reply_buttons(token, q6())
        return

    # Q6：奨学金 → タイプ判定
    if key == "q6":
        has_loan = (val == "A")
        R = calc_risk(
            s.get("q2", "B"),
            s.get("q3", "B"),
            s.get("q4", "B")
        )
        surplus = calc_surplus(s.get("q5", "A"))
        type_id = determine_type(
            s.get("intuitive", False),
            s.get("judging", True),
            R, surplus
        )
        result = build_result(type_id, has_loan)
        s["step"] = 99
        reply_text(token, result)
        return
