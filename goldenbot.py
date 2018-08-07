import discord
import requests
import asyncio
import configparser
import os
import sqlite3
import re
import logging

from time import sleep, time
from tabulate import tabulate
from bs4 import BeautifulSoup


logging.basicConfig(filename='logs/goldenbot.log', level=logging.INFO, format='%(asctime)s -- %(levelname)s -- %(message)s')


def cmc_api_url(symbol):
    with sqlite3.connect("db.sqlite3") as db:
        cursor = db.cursor()
        cursor.execute("SELECT `id` FROM `cmc_api` WHERE `symbol` = '{}'".format(symbol.upper()))
        data = cursor.fetchone()

    return "https://api.coinmarketcap.com/v2/ticker/{}/".format(data[0])


def is_fiat(name):
    # TODO: put the tuple in the config file
    if name in ("USD", "EUR", "GBP", "AUD"):
        return True
    else:
        return False


def is_crypto(name):
    with sqlite3.connect("db.sqlite3") as db:
        cursor = db.cursor()
        cursor.execute("SELECT `symbol` FROM `cmc_api`")
        datas = cursor.fetchall()

    cryptos = [data[0] for data in datas]

    if name.upper() in cryptos:
        return True
    else:
        return False


def faucet(url):
    try:
        r = requests.get(url, timeout=10)
    except requests.Timeout:
        return None, None
    else:
        soup = BeautifulSoup(r.text, 'html.parser')
        if url == "https://faucet.garlicoin.co.uk/":
            h2 = soup.find('h2')
            balance = "₲ {}".format(h2.text.replace("Current Balance ", "").replace(" GRLC", ""))
            address = soup.find("span", class_="badge badge-light")
            donation = address.text
            return balance, donation

        elif url == "https://faucetgarlico.in/":
            p = soup.find_all("p", style="color: #FFFFFF; text-align:center")
            balance = "₲ {}".format(p[-1].text)
            address = soup.find(string=re.compile("Donate to the faucet"))
            donation = address.split(": ")[-1]
            return balance, donation

        elif url == "https://faucet.garlicpool.org/":
            p = soup.find(string=re.compile("GRLC in faucet"))
            balance = "₲ {}".format(p.split(":\n")[-1])
            address = soup.find(string=re.compile("Please donate"))
            donation = address.split(": ")[-1]
            return balance, donation

        elif url == "https://www.twitch.tv/thedrashy":
            balance = "N/A"
            donation = "GfrzZTqhako6n4prYesPSg5uD9FLZmKynH"
            return balance, donation


def apply_rate(value, rate, currency):
    # value = $0.053408 and rate = 7.07003
    # Converting value to a float
    value = float(value.replace("$", ""))

    # Apply the rate on the value
    result = value/rate

    # Format the output
    formats = {"BTC": ("฿", 8), "ETH": ("Ξ", 8), "LTC": ("Ł", 8), "NANO": ("η", 5),
               "GRLC": ("₲", 5), "EUR": ("€", 6), "GBP": ("£", 6), "AUD": ("$", 6)}

    try:
        formater = "{0}{{:.{1}f}}".format(*formats[currency.upper()])
    except KeyError:
        formater = "{0} {{:.{1}f}}".format(currency.upper(), 6)

    return formater.format(result)


def get_fiats():
    try:
        usd_eur = requests.get("{}?convert=EUR".format(cmc_api_url("GRLC")), timeout=10)
        gbp = requests.get("{}?convert=GBP".format(cmc_api_url("GRLC")), timeout=10)
        aud = requests.get("{}?convert=AUD".format(cmc_api_url("GRLC")), timeout=10)
    except requests.Timeout:
        return None

    usd = usd_eur.json()["data"]["quotes"]["USD"]["price"]
    eur = usd_eur.json()["data"]["quotes"]["EUR"]["price"]
    gbp = gbp.json()["data"]["quotes"]["GBP"]["price"]
    aud = aud.json()["data"]["quotes"]["AUD"]["price"]

    return float(usd), float(eur), float(gbp), float(aud)


def get_cryptos():
    try:
        grlc_btc = requests.get("{}?convert=BTC".format(cmc_api_url("GRLC")), timeout=10)
        eth_btc = requests.get("{}?convert=BTC".format(cmc_api_url("ETH")), timeout=10)
        ltc_btc = requests.get("{}?convert=BTC".format(cmc_api_url("LTC")), timeout=10)
        nano_btc = requests.get("{}?convert=BTC".format(cmc_api_url("NANO")), timeout=10)
    except requests.Timeout:
        return None

    grlc_btc = float(grlc_btc.json()["data"]["quotes"]["BTC"]["price"])
    eth_btc = float(eth_btc.json()["data"]["quotes"]["BTC"]["price"])
    ltc_btc = float(ltc_btc.json()["data"]["quotes"]["BTC"]["price"])
    nano_btc = float(nano_btc.json()["data"]["quotes"]["BTC"]["price"])

    grlc_eth = grlc_btc / eth_btc
    grlc_ltc = grlc_btc / ltc_btc
    grlc_nano = grlc_btc / nano_btc

    return grlc_btc, grlc_eth, grlc_ltc, grlc_nano


def fstr(max_size, value):
    # Get the len of the integer part
    i_part = len(str(int(value)))
    f_part = max_size - i_part - 1

    formater = "{" + ":.{}f".format(f_part) + "}"

    return formater.format(value)


def get_change_db(column):
    # Calculate 24h ago timestamps
    min_t = int(time()) - 24 * 60 * 60

    # Get prices that are >= min_t
    sql = "SELECT `{0}` FROM `cmc_exchanges` WHERE `timestamp` >= {1} AND `timestamp` <= {2};".format(column, min_t, min_t + 120)
    with sqlite3.connect("db.sqlite3") as db:
        cursor = db.cursor()
        cursor.execute(sql)
        result = cursor.fetchone()

    if result:
        return result[0]
    else:
        return None


def main():
    client = discord.Client()
    conf = configparser.RawConfigParser()
    conf.read("config.txt")
    cooldown = {}

    BOT_TOKEN = conf.get('goldenbot_conf', 'BOT_TOKEN')
    PRICE_CHANNEL = conf.get('goldenbot_conf', 'PRICE_CHANNEL')

    async def not_spam(client, message, cooldown):
        # cooldown: {User/Member: [cooldown timestamp, number of messages]}
        # 6 messages every minute, bot will alert when cooled down and every attempt will double the remaining time

        # Check if the message starts with !
        if message.content.startswith("!"):
            # Check if the message author is in cooldown
            if message.author in cooldown:
                # Check if current timestamp >= cooldown timestamp
                if time() >= cooldown[message.author][0]:
                    # Reset the counter and set a new cooldown timestamp
                    cooldown[message.author] = [int(time()) + 60, 1]
                    return True
                elif cooldown[message.author][1] < 5:
                    # User is in the limits
                    cooldown[message.author][1] += 1
                    return True
                elif cooldown[message.author][1] == 5:
                    # Warn the user on the channel
                    await client.send_message(message.channel, "<@{}> You reached the limit of 6 commands in less than a minute, you can use the bot again in 1 minute.\nEvery attempt to use the bot during this period **will double the remaining time**.".format(message.author.id))
                    cooldown[message.author] = [int(time()) + 60, 6]
                    return False
                else:
                    cooldown[message.author][0] += cooldown[message.author][0] - int(time())
                    cooldown[message.author][1] += 1
                    # Inform the user by PM
                    remaining = int((cooldown[message.author][0] - int(time())) / 60)
                    await client.send_message(message.author, "<@{}> You reached the abuse limit, you can use the bot again in {} minutes.\nEvery attempt to use the bot during this period will double the remaining time.\n**STOP SPAMMING!**".format(message.author.id, remaining))
                    return False
            else:
                # Not spam
                cooldown[message.author] = [time(), 1]
                return True
        else:
            # Not a command so we don't need to do all the tests to find what command the user typed
            return False

    async def faucets(client, message, verbose=False):
            if verbose:
                tmp = await client.send_message(message.channel, "Acquiring data from the faucets...")
            urls = ["https://faucet.garlicoin.co.uk/",
                    "https://faucetgarlico.in/",
                    "https://faucet.garlicpool.org/",
                    "https://www.twitch.tv/thedrashy"]
            msg = []
            for url in urls:
                bal, addr = faucet(url)
                if verbose:
                    await client.edit_message(tmp, "Acquiring data from the faucets... [{}/{}]".format(urls.index(url) + 1, len(urls)))
                if bal and addr:
                    msg.append([url, bal, addr])
                else:
                    msg.append([url, "timeout", "timeout"])

            table = tabulate(msg, headers=["Faucet URL", "Current Balance", "Donation Address"])
            return await client.send_message(message.channel, "```\n{}\n```".format(table))


    async def convert_3(client, message, msg):
        # No rate given, get it from CoinMarketCap
        amount = float(msg[0].replace(",", ".")) # In case someone sends 10,2 GRLC instead of 10.2
        curr1 = msg[1].upper()
        curr2 = msg[2].upper()

        # FIAT -> FIAT
        if is_fiat(curr1) and is_fiat(curr2):
            # Get the exchange rate (using BTC as a middle value)
            fiat1_btc = await get_rate_crypto(client, message, "BTC", curr1, verbose=False)
            fiat2_btc = await get_rate_crypto(client, message, "BTC", curr2)

            if fiat1_btc and fiat2_btc:
                rate = fiat2_btc / fiat1_btc
                conv_amount = amount * rate
                await client.send_message(message.channel, "```{0} {1} = {2} {3:.6f} (rate: {4:.6f})```".format(curr1, msg[0], curr2, conv_amount, rate))

        # CRYPTO -> CRYPTO
        elif is_crypto(curr1) and is_crypto(curr2):
            # Get each crypto rate in BTC then calculate the rate
            crypto1_btc = await get_rate_crypto(client, message, curr1, "BTC", verbose=False)
            crypto2_btc = await get_rate_crypto(client, message, curr2, "BTC")

            if crypto1_btc and crypto2_btc:
                rate = crypto1_btc / crypto2_btc
                conv_amount = amount * rate
                await client.send_message(message.channel, "```{0} {1} = {2} {3:.8f} (rate: {4:.8f})```".format(curr1, msg[0], curr2, conv_amount, rate))

        # FIAT -> CRYPTO or CRYPTO -> FIAT
        elif (is_crypto(curr1) or is_fiat(curr1)) and (is_crypto(curr2) or is_fiat(curr2)):
            # Find the FIAT and ask CoinMarketCap for the crypto using the FIAT
            if is_crypto(curr1):
                fiat = curr2
                crypto = curr1
            else:
                fiat = curr1
                crypto = curr2

            rate = await get_rate_crypto(client, message, crypto, fiat)
            if rate:
                if fiat == curr1:
                    conv_amount = amount / rate
                    await client.send_message(message.channel, "```{0} {1} = {2} {3:.8f} (rate: {4:.8f})```".format(curr1, msg[0], curr2, conv_amount, 1/rate))
                else:
                    conv_amount = amount * rate
                    await client.send_message(message.channel, "```{0} {1} = {2} {3:.8f} (rate: {4:.8f})```".format(curr1, msg[0], curr2, conv_amount, rate))

        else:
            # One or both currencies aren't known
            await client.send_message(message.channel, "One (or both) currency entered is not supported.")


    async def convert_4(client, message, msg):
        try:
            float(msg[3].replace(",", "."))
        except ValueError:
            # The rate isn't a numeric value, so we use CoinMarketCap instead
            await convert_3(client, message, msg)
        else:
            # Make the calculation using the given rate
            amount = float(msg[0].replace(",", ".")) # In case someone sends 10,2 GRLC instead of 10.2
            curr1 = msg[1].upper()
            curr2 = msg[2].upper()
            rate = float(msg[3].replace(",", ".")) # In case someone sends 0,02 instead of 0.02

            conv_amount = amount * rate
            await client.send_message(message.channel, "```{0} {1} = {2} {3:.6f} (rate: {4:.6f})```".format(curr1, msg[0], curr2, conv_amount, rate))

    async def get_rate_crypto(client, message, crypto, fiat="USD", verbose=True):
        # Somehow https://api.coinmarketcap.com/v1/ticker/bitcoin/?convert=BTC doesn't give an error!
        try:
            if verbose:
                tmp = await client.send_message(message.channel, "Acquiring rates from CoinMarketCap...")
            datas = requests.get("{0}?convert={1}".format(cmc_api_url(crypto), fiat), timeout=10)
            if verbose:
                await client.edit_message(tmp, "Acquiring rates from CoinMarketCap... Done!")
        except requests.Timeout:
            if verbose:
                await client.edit_message(tmp, "Error : Couldn't reach CoinMarketCap (timeout)")
            return None

        price = datas.json()["data"]["quotes"][fiat]["price"]
        return float(price)

    async def exchange(client, message, currency=None, verbose=True):
        rate = None
        if currency:
            if is_crypto(currency):
                # Get the rate in USD of the crypto
                rate = await get_rate_crypto(client, message, currency.upper(), "USD", False)

            elif currency.upper() in ("EUR", "GBP", "AUD"):
                # Get the rate of GRLC in USD and the currency
                rate1 = await get_rate_crypto(client, message, "GRLC", "USD", False)
                rate2 = await get_rate_crypto(client, message, "GRLC", currency.upper(), False)
                rate = rate1/rate2
            else:
                if verbose:
                    await client.send_message(message.channel, "Unknown currency '{}' (Available : EUR, GBP, AUD, all CMC cryptos)".format(currency))

        data = []
        if verbose:
            tmp = await client.send_message(message.channel, "Acquiring exchange rates from CoinMarketCap...")
        try:
            ex = requests.get("https://coinmarketcap.com/currencies/garlicoin/#markets", timeout=10)
            price = requests.get("{}?convert=BTC".format(cmc_api_url("GRLC")), timeout=10)
        except requests.Timeout:
            ex = None
            price = None

        if ex and price:
            price_usd = float(price.json()["data"]["quotes"]["USD"]["price"])
            price_btc = float(price.json()["data"]["quotes"]["BTC"]["price"])
            change_24h = float(price.json()["data"]["quotes"]["USD"]["percent_change_24h"])
            mcap = float(price.json()["data"]["quotes"]["USD"]["market_cap"])

            total_v = 0 #Total volume
            total_vd = 0 #Total volume (dollars)

            if verbose:
                await client.edit_message(tmp, "Acquiring exchange rates from CoinMarketCap... Done!")
            soup = BeautifulSoup(ex.text, 'html.parser')
            table = soup.find('table', attrs={'id': 'markets-table'})
            table_body = table.find('tbody')

            rows = table_body.find_all('tr')
            for row in rows:
                #print(row)
                p = row.find('span', class_="price")
                v = row.find('span', class_="volume")
                price_n = float(p.attrs['data-native'])
                vol_n = float(v.attrs['data-native'])
                total_v += vol_n

                cols = row.find_all('td')
                cols = [ele.text.strip() for ele in cols]

                total_vd += float(cols[3][1:].replace(",", "")) #Remove $ sign and commas

                # Get the % change on 24h from the db
                price = float(p.text.strip().replace("$", ""))
                price_24h = get_change_db("{0}_{1}".format(cols[1], cols[2]))
                if price_24h:
                    change = (price / price_24h - 1) * 100
                    if change < 0:
                        change = "-{:.2f}%".format(change * -1)
                    elif change > 0:
                        change = "+{:.2f}%".format(change)
                    else:
                        change = "0.00%"
                else:
                    change = "N/A"

                d = [cols[0], cols[1], cols[2], cols[3] + " ({})".format(str(vol_n)),
                     cols[4] + " ({:.8f})".format(price_n), change]
                data.append(d)

            total_vd = str(round(total_vd))
            total_v = str(round(total_v))

            if rate:
                # Calculate the price in the currency selected
                data = [x + [apply_rate(x[4].split(" ")[0], rate, currency)] for x in data]
                table = tabulate(data, headers=["No", "Exchange", "Pair", "Volume (native)", "Price (native)",
                                                 "24h change", "Price ({})".format(currency.upper())])
            else:
                #Add extra info
                data.append(["","","","",""])
                data.append(["",""," Aggregate:","${0} {1}₲".format(total_vd, total_v),"${0} ฿{1:.8f}".format(price_usd, price_btc)])
                data.append(["","","24h change:","{}%".format(change_24h),"",""])
                data.append(["","","Market cap:","${}".format(mcap)])
                table = tabulate(data, headers=["No", "Exchange", "Pair", "Volume (native)", "Price (native)", "24h change"])

            x = await client.send_message(message.channel, "```js\n{}```".format(table))
            return x #For background task to delete message
        else:
            # Timeout
            if verbose:
                await client.edit_message(tmp, "Error : Couldn't reach CoinMarketCap (timeout)")

    @client.event
    async def on_ready():
        print('Logged in as {} <@{}>'.format(client.user.name, client.user.id))
        print('------')

    @client.event
    async def on_message(message):
        if await not_spam(client, message, cooldown):
            if message.content.startswith("!faucet"):
                # Get the url, current balance and donation address for each faucet
                await faucets(client, message, verbose=True)


            if message.content.startswith("!fiat"):
                # Get the GRLC price in USD, EUR, GBP & AUD
                tmp = await client.send_message(message.channel, "Acquiring fiat rates from CoinMarketCap...")
                fiats = get_fiats()
                if fiats:
                    await client.edit_message(tmp, "Acquiring fiat rates from CoinMarketCap... Done!")
                    symbols = [("USD", "$"), ("EUR", "€"), ("GBP", "£"), ("AUD", "$")]
                    data = [[symbols[i][0], "{0} {1}".format(symbols[i][1],fstr(9, fiats[i])), "₲ {}".format(fstr(9, 1/fiats[i]))] for i in range(4)]
                    table = tabulate(data, headers=["", "Garlicoin", "Fiat"])

                    await client.send_message(message.channel, "```js\n{}```".format(table))
                else:
                    # Timeout
                    await client.edit_message(tmp, "Error : Couldn't reach CoinMarketCap (timeout)")


            if message.content.startswith("!crypto"):
                # Get the GRLC price in BTC, ETH, LTC, NANO
                tmp = await client.send_message(message.channel, "Acquiring crypto rates from CoinMarketCap...")
                cryptos = get_cryptos()

                if cryptos:
                    await client.edit_message(tmp, "Acquiring crypto rates from CoinMarketCap... Done!")
                    symbols = [("BTC", "฿"), ("ETH", "Ξ"), ("LTC", "Ł"), ("NANO", "η")]
                    data = [[symbols[i][0], "{0} {1}".format(symbols[i][1],fstr(10, cryptos[i])), "₲ {}".format(fstr(10, 1/cryptos[i]))] for i in range(4)]
                    table = tabulate(data, headers=["", "Garlicoin", "Crypto"])

                    await client.send_message(message.channel, "```js\n{}```".format(table))
                else:
                    # Timeout
                    await client.edit_message(tmp, "Error : Couldn't reach CoinMarketCap (timeout)")


            if message.content.startswith("!graph"):
                msg = message.content.replace("!graph ", "").split(" ")
                if os.path.isfile("{}.png".format(msg[0].lower())):
                    await client.send_file(message.channel,"{}.png".format(msg[0].lower()))
                elif message.content == "!graph" or message.content == "!graph ":
                    await client.send_file(message.channel,"1d.png")
                else:
                    await client.send_message(message.channel, "Error: Unable to grab chart. Options are !graph [1d|1w|1m|3m|6m|all].")


            if message.content.startswith("!conv"):
                # !conv [amount] [currency1] [currency2] [rate (optional)] --> [currency1] [amount] = [currency2] [converted amount] ([rate])
                msg = message.content.replace("!conv ", "").split(" ")

                try:
                    # Check if the amount sent by the user is a number
                    float(msg[0].replace(",", "."))
                except ValueError:
                    # The amount isn't a numeric value
                    if len(msg) >= 2:
                        msg = ["1"] + msg
                        # Show a custom message if currency1 == currency2
                        if msg[1] == msg[2]:
                            await client.send_message(message.channel, "```js\n{0} {1} = {0} {1}```".format(msg[1], msg[0]))

                        # Check if there is a rate
                        elif len(msg) == 3:
                            await convert_3(client, message, msg)

                        elif len(msg) == 4:
                            await convert_4(client, message, msg)

                        else:
                            # Not enough parameters sent
                            error_txt = "Not enough parameters given : `!conv [amount] [cur1] [cur2] [rate (optional)]`\n" \
                                        "[cur1] and [cur2] can be : USD, EUR, GBP, AUD, GRLC, BTC, ETH, LTC or NANO"
                            await client.send_message(message.channel, error_txt)
                    else:
                        await client.send_message(message.channel, "Error: Unable to get the amount to convert.")

                else:
                    # Show a custom message if currency1 == currency2
                    if msg[1] == msg[2]:
                        await client.send_message(message.channel, "```js\n{0} {1} = {0} {1}```".format(msg[1], msg[0]))

                    # Check if there is a rate
                    elif len(msg) == 3:
                        await convert_3(client, message, msg)

                    elif len(msg) == 4:
                        await convert_4(client, message, msg)

                    else:
                        # Not enough parameters sent
                        error_txt = "Not enough parameters given : `!conv [amount] [cur1] [cur2] [rate (optional)]`\n" \
                                    "[cur1] and [cur2] can be : USD, EUR, GBP, AUD, GRLC, BTC, ETH, LTC or NANO"
                        await client.send_message(message.channel, error_txt)


            if message.content.startswith("!exchange"):
                if " " in message.content:
                    await exchange(client, message, currency=message.content.split(" ")[1])
                else:
                    await exchange(client, message)

            if message.content.startswith("!net"):
                tmp = await client.send_message(message.channel, "Acquiring data from CMC/garli.co.in...")
                try:
                    price = requests.get(cmc_api_url("GRLC"), timeout=10)
                    diff = requests.get("https://garli.co.in/api/getdifficulty", timeout=10)
                    blocks = requests.get("https://garli.co.in/api/getblockcount", timeout=10)
                    hrate = requests.get("https://garli.co.in/api/getnetworkhashps", timeout=10)
                    supply = requests.get("https://garli.co.in/ext/getmoneysupply", timeout=10)
                except requests.Timeout:
                    price = None

                if price:
                    await client.edit_message(tmp, "Acquiring data from CMC/garli.co.in... Done!")
                    price = round(float(price.json()["data"]["quotes"]["USD"]["price"]), 6)
                    diff = round(diff.json(), 2)
                    blocks = blocks.json()
                    hrate = round(float(hrate.json()) / 10e8, 2) # Convert to GH/s
                    supply = round(supply.json())

                    #Profitability in USD/Mh/day
                    profit = round(diff * 2**32 / 1e6 / 60 / 60.0 / 24 * price, 2)
                    table = tabulate([[price, diff, blocks, hrate, supply]], headers=["Price (USD)", "Difficulty", "Block", "Hashrate (GH/s)", "Supply"])
                    await client.send_message(message.channel, "```js\n{}```".format(table))
                    await client.send_message(message.channel, "```js\nProfitability ($/Mh/day): {}```".format(profit))
                else:
                    await client.edit_message(tmp, "Error : Couldn't reach CMC/garli.co.in (timeout)")

            if message.content.startswith("!help"):
                help_text = "<@{}>, I'm GoldenBot, I'm here to assist you during your trades!\n```" \
                            "!help     : Displays a list of commands and what they do\n" \
                            "!faucets  : Displays all faucets url, current balance and donation address\n" \
                            "!fiat     : Displays current price of GRLC in FIATs\n" \
                            "!crypto   : Displays current price of GRLC in Cryptos\n" \
                            "!net      : Displays price, difficulty, block, hashrate, supply and profitability\n\n" \
                            "!exchange : Displays all the current rates by exchange (optional: convert it in another currency)\n" \
                            "            Usage : !exchange [currency]\n" \
                            "            supported currencies: EUR, GBP, AUD, all CMC crytpos\n" \
                            "!graph    : Displays the price chart.\n" \
                            "            Usage : !graph [1d|1w|1m|3m]\n" \
                            "!conv     : Converts an amount of one currency to another\n" \
                            "            Usage: !conv [amount] [cur1] [cur2] [rate (optional)]\n" \
                            "            supported currencies: USD, EUR, GBP, AUD, all CMC crytpos" \
                            "```".format(message.author.id)
                await client.send_message(message.channel, help_text)

    async def background_update():
        #Displays/updates 1d graph and exchange info in PRICE_CHANNEL
        graph, exc, fct = None, None, None
        await client.wait_until_ready()
        channel = discord.Object(id=PRICE_CHANNEL)
        temp = await client.send_message(channel, '.') #Temporary message for exchange() function
        await client.delete_message(temp) #Delete before update

        while not client.is_closed:
            if graph: await client.delete_message(graph) #Delete before update
            if os.path.isfile("1d.png"):
                graph = await client.send_file(channel, "1d.png")
            if exc: await client.delete_message(exc)
            if fct: await client.delete_message(fct)
            exc = await exchange(client, temp, verbose=False)
            fct = await faucets(client, temp)

            await asyncio.sleep(5*60) #Every 5 minutes

    client.loop.create_task(background_update())

    client.run(BOT_TOKEN)


if __name__ == "__main__":
    while True:
        try:
            main()
        except ConnectionResetError:
            sleep(5)
