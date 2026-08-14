"""Download Android Platform Tools (adb) into tools/platform-tools.
Used by bootstrap.ps1; also runnable standalone: python download_adb.py
Relies on Python's urllib because PowerShell's TLS stack can fail on some hosts.
"""
import urllib.request, zipfile, os, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
DEST = os.path.join(HERE, "platform-tools")
ZIP = os.path.join(HERE, "platform-tools.zip")
URL = "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"

if os.path.exists(os.path.join(DEST, "adb.exe")):
    print("adb already present at", DEST)
else:
    print("downloading", URL)
    r = urllib.request.urlopen(URL, timeout=180)
    with open(ZIP, "wb") as f:
        shutil.copyfileobj(r, f)
    print("downloaded", os.path.getsize(ZIP), "bytes")
    with zipfile.ZipFile(ZIP) as z:
        z.extractall(DEST)
    os.remove(ZIP)
    # flatten nested platform-tools/ dir if the archive carried one
    inner = os.path.join(DEST, "platform-tools")
    if os.path.isdir(inner):
        for name in os.listdir(inner):
            shutil.move(os.path.join(inner, name), os.path.join(DEST, name))
        os.rmdir(inner)
    print("done; adb exists:", os.path.exists(os.path.join(DEST, "adb.exe")))
