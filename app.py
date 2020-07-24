# encoding: utf-8
import json
import os
import random
import requests

from flask import Flask, request, abort

from linebot import (
    LineBotApi, WebhookHandler
)
from linebot.exceptions import (
    InvalidSignatureError
)
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    LocationMessage,
    TemplateSendMessage, ButtonsTemplate, URITemplateAction,
)


app = Flask(__name__)

# 使用環境變數，才不會外洩秘密
GOOGLE_API_KEY = os.environ['GOOGLE_API_KEY']
handler = WebhookHandler(os.environ['CHANNEL_SECRET'])
line_bot_api = LineBotApi(os.environ['CHANNEL_ACCESS_TOKEN'])

# ================= 抓Opendata =================
import pandas as pd

def download():
    import csv
    import requests
    CSV_URL = 'https://quality.data.gov.tw/dq_download_csv.php?nid=115950&md5_url=ee25ae45fd566bcb8c4c22a915f169a8'
    with requests.Session() as s:
        download = s.get(CSV_URL).text
        df = pd.read_csv(CSV_URL)
        return df

import time
from datetime import datetime
#----------- 每10分鐘抓一次
#while True:
    #download()
    #print("Dowloaded at:",str(datetime.now()))
    #time.sleep(10*60)

#------------ 只抓一次
df = download().to_dict('records')


# ================= Home =================
@app.route('/')
def index():
    return "<p>Hello World!</p>"

@app.route("/callback", methods=['POST'])
def callback():
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']

    # get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # handle webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

# ================= 機器人區塊 Start =================
@handler.add(MessageEvent, message=TextMessage)  # default
def handle_text_message(event):                  # default
    msg = event.message.text # message from user
    uid = event.source.user_id # user id
 
    user_intent = "FindNursing"

    # 3. 根據使用者的意圖做相對應的回答
    if user_intent == "FindNursing": # 當使用者意圖為詢問午餐時
        # 建立一個 button 的 template
        buttons_template_message = TemplateSendMessage(
            alt_text="請告訴我你在哪兒",
            template=ButtonsTemplate(
                text="請告訴我你在哪兒",
                actions=[
                    URITemplateAction(
                        label="傳送我的位置訊息",
                        uri="line://nv/location"
                    )
                ]
            )
        )
        line_bot_api.reply_message(
            event.reply_token,
            buttons_template_message)
    else: # 聽不懂時的回答
        msg = "抱歉，我聽不懂你在說什麼"
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=msg))

@handler.add(MessageEvent, message=LocationMessage)
def handle_location_message(event):
    # 獲取使用者的經緯度
    lat = event.message.latitude
    long = event.message.longitude
    
    # 使用 Google API Start =========
    # 1. 取得最近居護機構
    from math import cos, asin, sqrt
    def distance(lat1, lon1, lat2, lon2):
        p = 0.017453292519943295  #Pi/180
        a = 0.5 - cos((lat2-lat1)*p)/2 + cos(lat1*p)*cos(lat2*p) * (1-cos((lon2-lon1)*p)) / 2
        return 12742 * asin(sqrt(a)) #2*R*asin..

    def closest(data, zipcode):
        dl = []
        for p in data:
            ap = {
            '縣市別': zipcode['縣市別'],
            '機構類型': zipcode['機構類型'],
            '機構代碼': zipcode['機構代碼'],
            '機構名稱': zipcode['機構名稱'],
            '地址': zipcode['地址'],
            '電話': zipcode['電話'],
            '定位地址': zipcode['定位地址'],
            'WGS84經度': p['WGS84經度'],
            'WGS84緯度': p['WGS84緯度'],
            'a': zipcode['WGS84經度'],
            'b': zipcode['WGS84緯度'],
            '距離': distance(zipcode['WGS84經度'],zipcode['WGS84緯度'],p['WGS84經度'],p['WGS84緯度'])
            }
            dl.append(ap)
        dl_sorted = sorted(dl, key=lambda k: k['距離'])
        return dl_sorted[0]

    def calculateNearestOne(dict_df2):
        dicts = []
        for zc in df:
            dicts.append(closest(dict_df2, zc))
   
        dl_sorted = sorted(dicts, key=lambda k: k['距離'])
        return dl_sorted[0]


    #lat = [25.058360]
    #lng = [121.445734]
    lat2 = list()
    lat2.append(lat)
    lng2 = list()
    lng2.append(long)

    dict = {
        "WGS84經度": lng2,
        "WGS84緯度": lat2
    }

    dict_df = pd.DataFrame(dict)
    dict_df = dict_df.to_dict('records')

    result = calculateNearestOne(dict_df)
    
    details = "機構名稱：{}\n電話：{}".format(result['機構名稱'],result['電話']) 
    
    the_url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json?key={}&input={}&inputtype=textquery&fields=photos,rating".format(GOOGLE_API_KEY, result['機構名稱'])
    the_results = requests.get(the_url)
    the_restaurants_dict = the_results.json()
    restaurant = the_restaurants_dict["candidates"][0]

    if restaurant.get("photos") is None:
        thumbnail_image_url = None
    else:
        # 根據文件，最多只會有一張照片
        photo_reference = restaurant["photos"][0]["photo_reference"]
        thumbnail_image_url = "https://maps.googleapis.com/maps/api/place/photo?key={}&photoreference={}&maxwidth=1024".format(GOOGLE_API_KEY, photo_reference)

    # 6. 取得機構的 Google map 網址
    map_url = "https://www.google.com/maps/search/?api=1&query={lat},{long}&query_place_id={place_id}".format(
        lat=result["WGS84緯度"],
        long=result["WGS84經度"],
        place_id=result["機構名稱"]
    )
    # 使用 Google API End =========
    
    # 回覆使用 Buttons Template
    buttons_template_message = TemplateSendMessage(
    alt_text=result["機構名稱"],
    template=ButtonsTemplate(
            thumbnail_image_url = thumbnail_image_url,
            title=result["機構名稱"],
            text=details,
            actions=[
                URITemplateAction(
                    label='查看地圖位置',
                    uri=map_url
                ),
            ]
        )
    )

    line_bot_api.reply_message(
        event.reply_token,
        buttons_template_message)


# ================= 機器人區塊 End =================

if __name__ == "__main__":
    app.run(host='0.0.0.0',port=int(os.environ['PORT']))
