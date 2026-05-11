@echo off
cd /d d:\BigData\PycharmProject\TOMI-GPT
C:\Users\YaRa\anaconda3\python.exe -X utf8 -m uvicorn agent.ableton_bridge:app --host 0.0.0.0 --port 8002
