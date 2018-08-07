import os
import time
import threading


class GraphThread(threading.Thread):
    def __init__(self, time_range):
        threading.Thread.__init__(self, target=grab_chart, args=(time_range,))
        self.start()


def grab_chart(time_range):
    sleeping_ranges = {"1d": 5 * 60,       # Updates every 5 minutes
                       "1w": 60 * 60,       # Updates every hour
                       "1m": 4 * 60 * 60,   # Updates every 4 hours
                       "3m": 11 * 60 * 60,  # Updates every 11 hours
                       "6m": 24 * 60 * 60,  # Every day
                       "all": 48 *60 * 60}  # Every 2 days
    while True:
        with lock:  # Using lock to be sure that 2 chromium threads won't start at the same time because they both create a screenshot.png file
            os.system('chromium-browser --headless --disable-gpu --screenshot "https://bitscreener.com/coins/garlicoin?timeframe={}&chart_type=candle&chart_unit=usd&is_global=true" --window-size=1920,1080'.format(time_range))
            os.system('mv screenshot.png screenshot_{}.png'.format(time_range))
            os.system('convert screenshot_{0}.png -crop 1213x500+343+420 {0}.png'.format(time_range))
        time.sleep(sleeping_ranges[time_range])


lock = threading.Lock()

# Using threads so that time.sleep() doesn't stop all other updates
for time_range in ["1d", "1w", "1m", "3m", "6m", "all"]:
    GraphThread(time_range)
