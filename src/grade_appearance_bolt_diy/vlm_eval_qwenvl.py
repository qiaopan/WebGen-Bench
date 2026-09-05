import base64
import mimetypes
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from prompt import appearance_prompt

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def _get_client():
    api_key = (
        os.getenv("AZURE_OPENAI_API_KEY", "").strip()
        or os.getenv("DASHSCOPE_API_KEY", "").strip()
    )
    base_url = os.getenv(
        "APPEARANCE_BASE_URL",
        os.getenv("WEBVOYAGER_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    ).strip()
    if not api_key:
        raise RuntimeError(
            "未找到 AZURE_OPENAI_API_KEY 或 DASHSCOPE_API_KEY，"
            "请先在项目根目录的 .env 中配置。"
        )
    return OpenAI(api_key=api_key, base_url=base_url, timeout=120.0, max_retries=2)

def encode_image(image_path):
  with open(image_path, "rb") as image_file:
    return base64.b64encode(image_file.read()).decode('utf-8')


def get_score_result(image_paths, instruction, model=None):
    model = model or os.getenv(
        "APPEARANCE_API_MODEL",
        os.getenv("WEBVOYAGER_API_MODEL", "qwen3-vl-32b-instruct"),
    )
    base64_images = []
    
    for image_path in image_paths:    
        base64_image = encode_image(image_path)
        base64_images.append(base64_image)
        
    prompt = appearance_prompt.format(
        instruction=instruction,
    )
    
    user_content = [{
                        "type": "text",
                        "text": prompt
                    }]
    
    for image_path, base64_image in zip(image_paths, base64_images):
        mime_type = mimetypes.guess_type(image_path)[0] or "image/png"
        user_content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:{mime_type};base64,{base64_image}"
            }
        })

    chat_response = _get_client().chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "You are a helpful assistant."
            },
            {
                "role": "user",
                "content": user_content
            }
        ],
    )

    usage = chat_response.usage
    usage_data = {
        "prompt_tokens": usage.prompt_tokens if usage else 0,
        "completion_tokens": usage.completion_tokens if usage else 0,
        "total_tokens": usage.total_tokens if usage else 0,
    }
    return chat_response.choices[0].message.content, usage_data, model
