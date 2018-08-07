import time
import requests
import sqlite3
import logging

from bs4 import BeautifulSoup


logging.basicConfig(filename='logs/database.log', level=logging.INFO, format='%(asctime)s -- %(levelname)s -- %(message)s')


def exchanges_price_grabber():
    logging.info("Exchanges price grabber started")
    d = {}

    try:
        ex = requests.get("https://coinmarketcap.com/currencies/garlicoin/#markets", timeout=10)
    except requests.Timeout:
        ex = None
        logging.error("CMC Timeout (https://coinmarketcap.com/currencies/garlicoin/#markets)")

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
              "(`timestamp`, `Trade Satoshi_GRLC/BTC`, `CoinFalcon_GRLC/BTC`, `CryptoBridge_GRLC/BTC`, " \
              "`Nanex_GRLC/NANO`, `Trade Satoshi_GRLC/LTC`, `Trade Satoshi_GRLC/BCH`, `Trade Satoshi_GRLC/DOGE`, " \
              "`Trade Satoshi_GRLC/USDT`, `CoinFalcon_GRLC/ETH`) VALUES " \
              "('{0}', '{1}', '{2}', '{3}', '{4}', '{5}', '{6}', '{7}', '{8}', '{9}')"
        sql = sql.format(timestamp, d["Trade Satoshi_GRLC/BTC"], d["CoinFalcon_GRLC/BTC"], d["CryptoBridge_GRLC/BTC"],
                         d["Nanex_GRLC/NANO"], d["Trade Satoshi_GRLC/LTC"], d["Trade Satoshi_GRLC/BCH"],
                         d["Trade Satoshi_GRLC/DOGE"],d["Trade Satoshi_GRLC/USDT"], d["CoinFalcon_GRLC/ETH"])

        logging.debug(sql)

        with sqlite3.connect("db.sqlite3") as db:
            cursor = db.cursor()
            cursor.execute(sql)
            db.commit()

    logging.info("Exchanges price grabber finished")


def update_cmc_api():
    logging.info("CMC API cryptos update started")
    try:
        r = requests.get("https://api.coinmarketcap.com/v2/listings/", timeout=10)
    except requests.Timeout:
        r = None
        logging.error("CMC API Timeout (https://api.coinmarketcap.com/v2/listings/)")

    if r:
        sqls = []
        for item in r.json()["data"]:
            sqls.append("INSERT INTO `cmc_api` (`id`, `symbol`) VALUES ('{0}', '{1}');".format(item["id"], item["symbol"]))

        with sqlite3.connect("db.sqlite3") as db:
            cursor = db.cursor()
            cursor.execute("DROP TABLE `cmc_api`;")
            cursor.execute("CREATE TABLE `cmc_api` (`id`    INTEGER NOT NULL UNIQUE," \
                           "`symbol`    TEXT NOT NULL, PRIMARY KEY(`id`,`symbol`));")
            for sql in sqls:
                # logging.debug(sql)
                cursor.execute(sql)
            db.commit()

    logging.info("CMC API cryptos update finished")


def daily_cleanup():
    logging.info("Daily cleanup started")
    timestamp = int(time.time())
    limit_timestamp = timestamp - 7 * 24 * 60 * 60
    sql = "DELETE FROM `cmc_exchanges` WHERE `timestamp` <= {}".format(limit_timestamp)

    logging.debug(sql)

    with sqlite3.connect("db.sqlite3") as db:
        cursor = db.cursor()
        cursor.execute(sql)
        db.commit()

    logging.info("Daily cleanup finished")


next_api_update = int(time.time())
next_cleanup = int(time.time()) + 24 * 60 * 60

while True:
    # Get exchanges' prices and store them in a database every minute
    exchanges_price_grabber()

    # Update the CMC API cryptos every hour
    if time.time() >= next_api_update:
        update_cmc_api()
        next_api_update = int(time.time()) + 60 * 60

    # Once daily clean the old data (older than 7 days)
    if time.time() >= next_cleanup:
        daily_cleanup()
        next_cleanup = int(time.time()) + 24 * 60 * 60

    # Sleep for a minute
    time.sleep(60)
