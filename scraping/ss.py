import csv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from time import sleep

# ตั้งค่าเบราว์เซอร์
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))

# เปิดเว็บที่ต้องการดึงข้อมูล
driver.get("https://www.mercular.com/computer/laptop/gaming-laptop?categoryId=2158&attributeOption=LAPTOP_TYPE%2FGAMING_LAPTOP&sortBy=recommended")

# รอให้ข้อมูลโหลด
driver.implicitly_wait(10)

# คลิกปุ่มโหลดเพิ่มเติมจนกว่าจะไม่มีปุ่ม
button = driver.find_element(By.CSS_SELECTOR, ".css-3jzqeg")
sleep(1)
while(button):
    button.click()
    sleep(0.75)
    try:
        button = driver.find_element(By.CSS_SELECTOR, ".css-3jzqeg")
    except:
        button = None

# ค้นหาก้อนใหญ่ทั้งหมด
job_elements = driver.find_elements(By.CSS_SELECTOR, "div.MuiGrid-root.MuiGrid-item.MuiGrid-grid-xs-12.MuiGrid-grid-sm-6.MuiGrid-grid-md-4.MuiGrid-grid-lg-3.css-5hgqbg")

# สร้างลิสต์เก็บข้อมูล
data = []

# วนลูปในแต่ละก้อนใหญ่
for job_element in job_elements:
    
    try:
        title = job_element.find_element(By.CSS_SELECTOR, "div.product-title.css-1ge74nh").text
    except:
        title = "N/A"

    try:
        price = job_element.find_element(By.CSS_SELECTOR, ".css-ikx1jg").text
    except:
        price = "N/A"

    try:
        box_data = job_element.find_element(By.CSS_SELECTOR, "div.css-13mgtqc")
        inner_box_data = box_data.find_elements(By.CSS_SELECTOR, "div.cpu-spec.css-1hraeyv")

        # ดึงข้อมูล CPU, RAM, Graphic, SSD, Resolution
        cpu = inner_box_data[0].find_element(By.TAG_NAME, "p").text if len(inner_box_data) > 0 else "N/A"
        ram = inner_box_data[1].find_element(By.TAG_NAME, "p").text if len(inner_box_data) > 1 else "N/A"
        graphic = inner_box_data[2].find_element(By.TAG_NAME, "p").text if len(inner_box_data) > 2 else "N/A"
        ssd = inner_box_data[3].find_element(By.TAG_NAME, "p").text if len(inner_box_data) > 3 else "N/A"
        resolution = inner_box_data[4].find_element(By.TAG_NAME, "p").text if len(inner_box_data) > 4 else "N/A"
    except:
        cpu = ram = graphic = ssd = resolution = "N/A"

    # เก็บข้อมูลในลิสต์
    data.append({
        "title": title,
        "price": price,
        "cpu": cpu,
        "ram": ram,
        "graphic": graphic,
        "SSD": ssd,
        "resolution": resolution,
    })

# บันทึกข้อมูลลงไฟล์ CSV
with open('scraped_data.csv', mode='w', newline='', encoding='utf-8') as file:
    writer = csv.DictWriter(file, fieldnames=["title", "price", "cpu", "ram", "graphic", "SSD", "resolution"])
    writer.writeheader()  # เขียน header ของคอลัมน์
    writer.writerows(data)  # เขียนข้อมูลที่ scrape มา

# แสดงข้อมูลที่ดึงมา
print("Data saved to scraped_data.csv")

# ปิดเบราว์เซอร์
driver.quit()
