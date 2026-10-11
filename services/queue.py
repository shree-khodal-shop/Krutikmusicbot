import asyncio
from typing import Dict, List, Optional

class QueueItem:
    def __init__(self, title: str, url: str, duration: Optional[int], user_name: str, user_id: int, file_path: Optional[str] = None):
        self.title = title
        self.url = url
        self.duration = duration
        self.user_name = user_name
        self.user_id = user_id
        self.file_path = file_path

class MusicQueue:
    def __init__(self):
        self.queues: Dict[int, List[QueueItem]] = {}
        self.locks: Dict[int, asyncio.Lock] = {}

    def _get_lock(self, chat_id: int) -> asyncio.Lock:
        if chat_id not in self.locks:
            self.locks[chat_id] = asyncio.Lock()
        return self.locks[chat_id]

    async def add_item(self, chat_id: int, item: QueueItem):
        async with self._get_lock(chat_id):
            if chat_id not in self.queues:
                self.queues[chat_id] = []
            self.queues[chat_id].append(item)

    async def get_next(self, chat_id: int) -> Optional[QueueItem]:
        async with self._get_lock(chat_id):
            if chat_id in self.queues and self.queues[chat_id]:
                return self.queues[chat_id].pop(0)
            return None

    async def peek(self, chat_id: int) -> Optional[QueueItem]:
        async with self._get_lock(chat_id):
            if chat_id in self.queues and self.queues[chat_id]:
                return self.queues[chat_id][0]
            return None

    async def get_queue(self, chat_id: int) -> List[QueueItem]:
        async with self._get_lock(chat_id):
            return list(self.queues.get(chat_id, []))

    async def clear_queue(self, chat_id: int):
        async with self._get_lock(chat_id):
            if chat_id in self.queues:
                self.queues[chat_id].clear()

queue_manager = MusicQueue()
