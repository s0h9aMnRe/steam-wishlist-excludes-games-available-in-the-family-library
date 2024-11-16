# steam愿望单排除家庭库内有的游戏

# 项目简介

代码使用AI辅助编写。若有大神认为其不够简单，可进行简化。目前未编写UI界面。

起因是考虑到家庭组中大家都有的游戏就无需在愿望单中购买了，但steam至今尚未推出能方便且一目了然地排除愿望单内家庭组已有的游戏的功能。（而且我的愿望单中有近千个游戏，不适合人工逐个去筛选）

# 实现思路

由于家庭库的游戏能够在steam客户端库的搜索页面被搜到，所以可以通过逐个查询游戏库中是否存在愿望单里的游戏，以此来判断家庭组中是否有愿望单里的游戏。

具体做法是：先导出愿望单txt文件，接着读取每一行txt文件内容，在steam客户端库界面进行复制，然后通过屏幕OCR识别是否出现“找不到您要找的游戏吗?搜索Steam商店”这几行字来进行判断，如果出现这几行字，就将复制的文字另存为一个result.txt文件。该result.txt文件内的游戏名称就是未能在steam客户端库搜索界面搜到的游戏，也就是愿望单中未在家庭库内的游戏。

# 用前准备

## 浏览器插件安装
需要在浏览器安装插件，插件地址为：https://augmentedsteam.com/。其用途是导出愿望单。

## Python模块安装

### pyperclip
```bash
pip install pyperclip
```
这是一个用于复制和粘贴文本到剪贴板的模块，它提供了简单的接口来访问系统剪贴板。

### pyautogui
```bash
pip install pyautogui
```
这个模块可用于自动化鼠标和键盘操作。

### pytesseract
```bash
pip install pytesseract
```
pytesseract是一个光学字符识别（OCR）工具的Python封装，它可以识别图像中的文字。不过，要使用它，还需要安装Tesseract OCR引擎（在不同操作系统下安装方式不同）。

在Ubuntu系统中：
```bash
sudo apt - get install tesseract - ocr
```
在Windows系统中，需要从官网（https://github.com/UB-Mannheim/tesseract/wiki）下载安装包进行安装。

### Pillow
```bash
pip install Pillow
```
Pillow提供了强大的图像处理功能，比如打开图像`Image.open()`、保存图像、对图像进行裁剪、旋转等操作。

### pyscreenshot
```bash
pip install pyscreenshot
```
这个模块用于截取屏幕图像。

具体使用方法在代码注释内有详细说明。
