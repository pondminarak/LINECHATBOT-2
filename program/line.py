from neo4j import GraphDatabase
from flask import Flask, request, jsonify
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, QuickReply, QuickReplyButton, MessageAction
from sentence_transformers import SentenceTransformer, util
import numpy as np
import faiss  # Import FAISS for efficient similarity search
import json
import requests
import pandas as pd

# Load the sentence transformer model
model = SentenceTransformer('sentence-transformers/distiluse-base-multilingual-cased-v2')

# Neo4j connection details
URI = "neo4j://localhost"
AUTH = ("neo4j", "123456789")

def run_query(query, parameters=None):
    with GraphDatabase.driver(URI, auth=AUTH) as driver:
        driver.verify_connectivity()
        with driver.session() as session:
            result = session.run(query, parameters)
            return [record for record in result]
    driver.close()

def create_query(query, parameters=None):
   with GraphDatabase.driver(URI, auth=AUTH) as driver:
       driver.verify_connectivity()
       with driver.session() as session:
           result = session.run(query, parameters)
           return result
   driver.close()

# Function to create or update user node with uid and log conversation
def upsert_user_and_log_conversation(uid, question, response):
    result = run_query(f"MATCH (n:UserId) WHERE n.userId='{uid}' RETURN n;")
    if(result == []): # if no history chat => create one!
        create_query(f"CREATE (user:UserId {{userId:'{uid}'}})")

    # create chat history
    create_query(f"MATCH (n:UserId) WHERE n.userId='{uid}' CREATE (n)-[:Conversation]->(:ChatHistory {{msg_send: '{question}', msg_reply: '{response}'}})")
    print("="*20 + "save history" + "="*20)

cypher_query = '''
MATCH (n:Greeting) RETURN n.name as name, n.msg_reply as reply;
'''

quick_reply_price = 0
quick_reply_title = None
quick_reply_cpu = None
quick_reply_ram = None
quick_reply_graphic = None
quick_reply_ssd = None
quick_reply_resulutions = None

# Retrieve greetings from the Neo4j database
greeting_corpus = []
results = run_query(cypher_query)
for record in results:
    greeting_corpus.append(record['name'])

# Ensure corpus is unique
greeting_corpus = list(set(greeting_corpus))
print(greeting_corpus)

# Encode the greeting corpus into vectors using the sentence transformer model
greeting_vecs = model.encode(greeting_corpus, convert_to_numpy=True, normalize_embeddings=True)

# Initialize FAISS index
d = greeting_vecs.shape[1]  # Dimension of vectors
index = faiss.IndexFlatL2(d)  # L2 distance index (cosine similarity can be used with normalization)
index.add(greeting_vecs)  # Add vectors to FAISS index

def compute_similar_faiss(sentence):
    # Encode the query sentence
    ask_vec = model.encode([sentence], convert_to_numpy=True, normalize_embeddings=True)
    # Search FAISS index for nearest neighbor
    D, I = index.search(ask_vec, 1)  # Return top 1 result
    return D[0][0], I[0][0]

def neo4j_search(neo_query):
    results = run_query(neo_query)
    for record in results:
        response_msg = record['reply']
    return response_msg

# Ollama API endpoint (assuming you're running Ollama locally)
OLLAMA_API_URL = "http://localhost:11434/api/generate"

headers = {
    "Content-Type": "application/json"
}

def llama_generate_response(prompt):
    # Prepare the request payload for the supachai/llama-3-typhoon-v1.5 model
    payload = {
        "model": "supachai/llama-3-typhoon-v1.5",  # Adjust model name as needed
        "prompt": prompt + "ตอบไม่เกิน 20 คำและเข้าใจง่าย",
        "stream": False
    }

    # Send the POST request to the Ollama API
    response = requests.post(OLLAMA_API_URL, headers=headers, data=json.dumps(payload))

    # Check if the request was successful
    if response.status_code == 200:
        # Parse the response JSON
        response_data = response.text
        data = json.loads(response_data)
        decoded_text = data.get("response", "No response found.")
        return "นี้คือคำตอบเพิ่มเติมที่มีนอกเหนือจากคลังความรู้ของเรานะครับ : " + decoded_text
    else:
        # Handle errors
        print(f"Failed to get a response: {response.status_code}, {response.text}")
        return "Error occurred while generating response."

# Modify compute_response to log the conversation
def compute_response(sentence, uid):
    # Compute similarity
    score, index = compute_similar_faiss(sentence)
    if score > 0.5:
        # Use the new API-based method to generate a response
        prompt = f"คำถาม: {sentence}\nคำตอบ:"
        my_msg = llama_generate_response(prompt)
    else:
        Match_greeting = greeting_corpus[index]
        My_cypher = f"MATCH (n:Greeting) WHERE n.name = '{Match_greeting}' RETURN n.msg_reply as reply"
        my_msg = neo4j_search(My_cypher)

    # Log the user and conversation into Neo4j
    # upsert_user_and_log_conversation(uid, sentence, my_msg)

    print(my_msg)
    return my_msg

# New function to send quick reply messages
def send_quick_reply_message(reply_token, line_bot_api, response_msg, uid, msg):
    quick_reply = QuickReply(items=[
        QuickReplyButton(action=MessageAction(label="สวัสดี", text="สวัสดี")),
        QuickReplyButton(action=MessageAction(label="แนะนำ Notebook หน่อย", text="แนะนำ Notebook หน่อย")),
        QuickReplyButton(action=MessageAction(label="จัดสเปคให้หน่อย", text="แนะนำ Notebook หน่อย")),
        QuickReplyButton(action=MessageAction(label="ปรึกษาเรื่องIT", text="ปรึกษาเรื่องIT")),
        QuickReplyButton(action=MessageAction(label="ขอบคุณ", text="ขอบคุณ")),
    ])

    line_bot_api.reply_message(
        reply_token,
        TextSendMessage(text=response_msg, quick_reply=quick_reply)
    )
    upsert_user_and_log_conversation(uid, response_msg, msg)

# New function to send new quick reply questions title
def send_new_quick_reply_message(reply_token, line_bot_api,uid, msg):
    quick_reply = QuickReply(items=[
        QuickReplyButton(action=MessageAction(label="ASUS", text="ASUS")),
        QuickReplyButton(action=MessageAction(label="Acer", text="Acer")),
        QuickReplyButton(action=MessageAction(label="MSI", text="MSI")),
        QuickReplyButton(action=MessageAction(label="HP", text="HP")),
        QuickReplyButton(action=MessageAction(label="Lenovo", text="Lenovo")),
        QuickReplyButton(action=MessageAction(label="Gigabyte", text="Gigabyte")),
        QuickReplyButton(action=MessageAction(label="Dell", text="Dell"))
    ])

    line_bot_api.reply_message(
        reply_token,
        TextSendMessage(text="คุณต้องการดู Notebook ประเภทไหน?", quick_reply=quick_reply)
    )
    upsert_user_and_log_conversation(uid,"คุณต้องการดู Notebook ประเภทไหน?", msg)

# Function to handle the user's quick reply selection
def handle_quick_reply_selection(msg):
    global quick_reply_title  # Use the global variable to store the selected brand
    quick_reply_title = msg  # Store the user's choice
    print(f"Selected title: {quick_reply_title}")
    return quick_reply_title


# New function to send quick reply for different notebook 
def send_notebook_price_quick_reply(reply_token, line_bot_api,uid, msg):
    quick_reply = QuickReply(items=[
        QuickReplyButton(action=MessageAction(label="10000-20000", text="10000-20000")),
        QuickReplyButton(action=MessageAction(label="10000-30000", text="10000-30000")),
        QuickReplyButton(action=MessageAction(label="10000-40000", text="10000-40000")),
        QuickReplyButton(action=MessageAction(label="10000-50000", text="10000-50000")),
        QuickReplyButton(action=MessageAction(label="10000-60000", text="10000-60000")),
        QuickReplyButton(action=MessageAction(label="10000-70000", text="10000-70000")),
        QuickReplyButton(action=MessageAction(label="10000-80000", text="10000-80000")),
        QuickReplyButton(action=MessageAction(label="10000-90000", text="10000-90000")),
        QuickReplyButton(action=MessageAction(label="10000-100000", text="10000-100000")),
        QuickReplyButton(action=MessageAction(label="100000-200000", text="100000-200000")),
    ])

    line_bot_api.reply_message(
        reply_token,
        TextSendMessage(text="ราคาที่คุณต้องการ", quick_reply=quick_reply)
    )
    upsert_user_and_log_conversation(uid,"ราคาที่คุณต้องการ", msg)

def handle_price_selection(msg):
    global quick_reply_price  # Use the global variable to store the selected price range
    quick_reply_price = msg # Store the user's choice
    print(f"Selected price: {quick_reply_price}")
    return quick_reply_price


# New function to send quick reply for different notebook cpu
def send_notebook_cpu_quick_reply(reply_token, line_bot_api,uid, msg):
    quick_reply = QuickReply(items=[
        QuickReplyButton(action=MessageAction(label="Core", text="Core")),
        QuickReplyButton(action=MessageAction(label="Ryzen", text="Ryzen")),
        QuickReplyButton(action=MessageAction(label="Core i3", text="Core i3")),
        QuickReplyButton(action=MessageAction(label="Core i5", text="Core i5")),
        QuickReplyButton(action=MessageAction(label="Core i7", text="Core i7")),
        QuickReplyButton(action=MessageAction(label="Core i9", text="Core i3")),
        QuickReplyButton(action=MessageAction(label="Ryzen7", text="Ryzen7")),
        QuickReplyButton(action=MessageAction(label="Ryzen9", text="Ryzen9"))
    ])

    line_bot_api.reply_message(
        reply_token,
        TextSendMessage(text="CPU ที่คุณต้องการ", quick_reply=quick_reply)
    )
    upsert_user_and_log_conversation(uid,"CPU ที่คุณต้องการ", msg)

def handle_cpu_selection(msg):
    global quick_reply_cpu  # Use the global variable to store the selected price range
    quick_reply_cpu = msg  # Store the user's choice
    print(f"Selected cpu: {quick_reply_cpu}")
    return quick_reply_cpu


# New function to send quick reply for different notebook RAM
def send_notebook_ram_quick_reply(reply_token, line_bot_api,uid, msg):
    quick_reply = QuickReply(items=[
        QuickReplyButton(action=MessageAction(label="8GB", text="8GB")),
        QuickReplyButton(action=MessageAction(label="16GB", text="16GB")),
        QuickReplyButton(action=MessageAction(label="32GB", text="32GB")),
        QuickReplyButton(action=MessageAction(label="64GB", text="64GB"))
    ])

    line_bot_api.reply_message(
        reply_token,
        TextSendMessage(text="RAM ที่คุณต้องการ", quick_reply=quick_reply)
    )
    upsert_user_and_log_conversation(uid,"RAM ที่คุณต้องการ", msg)

def handle_ram_selection(msg):
    global quick_reply_ram  # Use the global variable to store the selected price range
    quick_reply_ram = msg  # Store the user's choice
    print(f"Selected ram: {quick_reply_ram}")
    return quick_reply_ram

# New function to send quick reply for different notebook graphic
def send_notebook_graphic_quick_reply(reply_token, line_bot_api,uid, msg):
    quick_reply = QuickReply(items=[
        QuickReplyButton(action=MessageAction(label="GTX", text="GTX")),
        QuickReplyButton(action=MessageAction(label="RTX", text="RTX")),
        QuickReplyButton(action=MessageAction(label="GeForce GTX10", text="GeForce GTX10")),
        QuickReplyButton(action=MessageAction(label="GeForce GTX16", text="GeForce GTX16")),
        QuickReplyButton(action=MessageAction(label="GeForce RTX20", text="GeForce RTX20")),
        QuickReplyButton(action=MessageAction(label="GeForce RTX30", text="GeForce RTX30")),
        QuickReplyButton(action=MessageAction(label="GeForce RTX40", text="GeForce RTX40")),
    ])

    line_bot_api.reply_message(
        reply_token,
        TextSendMessage(text="การ์ดจอ ที่คุณต้องการ", quick_reply=quick_reply)
    )
    upsert_user_and_log_conversation(uid,"การ์ดจอ ที่คุณต้องการ", msg)

def handle_graphic_selection(msg):
    global quick_reply_graphic  # Use the global variable to store the selected price range
    quick_reply_graphic = msg  # Store the user's choice   
    print(f"Selected graphic: {quick_reply_graphic}")
    return quick_reply_graphic

# New function to send quick reply for different notebook SSD
def send_notebook_ssd_quick_reply(reply_token, line_bot_api,uid, msg):
    quick_reply = QuickReply(items=[
        QuickReplyButton(action=MessageAction(label="512GB", text="512GB")),
        QuickReplyButton(action=MessageAction(label="1TB", text="1TB"))
    ])

    line_bot_api.reply_message(
        reply_token,
        TextSendMessage(text="ต้องการพื้นที่เท่าไหร่ ที่คุณต้องการ", quick_reply=quick_reply)
    )
    upsert_user_and_log_conversation(uid,"ต้องการพื้นที่เท่าไหร่ ที่คุณต้องการ", msg)

def handle_ssd_selection(msg):
    global quick_reply_ssd  # Use the global variable to store the selected price range
    quick_reply_ssd = msg  # Store the user's choice   
    print(f"Selected SSD: {quick_reply_ssd}")
    return quick_reply_ssd

# New function to send quick reply for different notebook resulutions
def send_notebook_resulutions_quick_reply(reply_token, line_bot_api,uid, msg):
    quick_reply = QuickReply(items=[
        QuickReplyButton(action=MessageAction(label="120Hz", text="120Hz")),
        QuickReplyButton(action=MessageAction(label="144Hz", text="144Hz")),
        QuickReplyButton(action=MessageAction(label="165Hz", text="165Hz")),
        QuickReplyButton(action=MessageAction(label="240Hz", text="240Hz")),
        QuickReplyButton(action=MessageAction(label="360Hz", text="360Hz"))
    ])

    line_bot_api.reply_message(
        reply_token,
        TextSendMessage(text="ความละเอียดจอที่ต้องการ ที่คุณต้องการ", quick_reply=quick_reply)
    )
    upsert_user_and_log_conversation(uid,"ความละเอียดจอที่ต้องการ ที่คุณต้องการ", msg)

def handle_resulutions_selection(msg):
    global quick_reply_resulutions  # Use the global variable to store the selected price range
    quick_reply_resulutions = msg  # Store the user's choice   
    print(f"Selected resolution: {quick_reply_resulutions}")
    return quick_reply_resulutions

def send_notebook_confirm_quick_reply(reply_token, line_bot_api,uid, msg):
    quick_reply = QuickReply(items=[
        QuickReplyButton(action=MessageAction(label="ตกลง", text="ตกลง")),
        QuickReplyButton(action=MessageAction(label="ย้อนกลับหน้าแรก", text="ย้อนกลับหน้าแรก")),
    ])

    line_bot_api.reply_message(
        reply_token,
        TextSendMessage(text=f"คุณเลือกแบรนด์ : {quick_reply_title}\nราคา : {quick_reply_price}\nCPU : {quick_reply_cpu}\nRAM : {quick_reply_ram}\nGraphic : {quick_reply_graphic}\nSSD : {quick_reply_ssd}\nResolution : {quick_reply_resulutions}\n. กรุณาเลือกต่อไป.", quick_reply=quick_reply)
    )
    upsert_user_and_log_conversation(uid,"ส่งข้อมูลสเปคที่คุณต้องหรือไม่", msg)


data = pd.read_csv(r'D:\PSU 4 YEARS\YEAR 4\term1\241-331\MINI PROJECT2\test\scraped_data.csv')

# ลบสัญลักษณ์฿ และแปลงข้อมูลในคอลัมน์ price เป็นตัวเลข
data['price'] = data['price'].replace({'฿': '', ',': ''}, regex=True).astype(float)

# ฟังก์ชันสำหรับค้นหาโน๊ตบุ๊คตามแบรนด์, CPU, RAM, ช่วงราคา, กราฟิก, SSD และรีโซลูชัน
def search_laptops(brand, min_price , cpu, ram, max_price, graphic, ssd, resolution, tk, line_bot_api, uid, msg):
    # กรองข้อมูลตามแบรนด์, CPU, RAM, ช่วงราคา, กราฟิก, SSD และรีโซลูชัน
    filtered_data = data[
        (data['title'].str.contains(brand, case=False)) &
        (data['price'] >= min_price) & 
        (data['price'] <= max_price) &
        (data['cpu'].str.contains(cpu, case=False)) &
        (data['ram'].str.contains(ram, case=False)) &  
        (data['graphic'].str.contains(graphic, case=False)) &
        (data['SSD'].str.contains(ssd, case=False)) &  # เงื่อนไข SSD
        (data['resolution'].str.contains(resolution, case=False))  # เงื่อนไขรีโซลูชัน
    ]
    # return filtered_data

    quick_reply = QuickReply(items=[
        QuickReplyButton(action=MessageAction(label="สวัสดี", text="สวัสดี")),
        QuickReplyButton(action=MessageAction(label="แนะนำ Notebook หน่อย", text="แนะนำ Notebook หน่อย")),
        QuickReplyButton(action=MessageAction(label="จัดสเปคให้หน่อย", text="แนะนำ Notebook หน่อย")),
        QuickReplyButton(action=MessageAction(label="ปรึกษาเรื่องIT", text="ปรึกษาเรื่องIT")),
        QuickReplyButton(action=MessageAction(label="ขอบคุณ", text="ขอบคุณ"))
    ])

    reply_msg = ""
    # ตรวจสอบข้อมูลที่ถูกกรอง
    if not filtered_data.empty:
        print("โน๊ตบุ๊คที่ค้นพบ:")
        for index, row in filtered_data.iterrows():
            reply_msg = reply_msg + f"{row['title']}\nราคา : {row['price']}\nCPU : {row['cpu']}\nRAM : {row['ram']}\nGraphic : {row['graphic']}\nSSD : {row['SSD']}\nResolution : {row['resolution']}\n\n"
        reply_msg[:-2]
    else:
        print("ไม่พบโน๊ตบุ๊คที่ตรงตามเงื่อนไข")
        reply_msg = "ไม่พบโน๊ตบุ๊คที่ตรงตามเงื่อนไข"

    line_bot_api.reply_message(
        tk,
        TextSendMessage(text=reply_msg, quick_reply=quick_reply)
    )

# # รับข้อมูลจากผู้ใช้
# user_input_brand = quick_reply_title
# user_input_price_range = quick_reply_price
# user_input_cpu = quick_reply_cpu
# user_input_ram = quick_reply_ram
# user_input_graphic = quick_reply_graphic
# user_input_ssd = quick_reply_ssd
# user_input_resolution = quick_reply_resulutions  # รับข้อมูลรีโซลูชัน

# # แยกช่วงราคา
# min_price, max_price = map(float, user_input_price_range.split('-'))

# แสดงผลโน๊ตบุ๊คที่ตรงตามคำค้นหา
# result = search_laptops(user_input_brand, user_input_cpu, user_input_ram, min_price, max_price, user_input_graphic, user_input_ssd, user_input_resolution)


# # ตรวจสอบข้อมูลที่ถูกกรอง
# if not result.empty:
#     print("โน๊ตบุ๊คที่ค้นพบ:")
#     print(result)
# else:
#     print("ไม่พบโน๊ตบุ๊คที่ตรงตามเงื่อนไข")



app = Flask(__name__)

@app.route("/", methods=['POST'])
def linebot():
    body = request.get_data(as_text=True)
    try:
        json_data = json.loads(body)
        access_token = 'nb7Lc36ImomAFYsKek9mtegv/DhVtYayaUksY3vxuFtGLXONd3zOmL+eLNKlO8HqOXb4a0/StXwS8AfZNpp5p+hjSk2wJzo/cpDtnG/SQNaSSudV4p78otUOIb042B9fXDW8nMyDC5mj7OCEQgN8JwdB04t89/1O/w1cDnyilFU='
        secret = '5280c53da8243d3e54a55d3aa4c9caa7'
        line_bot_api = LineBotApi(access_token)
        handler = WebhookHandler(secret)
        signature = request.headers['X-Line-Signature']
        handler.handle(body, signature)

        msg = json_data['events'][0]['message']['text']
        tk = json_data['events'][0]['replyToken']
        uid = json_data['events'][0]['source']['userId']  # Get the user ID from LINE event data

        # Pass both the message and uid to compute_response
        response_msg = compute_response(msg, uid)

        # Check if the message is a quick reply button action
        if msg in ["แนะนำ Notebook หน่อย", "จัดสเปคให้หน่อย"]:
            # Send a new set of quick replies with questions
            send_new_quick_reply_message(tk, line_bot_api, uid, msg)
        elif msg in ["ASUS", "Acer", "MSI", "HP", "Lenovo", "Gigabyte", "Dell"] :   
            send_notebook_price_quick_reply(tk, line_bot_api,uid, msg)
            handle_quick_reply_selection(msg) 
        elif msg in ["10000-20000", "10000-30000","10000-40000","10000-50000","10000-60000","10000-70000","10000-80000","10000-90000","10000-100000","100000-200000"] :
            send_notebook_cpu_quick_reply(tk, line_bot_api, uid, msg) 
            handle_price_selection(msg)
        elif msg in ["Core","Ryzen","Core i3","Core i5","Core i7","Core i9","Ryzen7","Ryzen9"] :
            send_notebook_ram_quick_reply(tk, line_bot_api, uid, msg)
            handle_cpu_selection(msg)
        elif msg in ["8GB","16GB","32GB","64GB"] :
            send_notebook_graphic_quick_reply(tk, line_bot_api, uid, msg)
            handle_ram_selection(msg)
        elif msg in ["GTX","RTX","GeForce GTX10","GeForce GTX16","GeForce RTX20","GeForce RTX30","GeForce RTX40"] :
            send_notebook_ssd_quick_reply(tk, line_bot_api, uid, msg)
            handle_graphic_selection(msg)
        elif msg in ["512GB","1TB"] :
            send_notebook_resulutions_quick_reply(tk, line_bot_api, uid, msg)
            handle_ssd_selection(msg)
        elif msg in ["120Hz","144Hz","165Hz","240Hz","360Hz"] :
            handle_resulutions_selection(msg)
            send_notebook_confirm_quick_reply(tk, line_bot_api, uid, msg)
        elif msg in ["ตกลง"] :
            # search_laptops(brand, min_price , cpu, ram, max_price, graphic, ssd, resolution,tk, line_bot_api, uid, msg)
            min_price, max_price = map(float, quick_reply_price.split('-'))
            search_laptops(quick_reply_title, 
                                    min_price, 
                                    quick_reply_cpu, 
                                    quick_reply_ram, 
                                    max_price, 
                                    quick_reply_graphic, 
                                    quick_reply_ssd, 
                                    quick_reply_resulutions,
                                    tk,
                                    line_bot_api,
                                    uid,
                                    msg,
                                    )
        else:
            # Send the original response message with quick reply options
            send_quick_reply_message(tk, line_bot_api, response_msg,uid, msg)

        print(msg, tk)
        return(msg)
    except Exception as e:
        print(body)
        print(f"Error: {e}")
    return 'OK'

if __name__ == '__main__':
    app.run(port=5000)
