del "KoboUtilities.zip"
rem "c:\Program Files\7-Zip\7z.exe" a "KoboUtilities.zip" __init__.py about.txt action.py book.py changelog.txt common_utils.py container.py dialogs.py jobs.py config.py "KoboUtilities_Help.html" plugin-import-name-KoboUtilities.txt run.cmd images/*
"c:\Program Files\7-Zip\7z.exe" a "KoboUtilities.zip" __init__.py about.txt action.py book.py common_utils.py container.py dialogs.py jobs.py config.py plugin-import-name-KoboUtilities.txt changelog.txt run.cmd images/* help/KoboUtilities_Help*.html translations/*.po translations/*.mo
mode 165,9999
rem copy KoboReader.sqlite e:\.kobo
calibre-debug -s
calibre-customize -a "KoboUtilities.zip"
SET CALIBRE_DEVELOP_FROM=E:\Development\GitHub\calibre\src
calibre-debug  -g



