import os
import pyperclip
import pyautogui
import time
import pytesseract
from PIL import Image
import pyscreenshot as ImageGrab

# 设置tesseract的安装路径（如果tesseract没有添加到系统环境变量中）
pytesseract.pytesseract.tesseract_cmd = 'C:\\Program Files\\Tesseract-OCR\\tesseract.exe'

# 构建文件路径
wishlist_file_path = r'C:\Users\Admin\Desktop\新建文件夹\wishlist.txt' #这个为读取你使用augmentedsteam插件导出的愿望单，地址改成你自己的wishlist.txt地址
result_file_path = r'C:\Users\Admin\Desktop\result.txt' # 这个是你愿望单内没有在家庭库的结果，result文件的地址，我这个选择是导出在桌面上

def copy_and_paste_lines():
    with open(wishlist_file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        for line in lines:
            # 复制每一行内容到系统剪贴板
            pyperclip.copy(line.strip())

            # 等待一段时间，确保操作稳定，等待1秒
            time.sleep(1)

            # 将鼠标移动到指定位置，这个位置就是你库的搜索框的位置，使用POS坐标
            pyautogui.moveTo(605, 456)

            # 在该位置点击鼠标左键
            pyautogui.click()

            # 进行粘贴操作
            pyautogui.hotkey('ctrl', 'v')
            
            # 等待一段时间，确保操作稳定，等待2秒
            time.sleep(2)

            # 识图部分，这个位置就是出现“找不到您要找的游戏吗?搜索 Steam 商店”的位置
            left = 565
            top = 526
            right = 750
            bottom = 570

            # 截取指定坐标范围的桌面图像
            screenshot = ImageGrab.grab(bbox=(left, top, right, bottom))

            # 使用tesseract进行文字识别
            text = pytesseract.image_to_string(screenshot)

            print(text)
           # 由于默认的 Tesseract OCR 引擎只有英文，所以哪怕有 找不到您要找的游戏吗?搜索 Steam 商店，这几个中文，其实就只能识别出来steam几个英文字母
            if "Steam" in text: 
                with open(result_file_path, "a", encoding="utf-8") as result_f:
                    result_f.write(line)
            # 在库的搜索栏删除当前复制的游戏名字，进行下一个循环
            pyautogui.click()
            pyautogui.hotkey('ctrl', 'a')
            pyautogui.press('delete')

if __name__ == "__main__":
    copy_and_paste_lines()
