"""
import os
import time
import threading
import requests
import sqlite3

from bs4 import BeautifulSoup


class GraphThread(threading.Thread):
    def __init__(self, time_range):
        threading.Thread.__init__(self, target=grab_chart, args=(time_range,))
        self.start()

class ExchangeThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self, target=grab_exchanges)
        self.start()

class CMC_API_Thread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self, target=update_cmc_api)
        self.start()

class SaveTickerThread(threading.Thread):
    def __init__(self, ticker, timestamp, table, period):
        threading.Thread.__init__(self, target=save_ticker_db, args=(ticker, timestamp, table, period,))
        self.start()

class RequestsThread(threading.Thread):
    def __init__(self, url):
        self._return = []
        threading.Thread.__init__(self, target=get_ticker, args=(url, self._return,))
        self.start()
    def join(self):
        threading.Thread.join(self)
        return self._return[0]


def get_ticker(url, _return):
    try:
        _return.append(requests.get(url, timeout=10))
    except requests.Timeout:
        _return.append(None)


def update_cmc_api():
    while True:
        try:
            r = requests.get("https://api.coinmarketcap.com/v2/listings/", timeout=10)
        except requests.Timeout:
            r = None

        if r:
            sqls = []
            for item in r.json()["data"]:
                sqls.append("INSERT INTO `cmc_api` (`id`, `symbol`) VALUES ('{0}', '{1}');".format(item["id"], item["symbol"]))

            with lock:
                with sqlite3.connect("db.sqlite3") as db:
                    cursor = db.cursor()
                    cursor.execute("DROP TABLE `cmc_api`;")
                    cursor.execute("CREATE TABLE `cmc_api` (" \
                                   "`id`    INTEGER NOT NULL UNIQUE," \
                                   "`symbol`    TEXT NOT NULL," \
                                   "PRIMARY KEY(`id`,`symbol`));")
                    for sql in sqls:
                        cursor.execute(sql)
                    db.commit()

        time.sleep(60 * 60)


def save_ticker_db(ticker, timestamp, table, period):
    # Get the last entry in the DB
    with lock:
        with sqlite3.connect("db.sqlite3") as db:
            cursor = db.cursor()
            cursor.execute("SELECT * FROM `{}` ORDER BY `id` DESC LIMIT 1;".format(table))
            # DB columns : id, timestamp, open, close, high, low
            id_db, timestamp_db, open_db, close_db, high, low = cursor.fetchone()

    sqls = []
    # Check if timestamp is < than the one on the DB + 15 minutes
    if timestamp < timestamp_db + period:
        # Update the close price if needed
        if close_db != ticker:
            sqls.append("UPDATE `{0}` SET `close` = '{1}' WHERE `id` = {2};".format(table, ticker, id_db))
        # Check if price is higher than H or lower than L and update H & L accordingly
        if ticker > high:
            sqls.append("UPDATE `{0}` SET `high` = '{1}' WHERE `id` = {2};".format(table, ticker, id_db))
        elif ticker < low:
            sqls.append("UPDATE `{0}` SET `low` = '{1}' WHERE `id` = {2};".format(table, ticker, id_db))
    else:
        # Set the close price at ticker and set a new record using timestamp and open, low & high price
        sqls.append("UPDATE `{0}` SET `close` = '{1}' WHERE `id` = {2};".format(table, ticker, id_db))
        if ticker > high:
            sqls.append("UPDATE `{0}` SET `high` = '{1}' WHERE `id` = {2};".format(table, ticker, id_db))
        elif ticker < low:
            sqls.append("UPDATE `{0}` SET `low` = '{1}' WHERE `id` = {2};".format(table, ticker, id_db))
        sqls.append("INSERT INTO `{0}` (`timestamp`, `open`, `close`, `high`, `low`) " \
                    "VALUES ({1}, {2}, {2}, {2}, {2})".format(table, timestamp_db + period, ticker))

    if sqls:
        with lock:
            with sqlite3.connect("db.sqlite3") as db:
                cursor = db.cursor()
                for sql in sqls:
                    cursor.execute(sql)
                db.commit()


def grab_chart(time_range):
    sleeping_ranges = {"1d": 5 * 60,       # Updates every 5 minutes
                       "1w": 60 * 60,       # Updates every hour
                       "1m": 4 * 60 * 60,   # Updates every 4 hours
                       "3m": 11 * 60 * 60}  # Updates every 11 hours
    while True:
        with lock:  # Using lock to be sure that 2 chromium threads start at the same time because they both create a screenshot.png file
            os.system('chromium-browser --headless --disable-gpu --screenshot "https://bitscreener.com/coins/garlicoin?timeframe={}&chart_type=candle&chart_unit=usd&is_global=true" --window-size=1920,1080'.format(time_range))
            os.system('mv screenshot.png screenshot_{}.png'.format(time_range))
            os.system('convert screenshot_{0}.png -crop 1213x500+343+420 {0}.png'.format(time_range))
        time.sleep(sleeping_ranges[time_range])


def grab_exchanges():
    next_cleanup = int(time.time()) + 24 * 60 * 60
    while True:
        # Get exchanges' prices and store them in a database every minute
        d = {}

        try:
            ex = requests.get("https://coinmarketcap.com/currencies/garlicoin/#markets", timeout=10)
        except requests.Timeout:
            ex = None

        if ex:
            timestamp = int(time.time())
            soup = BeautifulSoup(ex.text, 'html.parser')
            table = soup.find('table', attrs={'id': 'markets-table'})
            table_body = table.find('tbody')

            rows = table_body.find_all('tr')
            for row in rows:
                p = row.find('span', class_="price")
                m = row.find_all("a")

                price = float(p.text.strip().replace("$", ""))
                name = "{0}_{1}".format(m[0].text, m[1].text)   # ie: name = "Trade Satoshi_GRLC/BTC"

                d[name] = price

            sql = "INSERT INTO `cmc_exchanges` "\
                  "(`timestamp`, `Trade Satoshi_GRLC/BTC`, `CoinFalcon_GRLC/BTC`, `CryptoBridge_GRLC/BTC`, `Nanex_GRLC/NANO`, " \
                  "`Trade Satoshi_GRLC/LTC`, `Trade Satoshi_GRLC/BCH`, `Trade Satoshi_GRLC/DOGE`, `Trade Satoshi_GRLC/USDT`, `CoinFalcon_GRLC/ETH`) " \
                  "VALUES " \
                  "('{0}', '{1}', '{2}', '{3}', '{4}', '{5}', '{6}', '{7}', '{8}', '{9}')"
            sql = sql.format(timestamp, d["Trade Satoshi_GRLC/BTC"], d["CoinFalcon_GRLC/BTC"], d["CryptoBridge_GRLC/BTC"],
                             d["Nanex_GRLC/NANO"], d["Trade Satoshi_GRLC/LTC"], d["Trade Satoshi_GRLC/BCH"],
                             d["Trade Satoshi_GRLC/DOGE"],d["Trade Satoshi_GRLC/USDT"], d["CoinFalcon_GRLC/ETH"])
            print(sql)
            with lock:
                with sqlite3.connect("db.sqlite3") as db:
                    cursor = db.cursor()
                    cursor.execute(sql)
                    db.commit()

        # Once daily clean the old data (older than 7 days)
        if time.time() >= next_cleanup:
            timestamp = int(time.time())
            limit_timestamp = timestamp - 7 * 24 * 60 * 60
            sql = "DELETE FROM `cmc_exchanges` WHERE `timestamp` <= {}".format(limit_timestamp)

            print(sql)
            with lock:
                with sqlite3.connect("db.sqlite3") as db:
                    cursor = db.cursor()
                    cursor.execute(sql)
                    db.commit()
            next_cleanup = timestamp + 24 * 60 * 60

        # Sleep for a minute
        time.sleep(60)


lock = threading.Lock()

# Using threads so that time.sleep() doesn't stop all other updates
ExchangeThread()
CMC_API_Thread()
for time_range in ["1d", "1w", "1m", "3m"]:
    GraphThread(time_range)

while True:
    # Get the current value of GRLC from CMC
    timestamp = int(time.time())
    cmc = RequestsThread("https://api.coinmarketcap.com/v2/ticker/2475/?convert=BTC").join()
    nanex = RequestsThread("https://nanex.co/api/public/ticker/grlcnano").join()
    cb = RequestsThread("https://api.crypto-bridge.org/api/v1/ticker").join()
    ts = RequestsThread("https://tradesatoshi.com/api/public/getticker?market=GRLC_BTC").join()

    if cmc:
        cmc_usd = float(cmc.json()["data"]["quotes"]["USD"]["price"])
        SaveTickerThread(cmc_usd, timestamp, "cmc_usd_1d", 15 * 60)
        SaveTickerThread(cmc_usd, timestamp, "cmc_usd_1w", 60 * 60)
        SaveTickerThread(cmc_usd, timestamp, "cmc_usd_1m", 4 * 60 * 60)
        SaveTickerThread(cmc_usd, timestamp, "cmc_usd_3m", 12 * 60 * 60)

        cmc_btc = float(cmc.json()["data"]["quotes"]["BTC"]["price"])
        SaveTickerThread(cmc_btc, timestamp, "cmc_btc_1d", 15 * 60)
        SaveTickerThread(cmc_btc, timestamp, "cmc_btc_1w", 60 * 60)
        SaveTickerThread(cmc_btc, timestamp, "cmc_btc_1m", 4 * 60 * 60)
        SaveTickerThread(cmc_btc, timestamp, "cmc_btc_3m", 12 * 60 * 60)

    if nanex:
        nanex = float(nanex.json()["last_trade"])
        SaveTickerThread(nanex, timestamp, "nanex_1d", 15 * 60)
        SaveTickerThread(nanex, timestamp, "nanex_1w", 60 * 60)
        SaveTickerThread(nanex, timestamp, "nanex_1m", 4 * 60 * 60)
        SaveTickerThread(nanex, timestamp, "nanex_3m", 12 * 60 * 60)

    if cb:
        for i in cb.json():
            if i["id"] == "GRLC_BTC":
                cb = float(i["last"])
        SaveTickerThread(cb, timestamp, "cb_1d", 15 * 60)
        SaveTickerThread(cb, timestamp, "cb_1w", 60 * 60)
        SaveTickerThread(cb, timestamp, "cb_1m", 4 * 60 * 60)
        SaveTickerThread(cb, timestamp, "cb_3m", 12 * 60 * 60)

    if ts:
        ts = float(ts.json()["result"]["last"])
        SaveTickerThread(ts, timestamp, "ts_1d", 15 * 60)
        SaveTickerThread(ts, timestamp, "ts_1w", 60 * 60)
        SaveTickerThread(ts, timestamp, "ts_1m", 4 * 60 * 60)
        SaveTickerThread(ts, timestamp, "ts_3m", 12 * 60 * 60)

    # TODO: CF ticker (uses wss not http)

    time.sleep((timestamp + 60) - int(time.time()))
"""
