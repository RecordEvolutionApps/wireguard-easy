import asyncio
from ironflock import IronFlock
from datetime import datetime
import os

DEVICE_KEY = os.environ["DEVICE_KEY"]

async def main():
    ironflock = IronFlock()  # no mainFunc

    async def run_once(session, details):
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
        # schedule stop safely after current task
        asyncio.create_task(ironflock.component.stop())

    # attach the callback before starting
    ironflock.component.on_join(run_once)

    # start the component (blocking until stop is called)
    await ironflock.component.start()

if __name__ == "__main__":
    asyncio.run(main())