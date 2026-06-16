"""Сервис для работы с временными файлами проекта."""

import re
import shutil
from pathlib import Path
from uuid import uuid4

from fileoptimizer.exceptions import StorageError


class StorageService:
    """Сервис для создания, хранения и удаления временных файлов."""

    def __init__(self, base_dir: Path = Path("tmp/jobs")) -> None:
        """Инициализирует сервис временного хранения файлов."""
        self.base_dir = base_dir

    def create_job_dir(self) -> Path:
        """Создаёт папку отдельной задачи обработки."""
        job_dir = self.base_dir / uuid4().hex

        self.get_input_dir(job_dir)
        self.get_output_dir(job_dir)

        return job_dir

    @staticmethod
    def get_input_dir(job_dir: Path) -> Path:
        """Возвращает папку для исходных файлов задачи."""
        input_dir = job_dir / "input"
        input_dir.mkdir(parents=True, exist_ok=True)

        return input_dir

    @staticmethod
    def get_output_dir(job_dir: Path) -> Path:
        """Возвращает папку для обработанных файлов задачи."""
        output_dir = job_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        return output_dir
