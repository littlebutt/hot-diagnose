import asyncio
from websockets import connect


async def make_conn(uri):
    async with connect(uri) as websocket:
        while True:
            res = await websocket.recv()
            print(str(res))


if __name__ == '__main__':
    asyncio.run(make_conn("ws://localhost:8765"))