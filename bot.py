import discord
import requests
import asyncio
import configparser
import os
import nimiqrpc
import pickle
import datetime

from time import sleep, time
from tabulate import tabulate
from bs4 import BeautifulSoup

coins = []
fiats = []
faucet = {}
prices = []

def main():
    nimiq = nimiqrpc.NimiqApi()

    client = discord.Client()
    conf = configparser.RawConfigParser()
    conf.read("config.txt")

    BOT_TOKEN = conf.get('bot_conf', 'BOT_TOKEN')
    PRICE_CHANNEL = conf.get('bot_conf', 'PRICE_CHANNEL')
    NIMIQX_KEY = conf.get('bot_conf', 'NIMIQX_KEY')
    NOMICS_KEY = conf.get('bot_conf', 'NOMICS_KEY')

    def format_num(num,dp):
        magnitude = 0
        while abs(num) >= 1000:
            magnitude += 1
            num /= 1000.0
        return '{}{}'.format('{:f}'.format(round(num,dp)).rstrip('0').rstrip('.'), ['', 'K', 'M', 'B', 'T'][magnitude])

    async def exchange():
        data = []
        try:
            ex = requests.get("https://coinmarketcap.com/currencies/nimiq/#markets", timeout=10)
            price = requests.get("https://api.coinpaprika.com/v1/ticker/nim-nimiq", timeout=10)
            nimex = requests.get("https://www.nimex.app/api/v1/info", timeout=10)
        except requests.Timeout:
            ex = None
            price = None
            nimex = None

        if ex and price:
            price_usd = float(price.json()["price_usd"])
            price_btc = float(price.json()["price_btc"])
            change_24h = float(price.json()["percent_change_24h"])
            mcap = float(price.json()["market_cap_usd"])

            total_v = 0 #Total volume
            total_vd = 0 #Total volume (dollars)

            soup = BeautifulSoup(ex.text, 'html.parser')
            table = soup.find('table', attrs={'id': 'markets-table'})
            table_body = table.find('tbody')

            rows = table_body.find_all('tr')
            for row in rows:
                p = row.find('span', class_="price")
                v = row.find('span', class_="volume")
                price_n = float(p.attrs['data-btc'])
                vol_n = float(v.attrs['data-native'])
                total_v += vol_n

                vol_str = format_num(vol_n,3)

                cols = row.find_all('td')
                cols = [ele.text.strip() for ele in cols]

                total_vd += float(cols[3][1:].replace(",", "")) #Remove $ sign and commas

                d = [cols[0], cols[1], cols[2], cols[3] + " ({})".format(vol_str),
                     cols[4] + " ({}sat)".format(str(round(price_n*1e8,1)))]
                data.append(d)

            total_vd = round(total_vd)
            total_v = round(total_v)

            if nimex:
                nimex = nimex.json()["table"]
                data.append(["N", "Nimex (manual)", "NIM/ETH", "${}".format(nimex["volume_usd"]), "${}".format(nimex["last_price_usd"])])

            #Add extra info
            data.append(["","","","",""])
            data.append(["",""," Aggregate:","${} {}".format(format_num(total_vd,6), format_num(total_v,3)),"${} {}sat".format(price_usd, round(price_btc*1e8,1))])
            data.append(["","","24h change:","{}%".format(change_24h),"",""])
            data.append(["","","Market cap:","${}".format(format_num(mcap,6))])
        return data
        

    @client.event
    async def on_ready():
        print('Logged in as {} <@{}>'.format(client.user.name, client.user.id))
        print('------')

    @client.event
    async def on_message(message):
        global faucet

        if message.content.startswith("!bal"):
            balance = round(nimiq.accounts()[0]['balance'] / 1e5,2)
            msg = "The faucet balance is currently {}NIM.\nDonations: NQ91 J1N0 FYRL HVM4 8PJY DDJB JP4K NQJB XY2Y.".format(balance)
            await client.send_message(message.channel, "```{}```".format(msg))

        if message.content.startswith("!claim") and message.server is not None:
            author = message.author.id
            cur = datetime.datetime.now()

            if author in faucet:
                last_claim = faucet[author]
                allowed = (cur - last_claim).total_seconds() / 3600 >= 1
            else:
                allowed = True

            if allowed:
                msg = message.content.split(" ")
                if len(msg) == 2 and len(msg[1]) == 36:
                    b = msg[1]
                    addr = ' '.join(b[i:i+4] for i in range(0,len(b),4))
                elif len(msg) == 10 and len(''.join(msg[1:])) == 36:
                    addr = ' '.join(msg[1:])
                else:
                    await client.send_message(message.channel, "```Usage: !claim [address]```")
                    return
                balance = nimiq.accounts()[0]['balance']
                if balance > 25138:
                    try:
                        tx = nimiq.send_transaction('NQ91 J1N0 FYRL HVM4 8PJY DDJB JP4K NQJB XY2Y', addr, 25000, 138)
                    except:
                        await client.send_message(message.channel, "```Error sending TX.```")
                    else:
                        faucet[author] = datetime.datetime.now()
                        await client.send_message(message.channel, "```Sent {}NIM tx:{}```".format(0.25, tx))
                else:
                    await client.send_message(message.channel, "```Faucet is empty!```")
            else:
                await client.send_message(message.channel, "```Can only claim every hour!```")
                return

        if message.content.startswith("!help"):
            msg =   "!exchange - shows prices across all exchanges.\n"\
                    "!conv [amount] [cur1] [cur2] - convert from currency 1 to 2.\n"\
                    "!graph [3h/6h/1d/1w/1m/3m] - show candle graph for selected time range.\n"\
                    "!network - get hashrate/network statistics.\n"\
                    "!bal - check balance of faucet\n"\
                    "!claim [addr] - claim 0.25NIM per hour"
            await client.send_message(message.channel, "```{}```".format(msg))

        if message.content.startswith("!network"):
            try:
                r = requests.get("https://api.nimiqx.com/network-stats/?api_key={}".format(NIMIQX_KEY))
            except:
                await client.send_message(message.channel, "Error: cannot reach Nimiqx API.")
            else:
                r = r.json()
                msg = "Hashrate (GH): {}\n"\
                      "Nim/day/kH: {}\n"\
                      "Block height: {}\n"\
                      "Block reward: {}".format(r["hashrate"]/1e9, r["nim_day_kh"], r["height"], r["last_reward"]/1e5)
                await client.send_message(message.channel, "```js\n{}```".format(msg))

        if message.content.startswith("!conv"):
            msg = message.content.replace("!conv ", "").split(" ")

            try:
                # Check if the amount sent by the user is a number
                float(msg[0].replace(",", "."))
            except ValueError:
                await client.send_message(message.channel, "Error: Unable to get the amount to convert.")
            else:
                if len(msg) == 3:
                    msg[1] = msg[1].upper()
                    msg[2] = msg[2].upper()
                    if msg[1] == msg[2]:
                        await client.send_message(message.channel, "```js\n{0} {1} = {0} {1}```".format(msg[1], msg[0]))
                    elif len(coins) > 0 and len(fiats) > 0:
                        price1, price2 = -1, -1
                        result = -1
                        cur1 = next((i for i in coins if i['currency'] == msg[1]), None)
                        cur2 = next((i for i in coins if i['currency'] == msg[2]), None)
                        if not cur1:
                            cur1 = next((i for i in fiats if i['currency'] == msg[1]), None)
                            price1 = float(cur1["rate"]) if cur1 else -1
                        if not cur2:
                            cur2 = next((i for i in fiats if i['currency'] == msg[2]), None)
                            price2 = float(cur2["rate"]) if cur2 else -1
                        if cur1 and cur2:
                            price1 = float(cur1["price"]) if price1 == -1 else price1
                            price2 = float(cur2["price"]) if price2 == -1 else price2
                            result = round(float(msg[0])*price1/price2,8) if (price1 != -1 and price2 != -1) else -1
                        if result != -1:
                            await client.send_message(message.channel, "{} {} = {} {}".format(msg[0],msg[1],result,msg[2]))
                        else:
                            await client.send_message(message.channel, "Currencies provided not supported. Use 3 letter code for FIAT, CMC code for CRYPTO.")
                    else:
                        await client.send_message(message.channel, "Conversion rates unavailable.")
                else:
                    error_txt = "Not enough parameters given : `!conv [amount] [cur1] [cur2]`"
                    await client.send_message(message.channel, error_txt)

        if message.content.startswith("!graph"):
            msg = message.content.replace("!graph ", "").split(" ")
            if os.path.isfile("{}.png".format(msg[0].lower())):
                await client.send_file(message.channel,"{}.png".format(msg[0].lower()))
            elif message.content == "!graph" or message.content == "!graph ":
                await client.send_file(message.channel,"1d.png")
            else:
                await client.send_message(message.channel, "Error: Unable to grab chart. Options are !graph [3h/6h/1d/1w/1m/3m].")

        if message.content.startswith("!exchange"):
            if len(prices) == 0:
                await client.send_message(message.channel, "Error : Couldn't reach CoinMarketCap.")
            else:
                table = tabulate(prices, headers=["No", "Exchange", "Pair", "Volume (native)", "Price (BTC)"])
                x = await client.send_message(message.channel, "```js\n{}```".format(table))
                return x

    async def background_update():
        global prices
        global coins
        global fiats

        await client.wait_until_ready()
        channel = discord.Object(id=PRICE_CHANNEL)

        while not client.is_closed:
            try:
                coins_r = requests.get("https://api.nomics.com/v1/prices?key={}".format(NOMICS_KEY))
                fiats_r = requests.get("https://api.nomics.com/v1/exchange-rates?key={}".format(NOMICS_KEY))
            except:
                coins = []
                fiats = []
            else:
                coins = coins_r.json()
                fiats = fiats_r.json()

            prices = await exchange()
            #Get aggregate price from table
            if len(prices) >= 3:
                p = prices[-3][4]
                await client.change_presence(game=discord.Game(name=p))
            else:
                await client.change_presence(game=discord.Game(name='Fetch error'))
            await asyncio.sleep(60)

    client.loop.create_task(background_update())
    client.run(BOT_TOKEN)

if __name__ == "__main__":
    main()