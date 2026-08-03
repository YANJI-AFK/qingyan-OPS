"""直接测试 Ollama 对各种导航指令的响应"""
import requests, json
from datetime import datetime

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5:7b-instruct-q4_K_M"

SYSTEM_PROMPT = (
    "意图解析器。你只能输出一行 JSON。\n"
    "\n"
    "intent 可选值: navigate / query / query_monitor / operate / assign / delete / summary / search / greeting / unknown\n"
    "\n"
    "示例（严格按此格式，不要任何额外文字）：\n"
    '  打开监控 -> {"intent":"navigate","api":"navigate","params":{"target":"/monitor"}}\n'
    '  打开工单列表 -> {"intent":"navigate","api":"navigate","params":{"target":"/tickets"}}\n'
    '  跳转到工单列表 -> {"intent":"navigate","api":"navigate","params":{"target":"/tickets"}}\n'
    '  打开统计看板 -> {"intent":"navigate","api":"navigate","params":{"target":"/tickets/stats"}}\n'
    '  打开配置页 -> {"intent":"navigate","api":"navigate","params":{"target":"/tickets/config"}}\n'
    '  回到首页 -> {"intent":"navigate","api":"navigate","params":{"target":"/"}}\n'
    '  查看工单5 -> {"intent":"query","api":"tickets_detail","params":{"id":5}}\n'
    '  有多少未完成的工单 -> {"intent":"query","api":"tickets_stat","params":{"status":"未完成"}}\n'
    '  你好 -> {"intent":"greeting","params":{}}\n'
    "\n"
    "规则：输出必须是纯 JSON 一行，不要 ``` 标记。target 必须是路由路径如 /monitor、/tickets。\n"
)

today = datetime.now().strftime("%Y-%m-%d")
prompt_base = SYSTEM_PROMPT.replace("{{CURRENT_DATE}}", today)

tests = [
    "打开监控大屏",
    "打开监控",
    "跳转到监控页面",
    "查看监控",
    "监控",
    "打开工单列表",
    "跳转到工单列表",
    "回到首页",
]

for text in tests:
    prompt = f"{prompt_base}\n\n用户说：{text}\n\n请输出 JSON："
    payload = {"model": MODEL, "prompt": prompt, "stream": False,
               "options": {"temperature": 0.1, "num_predict": 100}}
    try:
        r = requests.post(OLLAMA_URL, json=payload, timeout=30)
        resp = r.json().get("response", "").strip()
        print(f"[{text}] -> {resp[:120]}")
    except Exception as e:
        print(f"[{text}] ERROR: {e}")
