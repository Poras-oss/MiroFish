"""
LLM客户端封装
统一使用OpenAI格式调用
"""

import json
import re
import time
import threading
from collections import deque
import hashlib
from typing import Optional, Dict, Any, List
from openai import OpenAI

from ..config import Config


class LLMClient:
    """LLM客户端"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None
    ):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model = model or Config.LLM_MODEL_NAME
        
        if not self.api_key:
            raise ValueError("LLM_API_KEY 未配置")
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
        # 简单内存速率限制器（每个profile使用固定窗口）
        self._locks = {}
        self._timestamps = {}
        for profile_name in getattr(Config, 'MODEL_PROFILES', {}):
            self._locks[profile_name] = threading.Lock()
            self._timestamps[profile_name] = deque()
        # prompt cache (simple LRU-backed dict)
        self._prompt_cache: Dict[str, Any] = {}
        self._prompt_cache_order = deque()
        self._prompt_cache_lock = threading.Lock()
        self._prompt_cache_ttl = getattr(Config, 'PROMPT_CACHE_TTL', 3600)
        self._prompt_cache_max = 1024
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: Optional[Dict] = None
    ) -> str:
        """
        发送聊天请求
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数
            response_format: 响应格式（如JSON模式）
            
        Returns:
            模型响应文本
        """
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if response_format:
            kwargs["response_format"] = response_format

        response = self.raw_create(**kwargs)
        content = response.choices[0].message.content
        # 部分模型（如MiniMax M2.5）会在content中包含<think>思考内容，需要移除
        content = re.sub(r'<think>[\s\S]*?</think>', '', content).strip()
        return content
    
    def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """
        发送聊天请求并返回JSON
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数
            
        Returns:
            解析后的JSON对象
        """
        response = self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"}
        )
        # 清理markdown代码块标记
        cleaned_response = response.strip()
        cleaned_response = re.sub(r'^```(?:json)?\s*\n?', '', cleaned_response, flags=re.IGNORECASE)
        cleaned_response = re.sub(r'\n?```\s*$', '', cleaned_response)
        cleaned_response = cleaned_response.strip()

        try:
            return json.loads(cleaned_response)
        except json.JSONDecodeError:
            raise ValueError(f"LLM返回的JSON格式无效: {cleaned_response}")

    def _find_profile_for_model(self, model_name: str) -> Optional[str]:
        """根据模型名在MODEL_PROFILES中找到匹配的profile名称"""
        for name, info in getattr(Config, 'MODEL_PROFILES', {}).items():
            if info.get('model') == model_name:
                return name
        return None

    def raw_create(self, **kwargs) -> Any:
        """直接调用底层OpenAI create接口，带简单速率限制与profile守护。

        Accepts same kwargs as `self.client.chat.completions.create`.
        """
        model_name = kwargs.get('model', self.model)
        profile = self._find_profile_for_model(model_name) or 'structured'

        # 应用profile的max_tokens默认值
        profile_conf = Config.MODEL_PROFILES.get(profile, {})
        if 'max_tokens' in profile_conf and 'max_tokens' not in kwargs:
            kwargs['max_tokens'] = profile_conf['max_tokens']

        # Prompt trimming based on chars (best-effort, character-based)
        if 'messages' in kwargs and isinstance(kwargs['messages'], list):
            max_prompt_chars = int(profile_conf.get('max_prompt_chars', getattr(Config, 'PROMPT_MAX_CHARS', 50000)))
            kwargs['messages'] = self._trim_messages(kwargs['messages'], max_prompt_chars)

        # Client-side prompt cache: use when model is groq and user enabled groq cache OR profile is 'retrieval'
        model_lower = model_name.lower()
        cacheable = (("groq" in model_lower and getattr(Config, 'USE_GROQ_CACHE', True)) or profile == 'retrieval')
        cache_key = None
        if cacheable:
            try:
                cache_key = self._make_prompt_key(model_name, kwargs)
                with self._prompt_cache_lock:
                    entry = self._prompt_cache.get(cache_key)
                    if entry:
                        ts, resp = entry
                        if time.time() - ts < self._prompt_cache_ttl:
                            return resp
                        else:
                            # expired
                            del self._prompt_cache[cache_key]
                            try:
                                self._prompt_cache_order.remove(cache_key)
                            except Exception:
                                pass
            except Exception:
                cache_key = None

        # 简单循环窗口速率限制（RPM）
        rpm = int(profile_conf.get('rpm', 30))
        lock = self._locks.get(profile)
        timestamps = self._timestamps.get(profile)

        if lock and timestamps is not None:
            with lock:
                now = time.time()
                # 保留最近60秒内的时间戳
                while timestamps and timestamps[0] <= now - 60:
                    timestamps.popleft()
                if len(timestamps) >= rpm:
                    # 已达上限，等待到最早一条过期
                    wait_for = 60 - (now - timestamps[0])
                    time.sleep(min(wait_for, 1.0))
                timestamps.append(time.time())

        # Finally call underlying client
        resp = self.client.chat.completions.create(**kwargs)

        # Store in prompt cache if applicable
        if cacheable and cache_key:
            try:
                with self._prompt_cache_lock:
                    # simple LRU eviction
                    if cache_key in self._prompt_cache:
                        del self._prompt_cache[cache_key]
                        try:
                            self._prompt_cache_order.remove(cache_key)
                        except Exception:
                            pass
                    self._prompt_cache[cache_key] = (time.time(), resp)
                    self._prompt_cache_order.append(cache_key)
                    if len(self._prompt_cache_order) > self._prompt_cache_max:
                        old = self._prompt_cache_order.popleft()
                        if old in self._prompt_cache:
                            del self._prompt_cache[old]
            except Exception:
                pass

        return resp

    def _make_prompt_key(self, model_name: str, kwargs: Dict[str, Any]) -> str:
        """Create a stable hash key for the model+messages+options."""
        m = hashlib.sha256()
        m.update(model_name.encode('utf-8'))
        # include temperature and response_format if present
        temp = str(kwargs.get('temperature', ''))
        m.update(temp.encode('utf-8'))
        rf = json.dumps(kwargs.get('response_format', ''), separators=(',', ':'), ensure_ascii=False)
        m.update(rf.encode('utf-8'))
        # messages
        try:
            msgs = kwargs.get('messages', [])
            # canonicalize messages to JSON without spaces
            m.update(json.dumps(msgs, ensure_ascii=False, separators=(',', ':'), sort_keys=False).encode('utf-8'))
        except Exception:
            m.update(repr(kwargs.get('messages')).encode('utf-8'))
        return m.hexdigest()

    def _trim_messages(self, messages: List[Dict[str, str]], max_chars: int) -> List[Dict[str, str]]:
        """Trim messages to fit within max_chars (character-based heuristic).

        Keeps system messages, and retains the most recent user/assistant messages.
        """
        if not messages:
            return messages

        # compute lengths
        def content_len(m):
            return len(m.get('content', '') or '')

        total = sum(content_len(m) for m in messages)
        if total <= max_chars:
            return messages

        # separate system messages
        system_msgs = [m for m in messages if m.get('role') == 'system']
        other_msgs = [m for m in messages if m.get('role') != 'system']

        system_len = sum(content_len(m) for m in system_msgs)
        # start adding recent messages until reach limit
        allowed = max_chars - system_len
        if allowed <= 0:
            # truncate system messages themselves
            truncated = []
            remaining = max_chars
            for m in system_msgs:
                c = m.get('content', '') or ''
                if remaining <= 0:
                    break
                take = min(len(c), remaining)
                truncated.append({'role': m.get('role'), 'content': c[:take] + ('...(truncated)' if take < len(c) else '')})
                remaining -= take
            return truncated

        kept = []
        cur = 0
        # iterate from most recent
        for m in reversed(other_msgs):
            l = content_len(m)
            if cur + l <= allowed:
                kept.append(m)
                cur += l
            else:
                # partially include this message from the end
                remaining = allowed - cur
                if remaining > 20:
                    txt = m.get('content', '') or ''
                    # keep the tail part to preserve recent context
                    part = txt[-remaining:]
                    kept.append({'role': m.get('role'), 'content': '...(truncated) ' + part})
                    cur += remaining
                break

        kept.reverse()
        return system_msgs + kept

