"""
Альбомы VIBEMP3 — пользовательские именованные плейлисты.

Альбом — это просто имя + упорядоченный список путей к mp3-файлам,
которые пользователь сам туда добавил (треки физически остаются на диске
там же, где были; альбом лишь хранит ссылки на них, как обычный плейлист
в любом музыкальном приложении).

Хранение: один JSON-файл albums.json в папке приложения со списком всех
альбомов. Формат:
{
  "albums": [
    {"name": "Вечерний плейлист", "tracks": ["C:/Music/a.mp3", "C:/Music/b.mp3"]},
    ...
  ]
}
"""

import json
import os


def _albums_path(base_dir: str) -> str:
    return os.path.join(base_dir, "albums.json")


class Album:
    """Один альбом: имя + список путей к трекам."""

    def __init__(self, name: str, tracks: list[str] | None = None):
        self.name = name
        self.tracks: list[str] = list(tracks) if tracks else []

    def to_dict(self) -> dict:
        return {"name": self.name, "tracks": self.tracks}

    @classmethod
    def from_dict(cls, data: dict) -> "Album":
        return cls(data.get("name", "Без названия"), data.get("tracks", []))

    def add_tracks(self, filepaths: list[str]) -> int:
        """Добавляет треки в конец альбома, пропуская уже имеющиеся. Возвращает число добавленных."""
        added = [p for p in filepaths if p not in self.tracks]
        self.tracks.extend(added)
        return len(added)

    def remove_track_at(self, index: int):
        if 0 <= index < len(self.tracks):
            del self.tracks[index]

    def remove_track(self, filepath: str):
        if filepath in self.tracks:
            self.tracks.remove(filepath)


class AlbumLibrary:
    """Коллекция всех альбомов пользователя + персистентность в albums.json."""

    def __init__(self, base_dir: str):
        self._base_dir = base_dir
        self.albums: list[Album] = []

    # ---------- CRUD ----------

    def create_album(self, name: str) -> Album:
        """Создаёт новый альбом с уникальным именем (добавляет суффикс при коллизии) и добавляет в библиотеку."""
        unique_name = self._make_unique_name(name)
        album = Album(unique_name)
        self.albums.append(album)
        return album

    def _make_unique_name(self, desired_name: str) -> str:
        existing = {a.name for a in self.albums}
        if desired_name not in existing:
            return desired_name
        i = 2
        while f"{desired_name} ({i})" in existing:
            i += 1
        return f"{desired_name} ({i})"

    def delete_album(self, name: str) -> bool:
        for i, album in enumerate(self.albums):
            if album.name == name:
                del self.albums[i]
                return True
        return False

    def get_album(self, name: str) -> Album | None:
        for album in self.albums:
            if album.name == name:
                return album
        return None

    def rename_album(self, old_name: str, new_name: str) -> bool:
        album = self.get_album(old_name)
        if album is None or not new_name.strip():
            return False
        album.name = self._make_unique_name(new_name.strip())
        return True

    # ---------- Персистентность ----------

    def to_dict(self) -> dict:
        return {"albums": [a.to_dict() for a in self.albums]}

    def load(self, path: str | None = None):
        path = path or _albums_path(self._base_dir)
        if not os.path.isfile(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.albums = [Album.from_dict(d) for d in data.get("albums", [])]
        except (OSError, json.JSONDecodeError) as e:
            print(f"[VIBEMP3] Не удалось загрузить альбомы ({path}): {e}")

    def save(self, path: str | None = None):
        path = path or _albums_path(self._base_dir)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        except OSError as e:
            print(f"[VIBEMP3] Не удалось сохранить альбомы ({path}): {e}")
