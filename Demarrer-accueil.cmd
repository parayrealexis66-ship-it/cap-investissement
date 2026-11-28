@echo off
setlocal
cd /d "%~dp0"
if not exist "%LOCALAPPDATA%\CapInvestissement\accueil\Scripts\python.exe" (
  py -3 -m venv "%LOCALAPPDATA%\CapInvestissement\accueil" || goto error
)
set "BOT_PY=%LOCALAPPDATA%\CapInvestissement\accueil\Scripts\python.exe"
"%BOT_PY%" -c "import discord; assert hasattr(discord, 'ui')" >nul 2>&1 || "%BOT_PY%" -m pip install "discord.py>=2.4,<3" || goto error
"%BOT_PY%" -c "import os,getpass,runpy,sys; sys.path.insert(0,'server'); os.environ['GUILD']=os.environ.get('GUILD') or input('Identifiant du serveur Discord : ').strip(); os.environ['BOT_TOKEN']=os.environ.get('BOT_TOKEN') or getpass.getpass('Jeton du bot (saisie masquee) : ').strip(); runpy.run_path('server/instant_confirmation.py',run_name='__main__')" || goto error
exit /b 0
:error
echo Verifiez Python, les permissions du bot et Message Content Intent dans le portail Discord.
pause
exit /b 1
