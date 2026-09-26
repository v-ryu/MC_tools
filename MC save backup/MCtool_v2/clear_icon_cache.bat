@echo off
taskkill /f /im explorer.exe
del /a %localappdata%\IconCache.db
del /a %localappdata%\Microsoft\Windows\Explorer\iconcache_*.db
start explorer.exe