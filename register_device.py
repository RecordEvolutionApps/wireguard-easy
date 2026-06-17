import asyncio
from ironflock import IronFlock
from datetime import datetime
import os

DEVICE_KEY = os.environ["DEVICE_KEY"]


async def main():
    # runs once after the connection joins the router
    print("########### Storing Device info ################")
    await ironflock.publish_to_table(
        "devices",
        {
            "tsp": datetime.now().astimezone().isoformat(),
            "url": f"https://{DEVICE_KEY}-wireguard_easy-51821.app.ironflock.com",
            "state": 1,
        },
    )
    print("done")
    # returning here lets run() stop the connection cleanly — no manual stop needed


if __name__ == "__main__":
    ironflock = IronFlock(mainFunc=main)
    ironflock.run()  # blocks until main() returns, then shuts down
