from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Union


@dataclass
class TaskHistoryRecord:
    task_id: str
    thread_id: str
    user_scope: str
    topic: str
    research_type: str
    status: str
    created_at: Union[int, str]
    last_updated_at: Union[int, str]
    completed_at: Optional[Union[int, str]] = None
    duration_seconds: Optional[int] = None
    current_step: int = 0
    report_path: Optional[str] = None
    error_message: Optional[str] = None
    steps_data: Optional[List[Dict[str, Any]]] = None
    result: Optional[Dict[str, Any]] = None
    final_result: Optional[Dict[str, Any]] = None
    input_digest: Optional[Dict[str, Any]] = None
    error_category: Optional[str] = None

    def to_dict(self, include_steps: bool = True) -> Dict[str, Any]:
        data = asdict(self)
        if not include_steps:
            data.pop("steps_data", None)
        return data


@dataclass
class ParsedFileRecord:
    file_id: str
    user_scope: str
    name: str
    type: str
    size: int
    parsed_at: str
    content: str = ""
    url: Optional[str] = None
    content_size: int = 0
    original_content_size: int = 0
    content_hash: str = ""
    source: str = "client_parser"
    truncated: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_used_at: Optional[str] = None

    def to_dict(self, include_content: bool = True) -> Dict[str, Any]:
        data = asdict(self)
        if not include_content:
            data.pop("content", None)
        return data
