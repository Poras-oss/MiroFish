"""
配置管理
统一从项目根目录的 .env 文件加载配置
"""

import os
from dotenv import load_dotenv

# 加载项目根目录的 .env 文件
# 路径: MiroFish/.env (相对于 backend/app/config.py)
project_root_env = os.path.join(os.path.dirname(__file__), '../../.env')

if os.path.exists(project_root_env):
    load_dotenv(project_root_env, override=True)
else:
    # 如果根目录没有 .env，尝试加载环境变量（用于生产环境）
    load_dotenv(override=True)


class Config:
    """Flask配置类"""
    
    # Flask配置
    SECRET_KEY = os.environ.get('SECRET_KEY', 'mirofish-secret-key')
    DEBUG = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'
    
    # JSON配置 - 禁用ASCII转义，让中文直接显示（而不是 \uXXXX 格式）
    JSON_AS_ASCII = False
    
    # LLM配置（统一使用OpenAI格式）
    LLM_API_KEY = os.environ.get('LLM_API_KEY')
    LLM_BASE_URL = os.environ.get('LLM_BASE_URL', 'https://generativelanguage.googleapis.com/v1beta/openai/')
    LLM_MODEL_NAME = os.environ.get('LLM_MODEL_NAME', 'gemini-2.5-flash')
    
    # 备用/回退 LLM 配置（如 Gemini API，用于大文本生成或 Groq 限流报错时的完美兜底）
    LLM_FALLBACK_API_KEY = os.environ.get('LLM_FALLBACK_API_KEY')
    LLM_FALLBACK_BASE_URL = os.environ.get('LLM_FALLBACK_BASE_URL', 'https://generativelanguage.googleapis.com/v1beta/openai/')
    LLM_FALLBACK_MODEL_NAME = os.environ.get('LLM_FALLBACK_MODEL_NAME', 'gemini-2.5-flash')
    
    # Zep配置
    ZEP_API_KEY = os.environ.get('ZEP_API_KEY')
    
    # 文件上传配置
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), '../uploads')
    ALLOWED_EXTENSIONS = {'pdf', 'md', 'txt', 'markdown'}
    
    # 文本处理配置
    DEFAULT_CHUNK_SIZE = 500  # 默认切块大小
    DEFAULT_CHUNK_OVERLAP = 50  # 默认重叠大小
    
    # OASIS模拟配置
    OASIS_DEFAULT_MAX_ROUNDS = int(os.environ.get('OASIS_DEFAULT_MAX_ROUNDS', '10'))
    OASIS_SIMULATION_DATA_DIR = os.path.join(os.path.dirname(__file__), '../uploads/simulations')
    
    # OASIS平台可用动作配置
    OASIS_TWITTER_ACTIONS = [
        'CREATE_POST', 'LIKE_POST', 'REPOST', 'FOLLOW', 'DO_NOTHING', 'QUOTE_POST'
    ]
    OASIS_REDDIT_ACTIONS = [
        'LIKE_POST', 'DISLIKE_POST', 'CREATE_POST', 'CREATE_COMMENT',
        'LIKE_COMMENT', 'DISLIKE_COMMENT', 'SEARCH_POSTS', 'SEARCH_USER',
        'TREND', 'REFRESH', 'DO_NOTHING', 'FOLLOW', 'MUTE'
    ]
    
    # Report Agent配置
    REPORT_AGENT_MAX_TOOL_CALLS = int(os.environ.get('REPORT_AGENT_MAX_TOOL_CALLS', '5'))
    REPORT_AGENT_MAX_REFLECTION_ROUNDS = int(os.environ.get('REPORT_AGENT_MAX_REFLECTION_ROUNDS', '2'))
    REPORT_AGENT_TEMPERATURE = float(os.environ.get('REPORT_AGENT_TEMPERATURE', '0.5'))
    # 模型档位配置（逻辑角色 -> 模型与速率/令牌上限）
    MODEL_PROFILES = {
        # retrieval / summarization
        "retrieval": {
            "model": os.environ.get('MODEL_RETRIEVAL', 'gemini-2.5-flash'),
            "rpm": int(os.environ.get('MODEL_RETRIEVAL_RPM', '1000')),
            "tpm": int(os.environ.get('MODEL_RETRIEVAL_TPM', '4000000')),
            "max_tokens": int(os.environ.get('MODEL_RETRIEVAL_MAX_TOKENS', '8192'))
        },
        # mid-quality JSON / structured outputs
        "structured": {
            "model": os.environ.get('MODEL_STRUCTURED', 'gemini-2.5-flash'),
            "rpm": int(os.environ.get('MODEL_STRUCTURED_RPM', '1000')),
            "tpm": int(os.environ.get('MODEL_STRUCTURED_TPM', '4000000')),
            "max_tokens": int(os.environ.get('MODEL_STRUCTURED_MAX_TOKENS', '8192'))
        },
        # final synthesis / agent interactions (higher quality)
        "final": {
            "model": os.environ.get('MODEL_FINAL', 'gemini-2.5-pro'),
            "rpm": int(os.environ.get('MODEL_FINAL_RPM', '1000')),
            "tpm": int(os.environ.get('MODEL_FINAL_TPM', '4000000')),
            "max_tokens": int(os.environ.get('MODEL_FINAL_MAX_TOKENS', '8192'))
        },
        # local small fallback
        "local_small": {
            "model": os.environ.get('MODEL_LOCAL_SMALL', 'gemini-2.5-flash'),
            "rpm": int(os.environ.get('MODEL_LOCAL_SMALL_RPM', '1000')),
            "tpm": int(os.environ.get('MODEL_LOCAL_SMALL_TPM', '4000000')),
            "max_tokens": int(os.environ.get('MODEL_LOCAL_SMALL_MAX_TOKENS', '8192'))
        }
    }

    # 是否允许在无法满足Groq额度时回退到本地小模型（仅用于非常小的任务）
    # Default to False since we keep everything on Groq for now
    USE_LOCAL_SMALL_FALLBACK = os.environ.get('USE_LOCAL_SMALL_FALLBACK', 'false').lower() == 'true'
    # Prompt trimming / caching
    PROMPT_MAX_CHARS = int(os.environ.get('PROMPT_MAX_CHARS', '2000000'))
    PROMPT_CACHE_TTL = int(os.environ.get('PROMPT_CACHE_TTL', '3600'))  # seconds
    USE_GROQ_CACHE = os.environ.get('USE_GROQ_CACHE', 'true').lower() == 'true'
    
    @classmethod
    def validate(cls):
        """验证必要配置"""
        errors = []
        if not cls.LLM_API_KEY:
            errors.append("LLM_API_KEY 未配置")
        if not cls.ZEP_API_KEY:
            errors.append("ZEP_API_KEY 未配置")
        return errors

