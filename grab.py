import requests
from bs4 import BeautifulSoup

d = {}

r = requests.get("https://coinpaprika.com/coin/nim-nimiq/#!exchanges", timeout=10)
soup = BeautifulSoup(r.text, 'html.parser')

table = soup.find('table', attrs={'id': 'cp-markets-table'})
table_body = table.find('tbody')

rows = table_body.find_all('tr')
for row in rows:
    #print(row.find_all('td'))
    p = row.find('span')
    #n = row.find('span', class_="uk-text-middle")
    print(p.attrs['title'])
    #m = row.find_all("a")

    #price = float(p.text)
    #name = "{0}_{1}".format(m[0].text, m[1].text)   # ie: name = "Trade Satoshi_GRLC/BTC"

    #d[name] = price
