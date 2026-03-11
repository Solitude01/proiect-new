"""
WebSocket Connection Manager with Room Isolation
Ensures data from different instances remains isolated.
"""

from typing import Dict, List, Set
from fastapi import WebSocket
import asyncio


class ConnectionManager:
    """
    Manages WebSocket connections with room-based isolation.
    Each instance has its own room, and broadcasts only go to that room.
    """

    def __init__(self):
        # Rooms: instance_id -> List of WebSocket connections
        self.rooms: Dict[str, List[WebSocket]] = {}
        # Track connection metadata for debugging
        self.connection_info: Dict[WebSocket, Dict] = {}

    async def connect(self, websocket: WebSocket, instance_id: str) -> bool:
        """
        Accept a WebSocket connection and add it to the instance room.

        Args:
            websocket: The WebSocket connection
            instance_id: The instance ID for room isolation

        Returns:
            True if connection was successful
        """
        try:
            await websocket.accept()

            # Initialize room if needed
            if instance_id not in self.rooms:
                self.rooms[instance_id] = []

            # Add to room
            self.rooms[instance_id].append(websocket)

            # Track connection metadata
            self.connection_info[websocket] = {
                "instance_id": instance_id,
                "client": getattr(websocket, "client", None)
            }

            print(f"[WebSocket] Client connected to room '{instance_id}'. Room size: {len(self.rooms[instance_id])}")
            return True

        except Exception as e:
            print(f"[WebSocket] Error accepting connection: {e}")
            return False

    def disconnect(self, websocket: WebSocket, instance_id: str) -> None:
        """
        Remove a WebSocket connection from its room.

        Args:
            websocket: The WebSocket connection to remove
            instance_id: The instance ID of the room
        """
        try:
            # Remove from room
            if instance_id in self.rooms:
                if websocket in self.rooms[instance_id]:
                    self.rooms[instance_id].remove(websocket)
                    print(f"[WebSocket] Client disconnected from room '{instance_id}'. Room size: {len(self.rooms[instance_id])}")

                # Clean up empty rooms
                if not self.rooms[instance_id]:
                    del self.rooms[instance_id]
                    print(f"[WebSocket] Room '{instance_id}' removed (empty)")

            # Remove from connection tracking
            if websocket in self.connection_info:
                del self.connection_info[websocket]

        except Exception as e:
            print(f"[WebSocket] Error during disconnect: {e}")

    async def broadcast_to_room(self, instance_id: str, message: dict) -> int:
        """
        Broadcast a message to all clients in a specific room.

        Args:
            instance_id: The target instance/room
            message: The message to broadcast (will be JSON serialized)

        Returns:
            Number of clients that received the message
        """
        if instance_id not in self.rooms:
            return 0

        disconnected = []
        sent_count = 0

        for ws in self.rooms[instance_id]:
            try:
                await ws.send_json(message)
                sent_count += 1
            except Exception as e:
                print(f"[WebSocket] Error sending to client in room '{instance_id}': {e}")
                disconnected.append(ws)

        # Clean up disconnected clients
        for ws in disconnected:
            self.disconnect(ws, instance_id)

        return sent_count

    def get_room_size(self, instance_id: str) -> int:
        """Get the number of connected clients in a room"""
        return len(self.rooms.get(instance_id, []))

    def get_all_rooms(self) -> Dict[str, int]:
        """Get a summary of all rooms and their sizes"""
        return {room_id: len(connections) for room_id, connections in self.rooms.items()}

    async def send_personal_message(self, websocket: WebSocket, message: dict) -> bool:
        """
        Send a message to a specific WebSocket connection.

        Args:
            websocket: The target WebSocket
            message: The message to send

        Returns:
            True if message was sent successfully
        """
        try:
            await websocket.send_json(message)
            return True
        except Exception as e:
            print(f"[WebSocket] Error sending personal message: {e}")
            # Mark for cleanup
            instance_id = self.connection_info.get(websocket, {}).get("instance_id")
            if instance_id:
                self.disconnect(websocket, instance_id)
            return False

    async def close_all_connections(self) -> None:
        """Close all WebSocket connections (for shutdown)"""
        for instance_id, connections in list(self.rooms.items()):
            for ws in connections:
                try:
                    await ws.close()
                except Exception:
                    pass
        self.rooms.clear()
        self.connection_info.clear()


# Global connection manager instance
manager = ConnectionManager()
