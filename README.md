# steam愿望单排除家庭库内有的游戏

# 项目简介

代码使用AI辅助编写。
起因是考虑到家庭组中大家都有的游戏就无需在愿望单中购买了，但steam至今尚未推出能方便且一目了然地排除愿望单内家庭组已有的游戏的功能。（而且我的愿望单中有上千个游戏，不适合人工逐个去筛选）

# 实现思路

由于家庭库的游戏能够在steam客户端库的搜索页面被搜到，所以可以通过逐个查询游戏库中是否存在愿望单里的游戏，以此来判断家庭组中是否有愿望单里的游戏。

具体做法是：先导出愿望单txt文件，接着读取每一行txt文件内容，在steam客户端库界面进行复制，然后通过屏幕OCR识别是否出现“找不到您要找的游戏吗?搜索Steam商店”这几行字来进行判断，如果出现这几行字，就将复制的文字另存为一个result.txt文件。该result.txt文件内的游戏名称就是未能在steam客户端库搜索界面搜到的游戏，也就是愿望单中未在家庭库内的游戏。

# 用前准备

## 浏览器插件安装
需要在浏览器安装插件，插件地址为：https://augmentedsteam.com/
其用途是导出愿望单。

## 如何导出愿望单
![如何确定安装好了augmentedsteam](https://github.com/s0h9aMnRe/steam-wishlist-excludes-games-available-in-the-family-library/blob/main/%E7%A4%BA%E4%BE%8B%E7%85%A7%E7%89%87/%E5%9B%BE%E7%89%871.png)

![图片2](https://github.com/s0h9aMnRe/steam-wishlist-excludes-games-available-in-the-family-library/blob/main/%E7%A4%BA%E4%BE%8B%E7%85%A7%E7%89%87/%E5%9B%BE%E7%89%872.png)

![图片3](https://github.com/s0h9aMnRe/steam-wishlist-excludes-games-available-in-the-family-library/blob/main/%E7%A4%BA%E4%BE%8B%E7%85%A7%E7%89%87/%E5%9B%BE%E7%89%873.png)

## 功能特点

- **自动检查游戏状态**：自动在Steam商店中搜索游戏，识别下架或无法找到的游戏
- **批量处理**：支持一次性检查整个愿望单中的所有游戏
- **断点续传**：支持暂停和继续检查，意外中断后可恢复进度
- **OCR识别**：使用先进的OCR技术识别搜索结果
- **红框定位**：提供可视化定位工具，确保准确识别搜索区域
- **结果导出**：生成详细的检查报告，包含所有游戏的状态信息
- **多分辨率支持**：完美适配4K等高分辨率屏幕

## 安装方法

1. 访问发布页面
2. 下载最新版本的 `SteamWishlistChecker.exe` 文件
3. 直接运行可执行文件，无需额外安装

## 使用说明

### 准备工作

1. 确保Steam客户端已启动并登录
2. 导出Steam愿望单为文本文件（每行一个游戏名称）

### 使用步骤

1. 启动Steam愿望单检查工具
2. 点击"显示红框"按钮，将红框拖动到Steam库的搜索栏位置
3. 点击"加载愿望单"按钮，选择愿望单文本文件
4. 点击"选择输出目录"按钮，选择结果保存位置
5. 点击"开始检查"按钮开始自动检查
6. 检查完成后，结果将保存在指定目录的文本文件中

### 控制选项

- **暂停/继续**：可随时暂停和继续检查过程
- **停止**：停止当前检查并保存进度
- **显示/隐藏红框**：控制定位红框的显示状态

## 实现原理

### 技术栈

- Python 3.10+
- Tkinter (GUI界面)
- EasyOCR (光学字符识别)
- PyAutoGUI (自动化控制)
- PyInstaller (打包为可执行文件)

### 工作原理

1. **界面交互**：用户通过GUI界面选择愿望单文件和输出目录
2. **红框定位**：用户将红框定位到Steam客户端的搜索栏区域
3. **自动化搜索**：程序自动在Steam搜索栏中输入游戏名称并执行搜索
4. **OCR识别**：对搜索结果区域进行截图，使用OCR识别"找不到您要找的游戏吗"提示
5. **结果记录**：根据OCR识别结果判断游戏是否存在，记录并显示结果
6. **报告生成**：检查完成后生成详细的文本报告

## 开发致谢

本工具的开发得到了以下项目的支持：

- **DeepSeek AI**：提供强大的AI编程辅助
- **AIPY (Advanced Intelligence Python)**：提供高级Python编程支持
- **EasyOCR**：提供高效准确的OCR识别功能
- **PyAutoGUI**：提供跨平台自动化控制能力

## 许可证

本项目采用 MIT 许可证发布。



## 贡献指南

欢迎贡献代码！请遵循以下步骤：

1. Fork 项目仓库
2. 创建新的分支 (`git checkout -b feature/your-feature`)
3. 提交你的修改 (`git commit -am 'Add some feature'`)
4. 推送到分支 (`git push origin feature/your-feature`)
5. 创建 Pull Request

## 问题反馈

如果在使用过程中遇到任何问题，请在 Issues 页面提交问题报告。
