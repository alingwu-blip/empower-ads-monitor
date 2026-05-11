#!/bin/bash
# Empower Mindfulness - 廣告助理
# 雙擊這個檔案就可以開啟廣告助理

cd "$(dirname "$0")"
clear
python3 ads_manager.py
echo ""
echo "按任意鍵關閉視窗..."
read -n 1
