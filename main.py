import os
from fastapi import FastAPI, Request, HTTPException
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from linebot.exceptions import InvalidSignatureError
from diagnosis import (
    Q_MBTI_EXIST, Q_MBTI_TYPE, Q_FALLBACK,
    Q2, Q3, Q4, Q5, Q6,
    parse_mbti, fallback_to_axes,
    calc_risk, calc_surplus,
    determine_type, build_result
)

app = FastAPI()

line_bot_api = LineBotApi(os.environ["LINE_CHANNEL_ACCESS_TOKEN"])
handler = WebhookHandler(os.environ["LINE_CHANNEL_SECRET"])

# インメモリセッション
sessions = {}

def get_session(uid):
    if uid not in sessions:
        sessions[uid] = {"step": 0}
    return sessions[uid]

def reply(token, text):
    line_bot_api.reply_message(token, TextSendMessage(text=text))

@app.get("/")
def health():
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

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    uid = event.source.user_id
    text = event.message.text.strip()
    token = event.reply_token
    s = get_session(uid)
    step = s["step"]

    # リセットコマンド
    if text in ["リセット", "restart", "もう一度"]:
        sessions[uid] = {"step": 0}
        reply(token, "診断をリセットしました！\n「診断スタート」と送ってね👋")
        return

    # ── STEP 0：開始 ──
    if step == 0:
        if "スタート" in text or "診断" in text or "start" in text.lower():
            s["step"] = 1
            reply(token, Q_MBTI_EXIST)
        else:
            reply(token, "「診断スタート」と送ってね！\nあなたのお金タイプを診断します🔍")
        return

    # ── STEP 1：MBTI経験有無 ──
    if step == 1:
        if text.upper().startswith("A"):
            s["step"] = 2
            reply(token, Q_MBTI_TYPE)
        else:
            s["step"] = 3
            reply(token, Q_FALLBACK)
        return

    # ── STEP 2：MBTIタイプ入力 ──
    if step == 2:
        if "わからない" in text or len(text) < 2:
            s["step"] = 3
            reply(token, Q_FALLBACK)
        else:
            intuitive, judging = parse_mbti(text)
            s["intuitive"] = intuitive
            s["judging"] = judging
            s["step"] = 4
            reply(token, Q2)
        return

    # ── STEP 3：補完質問（MBTI未経験者）──
    if step == 3:
        intuitive, judging = fallback_to_axes(text)
        s["intuitive"] = intuitive
        s["judging"] = judging
        s["step"] = 4
        reply(token, Q2)
        return

    # ── STEP 4：Q2 リスク許容度 ──
    if step == 4:
        s["q2"] = text[0].upper() if text else "B"
        s["step"] = 5
        reply(token, Q3)
        return

    # ── STEP 5：Q3 投資経験 ──
    if step == 5:
        s["q3"] = text[0].upper() if text else "B"
        s["step"] = 6
        reply(token, Q4)
        return

    # ── STEP 6：Q4 投資期間 ──
    if step == 6:
        s["q4"] = text[0].upper() if text else "B"
        s["step"] = 7
        reply(token, Q5)
        return

    # ── STEP 7：Q5 余裕感 ──
    if step == 7:
        s["q5"] = text[0].upper() if text else "A"
        s["step"] = 8
        reply(token, Q6)
        return

    # ── STEP 8：Q6 奨学金（最終）→ タイプ判定 ──
    if step == 8:
        q6 = text[0].upper() if text else "C"
        has_loan = (q6 == "A")

        R = calc_risk(s.get("q2","B"), s.get("q3","B"), s.get("q4","B"))
        surplus = calc_surplus(s.get("q5","A"))
        type_id = determine_type(
            s.get("intuitive", False),
            s.get("judging", True),
            R, surplus
        )
        result = build_result(type_id, has_loan)
        s["step"] = 99  # 完了
        reply(token, result)
        return
