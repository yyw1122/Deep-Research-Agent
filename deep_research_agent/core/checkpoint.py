"""检查点管理"""
import os
import json
import pickle
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class DateTimeEncoder(json.JSONEncoder):
    """自定义JSON编码器，处理datetime对象"""

    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


class CheckpointManager:
    """检查点管理器"""

    def __init__(self, checkpoint_dir: str = "./checkpoints"):
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def _get_checkpoint_path(self, task_id: str) -> Path:
        """获取检查点文件路径"""
        return self.checkpoint_dir / f"{task_id}.json"

    def save_checkpoint(self, task_id: str, state: Dict[str, Any]) -> bool:
        """保存检查点"""
        try:
            checkpoint_path = self._get_checkpoint_path(task_id)
            checkpoint_data = {
                "task_id": task_id,
                "timestamp": datetime.now().isoformat(),
                "state": state
            }
            with open(checkpoint_path, "w", encoding="utf-8") as f:
                json.dump(checkpoint_data, f, ensure_ascii=False, indent=2, cls=DateTimeEncoder)
            logger.info(f"检查点已保存: {task_id}")
            return True
        except Exception as e:
            logger.error(f"保存检查点失败: {e}")
            return False

    def load_checkpoint(self, task_id: str) -> Optional[Dict[str, Any]]:
        """加载检查点"""
        try:
            checkpoint_path = self._get_checkpoint_path(task_id)
            if not checkpoint_path.exists():
                return None
            with open(checkpoint_path, "r", encoding="utf-8") as f:
                checkpoint_data = json.load(f)
            logger.info(f"检查点已加载: {task_id}")
            return checkpoint_data.get("state")
        except Exception as e:
            logger.error(f"加载检查点失败: {e}")
            return None

    def delete_checkpoint(self, task_id: str) -> bool:
        """删除检查点"""
        try:
            checkpoint_path = self._get_checkpoint_path(task_id)
            if checkpoint_path.exists():
                checkpoint_path.unlink()
                logger.info(f"检查点已删除: {task_id}")
            return True
        except Exception as e:
            logger.error(f"删除检查点失败: {e}")
            return False

    def list_checkpoints(self) -> list:
        """列出所有检查点"""
        checkpoints = []
        for checkpoint_file in self.checkpoint_dir.glob("*.json"):
            try:
                with open(checkpoint_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    checkpoints.append({
                        "task_id": data.get("task_id"),
                        "timestamp": data.get("timestamp")
                    })
            except Exception:
                continue
        return sorted(checkpoints, key=lambda x: x.get("timestamp", ""), reverse=True)

    def cleanup_old_checkpoints(self, days: int = 7) -> int:
        """清理旧的检查点"""
        count = 0
        now = datetime.now()
        for checkpoint_file in self.checkpoint_dir.glob("*.json"):
            try:
                file_age = datetime.fromtimestamp(checkpoint_file.stat().st_mtime)
                if (now - file_age).days > days:
                    checkpoint_file.unlink()
                    count += 1
            except Exception:
                continue
        return count


# 全局检查点管理器
checkpoint_manager = CheckpointManager()