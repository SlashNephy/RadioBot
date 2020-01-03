import time
from threading import Thread

cd /opt/discord_radio

def restart():
    time.sleep(60 * 60 * 12)

    sudo systemctl restart np@discord_radio

t = Thread(target=restart)
t.start()

while True:
    python3 radio.py
