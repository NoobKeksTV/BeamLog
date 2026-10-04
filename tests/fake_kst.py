"""Nachgebauter KST-Telnet-Server für Tests (Login, Menü, Nachrichten, /SHOW USER)."""
import asyncio


class FakeKst:
    def __init__(self):
        self.server = None
        self.port = 0
        self.received: list[str] = []
        self.writers: list[asyncio.StreamWriter] = []

    async def start(self):
        self.server = await asyncio.start_server(self.handle, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def stop(self):
        for w in self.writers:
            w.close()
        self.server.close()
        await self.server.wait_closed()

    async def drop_all(self):
        """Simuliert Internetausfall: alle Client-Verbindungen hart schließen, Server läuft weiter."""
        for w in self.writers:
            w.close()
        self.writers.clear()

    async def push(self, line: str):
        for w in self.writers:
            w.write((line + "\r\n").encode("latin-1"))
            await w.drain()

    async def handle(self, reader, writer):
        self.writers.append(writer)
        writer.write(b"This telnet access is reserved to HAM only\r\nYour IP address is 127.0.0.1\r\nLogin:")
        await writer.drain()
        user = (await reader.readline()).decode().strip()
        writer.write(b"Password:")
        await writer.drain()
        pw = (await reader.readline()).decode().strip()
        if pw != "secret":
            writer.write(b"\r\nLogin:")
            await writer.drain()
            return
        writer.write(b"50/70 MHz..............1\r\n144/432 MHz............2\r\nMicrowave..............3\r\nYour choice           :")
        await writer.drain()
        room = (await reader.readline()).decode().strip()
        writer.write(f"1200Z {user} 144/432 MHz chat>\r\n".encode())
        await writer.drain()
        while True:
            raw = await reader.readline()
            if not raw:
                break
            line = raw.decode("latin-1").strip()
            self.received.append(line)
            if line.upper() == "/SHOW USER":
                writer.write(b"DL8NAS           JN59LE Klaus\r\n(DF7KF)          JO30XX Peter\r\nVU2CPL           MK83TE Manoj\r\nDN2LH-2          JO31AA Lars\r\nON4KST           JO20AA Server\r\n")
                writer.write(f"1201Z {user} 144/432 MHz chat>\r\n".encode())
            elif line.upper() == "/FAKEMSGS":
                writer.write(f"1203Z DL8NAS Klaus> ({user})  hallo an dich\r\n".encode())
                writer.write(b"1204Z DL8NAS Klaus> (DF7KF)  an peter, nicht an dich\r\n")
                writer.write(b"1205Z DL8NAS Klaus> cq cq oeffentlich\r\n")
                writer.write(f"1206Z {user}-2 Lars> (OK1ABC)  aus anderem Client\r\n".encode())
            elif line.upper().startswith("/CQ "):
                _, to, *rest = line.split(" ")
                writer.write(f"1202Z {user} Lars> ({to})  {' '.join(rest)}\r\n".encode())
            elif line:
                writer.write(f"1202Z {user} Lars> {line}\r\n".encode())
            await writer.drain()
