import asyncio
from pyppeteer import launch
import os
import time

async def main():
    i = 0
    browser = await launch(args=["--no-sandbox"])
    while True:
        try:
            for time_range in ["1d", "1w", "1m"]:
                if (time_range == "1w" and not i%3==0) or (time_range == "1m" and not i%6==0):
                    continue
                page = await browser.newPage()
                await page.setViewport({'width': 1920, 'height': 1080})
                await page.goto('https://bitscreener.com/coins/nimiq?timeframe={}&chart_type=candle'.format(time_range))
                await asyncio.sleep(5)
                await page.screenshot({'path': 'screenshot.png'})

                os.system('mv screenshot.png {}.png'.format(time_range))
                os.system('convert {0}.png -crop 1000x370+480+265 {0}.png'.format(time_range))
                print("Updated {} at {}".format(time_range,time.asctime(time.localtime(time.time()))
                await page.close()

            i += 1
            await asyncio.sleep(300)
        except KeyboardInterrupt:
            await browser.close()
            break

asyncio.get_event_loop().run_until_complete(main())
