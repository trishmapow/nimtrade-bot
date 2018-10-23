import asyncio
from pyppeteer import launch
import os

async def main():
    i = 0
    browser = await launch(args=["--no-sandbox"])
    while True:
        try:
            for time_range in ["1d", "1w", "1m"]:
                if (time_range == "1w" and not i%12==0) or (time_range == "1m" and not i%24==0):
                    continue
                page = await browser.newPage()
                await page.setViewport({'width': 1920, 'height': 1080})
                await page.goto('https://bitscreener.com/coins/nimiq?timeframe={}&chart_type=candle'.format(time_range))
                await asyncio.sleep(5)
                await page.screenshot({'path': 'screenshot.png'})

                os.system('mv screenshot.png {}.png'.format(time_range))
                os.system('convert {0}.png -crop 950x370+500+265 {0}.png'.format(time_range))

            i += 1
            await asyncio.sleep(300)
        except KeyboardInterrupt:
            await browser.close()
            break

asyncio.get_event_loop().run_until_complete(main())
